### Design Notes
1. We are taking upstream XS because it is least affected by constant Normal slope being used, also it is always on the reach per Ripple design
1. Doing one by one because the code is simpler and crs can be different
1. If we encounter multiple points we are taking first point for simplicity
1. There is not enough information to find out datum
1. Using output in parquet format for better analytics and querying
1. GPKGs if working with data on cloud have severe performance issues, hence downloading them locally
1. These are only us rc points for upstream, we can dig into HEC ras results or do raster querying to generate more points
1. `main_duckdb.py` is slower than `main.py` using GPD hence using geopandas approach.

### Instructions
1. Build image and push to a cloud registry
1. Register Job with Nomad
1. Submit jobs to Nomad
1. Once all parquet files are created for HUC, if needed, merge them into one GPKG layer using QGIS.
1. Once merged, points can enriched with HUC12 attribute by spatial joining against HUC12 Feature Service in QGIS.
1. Then use gdal to convert GPKG to Parquet.
