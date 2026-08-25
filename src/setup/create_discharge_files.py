"""Not used in ripple_pipeline.py or notebooks"""

import logging

import duckdb


def create_discharge_files(parquet_file, output_csv_dir):
    discharge_columns = ["f2year", "f5year", "f10year", "f25year", "f50year", "f100year"]

    con = duckdb.connect()
    con.execute(f"CREATE TABLE data AS SELECT * FROM read_parquet('{parquet_file}')")

    for col in discharge_columns:
        output_csv = f"{output_csv_dir}/{col.replace('f', 'flows_')}.csv"
        query = f"""
            COPY (SELECT id AS nwm_feature_id, {col} AS discharge FROM data)
            TO '{output_csv}' (FORMAT CSV, HEADER TRUE);
        """
        con.execute(query)
        logging.info(f"Created {output_csv}")

    con.close()
    logging.info("All discharge files have been created.")


if __name__ == "__main__":
    nwm_flowlines = "data/nwm_flowlines.parquet"  # Update this as necessary
    output_csv_dir = "data/scenarios"  # Update this as necessary
    create_discharge_files(nwm_flowlines, output_csv_dir)
