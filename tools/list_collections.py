import csv
from dataclasses import dataclass

import pystac_client


@dataclass
class Collection:
    id: str
    models_1d: int
    miles_1d: int


def list_collections(stac_endpoint):
    """
    Lists all available collections at a given STAC endpoint and writes them to CSV files.

    Parameters:
    - stac_endpoint (str): The STAC API endpoint.

    Returns:
    - None (writes collections to CSV files)
    """
    try:
        client = pystac_client.Client.open(stac_endpoint)
        collections = client.get_collections()

        ble_collections = []
        mip_collections = []
        for c in collections:
            if c.id.startswith("ble"):

                ble_collections.append(
                    Collection(
                        c.id,
                        c.summaries.to_dict()["coverage"]["HEC-RAS_models_w_1D"],
                        c.summaries.to_dict()["coverage"]["1D_HEC-RAS_river_miles"],
                    )
                )
            if c.id.startswith("mip"):
                mip_collections.append(
                    Collection(
                        c.id,
                        c.summaries.to_dict()["coverage"]["HEC-RAS_models_w_1D"],
                        c.summaries.to_dict()["coverage"]["1D_HEC-RAS_river_miles"],
                    )
                )

        # Write BLE collections to CSV
        with open("ble_collections.csv", "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["id", "models_1d", "miles_1d"])
            for collection in ble_collections:
                writer.writerow([collection.id, collection.models_1d, collection.miles_1d])

        # Write MIP collections to CSV
        with open("mip_collections.csv", "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["id", "models_1d", "miles_1d"])
            for collection in mip_collections:
                writer.writerow([collection.id, collection.models_1d, collection.miles_1d])

        print(f"Wrote BLE collections to ble_collections.csv")
        print(f"Wrote MIP collections to mip_collections.csv")

    except Exception as e:
        print(f"Error fetching collections: {e}")


if __name__ == "__main__":
    stac_endpoint = "https://stac2.dewberryanalytics.com"
    list_collections(stac_endpoint)
