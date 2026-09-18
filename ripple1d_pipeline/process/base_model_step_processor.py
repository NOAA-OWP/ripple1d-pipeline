from ..setup.collection_data import CollectionData
from ..setup.database import Database
from .base_step_processor import BaseStepProcessor, format_template
from .model import Model


class BaseModelStepProcessor(BaseStepProcessor):
    """Base class for model-level processing steps"""

    def __init__(self, collection: CollectionData, models: list[Model]):
        super().__init__(collection)
        self.models = models
        self.db_table = "models"

    def _format_model_payload(self, template: dict, model_id: str, model_name: str) -> dict:
        """Common model payload formatting"""
        replacements = {
            **self.collection.config["ripple_settings"],
            "model_id": model_id,
            "model_name": model_name,
            "source_model_directory": self.collection.source_models_dir,
            "source_network": self.collection.config["paths"]["SOURCE_NETWORK"],
        }
        return {key: format_template(value, replacements) for key, value in template.items()}

    def _update_database(self, database: Database, status: str):
        """Common model database update"""
        database.update_models_table(
            [(job_record.entity.id, job_record.id) for job_record in self.job_records[status]],
            self.process_name,
            status,
        )
