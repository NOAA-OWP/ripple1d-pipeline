import logging
import os
import subprocess
from typing import List, Type
from ..setup.collection_data import CollectionData


def setup_gdal_environment(collection: Type[CollectionData]):
    """
    Add GDAL binaries to the system PATH
    """
    GDAL_BINS_PATH = collection.config["flows2fim"]["GDAL_BINS_PATH"]
    GDAL_SCRIPTS_PATH = collection.config["flows2fim"]["GDAL_SCRIPTS_PATH"]

    if GDAL_BINS_PATH:
        # Add GDAL path to the system PATH
        os.environ["PATH"] = GDAL_BINS_PATH + os.pathsep + os.environ["PATH"]

    if GDAL_SCRIPTS_PATH:
        os.environ["PATH"] = GDAL_SCRIPTS_PATH + os.pathsep + os.environ["PATH"]


def run_flows2fim(
    collection: Type[CollectionData],
    output_subfolder: str = "qc",
    start_reaches: List = [],
    fim_format: str = "COG",
) -> None:
    """
    Create control CSVs and FIM outputs for each flow file in the flow_files_dir.

    Args:
        collection (CollectionData object): Contains parameters from config file.
            # output_dir (str): Directory where the output subfolder is located.
            # library_path (str): Path to the library directory.
            # library_db_path (str): Path to the SQLite library database.
            # flow_files_dir (str): Directory containing flow files (CSV format).
            # start_file (str): Name of flows to fim start file.
        output_subfolder (str): Subfolder where outputs will be placed.
        start_reaches (List): List of reaches to start.
        fim_format (str): Output format for FIM files ('GTiff' or 'VRT' or 'COG').
    """
    output_dir = collection.root_dir
    library_path = collection.library_dir
    library_db_path = collection.db_path
    start_file = collection.f2f_start_file
    flow_files_dir = collection.config["flows2fim"]["FLOW_FILES_DIR"]
    FLOWS2FIM_BIN_PATH = collection.config["flows2fim"]["FLOWS2FIM_BIN_PATH"]

    setup_gdal_environment(collection)

    output_subfolder_path = os.path.join(output_dir, output_subfolder)
    if not os.path.exists(output_subfolder_path):
        os.makedirs(output_subfolder_path)

    for flow_file in os.listdir(flow_files_dir):
        if flow_file.endswith(".csv"):
            flow_file_path = os.path.join(flow_files_dir, flow_file)
            basename = os.path.splitext(flow_file)[0]
            control_csv = os.path.join(output_subfolder_path, f"{basename.replace('flows', 'controls')}.csv")
            fim_output = os.path.join(output_subfolder_path, f"{basename.replace('flows', 'fim')}.{"vrt" if fim_format == "VRT" else "tif"}")

            # Generate control CSV
            cmd_controls = [
                FLOWS2FIM_BIN_PATH,
                "controls",
                "-db",
                library_db_path,
                "-f",
                flow_file_path,
                "-o",
                control_csv,
            ]

            if start_file:
                cmd_controls += ["-scsv", start_file]
            elif start_reaches:
                cmd_controls += [
                    "-sids",
                    ",".join([str(reach) for reach in start_reaches]),
                ]
            else:
                raise (ValueError("one of start_file or start_reaches must be provided"))

            subprocess.run(cmd_controls, shell=True, check=True)

            # Generate FIM output
            cmd_fim = [
                FLOWS2FIM_BIN_PATH,
                "fim",
                "-lib",
                library_path,
                "-c",
                control_csv,
                "-o",
                fim_output,
                "-fmt",
                fim_format,
            ]
            subprocess.run(cmd_fim, shell=True, check=True)

            logging.info(f"{basename} have been processed.")


if __name__ == "__main__":

    collection_name = ""
    collection = CollectionData(collection_name)
    run_flows2fim(collection)
