import logging
from time import sleep
from typing import Dict, List, Tuple

import requests

from ..setup.collection_data import CollectionData
from .base_reach_step_processor import BaseReachStepProcessor
from .job_client import JobRecord
from .reach import Reach


class GenericReachStepProcessor(BaseReachStepProcessor):
    """Handles generic reach processing steps"""

    def __init__(self, collection: CollectionData, reaches: List[Reach], process_name: str):
        super().__init__(collection, reaches)
        self.process_name = process_name

    def _execute_requests(self):
        """Generic reach request execution"""
        for reach in self.reaches:
            job_record = self._execute_single_request(reach)
            self._categorize_job_record(job_record)

    def _execute_single_request(self, reach: Reach) -> Tuple:
        """Single request implementation"""
        url = f"{self.collection.RIPPLE1D_API_URL}/processes/{self.collection.config["processing_steps"][self.process_name]["api_process_name"]}/execution"
        template = self.collection.config["processing_steps"][self.process_name]["payload_template"]
        payload = self._format_reach_payload(template, reach.id, reach.model.id, reach.model.name)

        for attempt in range(5):
            response = requests.post(url, json=payload)
            if response.status_code == 201:
                return JobRecord(reach, response.json()["jobID"], "accepted")
            logging.info(f"Attempt {attempt + 1} failed for model {reach.id}: {response.text}")
            sleep(attempt * self.collection.config["polling"]["API_LAUNCH_JOBS_RETRY_WAIT"])

        return JobRecord(reach, "", "not_accepted")
