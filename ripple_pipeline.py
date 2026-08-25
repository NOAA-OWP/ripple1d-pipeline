#!/usr/bin/env python3

import argparse
import logging
import time

# Import necessary modules
from src.process import *
from src.qc import *
from src.setup import *

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def setup(collection_name):
    """Setup the resources."""
    logging.info(f"Setting up the resources for collection: {collection_name}")

    # Instantiate CollectionData
    collection = CollectionData(collection_name)
    logging.info(f"Creating folder structure in {collection.root_dir}")
    collection.create_folders()

    # Instantiate STACImporter
    stac_importer = STACImporter(collection)
    logging.info("Downloading models from STAC catalog")
    stac_importer.get_models_from_stac()
    stac_importer.download_models_data()
    models_data = stac_importer.models_data
    # models_data = {"Baxter": {"model_name": "Baxter"}}

    create_src_models_gpkg(models_data, collection)

    logging.info("Filtering NWM reaches")
    filter_nwm_reaches(collection)

    logging.info("Initializing database")
    Database.init_db(collection)

    logging.info("Inserting models into database")
    Database.insert_models(models_data, collection)


def process(collection_name):
    """Process the data."""
    logging.info("Starting processing >>>>>>>>")
    # Instantiate CollectionData, Database, JobClient objects
    collection = CollectionData(collection_name)
    database = Database(collection)
    jobclient = JobClient(collection)

    models = [Model(*model) for model in collection.get_models()]
    logging.info(f"{len(models)} models available in source models folder")

    # TODO - Create a @dataclass for model_job_status & reach_job_status
    logging.info("Starting Conflate Model Step >>>>>>")
    conflate_step_processor = ConflateModelStepProcessor(collection, models)
    conflate_step_processor.execute_step(jobclient, database, timeout=20)
    logging.info("<<<<<<Finished Conflate Model Step")
    conflate_step_processor.dismiss_timedout_jobs(jobclient) # dismiss stale jobs so they don't occupy API

    logging.info("Starting Load Conflation Step >>>>>>")
    valid_models = conflate_step_processor.valid_entities
    load_conflation(valid_models, database)
    logging.info("Finished Load Conflation Step")

    logging.info("Starting Update Network Step >>>>>>")
    update_network(database)
    logging.info("<<<<<< Finished Update Network Step")

    logging.info("Starting Get Reaches by Models Step >>>>>>")
    reaches = [
        Reach(row[0], row[1], Model(row[2], row[3]))
        for row in database.get_reaches_by_models([model.id for model in valid_models])
    ]
    outlet_reaches = [reach for reach in reaches if reach.to_id is None]
    logging.info(f"{len(reaches)} reaches returned")
    logging.info("<<<<<< Finished Get Reaches by Models Step")

    # Reach Steps

    logging.info("Starting Extract Submodel Step >>>>>>")
    submodel_step_processor = GenericReachStepProcessor(collection, reaches, "extract_submodel")
    submodel_step_processor.execute_step(jobclient, database, timeout=10)
    logging.info("<<<<<< Finihsed Extract Submodel Step")

    logging.info("Starting Create Ras Terrain Step >>>>>>")
    terrain_step_processor = GenericReachStepProcessor(
        collection, submodel_step_processor.valid_entities, "create_ras_terrain"
    )
    terrain_step_processor.execute_step(jobclient, database, timeout=10)
    logging.info("<<<<<< Finished Create Ras Terrain Step")
    submodel_step_processor.dismiss_timedout_jobs(jobclient) # by dismissing jobs one step later, we give previous step more time, when possible

    logging.info("Starting Create Model Run Normal Depth Step  >>>>>>>>")
    create_model_step_processor = GenericReachStepProcessor(
        collection, terrain_step_processor.valid_entities, "create_model_run_normal_depth"
    )
    create_model_step_processor.execute_step(jobclient, database, timeout=15)
    logging.info("<<<<<< Finished Create Model Run Normal Depth Step")
    terrain_step_processor.dismiss_timedout_jobs(jobclient)

    logging.info("<<<<< Started Run Incremental Normal Depth Step")
    nd_step_processor = GenericReachStepProcessor(
        collection, create_model_step_processor.valid_entities, "run_incremental_normal_depth"
    )
    nd_step_processor.execute_step(jobclient, database, timeout=25)
    logging.info("<<<<< Finished Run Incremental Normal Depth Step")
    create_model_step_processor.dismiss_timedout_jobs(jobclient)
    nd_step_processor.dismiss_timedout_jobs(jobclient)

    logging.info("Starting nd create_rating_curves_db Step >>>>>>")
    nd_rc_step_processor = GenericReachStepProcessor(
        collection, nd_step_processor.valid_entities, "nd_create_rating_curves_db"
    )
    nd_rc_step_processor.execute_step(jobclient, database, timeout=15)
    logging.info("<<<<< Finished nd create_rating_curves_db Step")
    nd_rc_step_processor.dismiss_timedout_jobs(jobclient)

    logging.info("Starting Initial run_known_wse and Initial create_rating_curves_db Steps>>>>>>")
    execute_ikwse_for_network(
        outlet_reaches,
        collection,
        database,
        jobclient,
        nd_rc_step_processor.valid_entities,
        timeout=20,
    )
    logging.info("<<<<< Completed Initial run_known_wse and Initial create_rating_curves_db steps")

    logging.info("Starting Final execute_kwse_step >>>>>>")
    non_outlet_valid_reaches = [
        reach
        for reach in nd_rc_step_processor.valid_entities
        if reach.to_id is not None
        and reach.to_id in [valid_reach.id for valid_reach in nd_rc_step_processor.valid_entities]
    ]
    kwse_step_processor = KWSEStepProcessor(collection, non_outlet_valid_reaches)
    kwse_step_processor.execute_step(jobclient, database, timeout=240)
    logging.info("<<<<< Finished Final execute_kwse_step")
    kwse_step_processor.dismiss_timedout_jobs(jobclient)

    logging.info("Starting kwse create_rating_curves_db Step >>>>>>")
    kwse_rc_step_processor = GenericReachStepProcessor(
        collection, kwse_step_processor.valid_entities, "kwse_create_rating_curves_db"
    )
    kwse_rc_step_processor.execute_step(jobclient, database, timeout=15)
    logging.info("<<<<< Finished kwse create_rating_curves_db Step")
    kwse_rc_step_processor.dismiss_timedout_jobs(jobclient)

    logging.info("Starting Merge Rating Curves Step >>>>>>")
    load_all_rating_curves(database)
    logging.info("<<<<< Finished Merge Rating Curves Step")

    logging.info("Starting create_fim_lib Step >>>>>>")
    fimlib_step_processor = GenericReachStepProcessor(collection, nd_rc_step_processor.valid_entities, "create_fim_lib")
    fimlib_step_processor.execute_step(jobclient, database, timeout=150)
    logging.info("<<<<< Finished create_fim_lib Step")
    fimlib_step_processor.dismiss_timedout_jobs(jobclient)

    try:
        logging.info("Starting create extent library Step >>>>>>")
        create_extent_lib(collection)
        logging.info("<<<<< Finished create extent library Step")
    except:
        logging.error("Error - create extent library step failed")

    try:
        logging.info("Creating f2f start file >>>>>>")
        create_f2f_start_file([reach.id for reach in outlet_reaches], collection.f2f_start_file)
        logging.info("<<<<< Created f2f start file")
    except:
        logging.error("Error - unable to create f2f start file")


