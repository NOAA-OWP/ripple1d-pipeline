import logging
import os
import sqlite3

from ..setup.database import Database

logger = logging.getLogger(__name__)

# TODO Move functions to ../setup/database.py, delete load_scenario?


def process_reach_db_batch(reach_db_scenarios_batch, library_conn):
    """Process a batch of scenarios to avoid SQL variable limits."""
    cursor = library_conn.cursor()

    # Insert scenarios for this batch
    cursor.executemany(
        """
        INSERT OR IGNORE INTO scenarios (
            reach_id, us_flow, us_depth, us_wse, ds_depth, ds_wse, boundary_condition, map_exists
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [scenario[:8] for scenario in reach_db_scenarios_batch],
    )

    placeholders = ", ".join(["(?, ?, ?, ?)"] * len(reach_db_scenarios_batch))

    cursor.execute(
        f"""
        SELECT reach_id, us_flow, ds_wse, boundary_condition, id
        FROM scenarios
        WHERE (reach_id, us_flow, ds_wse, boundary_condition) IN (
            VALUES {placeholders}
        )
    """,
        [
            param
            for scenario in reach_db_scenarios_batch
            for param in (scenario[0], scenario[1], scenario[5], scenario[6])
        ],
    )

    # Get mapping
    scenario_id_map = {(row[0], row[1], row[2], row[3]): row[4] for row in cursor.fetchall()}

    metrics_data = [
        (scenario_id_map[(scenario[0], scenario[1], scenario[5], scenario[6])], scenario[8])
        for scenario in reach_db_scenarios_batch
        if scenario[8] is not None
    ]

    if metrics_data:
        cursor.executemany(
            """
            INSERT OR REPLACE INTO scenario_metrics
            (scenario_id, xs_overtopped) VALUES (?, ?)
        """,
            metrics_data,
        )


def process_reach_db(reach_db_path: str, library_conn: sqlite3.Connection) -> None:
    """
    Inserts scenarios from reach_db_path into the central library database.
    """
    reach_conn = sqlite3.connect(reach_db_path)
    try:
        reach_cursor = reach_conn.cursor()
        reach_cursor.execute(
            """
            SELECT reach_id, us_flow, us_depth, us_wse, ds_depth, ds_wse, boundary_condition,
                   map_exist, xs_overtopped
            FROM scenarios
            WHERE plan_suffix IN ('nd', 'kwse')
            """
        )
        # map_exist is nullable in the submodel schema and may be stored as '0'/'1'; normalize to 0/1
        reach_db_scenarios = [
            scenario[:7] + (int(scenario[7] or 0), scenario[8]) for scenario in reach_cursor.fetchall()
        ]

        if not reach_db_scenarios:
            return

        # Process in batches to avoid SQL variable limit (999 variables max)
        # Using 4 variables per record, so batch size of 240 gives us 960 variables
        batch_size = 240

        for i in range(0, len(reach_db_scenarios), batch_size):
            batch = reach_db_scenarios[i : i + batch_size]
            process_reach_db_batch(batch, library_conn)

        library_conn.commit()
    finally:
        reach_conn.close()


def load_scenario(db_path, reach_id, sub_db_path, timeout):
    """
    Inserts scenarios from sub_db_path into the central library database if sub_db_path exists.
    """
    conn = sqlite3.connect(db_path, timeout=timeout)
    try:
        if os.path.exists(sub_db_path):
            process_reach_db(sub_db_path, conn)
            try:
                os.remove(sub_db_path)
            except Exception as e:
                logger.exception(f"Could not remove {sub_db_path} Error: {e}")
    finally:
        conn.close()


def load_all_scenarios(database: type[Database]) -> None:
    """
    Loads all scenarios from submodel databases into the central library database.
    """
    db_path = database.db_path
    db_timeout = database.timeout
    submodels_dir = database.submodels_dir

    conn = sqlite3.connect(db_path, timeout=db_timeout)
    try:
        for submodel in os.listdir(submodels_dir):
            sub_db_path = os.path.join(submodels_dir, submodel, f"{submodel}.db")
            if os.path.exists(sub_db_path):
                process_reach_db(sub_db_path, conn)
                try:
                    os.remove(sub_db_path)
                except Exception as e:
                    logger.exception(f"Could not remove {sub_db_path} Error: {e}")

        logger.info("All scenarios loaded into central database")
    finally:
        conn.close()
