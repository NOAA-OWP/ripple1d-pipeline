import logging
import os
import sqlite3

logger = logging.getLogger(__name__)


def get_min_elev_curve(
    reach_id: int,
    submodels_directory: str,
    get_ds_wse: bool = False,
) -> list[list[float]] | None:
    """
    Build the minimum elevation curve for a reach.
    It returns an ordered list of ``[discharge, minimum_wse]`` pairs describing the lowest
    water-surface elevation for the reach at each discharge.

    This curve could be extracted for reach u/s or d/s wsel depending on the value of `get_ds_wse` argument.
    """
    submodel_db_path = os.path.join(submodels_directory, str(reach_id), f"{reach_id}.db")
    if not os.path.exists(submodel_db_path):
        logger.info(f"Submodel database not found for reach_id: {reach_id}")
        return None

    wse_col = "ds_wse" if get_ds_wse else "us_wse"

    conn = sqlite3.connect(submodel_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT us_flow, MIN({wse_col})
            FROM scenarios
            WHERE us_flow IS NOT NULL AND {wse_col} IS NOT NULL
            GROUP BY us_flow
            ORDER BY us_flow
            """
        )
        rows = cursor.fetchall()
    finally:
        conn.close()

    if not rows:
        return None

    return [[flow, wse] for flow, wse in rows]


def get_max_elevation(
    reach_id: int,
    submodels_directory: str,
    get_ds_wse: bool = False,
) -> float | None:
    """
    Fetch the max wsel elevation for a reach.

    This value could be extracted for reach u/s or d/s wsel depending on the value of `get_ds_wse` argument.
    """
    submodel_db_path = os.path.join(submodels_directory, str(reach_id), f"{reach_id}.db")
    if not os.path.exists(submodel_db_path):
        logger.info(f"Submodel database not found for reach_id: {reach_id}")
        return None

    wse_col = "ds_wse" if get_ds_wse else "us_wse"

    conn = sqlite3.connect(submodel_db_path)
    try:
        cursor = conn.cursor()
        cursor.execute(f"SELECT MAX({wse_col}) FROM scenarios")
        (max_elevation,) = cursor.fetchone()
    finally:
        conn.close()

    return max_elevation
