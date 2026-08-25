import json
import logging
import os
import sqlite3
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Lock
from typing import List, Optional, Tuple, Type

import requests

from ..setup.collection_data import CollectionData
from ..setup.database import Database
from .job_client import JobClient
from .reach import Reach


def get_min_max_elevation(
    downstream_id: int,
    submodels_directory: str,
) -> Tuple[Optional[float], Optional[float]]:
    """
    Fetch min and max upstream elevation for a reach
    """

    ds_submodel_db_path = os.path.join(submodels_directory, str(downstream_id), f"{downstream_id}.db")
    if not os.path.exists(ds_submodel_db_path):
        logging.info(f"Submodel database not found for reach_id: {downstream_id}")
        return None, None

    conn = sqlite3.connect(ds_submodel_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT MIN(us_wse), MAX(us_wse) FROM rating_curves")
        min_elevation, max_elevation = cursor.fetchone()
    finally:
        conn.close()
    return min_elevation, max_elevation


def process_reach(
    reach: Reach,
    collection: Type[CollectionData],
    database: Type[Database],
    job_client: Type[JobClient],
    valid_reaches: List[Reach],
    task_queue: Queue,
    central_db_lock: Lock,
    timeout_minutes: int = 30,
) -> None:
    """
    Process a single reach for KWSE.
    1. Find us min max elevation to use as boundary conditions
    2. Submit KWSE execution job to API and wait for it to finish
    3. Create FIM Library
    4. Load rating curves to central database
    5. Put upstream reaches in queue for later processing
    """

    DS_DEPTH_INCREMENT = collection.config["ripple_settings"]["DS_DEPTH_INCREMENT"]
    RAS_VERSION = collection.config["ripple_settings"]["RAS_VERSION"]
    RIPPLE1D_API_URL = collection.RIPPLE1D_API_URL
    submodels_directory = collection.submodels_dir

    try:
        submodel_directory_path = os.path.join(submodels_directory, str(reach.id))
        headers = {"Content-Type": "application/json"}

        if (
            reach.to_id
            and reach.id in [valid_reach.id for valid_reach in valid_reaches]
            and reach.to_id in [valid_reach.id for valid_reach in valid_reaches]
        ):
            min_elevation, max_elevation = get_min_max_elevation(reach.to_id, submodels_directory)
            if min_elevation and max_elevation:

                url = f"{RIPPLE1D_API_URL}/processes/run_known_wse/execution"
                payload = json.dumps(
                    {
                        "submodel_directory": submodel_directory_path,
                        "plan_suffix": "ikwse",
                        "min_elevation": min_elevation,
                        "max_elevation": max_elevation,
                        "depth_increment": DS_DEPTH_INCREMENT,
                        "ras_version": RAS_VERSION,
                        "write_depth_grids": False,
                    }
                )

                logging.info(f"Submitting task for reach {reach.id} with downstream {reach.to_id}")

                # to do: launch job with retry
                response = requests.post(url, headers=headers, data=payload)
                response_json = response.json()
                job_id = response_json.get("jobID")
                if not job_id or not job_client.check_job_successful(job_id, timeout_minutes=timeout_minutes):
                    logging.info(f"KWSE run failed for {reach.id}, API job ID: {job_id}")
                    with central_db_lock:
                        database.update_processing_table([(reach.id, job_id)], "run_iknown_wse", "failed")
                else:
                    with central_db_lock:
                        database.update_processing_table([(reach.id, job_id)], "run_iknown_wse", "successful")

                    rc_db = f"{RIPPLE1D_API_URL}/processes/create_rating_curves_db/execution"
                    rc_db_payload = json.dumps(
                        {
                            "submodel_directory": submodel_directory_path,
                            "plans": ["ikwse"],
                        }
                    )

                    # todo: try to launch job with retry
                    response = requests.post(rc_db, headers=headers, data=rc_db_payload)
                    rc_db_response_json = response.json()
                    rc_db_job_id = rc_db_response_json.get("jobID")

                    if not rc_db_job_id or not job_client.check_job_successful(
                        rc_db_job_id, timeout_minutes=timeout_minutes
                    ):
                        with central_db_lock:
                            database.update_processing_table(
                                [(reach.id, rc_db_job_id)], "ikwse_create_rating_curves_db", "failed"
                            )
                    else:
                        with central_db_lock:
                            database.update_processing_table(
                                [(reach.id, rc_db_job_id)], "ikwse_create_rating_curves_db", "successful"
                            )
            else:
                logging.info(f"Could not retrieve min/max elevation for reach_id: {reach.to_id}")

        upstream_reaches = database.get_upstream_reaches(reach.id, central_db_lock)
        for upstream_reach in upstream_reaches:
            task_queue.put(Reach(upstream_reach, reach.id, None))

    except Exception as e:
        logging.info(f"Error processing reach {reach.id}: {str(e)}")
        traceback.print_exc()


def execute_ikwse_for_network(
    initial_reaches: List[Reach],
    collection: Type[CollectionData],
    database: Type[Database],
    job_client: Type[JobClient],
    valid_reaches: List[Reach],
    timeout: int = 30,
) -> None:
    """
    Start processing the network from the given list of initial reaches.
    """
    OPTIMUM_PARALLEL_PROCESS_COUNT = collection.config["execution"]["OPTIMUM_PARALLEL_PROCESS_COUNT"]

    task_queue = Queue()
    db_lock = Lock()
    for reach in initial_reaches:
        task_queue.put(reach)

    with ThreadPoolExecutor(max_workers=OPTIMUM_PARALLEL_PROCESS_COUNT) as executor:
        futures = []
        while not task_queue.empty() or futures:
            while not task_queue.empty():
                reach = task_queue.get()
                future = executor.submit(
                    process_reach,
                    reach,
                    collection,
                    database,
                    job_client,
                    valid_reaches,
                    task_queue,
                    db_lock,
                    timeout,
                )
                futures.append(future)

            for future in futures.copy():
                if future.done():
                    futures.remove(future)

            time.sleep(1)
