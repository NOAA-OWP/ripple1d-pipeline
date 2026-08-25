import logging
import os
from pathlib import Path
from typing import List, Tuple

import yaml
from dotenv import load_dotenv


class CollectionData:
    """
    Load configuration file, assign filepaths, create folders within the collection's root directory.
    """

    def __init__(self, stac_collection_id, config_file="config.yaml"):
        self.stac_collection_id = stac_collection_id
        self.load_dotenv(".env")
        self.load_yaml(config_file)
        self.assign_paths()

    # TODO - Assign ALL parameters from config.yaml to attributes of CollectionData Class?
    def load_yaml(self, config_file):
        try:
            with open(str(Path.cwd() / "src" / config_file), "r") as file:
                self.config = yaml.safe_load(file)
        except FileNotFoundError:
            raise ValueError(f"File '{config_file}' not found. Ensure config.yaml is in the src directory.")
        except yaml.YAMLError:
            raise ValueError("Invalid YAML configuration")

    def load_dotenv(self, dotenv_file):
        try:
            load_dotenv(dotenv_file, override=True)
            self.RIPPLE1D_API_URL = os.getenv("RP_RIPPLE1D_API_URL")
            self.STAC_URL = os.getenv("RP_STAC_URL")
        except:
            raise ValueError("Invalid .env configuration")

    def assign_paths(self):
        """Assign filepaths to CollectionData object."""
        self.root_dir = os.path.join(self.config["paths"]["COLLECTIONS_ROOT_DIR"], str(self.stac_collection_id))
        self.db_path = os.path.join(self.root_dir, "ripple.gpkg")
        self.source_models_dir = os.path.join(self.root_dir, "source_models")
        self.source_models_gpkg_path = os.path.join(self.root_dir, "source_models", "source_models.gpkg")
        self.submodels_dir = os.path.join(self.root_dir, "submodels")
        self.library_dir = os.path.join(self.root_dir, "library")
        self.extent_library_dir = os.path.join(self.root_dir, "library_extent")
        self.f2f_start_file = os.path.join(self.root_dir, "start_reaches.csv")
        self.failed_jobs_report_path = os.path.join(self.root_dir, "failed_jobs_report.xlsx")
        self.timedout_jobs_report_path = os.path.join(self.root_dir, "timedout_jobs_report.xlsx")


    def create_folders(self):
        """Create folders for source models, submodels, and library."""

        os.makedirs(self.source_models_dir, exist_ok=True)
        os.makedirs(self.submodels_dir, exist_ok=True)
        os.makedirs(self.library_dir, exist_ok=True)

        logging.info(f"Folders created successfully inside {self.root_dir}")

    def get_models(self) -> List[Tuple[str, str]]:
        """Discover models and their associated .gpkg files in source models directory.

        Returns:
            List of tuples (model_dir_name, gpkg_base_name)
        """
        models = []
        base_path = Path(self.source_models_dir)

        try:
            if not base_path.exists():
                logging.error(f"Source models directory not found: {base_path}")
                return []

            for model_path in base_path.iterdir():
                if model_path.is_dir():
                    gpkg_files = list(model_path.glob("*.gpkg"))

                    # Handle .gpkg file validation
                    if len(gpkg_files) == 1:
                        gpkg_name = gpkg_files[0].stem
                        models.append((model_path.name, gpkg_name))
                    elif len(gpkg_files) > 1:
                        logging.error(f"Multiple .gpkg files in {model_path.name}, using first")
                    else:
                        logging.error(f"No .gpkg file found in {model_path.name}")

                    continue

            if not models:
                logging.warning(f"No valid model directories found in {base_path}")

            return models

        except Exception as e:
            logging.error(f"Model discovery failed: {str(e)}", exc_info=True)
            return []
