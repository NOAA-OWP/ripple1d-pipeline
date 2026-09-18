# Design Guide

The purpose of this file is to capture the reasoning behind the
major design decisions so they don't have to be rederived or reargued later. This is not a Readme or setup guide.

---

## Project layout

The repo is mainly separated into

1. `entrypoints` - scripts that are the ways to run the pipeline.
2. `notebooks` - notebooks that are the ways to run the pipeline, step by step. Kept as a top-level folder separate from `entrypoints` to keep `.ipynb` files apart from the `.py` scripts.
3. `ripple1d_pipeline` - package containing building block for the pipeline. This is the package name, so it can't be `src`. Recommended `src/ripple1d_pipeline/`layout is not adapted because the benefit of src/pkg-name (not having pkg in sys.path so that imported pkg is always from the install not from the src code) does not out weight the simplicity here. This is not a distributed library, we always want to run against the source code anyways. This could be debated but we are deciding to go with a simpler approach.
4. `tools` - completely separate and independent tools. No code from here is being used in main pipeline.

Entrypoint support code lives with its entrypoint, not in the package: `monitoring_database.py` is only used by `run_batch`, so it sits in `entrypoints/`. The decision if something belong in the pkg or here is "is it imported by any `ripple1d_pipeline.*` module?". If only an entrypoint uses it, it is not library code.

- Putting notebooks and entrypoints scripts into a folder means `import ripple1d_pipeline` won't work unless we have an **install** i.e. the package is installed into the environment so `import ripple1d_pipeline` resolves from any working directory (notebooks included). We do this by editible install. This is _not_ publishing, it just registers the local package.

## Logging

- **Named loggers.** Every module uses `logging.getLogger(__name__)`, so a log line names its source (`ripple1d_pipeline.process.job_client`). Entry scripts run as `__main__`, so they name their logger explicitly (`run_collection`, `run_batch`) to match `PROJECT_LOGGERS`.
- **Third-party logging** is managed separately from this repos logging so that separate logging level can be configured.

## Configuration

- Secretes are managed through environment variables.
- Config that varies between different machines are environments are also managed through the environment variable. This keeps per-machine values (`C:\Users\...`) out of source code entirely.
- We read config and env one time at load so as not to have scattered `os.getenv` calls with the exception of secrets, which are read from the environment at point of use so as not to store them in the config object which has a vulnerability that it could be logged at some point.
- Both YAML files and `.env` are located relative to the package, not the current working directory, so loading works identically from a script, a notebook, or a tool in any directory.
- Some env variables are required and some are defaults, if a required env variable is missing, we fail at startup. The default values for env variables are stored in the code itself.

## Packaging (`pyproject.toml`)

We do **not** publish this package. The packaging metadata exists for only the **editable install**, which is what makes `import ripple1d_pipeline` resolve from `entrypoints/` and the notebooks.

- **`version` is derived from git tags** (`hatch-vcs`), this is consistent with how we are doing it in flows2fim. Hardcoded versions are a weak point and can drift easily.
- **`[project.dependencies]` is deliberately empty.** Runtime dependencies come from conda-forge via pixi. If they were also listed here, the editable install would make uv fetch PyPI copies of packages conda already provides.

## Dependencies & environment (pixi)

This repo adopt `pixi` because it manage the whole enviornment including non python dependencies, such as the GDAL command-line tools, originally we had OSGeo4W shell separate setup but it was brittle. `uv` alone can't do this as there is no reliable GDAL CLI on PyPI for Windows.\
\
`pixi` also provide benefit of not having to activate environment separately which we were doing before with .venv setup.