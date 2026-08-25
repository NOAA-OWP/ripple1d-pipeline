import json
import logging
import os
from typing import Dict, List, Optional, Type

from ..setup.database import Database
from .model import Model


def load_json(file_path: str) -> Dict:
    """
    Loads JSON data from a given file path.
    """
    with open(file_path, "r") as file:
        data = json.load(file)
    return data

def get_ras_length(reach: Optional[dict]) -> float:
    """Safely extracts ras length from reach data as some time objects can be missing or have None values."""
    metrics =  reach.get("metrics", None)
    if metrics:
        lengths = metrics.get("lengths", None)
        if lengths:
            ras = lengths.get("ras", None)
            if ras:
                return ras

    return 0

def load_conflation(models: List[Model], database: Type[Database]) -> None:
    """
    Loads conflation data into the processing table from the specified model keys and source models directory.
    """
    source_models_directory = database.source_models_dir
    models_data = {}

    for model in models:
        file_path = f"{source_models_directory}\\{model.id}\\{model.name}.conflation.json"
        if os.path.exists(file_path):
            json_data = load_json(f"{source_models_directory}\\{model.id}\\{model.name}.conflation.json")
            models_data[model.id] = json_data
        else:
            logging.info(f"Does not exist {file_path}")

    # Order by number of reaches (ascending) and total RAS length (ascending to place higher lengths last)
    sorted_models_data = sorted(
        models_data.items(),
        key=lambda item: (
            len(item[1]["reaches"]),
            sum(get_ras_length(reach) for reach in item[1]["reaches"].values())
        )
    )

    for model_id, json_data in sorted_models_data:
        database.update_model_id_and_eclipsed(json_data, model_id)

    logging.info(f"Conflation loaded to {database.db_path} from .conflation.json files")
