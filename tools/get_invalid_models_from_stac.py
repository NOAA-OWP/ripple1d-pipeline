#!/usr/bin/env python3

import pystac_client
import logging

"""
    Cerrtain model properties are incompatible with Ripple1d, and this script identifies which
    models meet the given filtering criteria defined in the skip_model function.

    Output file:
        Each line contains an object describing the criteria met in skip_model function following
        a format similar to:
            
            {'title' : <reason skipped>, 'collection_id' : <collection id>, 'model_name' : <model name>}

        eg: {'title' : 'non-steady-flows', 'collection_id' : collection.id, 'model_name' : properties['model_name'] }
"""

logging.basicConfig(
    # level=logging.WARNING,
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

output_file = "invalid_models_out.txt"

def skip_model(collection, properties):
    if not isinstance(properties, object):
        return None

    if 'ras_units' in properties and properties['ras_units'] != 'English':
        logging.warning(f"\n\n****** {collection.id} - {properties['model_name']} has Metric ras_units **********")
        return { 'title' : 'non-English', 'collection_id' : collection.id, 'model_name' : properties['model_name'] }
    
    flows = properties['flows']
    any_flows_start_with_f = any(value.startswith('f') or value.startswith('F') for value in flows.values())
    if any_flows_start_with_f == False:
        if 'model_name' in properties and isinstance(properties['model_name'], str):
            logging.warning(f"\n\n****** {collection.id} - {properties['model_name']} has no steady flow files **********")
            return { 'title' : 'non-steady-flows', 'collection_id' : collection.id, 'model_name' : properties['model_name'] }
        else:
            return { 'title' : 'non-steady-flows', 'collection_id' : collection.id, 'model_name' : None }
    else:
        return None

def write_to_file(omitted_models, filename):

    with open(filename, 'w') as file:
        for item in omitted_models:
            file.write(str(item) + '\n')

def main():
    client = pystac_client.Client.open("https://stac2.dewberryanalytics.com")
    logging.info("made client connection, getting all collections")
    collections = client.get_all_collections()
    
    filtered_models = []
    for ind, collection in enumerate(collections):
        for item in collection.get_items():
            logging.info(f"{collection.id} - Model: {item.id} - Index: {ind}")

            filtered_model = skip_model(collection, item.properties)
            if filtered_model != None:
                if filtered_model not in filtered_models:
                    filtered_models.append(filtered_model)

    logging.info(f'{len(filtered_models)} filtered models written to {output_file}')
    write_to_file(filtered_models, output_file)


if __name__ == '__main__':
    main()