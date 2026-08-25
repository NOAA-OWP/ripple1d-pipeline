"""
Create Extent library from Depth library using GDAL operations.
After profiling, it is found that the optimum parallel process count is same number as CPU cores.
But the performance max out at 16 cores.
This script is compute intensive and not memory intensive.
Todo: On windows when working with VSI, update the script to use .as_posix().
On windows max cpu count can be 61
"""

import argparse
import logging
import multiprocessing
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List

from osgeo import gdal


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

    if gdal.VSIStatL(str(dest_tif)) is not None:
        logging.debug(f"Destination path {dest_tif} already exists. Skipping.")
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

    # Translate to COG, COG format can't be created with gdal_calc dircetly
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

    if gdal.VSIStatL(str(dest_tif)) is not None:
        logging.debug(f"Destination path {dest_tif} already exists. Skipping.")
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
        # dest_dir.mkdir(parents=True, exist_ok=True)

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
        # dest_dir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp_dir:
            create_domain_tif(tif_path, Path(tmp_dir), gpkg_path, dest_dir)

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

    dirs = [src_dir]
    tifs = []

    while dirs:
        cur_dir = dirs.pop()
        items = gdal.ReadDir(cur_dir)
        if items:
            for item in items:
                if item.endswith(".tif"):
                    tifs.append(cur_dir / item)
                else:
                    dirs.append(cur_dir / item)

    return tifs


def get_reachid_tif_map(tif_paths: List[Path]) -> Dict[str, Path]:
    """
    Create mapping of reach IDs to representative TIFF paths.

    Args:
        tif_paths: List of TIFF file paths

    Returns:
        Dictionary mapping reach IDs to TIFF paths
    """
    return {str(path.parent.parent.name): path for path in tif_paths}


def create_extent_lib(
    src_library, dest_library, submodels_dir, process_count=multiprocessing.cpu_count(), print_progress: bool = False
) -> None:
    """
    Main function to create extent library from depth library.

    Args:
        print_progress: Whether to display progress bar
    """
    logging.debug(f"Process Count: {process_count}")
    # Process FIM extent files
    logging.info("Walking through source library")
    tif_paths = get_all_tif_paths(src_library)
    logging.info(f"Found {len(tif_paths)} TIFF files in {src_library}")

    logging.info("Processing FIM files")
    with multiprocessing.Pool(process_count) as pool:
        for i, _ in enumerate(pool.imap_unordered(fim_worker, [(p, src_library, dest_library) for p in tif_paths]), 1):
            if print_progress:
                sys.stdout.write(f"\rProcessing FIMs: {i}/{len(tif_paths)}")
                sys.stdout.flush()
            else:
                if (i + 1) % 100 == 0:
                    logging.info(f"Processed {i+1}/{len(tif_paths)}.")
    if print_progress:
        sys.stdout.write("\n")

    # Process domain files
    logging.info("Processing domain files")
    reach_map = get_reachid_tif_map(tif_paths)
    with multiprocessing.Pool(process_count) as pool:
        for i, _ in enumerate(
            pool.imap_unordered(domain_worker, [(rid, p, dest_library, submodels_dir) for rid, p in reach_map.items()]),
            1,
        ):
            if print_progress:
                sys.stdout.write(f"\rProcessing domains: {i}/{len(reach_map)}")
                sys.stdout.flush()
            else:
                if (i + 1) % 100 == 0:
                    logging.info(f"Processed {i+1}/{len(reach_map)}.")

    if print_progress:
        sys.stdout.write("\n")


def main():
    """
    Main function to set up logging and call create_extent_lib.
    """
    parser = argparse.ArgumentParser(description="Create extent library from depth library.")
    parser.add_argument("-src", "--src_library", type=Path, required=True, help="Path to source library")
    parser.add_argument("-dst", "--dest_library", type=Path, required=True, help="Path to destination library")
    parser.add_argument("-m", "--submodels_dir", type=Path, required=True, help="Path to submodels directory")
    parser.add_argument("-pp", "--print_progress", action="store_true", help="Print progress")
    parser.add_argument(
        "-ll",
        "--log_level",
        type=str,
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s - %(levelname)s - %(message)s")

    # Create extent library
    create_extent_lib(args.src_library, args.dest_library, args.submodels_dir, print_progress=args.print_progress)
    logging.info("Extent library created successfully.")


if __name__ == "__main__":
    main()
