"""
Create Extent library from Depth library using GDAL operations.
After profiling, it is found that the optimum parallel process count is same number as CPU cores.
This script is compute intensive and not memory intensive.
"""

import logging
import multiprocessing
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Type

from ..setup.collection_data import CollectionData


def setup_gdal_environment(collection: CollectionData) -> None:
    """
    Configure GDAL environment paths from collection settings.

    Args:
        collection: CollectionData object containing configuration settings
    """
    gdal_bins = collection.config["flows2fim"]["GDAL_BINS_PATH"]
    gdal_scripts = collection.config["flows2fim"]["GDAL_SCRIPTS_PATH"]

    if gdal_bins:
        os.environ["PATH"] = str(gdal_bins) + os.pathsep + os.environ["PATH"]
    if gdal_scripts:
        os.environ["PATH"] = str(gdal_scripts) + os.pathsep + os.environ["PATH"]


def create_extent_tif(tif_path: Path, tmp_dir: Path, dest_dir: Path) -> None:
    """
    Create extent TIFF from depth TIFF using GDAL operations.

    Args:
        tif_path: Path to input TIFF file
        tmp_dir: Temporary directory for processing
        dest_dir: Destination directory for output file
    """
    tmp_tif = tmp_dir / f"tmp_{tif_path.stem}.tif"
    dest_tif = dest_dir / f"{tif_path.stem}.tif"

    if dest_tif.exists():
        logging.debug(f"Destination file {dest_tif} exists. Skipping processing.")
        return

    gdal_calc_cmd = [
        "gdal_calc",
        "-A",
        tif_path,
        "--outfile",
        tmp_tif,
        '--calc="1*(A>0)"',
        "--type=Byte",
    ]

    result = subprocess.run(gdal_calc_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.debug(f"gdal_calc stdout: {result.stdout}")
        logging.error(f"gdal_calc stderr: {result.stderr}")
        logging.debug(" ".join(gdal_calc_cmd))
        raise RuntimeError(f"gdal_calc failed for {tif_path}")

    if not os.path.exists(tmp_tif):
        logging.error(f"Temporary file {tmp_tif} not created!")
        raise FileNotFoundError(f"{tmp_tif} not created")

    # Translate to COG, COG format can't be created with gdal_calc
    gdal_translate_cmd = [
        "gdal_translate",
        "-of",
        "COG",
        tmp_tif,
        dest_tif,
    ]

    # Execute gdalwarp with output redirection
    result = subprocess.run(gdal_translate_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.debug(f"gdal_translate stdout: {result.stdout}")
        logging.error(f"gdal_translate stderr: {result.stderr}")
        logging.debug(" ".join(gdal_calc_cmd))
        logging.debug(" ".join(gdal_translate_cmd))

        if os.path.exists(dest_tif):  # clean up
            os.remove(dest_tif)
        raise RuntimeError(f"gdal_translate failed for {tif_path}")


def create_domain_tif(tif_path: Path, tmp_dir: Path, gpkg_path: Path, dest_dir: Path) -> None:
    """
    Create domain TIFF from geopackage using GDAL operations.

    Args:
        tif_path: Path to reference TIFF file
        tmp_dir: Temporary directory for processing
        gpkg_path: Path to input geopackage file
        dest_dir: Destination directory for output file
    """
    tmp_tif = tmp_dir / "tmp_domain.tif"
    dest_tif = dest_dir / "domain.tif"

    if dest_tif.exists():
        logging.debug(f"Domain file {dest_tif} exists. Skipping processing.")
        return

    # create a temporary raster with same extents as all other to burn xs_concave_hull
    gdal_calc_cmd = [
        "gdal_calc",
        "-A",
        tif_path,
        "--outfile",
        tmp_tif,
        '--calc="0*A"',
        "--type=Byte",
    ]

    result = subprocess.run(gdal_calc_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.debug(f"gdal_calc stdout: {result.stdout}")
        logging.error(f"gdal_calc stderr: {result.stderr}")
        logging.debug(" ".join(gdal_calc_cmd))
        raise RuntimeError(f"gdal_calc failed for domain from {tif_path}")

    if not os.path.exists(tmp_tif):
        logging.error(f"Temporary file {tmp_tif} not created!")
        raise FileNotFoundError(f"{tmp_tif} not created")

    # burn xs_concave_hull
    gdal_rasterize_cmd = ["gdal_rasterize", "-l", "XS_concave_hull", "-burn", "0", gpkg_path, tmp_tif]

    result = subprocess.run(gdal_rasterize_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.debug(f"gdal_rasterize stdout: {result.stdout}")
        logging.error(f"gdal_rasterize stderr: {result.stderr}")
        logging.debug(" ".join(gdal_rasterize_cmd))
        raise RuntimeError(f"gdal_rasterize failed for domain {tmp_tif}")

    # Translate to COG, COG format can't be created with gdal_calc, or burn value into
    gdal_translate_cmd = [
        "gdal_translate",
        "-of",
        "COG",
        tmp_tif,
        dest_tif,
    ]

    result = subprocess.run(gdal_translate_cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.debug(f"gdal_translate stdout: {result.stdout}")
        logging.error(f"gdal_translate stderr: {result.stderr}")
        logging.debug(" ".join(gdal_calc_cmd))
        logging.debug(" ".join(gdal_rasterize_cmd))
        logging.debug(" ".join(gdal_translate_cmd))

        if os.path.exists(dest_tif):  # clean up
            os.remove(dest_tif)
        raise RuntimeError(f"gdal_translate failed for {dest_tif}")


def fim_worker(args: tuple) -> None:
    """
    Worker function for processing FIM extent files.

    Args:
        args: Tuple containing (tif_path, library_dir, library_extent_dir)
    """
    tif_path, library_dir, library_extent_dir = args
    try:
        relative_path = tif_path.relative_to(library_dir)
        dest_path = library_extent_dir / relative_path
        dest_dir = dest_path.parent
        dest_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp_dir:
            create_extent_tif(tif_path, Path(tmp_dir), dest_dir)
    except Exception as e:
        logging.error(f"Error processing {tif_path}: {str(e)}")


def domain_worker(args: tuple) -> None:
    """
    Worker function for processing model domain files.

    Args:
        args: Tuple containing (reach_id, tif_path, library_extent_dir, submodels_dir)
    """
    reach_id, tif_path, library_extent_dir, submodels_dir = args
    try:
        tif_path = Path(tif_path)
        gpkg_path = Path(submodels_dir) / reach_id / f"{reach_id}.gpkg"
        dest_dir = Path(library_extent_dir) / reach_id

        if gpkg_path.exists():
            dest_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory() as tmp_dir:
                create_domain_tif(tif_path, Path(tmp_dir), gpkg_path, dest_dir)
        else:
            logging.error(f"Missing geopackage for reach {reach_id}: {gpkg_path}")
    except Exception as e:
        logging.error(f"Error processing domain {reach_id}: {str(e)}", exc_info=True)


def get_all_tif_paths(src_dir: Path) -> List[Path]:
    """
    Get all TIFF file paths recursively from source directory.

    Args:
        src_dir: Root directory to search

    Returns:
        List of Path objects for found TIFF files
    """
    return list(src_dir.rglob("*.tif"))


def get_reachid_tif_map(tif_paths: List[Path]) -> Dict[str, Path]:
    """
    Create mapping of reach IDs to representative TIFF paths.

    Args:
        tif_paths: List of TIFF file paths

    Returns:
        Dictionary mapping reach IDs to TIFF paths
    """
    return {str(path.parent.parent.name): path for path in tif_paths}


def create_extent_lib(collection: Type[CollectionData], print_progress: bool = False) -> None:
    """
    Main function to create extent library from depth library.

    Args:
        collection: CollectionData object with configuration
        print_progress: Whether to display progress bar
    """
    library_dir = Path(collection.library_dir)
    extent_library_dir = Path(collection.extent_library_dir)
    submodels_dir = Path(collection.submodels_dir)
    process_count = collection.config["execution"]["OPTIMUM_PARALLEL_PROCESS_COUNT"]

    setup_gdal_environment(collection)

    # Process FIM extent files
    tif_paths = get_all_tif_paths(library_dir)
    with multiprocessing.Pool(process_count) as pool:
        for i, _ in enumerate(
            pool.imap_unordered(fim_worker, [(p, library_dir, extent_library_dir) for p in tif_paths]), 1
        ):
            if print_progress:
                sys.stdout.write(f"\rProcessing FIMs: {i}/{len(tif_paths)}")
                sys.stdout.flush()
    if print_progress:
        sys.stdout.write("\n")

    # Process domain files
    reach_map = get_reachid_tif_map(tif_paths)
    with multiprocessing.Pool(process_count) as pool:
        for i, _ in enumerate(
            pool.imap_unordered(
                domain_worker, [(rid, p, extent_library_dir, submodels_dir) for rid, p in reach_map.items()]
            ),
            1,
        ):
            if print_progress:
                sys.stdout.write(f"\rProcessing domains: {i}/{len(reach_map)}")
                sys.stdout.flush()

    if print_progress:
        sys.stdout.write("\n")
