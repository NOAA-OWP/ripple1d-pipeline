import json
import logging
import os
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from queue import Queue
from threading import Lock

import requests

from ..setup.collection_data import CollectionData
from ..setup.database import Database
from .job_client import JobClient
from .reach import Reach
from .tailwater import get_max_elevation, get_min_elev_curve

logger = logging.getLogger(__name__)


def process_reach(
    reach: Reach,
    collection: type[CollectionData],
    database: type[Database],
    job_client: type[JobClient],
    valid_reaches: list[Reach],
    task_queue: Queue,
    central_db_lock: Lock,
    timeout_minutes: int = 30,
) -> None:
    """
    Process a single reach for KWSE.
    1. Build the tailwater min-elevation curve and max elevation to use as boundary
       conditions: from the u/s end of the downstream reach for a non-terminal
       reach, or the reach's own d/s end for a terminal reach
    2. Submit KWSE execution job to API and wait for it to finish
    3. Create FIM Library
    4. Load scenarios to central database
    5. Put upstream reaches in queue for later processing
    """

    DS_DEPTH_INCREMENT = collection.config["ripple_settings"]["DS_DEPTH_INCREMENT"]
    RAS_VERSION = collection.config["ripple_settings"]["RAS_VERSION"]
    RIPPLE1D_API_URL = collection.RIPPLE1D_API_URL
    submodels_directory = collection.submodels_dir

    try:
        submodel_directory_path = os.path.join(submodels_directory, str(reach.id))
        headers = {"Content-Type": "application/json"}

        if reach.id in [valid_reach.id for valid_reach in valid_reaches]:
            consider_outlet = False
            if (reach.to_id is None) or (reach.to_id not in [valid_reach.id for valid_reach in valid_reaches]):
                consider_outlet = True

                logger.info(f"{reach.id} will be considered outlet")

            # for outlet reaches, tailwater is the reach's d/s end itself
            # for non outlet reaches, tailwater is the d/s reach's u/s end
            tailwater_reach_id = reach.id if consider_outlet else reach.to_id
            min_elevation_curve = get_min_elev_curve(
                tailwater_reach_id,
                submodels_directory,
                consider_outlet,
            )
            max_elevation = get_max_elevation(
                tailwater_reach_id,
                submodels_directory,
                consider_outlet,
            )

            if min_elevation_curve and max_elevation:
                url = f"{RIPPLE1D_API_URL}/processes/run_known_wse/execution"
                payload = json.dumps(
                    {
                        "submodel_directory": submodel_directory_path,
                        "plan_suffix": "ikwse",
                        "min_elevation_curve": min_elevation_curve,
                        "max_elevation": max_elevation,
                        "depth_increment": DS_DEPTH_INCREMENT,
                        "ras_version": RAS_VERSION,
                        "write_depth_grids": False,
                    }
                )

                logger.info(f"Submitting task for reach {reach.id} with downstream {reach.to_id}")

                # to do: launch job with retry
                response = requests.post(url, headers=headers, data=payload)
                response_json = response.json()
                job_id = response_json.get("jobID")
                if not job_id or not job_client.check_job_successful(job_id, timeout_minutes=timeout_minutes):
                    logger.info(f"KWSE run failed for {reach.id}, API job ID: {job_id}")
                    with central_db_lock:
                        database.update_processing_table([(reach.id, job_id)], "run_iknown_wse", "failed")
                else:
                    with central_db_lock:
                        database.update_processing_table([(reach.id, job_id)], "run_iknown_wse", "successful")

                    scenarios_db = f"{RIPPLE1D_API_URL}/processes/create_scenarios_db/execution"
                    scenarios_db_payload = json.dumps(
                        {
                            "submodel_directory": submodel_directory_path,
                            "plans": ["ikwse"],
                        }
                    )

                    # todo: try to launch job with retry
                    response = requests.post(scenarios_db, headers=headers, data=scenarios_db_payload)
                    scenarios_db_response_json = response.json()
                    scenarios_db_job_id = scenarios_db_response_json.get("jobID")

                    if not scenarios_db_job_id or not job_client.check_job_successful(
                        scenarios_db_job_id, timeout_minutes=timeout_minutes
                    ):
                        with central_db_lock:
                            database.update_processing_table(
                                [(reach.id, scenarios_db_job_id)],
                                "ikwse_create_scenarios_db",
                                "failed",
                            )
                    else:
                        with central_db_lock:
                            database.update_processing_table(
                                [(reach.id, scenarios_db_job_id)],
                                "ikwse_create_scenarios_db",
                                "successful",
                            )
            else:
                logger.info(
                    f"Could not retrieve min elev curve and/or max elev value for reach_id: {tailwater_reach_id}"
                )

        upstream_reaches = database.get_upstream_reaches(reach.id, central_db_lock)
        for upstream_reach in upstream_reaches:
            task_queue.put(Reach(upstream_reach, reach.id, None))

    except Exception as e:
        logger.info(f"Error processing reach {reach.id}: {str(e)}")
        traceback.print_exc()


def execute_ikwse_for_network(
    initial_reaches: list[Reach],
    collection: type[CollectionData],
    database: type[Database],
    job_client: type[JobClient],
    valid_reaches: list[Reach],
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
