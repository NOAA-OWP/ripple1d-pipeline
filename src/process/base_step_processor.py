import logging
from abc import abstractmethod
from typing import Tuple

from ..setup.collection_data import CollectionData
from ..setup.database import Database
from .job_client import JobClient, JobRecord


class BaseStepProcessor:
    """Base class for all processing steps"""

    def __init__(self, collection: CollectionData):
        self.collection = collection
        self.job_records = {"accepted": [], "succeeded": [], "failed": [], "not_accepted": [], "unknown": []}

    def execute_step(self, job_client: JobClient, database: Database, timeout: int):
        """Template method defining the processing workflow"""
        self._execute_requests()
        self._update_database(database, "accepted")
        self._update_database(database, "not_accepted")
        logging.info("Jobs submitted, waiting for jobs to finish")
        self._wait_for_jobs(job_client, timeout)
        self._update_database(database, "succeeded")
        self._update_database(database, "failed")
        self._update_database(database, "unknown")
        self._log_results()

    @abstractmethod
    def _execute_requests(self):
        """Execute API requests for all items"""
        pass

    @abstractmethod
    def _update_database(self, database: Database, status: str):
        """Update database with current status"""
        pass

    def _wait_for_jobs(self, job_client: JobClient, timeout: int):
        """Common job waiting implementation"""
        self.job_records["succeeded"], self.job_records["failed"], self.job_records["unknown"] = (
            job_client.wait_for_jobs(self.job_records["accepted"], timeout)
        )

    def _categorize_job_record(self, job_record: JobRecord) -> None:
        """Categorizes a job result into appropriate status list"""

        if job_record.status == "accepted":
            self.job_records["accepted"].append(job_record)
        elif job_record.status == "not_accepted":
            self.job_records["not_accepted"].append(job_record)
        else:
            # For succeeded/failed/unknown from job_client
            self.job_records[job_record.status].append(job_record)

    def _log_results(self):
        """Common logging implementation"""
        logging.info(f"Successful: {len(self.job_records['succeeded'])}")
        logging.info(f"Failed: {len(self.job_records['failed'])}")
        logging.info(f"Not Accepted: {len(self.job_records['not_accepted'])}")
        logging.info(f"Unknown: {len(self.job_records['unknown'])}")

    def dismiss_timedout_jobs(self, job_client: JobClient):
        """Dismiss all unknown jobs"""
        job_client.dismiss_jobs(self.job_records["unknown"])

    @property
    def valid_entities(self):
        """Returns all entities that were succeeded or timedout(unknown)"""
        return [job_record.entity for job_record in self.job_records["succeeded"] + self.job_records["unknown"]]
