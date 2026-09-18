"""
Bridge processor module for masking depth library TIFs based on bridge locations.

Uses GDAL/OGR command-line tools via subprocess for all operations. This has benefits of maintainability and also easier debugging if you have existing intermediate outputs before the subprocess call.
"""

import json
import logging
import multiprocessing
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from ..logging_utils import configure_logging
from ..setup.collection_data import CollectionData
from .extent_library import get_all_tif_paths

logger = logging.getLogger(__name__)


def run_cmd(cmd: list, description: str) -> subprocess.CompletedProcess:
    """Run a command and raise on failure. This packages the error handling pattern used several times in extent_library.py whenever subprocess.run is called there"""
    result = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if result.returncode != 0:
        logger.debug(f"{description} stdout: {result.stdout}")
        logger.error(f"{description} stderr: {result.stderr}")
        logger.debug(f"Command: {' '.join(str(c) for c in cmd)}")
        raise RuntimeError(f"{description} failed")
    return result


def get_raster_info(
    tif_path: Path,
) -> tuple[tuple[float, float, float, float], tuple[float, float], float]:
    """Get bounds (xmin, ymin, xmax, ymax), resolution (xres, yres), and nodata value from a raster."""
    result = run_cmd(["gdalinfo", "-json", tif_path], f"gdalinfo {tif_path}")
    info = json.loads(result.stdout)
    corners = info["cornerCoordinates"]
    bounds = (
        corners["upperLeft"][0],
        corners["lowerRight"][1],
        corners["lowerRight"][0],
        corners["upperLeft"][1],
    )
    # geoTransform: [originX, pixelWidth, 0, originY, 0, pixelHeight]
    gt = info["geoTransform"]
    res = (abs(gt[1]), abs(gt[5]))
    nodata = info["bands"][0].get("noDataValue", -9999.0)
    return bounds, res, nodata


def align_raster(
    src_path: Path,
    output_path: Path,
    bounds: tuple[float, float, float, float],
    res: tuple[float, float],
    nodata: float = None,
    target_crs: str = None,
    resampling: str = "bilinear",
) -> None:
    """Align a raster to the specified extent and resolution, outputting a GeoTIFF.

    If target_crs is provided, the source raster will be reprojected to that CRS.
    """
    xmin, ymin, xmax, ymax = bounds
    xres, yres = res
    cmd = [
        "gdalwarp",
        "-overwrite",
        "-of",
        "GTiff",
        "-co",
        "COMPRESS=LZW",
        "-co",
        "TILED=YES",
        "-te",
        xmin,
        ymin,
        xmax,
        ymax,
        "-tr",
        xres,
        yres,
        "-r",
        resampling,
    ]
    if target_crs is not None:
        cmd.extend(["-t_srs", target_crs])
    if nodata is not None:
        cmd.extend(["-dstnodata", nodata])
    cmd.extend([src_path, output_path])
    run_cmd(cmd, f"gdalwarp align {src_path}")


def apply_bridge_mask(args: tuple) -> tuple[str, bool]:
    """
    Process a single depth TIF with bridge masking (worker function for multiprocessing).

    Expects pre-aligned local DEM and bridge rasters. Runs gdal_calc for the masking
    computation and overwrites the original file on success.
    """
    (
        depth_path,
        aligned_dem,
        aligned_bridges,
        library_parent,
        conv_factor,
        depth_nodata,
        reach_id,
    ) = args
    logger.debug(f"Processing {depth_path} with bridge mask")
    depth_path = Path(depth_path)

    try:
        with tempfile.TemporaryDirectory(dir=library_parent, prefix=f"{reach_id}_") as temp_dir:
            temp_dir = Path(temp_dir)

            # Algorithm: delta = (DEM + depth) - bridge_elev * conv_factor
            #   - bridge above water (delta < 0): set to nodata
            #   - bridge submerged (delta >= 0): depth = delta
            #   - no bridge (C is nodata): keep original depth
            calc_expr = (
                f"numpy.where((C == -9999) | numpy.isnan(C), A, "
                f"numpy.where((B + A) - (C * {conv_factor}) < 0, {depth_nodata}, "
                f"(B + A) - (C * {conv_factor})))"
            )

            temp_output = temp_dir / "result.tif"
            run_cmd(
                [
                    "gdal_calc",
                    "--hideNoData",  # If we don't pass this flag then gdal_calc will not evaluate pixels where one source is no data. This blanks out the depth raster since most of the bridge raster is nodata
                    "-A",
                    depth_path,
                    "-B",
                    aligned_dem,
                    "-C",
                    aligned_bridges,
                    "--outfile",
                    temp_output,
                    f"--NoDataValue={depth_nodata}",
                    "--co=COMPRESS=LZW",
                    "--quiet",
                    f"--calc={calc_expr}",
                ],
                "gdal_calc",
            )

            # gdal_calc can't work with COG so need to convert here
            cog_output = temp_dir / "output.tif"
            run_cmd(
                [
                    "gdal_translate",
                    "-of",
                    "COG",
                    "-co",
                    "COMPRESS=LZW",
                    temp_output,
                    cog_output,
                ],
                "gdal_translate",
            )
            logger.debug(f"Finished processing {depth_path}, moving result to original location")
            shutil.move(str(cog_output), str(depth_path))
            logger.debug(f"Successfully processed {depth_path}")
        return (str(depth_path), True)

    except Exception as e:
        logger.exception(f"Error processing {depth_path}: {e}")
        return (str(depth_path), False)


