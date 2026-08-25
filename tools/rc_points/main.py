#!/usr/bin/env python

""" """

import argparse
import json
import logging
import os
import shutil
import sqlite3
import subprocess
from datetime import datetime, timezone

import geopandas as gpd
import pandas as pd


class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "time": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
        }
        return json.dumps(log_record)


def setup_logging():
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.handlers = []
    logger.addHandler(handler)

    return logger


def download_collection_data(collection_id: str, s3_root_dir) -> None:
    aws_cmd = ["aws", "s3", "cp", f"{s3_root_dir}/{collection_id}/ripple.gpkg", f"./{collection_id}/ripple.gpkg"]
    subprocess.run(aws_cmd, check=True)

    aws_cmd = [
        "aws",
        "s3",
        "sync",
        f"{s3_root_dir}/{collection_id}/submodels",
        f"./{collection_id}/submodels",
        "--exclude",
        "*",
        "--include",
        "*.gpkg",
    ]
    subprocess.run(aws_cmd, check=True)


def upload_file_to_s3(local_path: str, s3_path: str) -> None:
    """
    Uploads a file to S3 using the AWS CLI.
    """
    aws_cmd = ["aws", "s3", "cp", local_path, s3_path]
    subprocess.run(aws_cmd, check=True)


def create_rc_points_parquet(ripple_gpkg_path, submodels_dir, output_parquet_path, collection_id):
    """Create Parquet file with rating curve points using GeoPandas"""

    try:
        reaches_gdf = gpd.read_file(ripple_gpkg_path, layer="reaches", columns=["reach_id"])
        # Read non-spatial processing table with explicit SQL connection because geopandas/pyogrio does not support fetching primary key
        with sqlite3.connect(ripple_gpkg_path) as conn:
            models_df = pd.read_sql("SELECT model_id, reach_id FROM processing;", conn)
            us_rcs_df = pd.read_sql(
                "SELECT reach_id, us_flow, us_wse FROM rating_curves WHERE boundary_condition = 'nd';", conn
            )
    except Exception as e:
        logging.error(f"Error reading base datasets: {str(e)}")
        raise e

    us_rcs_df["wse_m"] = (us_rcs_df["us_wse"] / 3.28084).round(2)
    us_rcs_df = us_rcs_df.rename(columns={"us_flow": "flow_cfs"})
    us_rcs_df.drop(columns=["us_wse"], inplace=True)

    # First create points gdf

    features = []
    reach_ids = [d for d in os.listdir(submodels_dir) if os.path.isdir(os.path.join(submodels_dir, d))]

    for reach_dir in reach_ids:
        reach_id = int(reach_dir)
        gpkg_path = os.path.join(submodels_dir, reach_dir, f"{reach_dir}.gpkg")

        if not os.path.exists(gpkg_path):
            logging.warning(f"Skipping {reach_dir}: GPKG not found")
            continue

        try:
            xs_gdf = gpd.read_file(gpkg_path, layer="XS")
            if xs_gdf.crs is None:
                raise ValueError("XS layer missing CRS information")

            xs_gdf = xs_gdf.to_crs("EPSG:5070")
            xs_row = xs_gdf.sort_values("river_station", ascending=False).iloc[0]
            xs_geom = xs_row.geometry

            # Get matching reach geometry
            reach_geom = reaches_gdf[reaches_gdf["reach_id"] == reach_id].geometry.iloc[0]

            intersection = xs_geom.intersection(reach_geom)
            if intersection.is_empty:
                continue

            point = intersection.geoms[0] if intersection.geom_type == "MultiPoint" else intersection

            model = models_df[models_df["reach_id"] == reach_id]["model_id"].iloc[0]

            features.append(
                {
                    "reach_id": reach_id,
                    "geometry": point,
                    "ras_river": xs_row.source_river,
                    "ras_reach": xs_row.source_reach,
                    "ras_xs_station": xs_row.source_river_station,
                    "model": model,
                }
            )

        except Exception as e:
            logging.error(f"Error processing {reach_dir}: {str(e)}")
            continue

    if not features:
        logging.error("No valid features found")
        return

    gdf = gpd.GeoDataFrame(features, crs="EPSG:5070")

    # Second, merge with rating curves
    result_gdf = gdf.merge(us_rcs_df, on="reach_id", how="inner")
    result_gdf["stac_collection"] = collection_id
    result_gdf["stac_item_id"] = result_gdf["model"]
    result_gdf = result_gdf[
        [
            "reach_id",
            "flow_cfs",
            "wse_m",
            "stac_collection",
            "stac_item_id",
            "ras_river",
            "ras_reach",
            "ras_xs_station",
            "geometry",
        ]
    ]

    result_gdf.sort_values("geometry", inplace=True, ignore_index=True)
    result_gdf.to_parquet(output_parquet_path, compression="lz4")


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Create a denormalized rating curves table for a ripple collection",
        usage="""
        python main.py -c ble_12090301_LowerColoradoCummins \
            -root "s3://fimc-data/ripple/fim_100_domain/collections" \
            -o "s3://fimc-data/ripple/derived-data/rating_curves_extended"
        """,
    )
    parser.add_argument(
        "-root", "--s3_root_prefix", required=True, type=str, help="Directory path collections folder on S3."
    )
    parser.add_argument("-o", "--s3_output_prefix", required=True, type=str, help="Directory path for output data.")
    parser.add_argument(
        "-c",
        "--collection_id",
        required=True,
        type=str,
        help="Collection ID.",
    )

    return parser.parse_args()


def main():
    setup_logging()
    args = parse_arguments()

    logging.info("Starting download of collection data")
    download_collection_data(args.collection_id, args.s3_root_prefix)
    logging.info("Finished downloading collection data")

    submodels_dir = os.path.join(args.collection_id, "submodels")
    ripple_gpkg_path = os.path.join(args.collection_id, "ripple.gpkg")
    output_parquet_path = os.path.join(args.collection_id, "rc_points.parquet")

    logging.info("Creating rating curves points Parquet file")
    create_rc_points_parquet(
        ripple_gpkg_path=ripple_gpkg_path,
        submodels_dir=submodels_dir,
        output_parquet_path=output_parquet_path,
        collection_id=args.collection_id,
    )
    logging.info("Finished creating rating curves points Parquet file")

    logging.info("Uploading Parquet file to S3")
    upload_file_to_s3(
        local_path=output_parquet_path,
        s3_path=f"{args.s3_output_prefix}/{args.collection_id}.parquet",
    )
    logging.info("Finished uploading Parquet file to S3")
    # logging.info("Deleting local files")
    # shutil.rmtree(args.collection_id)
    # logging.info("Finished deleting local files")


if __name__ == "__main__":
    main()
