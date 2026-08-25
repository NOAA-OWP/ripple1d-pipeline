from typing import Dict, List, Optional, Tuple

from ..setup.collection_data import CollectionData
from ..setup.database import Database
from .base_step_processor import BaseStepProcessor
from .reach import Reach


class BaseReachStepProcessor(BaseStepProcessor):
    """Base class for reach-level processing steps"""

    def __init__(self, collection: CollectionData, reaches: List[Reach]):
        super().__init__(collection)
        self.reaches = reaches
        self.db_table = "processing"

    def _format_reach_payload(
        self, template: Dict, reach_id: int, model_id: Optional[str] = None, model_name: Optional[str] = None
    ) -> Dict:
        """Common reach payload formatting"""
        replacements = {
            "nwm_reach_id": reach_id,
            "model_id": model_id or "",
            "model_name": model_name or "",
            "submodels_directory": self.collection.submodels_dir,
            "library_directory": self.collection.library_dir,
            "source_model_directory": self.collection.source_models_dir,
        }
        return {
            key: value.format(**replacements) if isinstance(value, str) else value for key, value in template.items()
        }

    def _update_database(self, database: Database, status: str):
        """Common reach database update"""
        database.update_processing_table(
            [(job_record.entity.id, job_record.id) for job_record in self.job_records[status]],
            self.process_name,
            status,
        )
