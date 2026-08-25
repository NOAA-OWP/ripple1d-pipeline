import os
import shutil
import sqlite3


def delete_reach_data(
    reach_ids,
    library_dir,
    submodels_dir,
    db_location,
    delete_submodels=False,
    delete_library=False,
    delete_rc_records=False,
    reset_network_records=False,
    reset_porcessing_job_records=False,
    # delete_kwse_files=False,
    # delete_nd_files=False,
):
    """Delete data associated with a reach."""
    # Connect to the database
    conn = sqlite3.connect(db_location)
    cursor = conn.cursor()

    # Delete records from the database if option is enabled
    if delete_rc_records:
        placeholders = ", ".join("?" for _ in reach_ids)
        cursor.execute(f"DELETE FROM rating_curves WHERE reach_id IN ({placeholders});", reach_ids)
        conn.commit()

    # Reset conflation_records
    if reset_network_records:
        placeholders = ", ".join("?" for _ in reach_ids)
        cursor.execute(
            f"""
                        UPDATE network
                        SET updated_to_id = NULL
                        WHERE reach_id IN ({placeholders});
                        """,
            reach_ids,
        )
        conn.commit()

    if reset_porcessing_job_records:
        placeholders = ", ".join("?" for _ in reach_ids)
        cursor.execute(
            f"""
                        UPDATE processing
                        SET extract_submodel_job_id = NULL,
                            extract_submodel_status = NULL,
                            create_ras_terrain_job_id = NULL,
                            create_ras_terrain_status = NULL,
                            create_model_run_normal_depth_job_id = NULL,
                            create_model_run_normal_depth_status = NULL,
                            run_incremental_normal_depth_job_id = NULL,
                            run_incremental_normal_depth_status = NULL,
                            run_known_wse_job_id = NULL,
                            run_known_wse_status = NULL,
                            create_fim_lib_job_id = NULL,
                            create_fim_lib_status = NULL
                        WHERE reach_id IN ({placeholders});
                        """,
            reach_ids,
        )
        conn.commit()

    conn.close()

    # Delete folders in submodels_dir if option is enabled
    if delete_submodels:
        for reach_id in reach_ids:
            folder_path = os.path.join(submodels_dir, str(reach_id))
            if os.path.exists(folder_path):
                shutil.rmtree(folder_path)

    # Delete folders in library_dir if option is enabled
    if delete_library:
        for reach_id in reach_ids:
            folder_path = os.path.join(library_dir, str(reach_id))
            if os.path.exists(folder_path):
                shutil.rmtree(folder_path)

    # these will cause problems with HEC-RAS as it keep track of internal files
    # Delete folders plans if option is enabled
    # if delete_kwse_files:
    #     for reach_id in reach_ids:
    #         folder_path = os.path.join(submodels_dir, str(reach_id), str(reach_id) + "_kwse")
    #         if os.path.exists(folder_path):
    #             shutil.rmtree(folder_path)
    #         plan_file = os.path.join(submodels_dir, str(reach_id), str(reach_id) + ".p03")
    #         flow_file = os.path.join(submodels_dir, str(reach_id), str(reach_id) + ".f03")
    #         if os.path.exists(plan_file):
    #             os.remove(plan_file)
    #         if os.path.exists(flow_file):
    #             os.remove(flow_file)

    # # Delete folders plans if option is enabled
    # if delete_nd_files:
    #     for reach_id in reach_ids:
    #         folder_path = os.path.join(submodels_dir, str(reach_id), str(reach_id) + "_nd")
    #         if os.path.exists(folder_path):
    #             shutil.rmtree(folder_path)
    #         plan_file = os.path.join(submodels_dir, str(reach_id), str(reach_id) + ".p02")
    #         flow_file = os.path.join(submodels_dir, str(reach_id), str(reach_id) + ".f02")
    #         if os.path.exists(plan_file):
    #             os.remove(plan_file)
    #         if os.path.exists(flow_file):
    #             os.remove(flow_file)
