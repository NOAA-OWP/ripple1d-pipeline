FROM python:3.11-slim

# Install Python dependencies
RUN pip install geopandas==1.0.1
RUN pip install duckdb==1.2.2
RUN pip install awscli==1.40.18
RUN pip install pyarrow==20.0.0

WORKDIR /app

COPY main.py .
ENTRYPOINT [ "python", "main.py" ]