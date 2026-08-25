#!/usr/bin/env python

import argparse
import json
import logging
import os
import shutil
import subprocess
from datetime import datetime, timezone

import duckdb
import geopandas as gpd
from shapely import wkb


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


def create_rc_points_parquet(ripple_gpkg_path, submodels_dir, output_parquet_path, huc_id, collection_id):
    """
    Creates a Parquet file with point geometries representing the intersection of:
    - The cross-section with the highest river_station from each submodel's XS table
    - The corresponding reach geometry from reaches.gpkg

    Args:
        output_parquet_path (str): Path for the output Parquet file
    """

    conn = duckdb.connect()
    conn.execute("INSTALL spatial; LOAD spatial;")
    conn.execute("INSTALL sqlite; LOAD sqlite;")

    # Create temporary table to store results directly
    conn.execute(
        "CREATE TEMP TABLE points (reach_id INTEGER, model VARCHAR, river VARCHAR, reach VARCHAR, station VARCHAR, geom GEOMETRY)"
    )

    # Preload base data first
    conn.execute(
        f"""
        CREATE TEMP TABLE models AS
        SELECT model_id, reach_id
        FROM sqlite_scan('{ripple_gpkg_path}', 'processing');
    """
    )

    conn.execute(
        f"""
        CREATE TEMP TABLE reaches AS
        SELECT reach_id, geom AS reach_geom
        FROM st_read('{ripple_gpkg_path}', layer='reaches');
    """
    )

    # Create indexes for faster lookups
    conn.execute("CREATE INDEX idx_models ON models (reach_id)")
    conn.execute("CREATE INDEX idx_reaches ON reaches (reach_id)")

    # Get list of reach_ids from submodels directory
    try:
        reach_ids = [name for name in os.listdir(submodels_dir) if os.path.isdir(os.path.join(submodels_dir, name))]
    except FileNotFoundError:
        raise ValueError(f"Submodels directory '{submodels_dir}' not found")

    for reach_id in reach_ids:
        int_reach_id = int(reach_id)
        gpkg_path = os.path.join(submodels_dir, reach_id, f"{reach_id}.gpkg")

        if not os.path.exists(gpkg_path):
            logging.warning(f"Skipping {reach_id}: GPKG file not found")
            continue

        # Get CRS of the XS layer in the submodel GPKG
        crs_query = f"""SELECT
            layers[1].geometry_fields[1].crs.auth_name as name,
            layers[1].geometry_fields[1].crs.auth_code as code
            FROM st_read_meta('{gpkg_path}')
        """
        crs_result = conn.execute(crs_query).fetchall()
        if not crs_result:
            logging.error(f"Skipping {reach_id}: Could not determine CRS")
            continue
        crs = f"{crs_result[0][0]}:{crs_result[0][1]}"

        try:
            query = f"""
            WITH xs AS (
                SELECT source_river, source_reach, source_river_station, ST_Transform(geom, '{crs}', 'EPSG:5070') AS geom
                FROM st_read('{gpkg_path}', layer='XS')
                ORDER BY river_station DESC
                LIMIT 1
            ),
            reach AS (
                SELECT geom as reach_geom
                FROM reaches
                WHERE reach_id = {int_reach_id}
            ),
            model AS (
                SELECT
                    model_id AS model_id
                FROM models
                WHERE reach_id = {int_reach_id}
            )
            INSERT INTO points
            SELECT
                {int_reach_id} as reach_id, m.model_id, xs.source_river, xs.source_reach,
                xs.source_river_station,
                (SELECT geom FROM (SELECT unnest(st_dump(ST_Intersection(xs.geom, r.reach_geom)), recursive := true) LIMIT 1))
            FROM xs, reach r, model m
            WHERE ST_Intersects(xs.geom, r.reach_geom)
            """
            conn.execute(query)

        except Exception as e:
            logging.error(f"Skipping {reach_id} due to error: {str(e)}")
            continue

        # finally:
        #     break

    conn.execute(
        f"""
        CREATE TEMP TABLE us_rcs AS (
            -- Upstream data
            SELECT
                reach_id,
                us_flow AS flow_cfs,
                ROUND(us_wse / 3.28084, 2) AS wse_m,
            FROM sqlite_scan('{ripple_gpkg_path}', 'rating_curves')
            WHERE boundary_condition = 'nd'
            );"""
    )

    conn.execute(
        f"""
        CREATE TEMP TABLE combined AS (
            SELECT
                p.reach_id,
                ST_AsWKB(p.geom) AS geom_wkb, -- for later conversion to shapely geometry
                u.flow_cfs,
                u.wse_m,
                {huc_id}::TEXT AS huc8,
                '{collection_id}'  AS stac_collection,
                p.model AS stac_item_id,
                p.river AS ras_river,
                p.reach AS ras_reach,
                p.station AS ras_xs_station,
            FROM points p
            LEFT JOIN us_rcs u ON p.reach_id = u.reach_id
        );"""
    )

    # this will not create a compliant geoparquet, it will be without bbox coloumn as well as in 4326 crs
    # # Write results from temp table to Parquet
    # conn.execute(f"""
    #     COPY (
    #         SELECT
    #             reach_id,
    #             geom
    #         FROM results
    #         WHERE geom IS NOT NULL
    #     ) TO '{output_parquet_path}' (FORMAT PARQUET)
    # """)

    query = "SELECT * FROM combined"
    df = conn.execute(query).df()

    df["geometry"] = df["geom_wkb"].apply(lambda x: wkb.loads(bytes(x)) if x else None)

    df.drop(columns="geom_wkb", inplace=True)

    # Now create GeoDataFrame
    gdf = gpd.GeoDataFrame(df, geometry="geometry")
    gdf.set_crs(epsg=5070, inplace=True)  # set actual CRS

    gdf.to_parquet(output_parquet_path, engine="pyarrow", write_covering_bbox=True)

    conn.close()


def parse_arguments():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Create a denormalized rating curves table for a ripple collection",
        usage="""
        python create_rating_curves_points.py -c ble_12090301_LowerColoradoCummins \
            -root "s3://fimc-data/ripple/fim_100_domain/collections" \
            -o "s3://fimc-data/ripple/derived-data/rating_curves_extended" -huc 12090301
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
    parser.add_argument("-huc", "--HUC8", default=None, type=str, help="HUC8.")

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
        huc_id=args.HUC8,
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
