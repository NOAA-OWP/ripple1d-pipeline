def create_f2f_start_file(reach_ids, filename):
    """
    Writes a list of reach IDs to a CSV file, each followed by ,"nd".

    Parameters:
    reach_ids (list): A list of reach ID integers or strings.
    filename (str): The name of the CSV file to write to.
    """
    with open(filename, "w") as csvfile:
        for rid in reach_ids:
            csvfile.write(f"{rid},nd\n")
