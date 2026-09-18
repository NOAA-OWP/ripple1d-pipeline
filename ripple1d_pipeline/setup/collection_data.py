import logging
import os
from pathlib import Path

from ..config import load_config, load_env

logger = logging.getLogger(__name__)


class CollectionData:
    """
    Load configuration file, assign filepaths, create folders within the collection's root directory.
    """

    def __init__(self, stac_collection_id):
        self.stac_collection_id = stac_collection_id
        load_env(override=True)
        self.config = load_config()
        self.RIPPLE1D_API_URL = self.config["endpoints"]["RIPPLE1D_API_URL"]
        self.STAC_URL = self.config["endpoints"]["STAC_URL"]
        self.assign_paths()

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
        self.bridge_tile_index_path = self.config["paths"].get("BRIDGE_TILE_INDEX_PATH", "")

    def create_folders(self):
        """Create folders for source models, submodels, and library."""

        os.makedirs(self.source_models_dir, exist_ok=True)
        os.makedirs(self.submodels_dir, exist_ok=True)
        os.makedirs(self.library_dir, exist_ok=True)

        logger.info(f"Folders created successfully inside {self.root_dir}")

    def get_models(self) -> list[tuple[str, str]]:
        """Discover models and their associated .gpkg files in source models directory.

        Returns:
            List of tuples (model_dir_name, gpkg_base_name)
        """
        models = []
        base_path = Path(self.source_models_dir)

        try:
            if not base_path.exists():
                logger.error(f"Source models directory not found: {base_path}")
                return []

            for model_path in base_path.iterdir():
                if model_path.is_dir():
                    gpkg_files = list(model_path.glob("*.gpkg"))

                    # Handle .gpkg file validation
                    if len(gpkg_files) == 1:
                        gpkg_name = gpkg_files[0].stem
                        models.append((model_path.name, gpkg_name))
                    elif len(gpkg_files) > 1:
                        logger.error(f"Multiple .gpkg files in {model_path.name}, using first")
                    else:
                        logger.error(f"No .gpkg file found in {model_path.name}")

                    continue

            if not models:
                logger.warning(f"No valid model directories found in {base_path}")

            return models

        except Exception as e:
            logger.exception(f"Model discovery failed: {str(e)}")
            return []
