import argparse
import csv
import logging

import requests

NOMAD_ADDRESS = ""
NOMAD_TOKEN = ""
GLCR_TOKEN = ""
BASE_S3_DIR = "fimc-data/ripple/fim_100_domain/collections"

NOMAD_JOB_ID = "create-extent-library"


def dispatch_job(
    job_id,
    collection_name,
):
    """Dispatch a job to the parameterized job template using the Nomad API"""

    api_url = f"{NOMAD_ADDRESS}/v1/job/{job_id}/dispatch"

    # Prepare metadata for the job
    payload = {
        "Meta": {
            "src_library_path": f"/vsis3/{BASE_S3_DIR}/{collection_name}/library",
            "dst_library_path": f"/vsis3/{BASE_S3_DIR}/{collection_name}/library_extent",
            "submodels_path": f"/vsis3/{BASE_S3_DIR}/{collection_name}/submodels",
            "glcr_token": GLCR_TOKEN,
        }
    }

    # Prepare headers
    headers = {"Content-Type": "application/json"}
    if NOMAD_TOKEN:
        headers["X-Nomad-Token"] = NOMAD_TOKEN

    try:
        # Make API request
        response = requests.post(api_url, json=payload, headers=headers)
        response.raise_for_status()  # Raise exception for HTTP errors

        # Log response for debugging
        logging.debug(f"Nomad API response: {response.status_code} - {response.text}")
        logging.info(f"Dispatched job for {collection_name}")

        return response.json().get("DispatchedJobID")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to dispatch job via API: {str(e)}")
        if hasattr(e, "response") and e.response is not None:
            logging.error(f"Response details: {e.response.status_code} - {e.response.text}")
        return ""
    except Exception as e:
        logging.error(f"An unexpected error occurred: {str(e)}")
        return ""


def main():
    """
    Main function to set up logging and traverse through list.
    """
    parser = argparse.ArgumentParser(description="Dispatch jobs to Nomad API")
    parser.add_argument(
        "-cl",
        "--collection_list",
        type=str,
        required=True,
        help="Path to the file containing the list of collection names",
    )
    parser.add_argument(
        "-ll",
        "--log_level",
        type=str,
        default="DEBUG",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level",
    )
    args = parser.parse_args()

    logging.basicConfig(level=getattr(logging, args.log_level), format="%(asctime)s - %(levelname)s - %(message)s")

    # Read collection names from the file
    try:
        with open(args.collection_list, "r") as file:
            collection_list = [line.strip() for line in file if line.strip()]
    except FileNotFoundError:
        logging.error(f"Collection list file not found: {args.collection_list}")
        return
    except Exception as e:
        logging.error(f"An error occurred while reading the collection list: {str(e)}")
        return

    # Prepare CSV file to save results
    output_csv = "dispatch_results.csv"
    with open(output_csv, mode="a", newline="") as csvfile:
        csv_writer = csv.writer(csvfile)
        csv_writer.writerow(["collection_name", "dispatched_job_id"])

        # Loop through collection names and dispatch jobs
        for collection_name in collection_list:
            logging.info(f"Dispatching job for collection: {collection_name}")
            dispatched_job_id = dispatch_job(NOMAD_JOB_ID, collection_name)
            csv_writer.writerow([collection_name, dispatched_job_id])

    logging.info("All jobs dispatched")
    logging.info(f"Dispatch results saved to {output_csv}")


if __name__ == "__main__":
    main()
