from typing import Dict, List

from ..setup.collection_data import CollectionData
from ..setup.database import Database
from .base_step_processor import BaseStepProcessor
from .model import Model


class BaseModelStepProcessor(BaseStepProcessor):
    """Base class for model-level processing steps"""

    def __init__(self, collection: CollectionData, models: List[Model]):
        super().__init__(collection)
        self.models = models
        self.db_table = "models"

    def _format_model_payload(self, template: Dict, model_id: str, model_name: str) -> Dict:
        """Common model payload formatting"""
        return {
            key: (
                value.format(
                    model_id=model_id, model_name=model_name, source_model_directory=self.collection.source_models_dir
                )
                if isinstance(value, str)
                else value
            )
            for key, value in template.items()
        }

    def _update_database(self, database: Database, status: str):
        """Common model database update"""
        database.update_models_table(
            [(job_record.entity.id, job_record.id) for job_record in self.job_records[status]],
            self.process_name,
            status,
        )
