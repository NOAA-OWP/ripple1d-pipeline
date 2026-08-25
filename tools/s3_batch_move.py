#!/usr/bin/env python3

import argparse
import os
import pathlib
import subprocess
import logging
import yaml
from pathlib import Path

from datetime import datetime
from ripple_pipeline import *
from src.setup import *


def s3_move(collection: str, failed: bool = False):

    config = load_config("config.yaml")

    COLLECTIONS_ROOT_DIR = config['paths']['COLLECTIONS_ROOT_DIR']
    S3_UPLOAD_PREFIX = config['paths']['S3_UPLOAD_PREFIX']
    S3_UPLOAD_FAILED_PREFIX = config['paths']['S3_UPLOAD_FAILED_PREFIX']
    RIPPLE1D_VERSION = config['RIPPLE1D_VERSION']

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

    subprocess.run(
        s3_mv_command, stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL
    )
    logging.info(f"Submitted S3 mv command on collection: {collection} ...")


def load_config(config_file):
    try:
        with open(str(Path.cwd() / "src" / config_file), 'r') as file:
            config = yaml.safe_load(file)
    except FileNotFoundError:
        raise ValueError(f"File '{config_file}' not found. Ensure config.yaml is in the src directory.")
    except yaml.YAMLError:
        raise ValueError("Invalid YAML configuration")
    
    return config
        
def batch_move(collection_list):
    """
    Iterate over each collection in a list of collections, and execute all Ripple1D setup, processing, and qc steps for each collection.

    Inputs:
        collection_list: A filepath to line separated list of collections.
            OR a string in quotes with space delimeted collections.
    """

    collections = read_input(collection_list)

    for id,collection in enumerate(collections):
        logging.info(f"Starting s3 mv for collection: {collection} ... {id}/{len(collections)}")
        
        # Toggle depending on if submitting failed collections or successful
        s3_move(collection) # Successful
        # s3_move(collection, True) # Failed

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
        python s3_batch_move.py -l "collection1 collection2 collection3"
        python s3_batch_move.py -l ~/collections.lst
    """

    parser = argparse.ArgumentParser(description="Run s3 mv on each collection in the collection list")

    parser.add_argument(
        "-l",
        "--collection_list",
        help=f"A filepath (.txt or .lst) containaing a new line separated list of valid collections or a space separated string of collections",
        required=True,
    )

    args = vars(parser.parse_args())

    batch_move(**args)

