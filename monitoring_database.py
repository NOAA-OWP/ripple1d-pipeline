import logging
import sqlite3
from datetime import datetime


class MonitoringDatabase:
    """
    Monitoring database class to monitor collection processing at scale.
    """

    def __init__(self, ip_address: str, maintainer: str, db_path: str, ripple1d_version: str, timeout=60) -> None:
        self.ripple1d_version = ripple1d_version
        self.db_path = db_path
        self.ip_address = ip_address
        self.maintainer = maintainer
        self.timeout = timeout

    def create_tables(self) -> None:
        """
        Initialize database and create tables
        """

        current_time = datetime.now()

        connection = sqlite3.connect(self.db_path, timeout=self.timeout)

        try:
            cursor = connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")

            # Create metadata table to store metadata
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    ripple1d_version TEXT,
                    start_time TIMESTAMP
                );
            """
            )

            cursor.execute(
                f"""
                INSERT INTO metadata
                VALUES (?, ?);
                """,
                (self.ripple1d_version, current_time),
            )

            # Create monitoring table to aggregate collection and machine level statuses
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS instances (
                    ip_address TEXT,
                    maintainer TEXT,
                    status_update_time TIMESTAMP,
                    current_collection_id TEXT,
                    last_collection_status TEXT,
                    total_collections_processed INTEGER,
                    total_successful_collections INTEGER,
                    total_collections_submitted INTEGER,
                    PRIMARY KEY (ip_address)
                );
            """
            )
            # Create error table to store error messages
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS collections (
                    ip_address TEXT,
                    collection_id TEXT,
                    collection_start_time TIMESTAMP,
                    collection_finish_time TIMESTAMP,
                    collection_status TEXT,
                    error_message TEXT,
                    PRIMARY KEY (ip_address, collection_id),
                    FOREIGN KEY (ip_address) REFERENCES instances(ip_address)
                );
                """
            )

            connection.commit()
            logging.info(f"Database initialized successfully at {self.db_path}")
        except Exception as e:
            logging.info(e)
            connection.rollback()
        finally:
            connection.close()

    def update_instances_table(
        self,
        status_update_time,
        current_collection_id,
        last_collection_status,
        total_collections_processed,
        total_successful_collections,
        total_collections_submitted,
    ) -> None:
        """
        Enter record to instances table in monitoring database.
        """

        conn = sqlite3.connect(self.db_path, timeout=self.timeout)

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO instances (
                    ip_address,
                    maintainer,
                    status_update_time,
                    current_collection_id,
                    last_collection_status,
                    total_collections_processed,
                    total_successful_collections,
                    total_collections_submitted
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.ip_address,
                    self.maintainer,
                    status_update_time,
                    current_collection_id,
                    last_collection_status,
                    total_collections_processed,
                    total_successful_collections,
                    total_collections_submitted,
                ),
            )
            conn.commit()
            logging.info(f"Instances Table record inserted in {self.db_path}")

        finally:
            conn.close()

    def update_collections_table(
        self,
        collection_id,
        collection_start_time,
        collection_finish_time,
        collection_status,
        error_message,
    ) -> None:
        """
        Enter record to collections table in monitoring database.
        """

        conn = sqlite3.connect(self.db_path, timeout=self.timeout)

        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO collections (
                    ip_address,
                    collection_id,
                    collection_start_time,
                    collection_finish_time,
                    collection_status,
                    error_message
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    self.ip_address,
                    collection_id,
                    collection_start_time,
                    collection_finish_time,
                    collection_status,
                    error_message,
                ),
            )
            conn.commit()
            logging.info(f"Collections Table record inserted in {self.db_path}")
        finally:
            conn.close()
