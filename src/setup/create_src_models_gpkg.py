import logging
import os
from typing import Dict, List, Type

import geopandas as gpd
import pandas as pd

from .collection_data import CollectionData


def load_layer_from_gpkg(gpkg_path: str, layer_name: str) -> gpd.GeoDataFrame:
    """
    Load a specified layer from a GeoPackage file.

    Args:
        gpkg_path (str): Path to the GeoPackage file
        layer_name (str): Name of the layer to load

    Returns:
        gpd.GeoDataFrame: Loaded GeoDataFrame or None if error occurs
    """
    try:
        return gpd.read_file(gpkg_path, columns=[], layer=layer_name)
    except Exception as e:
        logging.info(f"Error loading {layer_name} table from {gpkg_path}: {e}")
        return None


def process_and_save_layer(layer_name: str, gdfs: List[gpd.GeoDataFrame], output_path: str) -> None:
    """
    Process and save combined GeoDataFrames for a specific layer.

    Args:
        layer_name (str): Name of the layer being processed
        gdfs (List[gpd.GeoDataFrame]): List of GeoDataFrames to combine
        output_path (str): Path to output GeoPackage
    """
    if not gdfs:
        logging.info(f"No {layer_name} tables were combined.")
        return

    try:
        combined_gdf = gpd.GeoDataFrame(pd.concat(gdfs, ignore_index=True))
        combined_gdf.to_file(output_path, driver="GPKG", layer=layer_name)
        logging.info(f"Combined {layer_name} tables saved to {output_path}")
    except Exception as e:
        logging.info(f"Error saving combined {layer_name} table: {e}")


def create_src_models_gpkg(models_data: Dict, collection: Type[CollectionData]) -> None:
    """
    Combine multiple GeoPackage layers from different models into a single GeoPackage.

    Args:
        models_data (Dict): Dictionary of model data
        collection (CollectionData): Collection configuration object
    """
    target_crs = "EPSG:5070"
    output_gpkg_path = collection.source_models_gpkg_path
    layer_data = {"River": [], "XS": []}

    for model_id, model_data in models_data.items():
        gpkg_path = os.path.join(collection.source_models_dir, model_id, f"{model_data['model_name']}.gpkg")

        if not os.path.exists(gpkg_path):
            logging.info(f"GPKG file not found: {gpkg_path}")
            continue

        for layer_name in layer_data.keys():
            gdf = load_layer_from_gpkg(gpkg_path, layer_name)
            if gdf is not None:
                if gdf.crs is None or gdf.crs.to_string() != target_crs:
                    gdf = gdf.to_crs(target_crs)

                gdf["model_id"] = model_id
                layer_data[layer_name].append(gdf)

    for layer_name, gdfs in layer_data.items():
        process_and_save_layer(layer_name, gdfs, output_gpkg_path)
