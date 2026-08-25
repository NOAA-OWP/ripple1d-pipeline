import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Dict, List, Tuple, Type

from .collection_data import CollectionData


class Database:
    """
    Main database class to hold all Database methods (SQL Queries).
    """

    def __init__(self, collection: Type[CollectionData]):
        self.db_path = collection.db_path
        self.stac_collection_id = collection.stac_collection_id  # Not used currently
        self.source_models_dir = collection.source_models_dir  # Not used currently
        self.timeout = collection.config["database"]["DB_CONN_TIMEOUT"]
        self.submodels_dir = collection.submodels_dir

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _get_connection_non_central_db(self, db):
        conn = sqlite3.connect(db, timeout=self.timeout)
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _get_locked_connection(self, lock, db_path=None):
        # self.lock = lock
        if db_path is None:
            conn = sqlite3.connect(self.db_path, timeout=self.timeout)
        else:
            conn = sqlite3.connect(db_path)
        try:
            with lock:
                yield conn
        finally:
            conn.close()

    # Execute SQL operation: SELECT
    def execute_select_query(self, query: str, params: tuple = None, lock=None):
        if lock is None:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if params is None:
                    cursor.execute(query)
                else:
                    cursor.execute(query, params)
                result = cursor.fetchall()
                return result
        else:
            with self._get_locked_connection(lock) as conn:
                cursor = conn.cursor()
                if params is None:
                    cursor.execute(query)
                else:
                    cursor.execute(query, params)
                result = cursor.fetchall()
                return result

    # Execute SQL operation: SELECT one
    def execute_fetchone_query(
        self,
        query: str,
        params: tuple = None,
        lock: threading.Lock = None,
        db_path: str = None,
    ):
        if db_path is None:
            with self._get_locked_connection(lock) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result
        else:
            with self._get_locked_connection(lock, db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                result = cursor.fetchone()
                return result

    # Execute SQL operations: INSERT, UPDATE, DELETE
    def execute_dml_query(self, query: str, params: tuple = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()

    # Execute SQL operations: INSERT, UPDATE, DELETE
    def executemany_dml_query(self, query: str, params: tuple = None):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.executemany(query, params)
            conn.commit()

    @staticmethod
    def init_db(collection: Type[CollectionData]) -> None:
        """
        Initialize database and create tables
        """
        DB_CONN_TIMEOUT = collection.config["database"]["DB_CONN_TIMEOUT"]
        db_path = collection.db_path
        RIPPLE1D_VERSION = collection.config["RIPPLE1D_VERSION"]
        US_DEPTH_INCREMENT = collection.config["ripple_settings"]["US_DEPTH_INCREMENT"]
        DS_DEPTH_INCREMENT = collection.config["ripple_settings"]["DS_DEPTH_INCREMENT"]

        connection = sqlite3.connect(db_path, timeout=DB_CONN_TIMEOUT)
        try:
            cursor = connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")

            # Create metadata table to store metadata
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    ripple1d_version TEXT,
                    us_depth_increment REAL,
                    ds_depth_increment REAL
                );
            """
            )

            cursor.execute(
                f"""
                INSERT INTO metadata
                VALUES (?, ?, ?);
                """,
                (RIPPLE1D_VERSION, US_DEPTH_INCREMENT, DS_DEPTH_INCREMENT),
            )

            # Create models table to store model-level information
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS models (
                    collection_id TEXT,
                    model_id TEXT,
                    model_name TEXT,
                    conflate_model_job_id TEXT,
                    conflate_model_status TEXT,
                    PRIMARY KEY (collection_id, model_id)
                );
            """
            )

            # Create network table to store network relationships
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS network (
                    reach_id INTEGER PRIMARY KEY,
                    nwm_to_id INTEGER,
                    updated_to_id INTEGER,
                    FOREIGN KEY (reach_id) REFERENCES reaches (reach_id)
                );
                """
            )

            cursor.execute(
                """
                INSERT INTO network (reach_id, nwm_to_id)
                SELECT reach_id, nwm_to_id FROM reaches;
                """
            )

            # Indexes will speed up 'where downstream = ?' queries
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS network_nwm_to_id_idx ON network (nwm_to_id);
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS network_updated_to_id_idx ON network (updated_to_id);
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rating_curves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reach_id INTEGER,
                    us_flow INTEGER,
                    us_depth REAL,
                    us_wse REAL,
                    ds_depth REAL,
                    ds_wse REAL,
                    boundary_condition TEXT CHECK(boundary_condition IN ('nd','kwse')) NOT NULL,
                    FOREIGN KEY (reach_id) REFERENCES reaches (reach_id),
                    UNIQUE(reach_id, us_flow, ds_wse, boundary_condition)
                );
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rating_curves_no_map (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    reach_id INTEGER,
                    us_flow INTEGER,
                    us_depth REAL,
                    us_wse REAL,
                    ds_depth REAL,
                    ds_wse REAL,
                    boundary_condition TEXT CHECK(boundary_condition IN ('nd','kwse')) NOT NULL,
                    xs_overtopped BOOL CHECK(xs_overtopped IN (0, 1)),
                    FOREIGN KEY (reach_id) REFERENCES reaches (reach_id),
                    UNIQUE(reach_id, us_flow, ds_wse, boundary_condition)
                );
            """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS rating_curves_metrics (
                    rc_id INTEGER PRIMARY KEY,
                    xs_overtopped BOOL CHECK(xs_overtopped IN (0, 1)),
                    FOREIGN KEY (rc_id) REFERENCES rating_curves (id)
                );
            """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS rating_curves_reach_id ON rating_curves (reach_id);
            """
            )

            # Create processing table to store reach-specific processing information
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS processing (
                    reach_id INTEGER PRIMARY KEY,
                    collection_id TEXT,
                    model_id TEXT,
                    eclipsed BOOL CHECK(eclipsed IN (0, 1)),
                    extract_submodel_job_id TEXT,
                    extract_submodel_status TEXT,
                    create_ras_terrain_job_id TEXT,
                    create_ras_terrain_status TEXT,
                    create_model_run_normal_depth_job_id TEXT,
                    create_model_run_normal_depth_status TEXT,
                    run_incremental_normal_depth_job_id TEXT,
                    run_incremental_normal_depth_status TEXT,
                    nd_create_rating_curves_db_job_id TEXT,
                    nd_create_rating_curves_db_status TEXT,
                    run_iknown_wse_job_id TEXT,
                    run_iknown_wse_status TEXT,
                    ikwse_create_rating_curves_db_job_id TEXT,
                    ikwse_create_rating_curves_db_status TEXT,
                    run_known_wse_job_id TEXT,
                    run_known_wse_status TEXT,
                    kwse_create_rating_curves_db_job_id TEXT,
                    kwse_create_rating_curves_db_status TEXT,
                    create_fim_lib_job_id TEXT,
                    create_fim_lib_status TEXT,
                    FOREIGN KEY (collection_id, model_id) REFERENCES models (collection_id, model_id),
                    FOREIGN KEY (reach_id) REFERENCES reaches (reach_id)
                );
            """
            )

            cursor.execute(
                """
                INSERT INTO processing (reach_id)
                SELECT reach_id FROM network;
                """
            )

            # # Create metrics table to store reach-specific metrics
            # cursor.execute(
            #     """
            #     CREATE TABLE IF NOT EXISTS metrics (
            #         reach_id INTEGER PRIMARY KEY,
            #         xs_centerline_offset_mean INTEGER,
            #         xs_thalweg_offset_mean INTEGER,
            #         xs_centerline_offset_max INTEGER,
            #         xs_thalweg_offset_max INTEGER,
            #         coverage_start REAL,
            #         coverage_end REAL,
            #         network_to_ras_ratio REAL,
            #         FOREIGN KEY (reach_id) REFERENCES reaches (reach_id)
            #     );
            # """
            # )

            connection.commit()
            logging.info(f"Database initialized successfully at {db_path}")
        except Exception as e:
            logging.info(e)
            connection.rollback()
        finally:
            connection.close()

    @staticmethod
    def insert_models(models_data: Dict, collection: Type[CollectionData]) -> None:
        """ """
        collection_id = collection.stac_collection_id
        db_path = collection.db_path
        DB_CONN_TIMEOUT = collection.config["database"]["DB_CONN_TIMEOUT"]

        rows = [(collection_id, id, model_data["model_name"]) for id, model_data in models_data.items()]
        conn = sqlite3.connect(db_path, timeout=DB_CONN_TIMEOUT)
        try:
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT OR IGNORE INTO models (collection_id, model_id, model_name)
                VALUES (?, ?, ?)
                """,
                rows,
            )
            conn.commit()
            logging.info(f"Models record inserted at {db_path}")
        finally:
            conn.close()

    def update_models_table(self, model_job_ids, process_name: str, job_status: str) -> None:
        update_query = f"""
                UPDATE models
                SET {process_name}_job_id = ?, {process_name}_status = '{job_status}'
                WHERE model_id = ?;
                """
        params = [(model_job_id[1], model_job_id[0]) for model_job_id in model_job_ids]

        self.executemany_dml_query(update_query, params)

    def update_processing_table(self, reach_job_ids: List[Tuple[int, str]], process_name: str, job_status: str) -> None:
        """
        Updates the processing table with job_id and job_status for a given process.
        """
        update_query = f"""
                UPDATE processing
                SET {process_name}_job_id = ?, {process_name}_status = '{job_status}'
                WHERE reach_id = ?;
                """
        params = [(reach_job_id[1], reach_job_id[0]) for reach_job_id in reach_job_ids]

        self.executemany_dml_query(update_query, params)

    def update_model_id_and_eclipsed(self, data: Dict, model_id: str) -> None:
        """
        Updates the model_id and eclipsed status in the processing table
        based on upstream and downstream reach conflation data.
        """
        update_query = f"""
                UPDATE processing
                SET model_id = ?, eclipsed = ?
                WHERE reach_id = ?;
                """

        for key, value in data["reaches"].items():
            eclipsed = value["eclipsed"] == True
            self.execute_dml_query(update_query, (model_id, eclipsed, key))

    def get_valid_reaches(self) -> List[Tuple[int, int]]:
        """
        Get reaches that are not eclipsed by joining the network and processing tables.
        """
        select_query = f"""
                SELECT n.reach_id, n.nwm_to_id
                FROM network n
                JOIN processing p ON n.reach_id = p.reach_id
                WHERE p.eclipsed IS FALSE
                """
        return self.execute_select_query(select_query)

    def get_eclipsed_reaches(self) -> List[Tuple[int, int]]:
        """
        Get reaches that are eclipsed by joining the network and processing tables.
        """
        select_query = f"""
                SELECT n.reach_id, n.nwm_to_id
                FROM network n
                JOIN processing p ON n.reach_id = p.reach_id
                WHERE p.eclipsed IS TRUE
                """
        return self.execute_select_query(select_query)

    def update_to_id_batch(self, updates: List[Tuple[int, int]]) -> None:
        """
        Batch update the updated_to_id for multiple reaches.
        """
        update_query = f"""
                UPDATE network
                SET updated_to_id = ?
                WHERE reach_id = ?
                """
        self.executemany_dml_query(update_query, updates)

    def get_reaches_by_models(self, model_ids: List[str]) -> List[Tuple[int, int, str]]:
        """
        Retrieves reach IDs, updated_to_ids, and model keys from the network and processing tables
        where the model keys match and the reach is not eclipsed.
        """
        select_query = f"""
                SELECT n.reach_id, n.updated_to_id, p.model_id, m.model_name
                FROM network n
                JOIN processing p ON n.reach_id = p.reach_id
                JOIN models m ON p.model_id = m.model_id
                WHERE p.eclipsed IS FALSE AND p.model_id IN ({','.join(['?'] * len(model_ids))})
            """
        return self.execute_select_query(select_query, model_ids)

    def get_upstream_reaches(self, updated_to_id: int, db_lock: threading.Lock) -> List[int]:
        """
        Fetch upstream reach IDs from the 'network' table.
        """
        select_query = f"""
                SELECT reach_id
                FROM network
                WHERE updated_to_id = ?
                """
        temp_result = self.execute_select_query(select_query, (updated_to_id,), lock=db_lock)
        result = [row[0] for row in temp_result]
        return result

    def check_fim_lib_created(self, reach_id: int, db_lock: threading.Lock) -> bool:
        """
        Check if FIM library has been created for a reach.
        """
        select_query = f"""
                SELECT create_fim_lib_job_id
                FROM processing
                WHERE reach_id = ?
                """
        result = self.execute_fetchone_query(select_query, (reach_id,), lock=db_lock)

        if result is None:
            raise ValueError(f"No record found for reach_id {reach_id}")

        return result[0] is not None

    def execute_query_fetch_min_max(
        self,
        query: str,
        params: tuple = None,
        lock: threading.Lock = None,
    ):
        with self._get_locked_connection(lock) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            min, max = cursor.fetchone()
            return min, max

    def get_all_job_ids_for_process(
        self, process_name: str, process_table: str = "processing"
    ) -> List[Tuple[int, str]]:
        """
        Retrieves all job IDs for the specified process from the processing table.

        Args:
            db_path: Path to the SQLite database.
            process_name: The name of the process (e.g., "create_fim_lib").

        Returns:
            List of tuples containing reach_id and job_id for the specified process.
        """

        select_query = f"""
                SELECT {"reach_id" if process_table == "processing" else "model_id"}, {process_name}_job_id
                FROM {process_table}
                WHERE {process_name}_job_id IS NOT NULL
            """
        return self.execute_select_query(select_query)

    def get_entities_by_process_and_status(
        self, process_name: str, status: str, process_table: str = "processing",
    ) -> List[Tuple[int, str, str]]:
        """
        Retrieves entities for a given process and status.

        Returns:
            List of tuples (reach_id, job_id, status)
        """

        query = f"""
            SELECT {"reach_id" if process_table == "processing" else "model_id"}, {process_name}_job_id, {process_name}_status
            FROM {process_table}
            WHERE {process_name}_status = '{status}'
        """
        return self.execute_select_query(query)

    def update_table_with_job_status(self, process_table: str, process_name: str, job_status, entity):

        query = f"""
            UPDATE {process_table}
            SET {process_name}_status = ?
            WHERE {"reach_id" if process_table == "processing" else "model_id"} = ?;
        """
        params = (job_status, entity)
        self.execute_dml_query(query, params)
