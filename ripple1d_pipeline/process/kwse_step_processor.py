import logging
from time import sleep

import requests

from ..setup.collection_data import CollectionData
from .base_reach_step_processor import BaseReachStepProcessor
from .job_client import JobRecord
from .reach import Reach
from .tailwater import get_max_elevation, get_min_elev_curve

logger = logging.getLogger(__name__)


class KWSEStepProcessor(BaseReachStepProcessor):
    """Handles KWSE-specific reach processing"""

    def __init__(self, collection: CollectionData, reaches: list[Reach]):
        super().__init__(collection, reaches)
        self.process_name = "run_known_wse"

    def _execute_requests(self):
        """KWSE-specific request execution with elevation data"""
        for reach in self.reaches:
            job_record = self._execute_single_request(reach)
            self._categorize_job_record(job_record)

    def _execute_single_request(self, reach: Reach) -> JobRecord:
        """KWSE-specific request implementation with elevation data"""

        consider_outlet = False
        # if the .to_id reach is not in self.reaches then it has failed a previous step
        # and do not have a reach db, hence consider the reach outlet
        if (reach.to_id is None) or (reach.to_id not in [valid_reach.id for valid_reach in self.reaches]):
            consider_outlet = True
            logger.info(f"{reach.id} will be considered outlet")

        # for outlet reaches, tailwater is the reach's d/s end itself
        # for non outlet reaches, tailwater is the d/s reach's u/s end
        tailwater_reach_id = reach.id if consider_outlet else reach.to_id
        submodels_dir = self.collection.submodels_dir

        # At this point, these functions would query for both nd and ikwse rating  curves
        # but that is not problamatic because new ikwse scenarios are within the same range
        min_elevation_curve = get_min_elev_curve(
            tailwater_reach_id,
            submodels_dir,
            consider_outlet,
        )
        max_elev = get_max_elevation(
            tailwater_reach_id,
            submodels_dir,
            consider_outlet,
        )

        if not min_elevation_curve or not max_elev:
            logger.info(f"Could not retrieve min elev curve and/or max elev value for reach_id: {tailwater_reach_id}")
            return JobRecord(reach, "", "not_accepted")

        url = f"{self.collection.RIPPLE1D_API_URL}/processes/{self.collection.config['processing_steps'][self.process_name]['api_process_name']}/execution"
        template = self.collection.config["processing_steps"][self.process_name]["payload_template"]
        payload = self._format_reach_payload(template, reach.id)
        payload.update({"min_elevation_curve": min_elevation_curve, "max_elevation": max_elev})

        for attempt in range(5):
            response = requests.post(url, json=payload)
            if response.status_code == 201:
                return JobRecord(reach, response.json()["jobID"], "accepted")
            logger.info(f"Attempt {attempt + 1} failed for model {reach.id}: {response.text}")
            sleep(attempt * self.collection.config["polling"]["API_LAUNCH_JOBS_RETRY_WAIT"])

        return JobRecord(reach, "", "not_accepted")