def run_qc(collection_name, execute_flows2fim=False):
    """Perform quality control."""
    logging.info("Starting QC")
    collection = CollectionData(collection_name)
    database = Database(collection)
    job_client = JobClient(collection)

    logging.info("Creating Failed Job Report >>>>>>>>")
    create_failed_jobs_report(collection, database, job_client)
    logging.info("<<<<< Finished Creating Failed Job Report")

    logging.info("Creating TimedOut Job Report >>>>>>>>")
    create_timedout_jobs_report(collection, database, job_client)
    logging.info("<<<<< Finished Creating TimedOut Job Report")

    if execute_flows2fim:
        logging.info("Starting run_flows2fim step >>>>>>")
        run_flows2fim(collection)
        logging.info("<<<<< Finished run_flows2fim step")

        logging.info("Running copy_qc_map step >>>>>")
        copy_qc_map(collection)
        logging.info("<<<<< Finished copy_qc_map step")


def run_pipeline(collection: str):
    """Automate execution of all pipeline steps with conditional QC"""
    execute_flows2fim = False


    try:
        setup(collection)
        process(collection)
        execute_flows2fim = True
    except Exception as e:
        logging.error(f"Main workflow failed: {str(e)}")
        raise e

    finally:
        try:
            run_qc(collection, execute_flows2fim)
        except Exception as qc_error:
            logging.error(f"QC failed: {str(qc_error)}")

if __name__ == "__main__":
    """
    Sample Usage:
        python ripple_pipeline.py -c ble_12100302_Medina
    """

    parser = argparse.ArgumentParser(description="Run ripple pipeline steps on one collection")

    parser.add_argument(
        "-c",
        "--collection",
        help=f"A valid collection of HEC-RAS models. The collection will initially be pulled "
        "locally from the provided STAC URL (in config.py). "
        "https://radiantearth.github.io/stac-browser/#/external/stac2.dewberryanalytics.com/?.language=en ",
        required=True,
    )
    args = vars(parser.parse_args())

    run_pipeline(**args)
