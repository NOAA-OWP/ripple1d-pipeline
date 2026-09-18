#!/usr/bin/env python3

import argparse
import logging

# Import necessary modules
from ripple1d_pipeline import configure_logging
from ripple1d_pipeline.process import *
from ripple1d_pipeline.qc import *
from ripple1d_pipeline.setup import *

logger = logging.getLogger("run_collection")


def setup(collection_name):
    """Setup the resources."""
    logger.info(f"Setting up the resources for collection: {collection_name}")

    # Instantiate CollectionData
    collection = CollectionData(collection_name)
    logger.info(f"Creating folder structure in {collection.root_dir}")
    collection.create_folders()

    # Instantiate STACImporter
    stac_importer = STACImporter(collection)
    logger.info("Downloading models from STAC catalog")
    stac_importer.get_models_from_stac()
    stac_importer.download_models_data()
    models_data = stac_importer.models_data
    # models_data = {"Baxter": {"model_name": "Baxter"}}

    create_src_models_gpkg(models_data, collection)

    logger.info("Filtering NWM reaches")
    filter_nwm_reaches(collection)

    logger.info("Initializing database")
    Database.init_db(collection)

    logger.info("Inserting models into database")
    Database.insert_models(models_data, collection)


def process(collection_name):
    """Process the data."""
    logger.info("Starting processing >>>>>>>>")
    # Instantiate CollectionData, Database, JobClient objects
    collection = CollectionData(collection_name)
    database = Database(collection)
    jobclient = JobClient(collection)

    models = [Model(*model) for model in collection.get_models()]
    logger.info(f"{len(models)} models available in source models folder")

    # TODO - Create a @dataclass for model_job_status & reach_job_status
    logger.info("Starting Conflate Model Step >>>>>>")
    conflate_step_processor = ConflateModelStepProcessor(collection, models)
    conflate_step_processor.execute_step(jobclient, database, timeout=20)
    logger.info("<<<<<<Finished Conflate Model Step")
    conflate_step_processor.dismiss_timedout_jobs(jobclient)  # dismiss stale jobs so they don't occupy API

    logger.info("Starting Load Conflation Step >>>>>>")
    valid_models = conflate_step_processor.valid_entities
    load_conflation(valid_models, database)
    logger.info("Finished Load Conflation Step")

    logger.info("Starting Update Network Step >>>>>>")
    update_network(database)
    logger.info("<<<<<< Finished Update Network Step")

    logger.info("Starting Get Reaches by Models Step >>>>>>")
    reaches = [
        Reach(row[0], row[1], Model(row[2], row[3]))
        for row in database.get_reaches_by_models([model.id for model in valid_models])
    ]
    outlet_reaches = [reach for reach in reaches if reach.to_id is None]
    logger.info(f"{len(reaches)} reaches returned")
    logger.info("<<<<<< Finished Get Reaches by Models Step")

    # Reach Steps

    logger.info("Starting Extract Submodel Step >>>>>>")
    submodel_step_processor = GenericReachStepProcessor(collection, reaches, "extract_submodel")
    submodel_step_processor.execute_step(jobclient, database, timeout=10)
    logger.info("<<<<<< Finished Extract Submodel Step")

    logger.info("Starting Create Ras Terrain Step >>>>>>")
    terrain_step_processor = GenericReachStepProcessor(
        collection, submodel_step_processor.valid_entities, "create_ras_terrain"
    )
    terrain_step_processor.execute_step(jobclient, database, timeout=10)
    logger.info("<<<<<< Finished Create Ras Terrain Step")
    submodel_step_processor.dismiss_timedout_jobs(
        jobclient
    )  # by dismissing jobs one step later, we give previous step more time, when possible

    logger.info("Starting Create Model Run Normal Depth Step  >>>>>>>>")
    create_model_step_processor = GenericReachStepProcessor(
        collection,
        terrain_step_processor.valid_entities,
        "create_model_run_normal_depth",
    )
    create_model_step_processor.execute_step(jobclient, database, timeout=15)
    logger.info("<<<<<< Finished Create Model Run Normal Depth Step")
    terrain_step_processor.dismiss_timedout_jobs(jobclient)

    logger.info("<<<<< Started Run Incremental Normal Depth Step")
    nd_step_processor = GenericReachStepProcessor(
        collection,
        create_model_step_processor.valid_entities,
        "run_incremental_normal_depth",
    )
    nd_step_processor.execute_step(jobclient, database, timeout=25)
    logger.info("<<<<< Finished Run Incremental Normal Depth Step")
    create_model_step_processor.dismiss_timedout_jobs(jobclient)
    nd_step_processor.dismiss_timedout_jobs(jobclient)

    logger.info("Starting nd create_scenarios_db Step >>>>>>")
    nd_scenarios_step_processor = GenericReachStepProcessor(
        collection, nd_step_processor.valid_entities, "nd_create_scenarios_db"
    )
    nd_scenarios_step_processor.execute_step(jobclient, database, timeout=15)
    logger.info("<<<<< Finished nd create_scenarios_db Step")
    nd_scenarios_step_processor.dismiss_timedout_jobs(jobclient)

    logger.info("Starting Initial run_known_wse and Initial create_scenarios_db Steps>>>>>>")
    execute_ikwse_for_network(
        outlet_reaches,
        collection,
        database,
        jobclient,
        nd_scenarios_step_processor.valid_entities,
        timeout=20,
    )
    logger.info("<<<<< Completed Initial run_known_wse and Initial create_scenarios_db steps")

    logger.info("Starting Final execute_kwse_step >>>>>>")
    kwse_step_processor = KWSEStepProcessor(collection, nd_scenarios_step_processor.valid_entities)
    kwse_step_processor.execute_step(jobclient, database, timeout=240)
    logger.info("<<<<< Finished Final execute_kwse_step")
    kwse_step_processor.dismiss_timedout_jobs(jobclient)

    logger.info("Starting kwse create_scenarios_db Step >>>>>>")
    kwse_scenarios_step_processor = GenericReachStepProcessor(
        collection, kwse_step_processor.valid_entities, "kwse_create_scenarios_db"
    )
    kwse_scenarios_step_processor.execute_step(jobclient, database, timeout=15)
    logger.info("<<<<< Finished kwse create_scenarios_db Step")
    kwse_scenarios_step_processor.dismiss_timedout_jobs(jobclient)

    logger.info("Starting Merge Scenarios Step >>>>>>")
    load_all_scenarios(database)
    logger.info("<<<<< Finished Merge Scenarios Step")

    logger.info("Starting create_fim_lib Step >>>>>>")
    fimlib_step_processor = GenericReachStepProcessor(
        collection, nd_scenarios_step_processor.valid_entities, "create_fim_lib"
    )
    fimlib_step_processor.execute_step(jobclient, database, timeout=150)
    logger.info("<<<<< Finished create_fim_lib Step")
    fimlib_step_processor.dismiss_timedout_jobs(jobclient)

    try:
        logger.info("Starting bridge deck masking Step >>>>>>")
        process_bridges(collection)
        logger.info("<<<<< Finished bridge deck masking Step")
    except Exception:
        logger.exception("Error - bridge deck masking step failed")

    try:
        logger.info("Starting create extent library Step >>>>>>")
        create_extent_lib(collection)
        logger.info("<<<<< Finished create extent library Step")
    except Exception:
        logger.exception("Error - create extent library step failed")

    try:
        logger.info("Creating f2f start file >>>>>>")
        create_f2f_start_file([reach.id for reach in outlet_reaches], collection.f2f_start_file)
        logger.info("<<<<< Created f2f start file")
    except Exception:
        logger.exception("Error - unable to create f2f start file")


