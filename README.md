# Ripple1D Pipeline

Ripple1D Pipeline is a workflow that utilizes the [Ripple1d](https://github.com/NGWPC/ripple1d) to generate FIMs for difference scenarios.

Compatible with [ripple1d v0.11.0](https://github.com/NGWPC/ripple1d/releases/tag/v0.11.0). Use repository tags to get older versions.

For *why* the project is designed the way it is, see [design_guide.md](design_guide.md).

## Contents

- [`ripple1d_pipeline/`](ripple1d_pipeline) -  the pipeline package
    - [setup](ripple1d_pipeline/setup) -  initialization / pre-processing
    - [process](ripple1d_pipeline/process) -  Ripple1d API calls / processing
    - [qc](ripple1d_pipeline/qc) -  quality control / post-processing
- [`entrypoints/`](entrypoints) -  scripts that run the pipeline
- [`notebooks/`](notebooks) -  notebooks that run the pipeline, step by step
- [`tools/`](tools) -  independent tools, not used by the pipeline
- [`pixi-scripts/`](pixi-scripts) -  environment provisioning invoked by pixi

## Dependencies

pixi manages Python, GDAL, and flows2fim. The rest must be installed separately:

- Windows environment with Desktop Experience (GUI, not headless Windows, not non logged in sessions)
- [pixi](https://pixi.sh)
- HEC-RAS (v6.3.1)
- [Ripple1d](https://github.com/NGWPC/ripple1d) server (runs in its own environment)
- AWS credentials (access key id and secret access key) for pulling models from STAC
- Reference data (DEM, NWM flowlines, flow files) on disk

## Getting Started

Run all steps from the Windows Command Prompt (`cmd`), not PowerShell.

### 1. Install pixi

```cmd
powershell -ExecutionPolicy ByPass -c "irm -useb https://pixi.sh/install.ps1 | iex"
```

Reopen the terminal afterwards so `pixi` is on your PATH.

### 2. Clone the repo

```cmd
git clone https://github.com/NGWPC/ripple1d-pipeline.git
cd ripple1d-pipeline
```

### 3. Create the environment

```cmd
pixi install
```

This installs Python, all Python dependencies, and the GDAL command-line tools into a project-local environment, and registers the `ripple1d_pipeline` package into it. There is no virtual environment to create or activate separately, `pixi run <command>` activates it automatically.

### 4. Configure (see [Configuration](#configuration) below as well)

Copy `example.env` to `.env` and fill in the values for your machine.

### 5. Pull reference data

```cmd
mkdir C:\reference_data\flow_files
aws s3 sync s3://fimc-data/reference/nwm_return_period_flows C:\reference_data\flow_files
```

The DEM and NWM flowline paths are also set in `.env`.

### 6. Install HEC-RAS

1. Download the [HEC-RAS v631 Setup executable](https://github.com/HydrologicEngineeringCenter/hec-downloads/releases/download/1.0.26/HEC-RAS_631_Setup.exe)
2. Follow the install instructions, all default.
3. Open HEC-RAS once to accept the Terms and Conditions.

### 7. Set up and start the Ripple1D server

The Ripple1d server runs in its **own** environment (it is not managed by this project's pixi environment) and must run on a Windows machine with HEC-RAS installed.

```cmd
mkdir C:\venvs
cd /d C:\venvs
python -m venv ripple1d
cd ripple1d
Scripts\activate.bat
pip install git+https://github.com/NGWPC/ripple1d.git@v0.11.0
ripple1d start --thread_count <number less than total available CPUs>
```

If the last command is successful, two new terminal windows will appear (Huey consumer and Flask api), which can be minimized.

## **Configuration**

### 1. Environment file (`.env`) - required machine/environment specific settings

Copy `example.env` to `.env` and fill in the values for your machine:

`.env` holds everything that varies per environment, as `RP_*` variables.

### 2. Behavior config

The source code has `/ripple1d_pipeline/default_config.yaml` file that has all defaults configs that alter behavior of pipeline.

To change a behavior value **just for your machine** copy `config.example.yaml` to `config.yaml` at the repo root and uncomment the keys you want to override. These settings are deep-merged over the defaults.

## Running the pipeline

Everything runs through `pixi run`, which activates the environment before running any command. No activation step is needed separately.

**A single collection:**

```cmd
pixi run python entrypoints/run_collection.py -c mip_02020008
```

**A list of collections** (serially, plus pushing results to S3):

```cmd
pixi run python entrypoints/run_batch.py -l "C:\collection_lists\test_collections.lst"
```

Both accept `--log-level` (and `--third-party-log-level`); these can also be set via `RP_LOG_LEVEL` and `RP_THIRD_PARTY_LOG_LEVEL` in `.env`.

## Using Jupyter Notebooks

The notebooks in [`notebooks/`](notebooks) do the same work as `run_collection.py`, but provide more user control.

1. Open the repo in VSCode and open `notebooks/setup.ipynb`.
2. **Select Kernel** → the pixi environment (`.pixi\envs\dev\python.exe`). Use the `dev` environment: it has everything the pipeline needs plus the dev tooling.
3. In the *Parameters* cell, set `collection_name` to the collection you want to process.
4. Run `setup.ipynb` first, then `process.ipynb`, then `qc.ipynb`.
5. (Optional) Export the executed notebooks as HTML into the collection's working folder and send for quality review.

## Development

```cmd
pixi run lint      # ruff check .
pixi run format    # ruff format .
```

These run in the `dev` environment, which is the `default` environment plus ruff.

## Outputs

Following outputs are produced for each batch that is processed:

`source_models`: Folder containing source models data, which were conflated and used as source for creating submodels for NWM reaches

`submodels`: Folders for extracted HEC-RAS submodels for NWM reaches that are used to create FIMs

`library`: Folder containing FIM depth rasters per reach and per flow and downstream boundary condition

`library_extent`: Folder containing FIM extent rasters per reach and per flow and downstream boundary condition

`qc`: Folder containing data to evaluate quality of produced FIM library and scenarios

`error_report.xlsx`: Provide insight into the errors encountered during processing of each step

`ripple.gpkg`: Geopackage (SQLITE Database) containing records for reaches, models and scenarios

`start_reaches.csv`: Flows2FIM start file which can be used to create composite FIMs using Flows2FIM software

---