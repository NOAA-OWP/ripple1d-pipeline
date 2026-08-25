import logging
import os

import pandas as pd

from ..setup.collection_data import CollectionData


def write_df_to_excel(df: pd.DataFrame, process_name: str, file_path: str) -> None:
    """
    Writes the DataFrame to an Excel file at the specified file path with the given process name as the sheet name.
    If the file or sheet already exists, it will add a new sheet or overwrite the existing one.

    Args:
        df: A pandas DataFrame containing the reach_id, error (err), and traceback (tb).
        process_name: The name of the process to be used as the sheet name in the Excel file.
        file_path: The path to the Excel file where the data will be saved.

    Returns:
        None
    """

    if os.path.exists(file_path):
        # Load the existing workbook
        with pd.ExcelWriter(file_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            # Write the DataFrame to the specified sheet
            df.to_excel(writer, sheet_name=process_name, index=False)
    else:
        # Create a new Excel file and write the DataFrame to the specified sheet
        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name=process_name, index=False)

    logging.info(f"Data written to {file_path} in sheet {process_name}.")


def create_failed_jobs_report(collection: CollectionData, database, job_client) -> None:
    for step_name in collection.config["processing_steps"].keys():
            domain = collection.config["processing_steps"][step_name]["domain"]
            # Lets not capture the final status to preserve the timedout status jobs
            # job_client.poll_and_update_job_status(database, step_name, "models" if domain == "model" else "processing")
            failed_entities = database.get_entities_by_process_and_status(
                step_name, "failed", "models" if domain == "model" else "processing"
            )
            df = job_client.get_failed_jobs_df(failed_entities)
            write_df_to_excel(df, step_name, collection.failed_jobs_report_path)

def create_timedout_jobs_report(collection: CollectionData, database, job_client) -> None:
    for step_name in collection.config["processing_steps"].keys():
            domain = collection.config["processing_steps"][step_name]["domain"]
            timedout_entities = database.get_entities_by_process_and_status(
                step_name, "unknown", "models" if domain == "model" else "processing"
            )
            df = job_client.get_jobs_metadata_df(timedout_entities)
            write_df_to_excel(df, step_name, collection.timedout_jobs_report_path)
