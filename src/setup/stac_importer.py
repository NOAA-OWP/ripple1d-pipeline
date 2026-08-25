import logging
import os
from typing import List, Type

import boto3
import pystac_client
from dotenv import load_dotenv

from .collection_data import CollectionData


class STACImporter:
    """
    Methods to identify models from a STAC Collection, and download each model's gpkg files from AWS S3.
    """

    def __init__(self, collectiondata: Type[CollectionData]):
        self.db_path = collectiondata.db_path
        self.stac_collection = collectiondata.stac_collection_id
        self.stac_endpoint = collectiondata.STAC_URL
        self.source_models_dir = collectiondata.source_models_dir
        self.models_data = None
        self.model_ids = None
        load_dotenv(".env", override=True)

    def get_models_from_stac(self) -> None:
        """
        Retrieves GeoPackage file and conflation file paths for models in an STAC collection.
        Parameters:
        - self.stac_endpoint (str): The STAC API endpoint.
        - self.stac_collection (str): The name of the STAC collection.
        """
        client = pystac_client.Client.open(self.stac_endpoint)
        collection = client.get_collection(self.stac_collection)
        i = 0
        omitted = 0
        models_data = {}
        for item in collection.get_items():
            i += 1
            if self.filter_model(item):
                omitted += 1
                continue
            gpkg_key = ""
            for _, asset in item.assets.items():
                if "ras-geometry-gpkg" in asset.roles:
                    gpkg_key = asset.href
                    break
            if gpkg_key:
                models_data[item.id] = {"gpkg": gpkg_key, "model_name": item.properties["model_name"]}

        logging.info(f"Total {i} models in this collection")
        logging.info(f"{omitted} models were omitted from this collection")
        logging.info(f"Total usable models from this collection: {len(models_data)}.")

        self.models_data = models_data

    def download_models_data(self) -> None:
        """
        Downloads GeoPackage for models to a local folder.

        Parameters:
        - self.models_data (dict): Dictionary containing model IDs and their file URLs.
        - self.source_models_dir (str): The local directory to store the downloaded models.
        """
        session = boto3.Session(
            aws_access_key_id=os.environ.get("RP_STAC_AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("RP_STAC_AWS_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("RP_STAC_AWS_REGION", "us-east-1"),
        )

        s3_client = session.client("s3")

        for id, data in self.models_data.items():
            try:
                model_dir = os.path.join(self.source_models_dir, id)
                os.makedirs(model_dir, exist_ok=True)

                # Download GeoPackage
                local_gpkg_path = os.path.join(model_dir, f"{data["model_name"]}.gpkg")

                gpkg_url = data["gpkg"]
                bucket_name, key = gpkg_url.replace("s3://", "").split("/", 1)
                s3_client.download_file(bucket_name, key, local_gpkg_path)

                logging.info(f"Successfully downloaded files for {id}")
            except Exception as e:
                logging.info(f"Failed to download files for {id}: {e}")

    def get_model_ids(self) -> List[str]:
        self.model_ids = list(self.models_data.keys())
        return self.model_ids

    def filter_model(self, item) -> bool:
        """
        Filter function which determines if a model should be skipped for download.
        Cerrtain model properties are incompatible with Ripple1d.

        Args:
            item: Collection Object containing properties dictionary

        Returns:
            bool: True if model should be skipped, False otherwise
        """

        if item.properties["has_2d"]:
            logging.info(f"{item.id} skipping because it has 2d elements")
            return True
        if item.properties["ras_units"] != "English":
            logging.info(f"{item.id} skipping because it has non English Units")
            return True
        # If there are no steady flow files, skip the model (Ripple1d cannot process unsteady flow files)
        flows = item.properties["flows"]
        any_flows_start_with_f = any(value.startswith("f") or value.startswith("F") for value in flows.values())
        if any_flows_start_with_f == False:
            logging.info(f"{item.id} skipping because it has no valid steady flow files")
            return True
        else:
            return False
