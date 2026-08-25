import logging
import os
import shutil
from typing import Type

from ..setup.collection_data import CollectionData


def copy_qc_map(collection: Type[CollectionData]):
    """Copy QGIS Template file inside a 'qc' folder in root_dir"""
    dest_location = os.path.join(collection.root_dir, "qc", "qc_map.qgs")
    os.makedirs(os.path.join(collection.root_dir, "qc"), exist_ok=True)
    shutil.copyfile(collection.config["qc"]["QC_TEMPLATE_QGIS_FILE"], dest_location)

    logging.info(f"QC map created at {dest_location}")


def dismiss_timedout_jobs(collection: Type[CollectionData], database, job_client) -> None:
    for step_name in collection.config["processing_steps"].keys():
        domain = collection.config["processing_steps"][step_name]["domain"]
        timedout_entities = database.get_entities_by_process_and_status(
            step_name, "unknown", "models" if domain == "model" else "processing"
        )
        job_client.dismiss_jobs([entity[1] for entity in timedout_entities])

    logging.info("Timedout jobs dismissed.")