def run_qc(collection_name, execute_flows2fim=False):
    """Perform quality control."""
    logger.info("Starting QC")
    collection = CollectionData(collection_name)
    database = Database(collection)
    job_client = JobClient(collection)

    logger.info("Creating Failed Job Report >>>>>>>>")
    create_failed_jobs_report(collection, database, job_client)
    logger.info("<<<<< Finished Creating Failed Job Report")

    logger.info("Creating TimedOut Job Report >>>>>>>>")
    create_timedout_jobs_report(collection, database, job_client)
    logger.info("<<<<< Finished Creating TimedOut Job Report")

    if execute_flows2fim:
        logger.info("Starting run_flows2fim step >>>>>>")
        run_flows2fim(collection)
        logger.info("<<<<< Finished run_flows2fim step")

        logger.info("Running copy_qc_map step >>>>>")
        copy_qc_map(collection)
        logger.info("<<<<< Finished copy_qc_map step")


def run_pipeline(collection: str):
    """Automate execution of all pipeline steps with conditional QC"""
    execute_flows2fim = False

    try:
        setup(collection)
        process(collection)
        execute_flows2fim = True
    except Exception as e:
        logger.error(f"Main workflow failed: {str(e)}")
        raise e

    finally:
        try:
            run_qc(collection, execute_flows2fim)
        except Exception as qc_error:
            logger.exception(f"QC failed: {str(qc_error)}")


if __name__ == "__main__":
    """
    Sample Usage:
        python ripple_pipeline.py -c ble_12100302_Medina
    """

    parser = argparse.ArgumentParser(description="Run ripple pipeline steps on one collection")

    parser.add_argument(
        "-c",
        "--collection",
        help="A valid collection of HEC-RAS models. The collection will initially be pulled "
        "locally from the provided STAC URL (in config.py). ",
        required=True,
    )
    parser.add_argument(
        "--log-level",
        default=None,
        help="Logging level: DEBUG, INFO, WARNING, ERROR. Overrides RP_LOG_LEVEL env var. Default INFO.",
    )
    parser.add_argument(
        "--third-party-log-level",
        default=None,
        help="Logging level for third-party libraries, i.e. everything not listed under "
        "logging.FIRST_PARTY in config.yaml. Overrides RP_THIRD_PARTY_LOG_LEVEL env var. Default WARNING.",
    )
    args = vars(parser.parse_args())

    configure_logging(args.pop("log_level"), args.pop("third_party_log_level"))

    run_pipeline(**args)