def process_bridges(collection: "CollectionData") -> dict[str, any]:
    """
    Apply bridge masking to depth library TIFs in place.
    """
    library_dir = Path(collection.library_dir)
    submodels_dir = Path(collection.submodels_dir)
    bridge_index_path = collection.bridge_tile_index_path
    conv_factor = collection.config["bridge_processing"]["BRIDGE_ELEV_CONV_FACTOR"]

    reach_dirs = [d for d in library_dir.iterdir() if d.is_dir()]
    logger.info(f"Found {len(reach_dirs)} reaches to process")
    logger.info(f"Bridge index: {bridge_index_path}")

    t_total = time.perf_counter()
    reaches_with_bridges, reaches_without_bridges, files_modified = [], [], []

    for reach_dir in reach_dirs:
        reach_id = reach_dir.name
        logger.debug(f"Processing reach {reach_id}")

        # Use generator to stop at first match. Faster than getting all reach tifs
        sample_reach_tif = next(iter(reach_dir.rglob("*.tif")), None)
        if sample_reach_tif is None:
            logger.warning(f"Reach {reach_id}: no TIF files found, skipping")
            continue
        dem_path = submodels_dir / reach_id / "Terrain" / f"{reach_id}.seamless_3dep_dem_3m_5070.tif"
        if not dem_path.exists():
            raise FileNotFoundError(f"No DEM found for reach {reach_id}: {dem_path}")

        # The bridge query requires that all bridge tiles be in epsg 5070
        try:
            bounds, depth_res, depth_nodata = get_raster_info(sample_reach_tif)
            xmin, ymin, xmax, ymax = bounds
            t_query = time.perf_counter()
            result = run_cmd(
                [
                    "ogr2ogr",
                    "-f",
                    "CSV",
                    "-spat",
                    xmin,
                    ymin,
                    xmax,
                    ymax,
                    "-select",
                    "location",
                    "/vsistdout/",
                    bridge_index_path,
                ],
                "ogr2ogr bridge query",
            )
            dt_query = time.perf_counter() - t_query
            lines = result.stdout.strip().split("\n")
            intersecting_bridge_paths = lines[1:] if len(lines) > 1 else []
            logger.debug(f"Reach {reach_id}: {len(intersecting_bridge_paths)} bridges (query: {dt_query:.3f}s)")
        except Exception as e:
            logger.exception(f"Error querying bridges for reach {reach_id}: {e}")
            continue

        if not intersecting_bridge_paths:
            # No bridges in this reach - nothing to do
            reaches_without_bridges.append(reach_id)
            logger.info(f"Reach {reach_id}: no bridges, skipped")
            continue

        reaches_with_bridges.append(reach_id)

        # Only enumerate all TIFs for processing if there are bridges that intersect reach bounds
        reach_tifs = get_all_tif_paths(reach_dir)
        logger.debug(f"Reach {reach_id}: found {len(reach_tifs)} TIFs to process")

        with tempfile.TemporaryDirectory(dir=str(library_dir.parent), prefix=f"{reach_id}_") as reach_temp_dir:
            reach_temp_dir = Path(reach_temp_dir)

            bridges_vrt = reach_temp_dir / "bridges.vrt"
            run_cmd(
                ["gdalbuildvrt", bridges_vrt] + intersecting_bridge_paths,
                "gdalbuildvrt",
            )

            # Depth rasters are in EPSG:5070, reproject DEM and bridges to match
            target_crs = "EPSG:5070"

            t_align = time.perf_counter()
            aligned_dem = reach_temp_dir / "aligned_dem.tif"
            align_raster(
                dem_path,
                aligned_dem,
                bounds,
                depth_res,
                nodata=depth_nodata,
                target_crs=target_crs,
            )

            aligned_bridges = reach_temp_dir / "aligned_bridges.tif"
            align_raster(
                bridges_vrt,
                aligned_bridges,
                bounds,
                depth_res,
                nodata=depth_nodata,
                target_crs=target_crs,
                resampling="near",
            )
            logger.debug(f"Reach {reach_id}: aligned DEM and bridges ({time.perf_counter() - t_align:.1f}s)")

            worker_args = [
                (
                    str(depth_path),
                    str(aligned_dem),
                    str(aligned_bridges),
                    str(library_dir.parent),
                    conv_factor,
                    depth_nodata,
                    reach_id,
                )
                for depth_path in reach_tifs
            ]

            num_workers = collection.config["execution"]["OPTIMUM_PARALLEL_PROCESS_COUNT"]
            # Spawned workers start with a bare root logger that drops anything below
            # WARNING, so they need configure_logging too (it re-reads the levels from the
            # RP_* env vars they inherit). Their records go to the child's own stderr, which
            # under Jupyter is the kernel's output channel rather than the cell.
            with multiprocessing.Pool(processes=num_workers, initializer=configure_logging) as pool:
                for depth_path, success in pool.imap_unordered(apply_bridge_mask, worker_args):
                    if success:
                        files_modified.append(depth_path)
                    else:
                        logger.error(f"Failed to process {depth_path}")

            logger.info(
                f"Reach {reach_id}: processed {len(reach_tifs)} TIFs with {len(intersecting_bridge_paths)} bridges"
            )

    dt_total = time.perf_counter() - t_total
    logger.info(
        f"Bridge processing complete: {len(reaches_with_bridges)} with bridges, "
        f"{len(reaches_without_bridges)} without, total: {dt_total:.1f}s"
    )

    return {
        "reaches_with_bridges": reaches_with_bridges,
        "reaches_without_bridges": reaches_without_bridges,
        "modified": files_modified,
    }
