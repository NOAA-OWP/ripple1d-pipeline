#!/usr/bin/env python3

import argparse
import logging
import os
import pathlib
import socket
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import yaml

from monitoring_database import MonitoringDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def load_config(config_file):
    try:
        with open(str(Path.cwd() / "src" / config_file), "r") as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        raise ValueError(f"File '{config_file}' not found. Ensure config.yaml is in the src directory.")
    except yaml.YAMLError:
        raise ValueError("Invalid YAML configuration")

    return config


def s3_move(
    collection: str,
    config: dict,
    failed: bool = False,
):

    COLLECTIONS_ROOT_DIR = config["paths"]["COLLECTIONS_ROOT_DIR"]
    S3_UPLOAD_PREFIX = config["paths"]["S3_UPLOAD_PREFIX"]
    S3_UPLOAD_FAILED_PREFIX = config["paths"]["S3_UPLOAD_FAILED_PREFIX"]
    RIPPLE1D_VERSION = config["RIPPLE1D_VERSION"]

    if failed:
        dateime_obj = datetime.now()
        timestamp = dateime_obj.strftime("%m-%d-%Y_%H_%M")
        s3_mv_command = [
            "aws",
            "s3",
            "mv",
            f"{COLLECTIONS_ROOT_DIR}/{collection}",
            f"{S3_UPLOAD_FAILED_PREFIX}/{collection}_{RIPPLE1D_VERSION}_{timestamp}",
            "--recursive",
        ]
    else:
        s3_mv_command = [
            "aws",
            "s3",
            "mv",
            f"{COLLECTIONS_ROOT_DIR}/{collection}",
            f"{S3_UPLOAD_PREFIX}/{collection}",
            "--recursive",
        ]

    subprocess.Popen(s3_mv_command, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
    logging.info(f"Submitted S3 mv command on collection: {collection} ...")


@contextmanager
def exception_handler(table):
    try:
        yield
    except Exception as e:
        logging.error(f"Monitoring database- {table} TABLE write failed. Error Message: \n\t {e}")


def batch_pipeline(collection_list):
    """
    Iterate over each collection in a list of collections, and execute all Ripple1D setup, processing, and qc steps for each collection.

    Inputs:
        collection_list: A filepath to line separated list of collections.
            OR a string in quotes with space delimeted collections.
    """

    config = load_config("config.yaml")

    COLLECTIONS_ROOT_DIR = config["paths"]["COLLECTIONS_ROOT_DIR"]
    RIPPLE1D_VERSION = config["RIPPLE1D_VERSION"]
    MONITORING_DB_PATH = config["paths"]["MONITORING_DB_PATH"]

    # Get list of collections
    collections = read_input(collection_list)

    # Identify hostname, used to get IP Address
    hostname = f"{socket.gethostname()}"
    ip_address = socket.gethostbyname(hostname)
    username = os.getlogin()

    # Instantiate MonitoringDatabase class
    monitoring_database = MonitoringDatabase(ip_address, username, MONITORING_DB_PATH, RIPPLE1D_VERSION)
    monitoring_database.create_tables()

    # Set default values for monitoring database
    total_collections_submitted = len(collections)
    total_collections_processed = 0
    total_collections_succeeded = 0
    last_collection_status = None

    # Update instances table in monitoring database
    with exception_handler("INSTANCES"):
        monitoring_database.update_instances_table(
            f"{datetime.now()}",
            None,
            last_collection_status,
            total_collections_processed,
            total_collections_succeeded,
            total_collections_submitted,
        )

    for collection in collections:

        logging.info(f"Starting processing for collection: {collection} ...")
        # Construct the command to execute ripple_pipeline.py
        cmd = [
            "python",
            "ripple_pipeline.py",
            "--collection",
            collection,
        ]

        # Set up log files
        log_dir = os.path.join(COLLECTIONS_ROOT_DIR, collection)
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{collection}.log")

        with open(log_file, "a") as f:
            f.write("************************************************************************")
            f.write(f"\n--- Starting processing for collection: {collection} ---\n")
            f.flush()

            # Get timestamp for collection start time
            collection_start_time = datetime.now()

            # Reset collection status before next collection starts processing
            collection_status = None
            error_message = None
            collection_finish_time = None

            try:

                # Get timestamp for collection start time
                collection_start_time = datetime.now()

                # Update instances table in monitoring database before processing
                with exception_handler("INSTANCES"):
                    monitoring_database.update_instances_table(
                        f"{datetime.now()}",
                        collection,
                        last_collection_status,
                        total_collections_processed,
                        total_collections_succeeded,
                        total_collections_submitted,
                    )
                # Update collections table in monitoring database
                with exception_handler("COLLECTIONS"):
                    monitoring_database.update_collections_table(
                        collection,
                        collection_start_time,
                        None,
                        "running",
                        None,
                    )

                # Use subprocess to execute ripple_pipeline.py and send stdout & stderr to log file
                process = subprocess.run(cmd, shell=True, stdout=f, stderr=f)

                # Get timestamp after processing is finished
                collection_finish_time = datetime.now()

                # Increment counter for total collections processed
                total_collections_processed += 1

                if process.returncode != 0:
                    raise subprocess.CalledProcessError(process.returncode, cmd)

                # Logic for successfully processed collections
                logging.info(f"Collection {collection} processed successfully.")
                collection_status = "successful"
                total_collections_succeeded += 1

            except subprocess.CalledProcessError as e:

                logging.error(f"Error processing collection {collection}: {e} ")
                logging.info(f"See {log_file} for more details.")
                collection_status = "failed"
                error_message = str(e)

            except Exception as e:

                logging.error(f"Unexpected error occurred: {e}")
                logging.error(f"Executing run_pipeline on collection: {collection}")
                logging.info(f"See {log_file} for more details.")
                collection_status = "failed"
                error_message = str(e)

            finally:

                # Update collections table in monitoring database
                with exception_handler("COLLECTIONS"):
                    monitoring_database.update_collections_table(
                        collection,
                        collection_start_time,
                        collection_finish_time,
                        collection_status,
                        error_message,
                    )

                # Update instances table in monitoring database
                with exception_handler("INSTANCES"):
                    monitoring_database.update_instances_table(
                        f"{datetime.now()}",
                        None,  # reset current_collection_id
                        collection_status,
                        total_collections_processed,
                        total_collections_succeeded,
                        total_collections_submitted,
                    )

                # Move collection to S3 bucket
                s3_move(
                    collection,
                    config,
                    collection_status == "failed",
                )

                # Set last collection status
                last_collection_status = collection_status


def read_input(collection_list):
    collections = []
    if os.path.isfile(collection_list):
        source_file_extension = pathlib.Path(collection_list).suffix
        acceptable_file_formats = [".lst", ".txt", ".csv"]
        if source_file_extension.lower() not in acceptable_file_formats:
            raise Exception("Incoming file must be in .lst, .txt, or .csv format if submitting a file name and path.")

        with open(collection_list, "r") as collections_file:
            file_lines = collections_file.readlines()
            collections = [strip_newline(fl) for fl in file_lines]

    elif isinstance(collection_list, str):
        collection_list = collection_list.split()
        for collection in collection_list:
            collections.append(collection)

    else:
        raise Exception(
            "collection_list not a valid filepath, or a space seperated list of collections passed within quotes"
        )

    return collections


def strip_newline(collection):
    # Strips single or double quotes
    collection = collection.strip().replace('"', "")
    collection = collection.replace("'", "")
    return collection


if __name__ == "__main__":
    """
    Sample Usage:
        python batch_ripple_pipeline.py -l "collection1 collection2 collection3"
        python batch_ripple_pipeline.py -l ~/collections.lst
    """

    parser = argparse.ArgumentParser(description="Run ripple pipeline on each collection in the collection list")

    parser.add_argument(
        "-l",
        "--collection_list",
        help=f"A filepath (.txt or .lst) containing a new line separated list of valid collections or a space separated string of collections",
        required=True,
    )

    args = vars(parser.parse_args())

    batch_pipeline(**args)
