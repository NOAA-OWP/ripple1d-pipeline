import logging
from typing import Type

import geopandas as gpd

from .collection_data import CollectionData


def filter_nwm_reaches(collection: Type[CollectionData]) -> None:
    """
    Filters NWM flowlines that intersect with the convex hull of the River table from the river_gpkg_path GPKG file
    and saves the result to a new GPKG file (db_path).

    Args:
        CollectionData (Object) : Instance of the CollectionData class containing:
            nwm_flowlines_path (str): Path to the NWM flowlines parquet file.
            river_gpkg_path (str): Path to the GPKG file containing the River table.
            output_gpkg_path (str): Path to save the filtered NWM flowlines in a GPKG file.
    """

    nwm_flowlines_path = collection.config["paths"]["NWM_FLOWLINES_PATH"]
    river_gpkg_path = collection.source_models_gpkg_path
    output_gpkg_path = collection.db_path

    # Load NWM Flowlines from Parquet file
    nwm_flowlines_gdf = gpd.read_parquet(nwm_flowlines_path, columns=["id", "to_id", "geom"])

    # Load the River table from the GPKG file
    river_gdf = gpd.read_file(river_gpkg_path, layer="River")

    # Ensure both GeoDataFrames have the same CRS (coordinate reference system)
    if nwm_flowlines_gdf.crs != river_gdf.crs:
        nwm_flowlines_gdf = nwm_flowlines_gdf.to_crs(river_gdf.crs)

    # Calculate the convex hull of the entire river geometry
    river_convex_hull = river_gdf.unary_union.convex_hull

    # Filter NWM flowlines by intersecting with the convex hull of the river
    filtered_nwm_gdf = nwm_flowlines_gdf[nwm_flowlines_gdf.intersects(river_convex_hull)]

    # Rename columns
    filtered_nwm_gdf = filtered_nwm_gdf.rename(columns={"id": "reach_id", "to_id": "nwm_to_id"})

    # Save the filtered NWM flowlines to a new GeoPackage (GPKG) file
    filtered_nwm_gdf.to_file(output_gpkg_path, layer="reaches", driver="GPKG")

    logging.info(f"Subset NWM flowlines written to reaches table {output_gpkg_path}")
