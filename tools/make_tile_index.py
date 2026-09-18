import argparse
import os
import tempfile
from multiprocessing import Pool

from osgeo import gdal, ogr

# Enable GDAL exceptions for better error handling
gdal.UseExceptions()


def list_vsi_tifs(path):
    """
    Recursively list TIF files using GDAL's VSI file system handler.
    """
    print(f"Listing files in {path} (this may take a while)...")
    try:
        # ReadDirRecursive returns relative paths from the directory
        files = gdal.ReadDirRecursive(path)
        # Reconstruct full /vsis3/ paths
        full_paths = [os.path.join(path, f) for f in files if f.lower().endswith(".tif")]
        return full_paths
    except Exception as e:
        print(f"Error listing files: {e}")
        return []


def build_tileindex(args):
    """
    Worker function to build a tile index for a chunk of rasters.
    """
    idx, rasters, tmp_dir = args
    out_name = os.path.join(tmp_dir, f"tmp_index_{idx}.gpkg")

    if os.path.exists(out_name):
        print(f"Chunk {idx} already exists, skipping...")
        return out_name

    try:
        # gdal.TileIndex is the Python binding for gdaltindex
        gdal.TileIndex(out_name, rasters)
        return out_name
    except Exception as e:
        print(f"Error processing chunk {idx}: {e}")
        return None


def merge_gpkgs(gpkgs, output_file):
    """
    Merges multiple GPKGs into a single master GPKG.
    """
    print(f"Merging {len(gpkgs)} temporary files into {output_file}...")

    driver = ogr.GetDriverByName("GPKG")
    if os.path.exists(output_file):
        driver.DeleteDataSource(output_file)

    out_ds = driver.CreateDataSource(output_file)
    out_layer = None

    # Iterate through temporary GPKGs
    for gpkg_path in gpkgs:
        if not gpkg_path or not os.path.exists(gpkg_path):
            continue

        ds = ogr.Open(gpkg_path)
        if ds is None:
            continue

        in_layer = ds.GetLayer()

        # If this is the first layer, clone its structure to create the output layer
        if out_layer is None:
            out_layer = out_ds.CopyLayer(in_layer, "index")
        else:
            # For subsequent layers, copy features into the existing output layer
            # Using transactions significantly speeds up SQLite inserts
            out_layer.StartTransaction()
            for feat in in_layer:
                new_feat = ogr.Feature(out_layer.GetLayerDefn())

                # Copy Geometry
                geom = feat.GetGeometryRef()
                if geom:
                    new_feat.SetGeometry(geom.Clone())

                # Copy Attributes
                for i in range(feat.GetFieldCount()):
                    new_feat.SetField(i, feat.GetField(i))

                out_layer.CreateFeature(new_feat)
                new_feat = None
            out_layer.CommitTransaction()

        ds = None  # Close input DS

    out_ds = None  # Close and flush output DS


def main():
    parser = argparse.ArgumentParser(description="Parallel Tile Index Creator for S3 Rasters")

    parser.add_argument("--s3-path", required=True, help="S3 path (e.g., /vsis3/bucket/folder)")
    parser.add_argument("--final-gpkg", required=True, help="Output GeoPackage filename")
    parser.add_argument("--processes", type=int, default=20, help="Number of parallel processes")
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=300,
        help="Number of rasters per temporary GPKG",
    )

    args = parser.parse_args()

    cache_bridge_filename = args.s3_path.replace("/", "_").strip("_") + "_tifs.txt"
    cache_bridge_file = os.path.join(tempfile.gettempdir(), cache_bridge_filename)

    if os.path.exists(cache_bridge_file):
        print(f"Loading TIF list from {cache_bridge_file}...")
        with open(cache_bridge_file) as f:
            tifs = [line.strip() for line in f if line.strip()]
    else:
        tifs = list_vsi_tifs(args.s3_path)
        print(f"Saving TIF list to {cache_bridge_file}...")
        with open(cache_bridge_file, "w") as f:
            f.write("\n".join(tifs))
    print(f"Found {len(tifs)} TIFFs.")

    if len(tifs) == 0:
        print("No TIFFs found. Exiting.")
        return

    chunks = [tifs[i : i + args.chunk_size] for i in range(0, len(tifs), args.chunk_size)]
    print(f"Processing {len(chunks)} chunks with {args.processes} processes...")

    # Prepare arguments for map (idx, chunk_list, temp_dir)
    map_args = [(i, chunk, ".") for i, chunk in enumerate(chunks)]

    with Pool(args.processes) as p:
        tmp_indexes = p.map(build_tileindex, map_args)

    # Filter out any Nones in case of errors
    valid_indexes = [x for x in tmp_indexes if x is not None]

    if valid_indexes:
        merge_gpkgs(valid_indexes, args.final_gpkg)
        print(f"DONE. Output saved to: {args.final_gpkg}")
    else:
        print("No temporary indexes were created. Check errors above.")


if __name__ == "__main__":
    main()
