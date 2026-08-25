import logging
from typing import Type

from ..setup.database import Database


def update_network(database: Type[Database]) -> None:
    """
    Build the modified network by updating updated_to_id based on valid and eclipsed reaches.
    """
    valid_reaches = database.get_valid_reaches()
    eclipsed_reaches = database.get_eclipsed_reaches()

    valid_reaches_dict = {reach_id: nwm_to_id for reach_id, nwm_to_id in valid_reaches}
    eclipsed_reaches_dict = {reach_id: nwm_to_id for reach_id, nwm_to_id in eclipsed_reaches}

    updates = []
    for reach_id, nwm_to_id in valid_reaches:
        current_reach_id = nwm_to_id
        while current_reach_id:
            if current_reach_id in valid_reaches_dict:
                # Found a valid reach, prepare the update for updated_to_id and break the loop
                updates.append((current_reach_id, reach_id))
                break
            elif current_reach_id in eclipsed_reaches_dict:
                # Current reach is an eclipsed reach, continue to follow the nwm_to_id
                current_reach_id = eclipsed_reaches_dict[current_reach_id]
            else:
                # Reach is not in valid_reaches_dict or eclipsed_reaches_dict, break the loop
                break

    if updates:
        # Execute batch updates
        database.update_to_id_batch(updates)
        logging.info(f"Updated {len(updates)} reaches successfully.")
    else:
        logging.info("No updates to process.")
