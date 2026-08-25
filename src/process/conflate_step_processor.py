import logging
from time import sleep
from typing import Dict, List, Tuple

import requests

from ..setup.collection_data import CollectionData
from .base_model_step_processor import BaseModelStepProcessor
from .job_client import JobRecord
from .model import Model


class ConflateModelStepProcessor(BaseModelStepProcessor):
    """Handles model conflation specific logic"""

    def __init__(self, collection: CollectionData, models: List[Model]):
        super().__init__(collection, models)
        self.process_name = "conflate_model"

    def _execute_requests(self):
        """Model-specific request execution"""

        for model in self.models:
            job_record = self._execute_single_request(model)
            self._categorize_job_record(job_record)

    def _execute_single_request(self, model: Model) -> JobRecord:
        """Single request implementation with retries"""
        url = f"{self.collection.RIPPLE1D_API_URL}/processes/{self.collection.config["processing_steps"][self.process_name]["api_process_name"]}/execution"
        template = self.collection.config["processing_steps"][self.process_name]["payload_template"]
        payload = self._format_model_payload(template, model.id, model.name)

        for attempt in range(5):
            response = requests.post(url, json=payload)
            if response.status_code == 201:
                return JobRecord(model, response.json()["jobID"], "accepted")
            logging.debug(f"Attempt {attempt + 1} failed for model {model.id}: {response.text}")
            sleep(attempt * self.collection.config["polling"]["API_LAUNCH_JOBS_RETRY_WAIT"])

        return JobRecord(model, "", "not_accepted")
