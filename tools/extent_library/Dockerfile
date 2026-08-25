FROM ghcr.io/osgeo/gdal:ubuntu-small-3.9.2

WORKDIR /app

ENV CPL_VSIL_USE_TEMP_FILE_FOR_RANDOM_WRITE=TRUE
ENV GDAL_CACHEMAX=50%
ENV VSI_CACHE=TRUE

COPY main.py .
ENTRYPOINT [ "python", "main.py" ]