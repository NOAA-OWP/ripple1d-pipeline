# Ripple1D Pipeline
 
Ripple1D Pipeline is a workflow that utilizes the [Ripple1d](https://github.com/Dewberry/ripple1d) to generate FIMs and rating curves. 
Compatible with ripple1d==0.10.4. Use repository tags to get older versions.

## Contents
- [Initialization/Pre Processing source code](src/setup)
- [Ripple1d API Calls/Processing source code](src/process)
- [Quality Control/Post Processing source code](src/qc)


## Dependencies
 - Windows environment with Desktop Experience (GUI, not headless Windows)
 - Python version >=3.10 
 - [Ripple1d](https://github.com/Dewberry/ripple1d)
 - HEC-RAS (v6.3.1)
 - GDAL
 - [Flows2fim](https://github.com/ar-siddiqui/flows2fim) (if creating composite rasters)
 - AWS profile in `~\.aws\config` which includes valid AWS credentials (access key id and secret access key).

## Getting Started

### 1. **Checkout the Repo**
   - Clone this repository to your local machine.  
   ```git clone https://gitlab.sh.nextgenwaterprediction.com/NGWPC/ripple1d-pipeline C:\Users\<username>\Downloads\ripple1d-pipeline```


### 2. **Create a Virtual Environment**
   - Create a virtual environment in Python:
     - **Windows:**
     ```Powershell
     cd C:\venvs *OR* mkdir C:\venvs 
     python3 -m venv ripple1d_pipeline
     ```
     - **Linux**
     ```bash
     mkdir -p /venvs && cd /venvs
     python3 -m venv ripple1d_pipeline
     ```

### 3. **Activate the Virtual Environment**
   - **Windows:**
     ```Powershell
     ripple1d_pipeline\Scripts\activate
     ```
   - **Linux:**
     ```bash
     source ripple1d_pipeline/bin/activate
     ```

### 4. **Navigate to the Root of the Repo**
   - Use your terminal to navigate to the root folder of the repository:
   - **Windows:**
     ```Powershell
     cd /d <path\to\your\repo from step 1>
     ```
   - **Linux:**
     ```bash
     cd <path/to/your/repo from step 1>
     ```

### 5. **Install Requirements**
   - Install the necessary dependencies in your virtual environment:
     ```bash
     pip install -r requirements.txt
     ```

### 6. **Set up and start Ripple1D Server** 
The Ripple1d server must be installed and ran on a windows machine, with HEC-Ras installed.   
   - Create ripple1d virtual environment, activate, install ripple1d, start ripple1d.
      ```Powershell
      cd /d C:\venvs
      python3 -m venv ripple1d_<ripple1d version>
      cd ripple1d_<ripple1d version>
      .\Scripts\activate
      pip install ripple1d==<ripple1d version>
      ripple1d start --thread_count <number less than total available CPUs>
      ```
If the last command is successful, two new terminal windows will appear (Huey consumer and Flask api), which can be minimized. 

### 7. **Install GDAL**
The easiest way is to download the [OSGeo4W network installer](https://download.osgeo.org/osgeo4w/v2/osgeo4w-setup.exe), this aligns with the current default paths listed in `config.yaml`.

### 8. **Install flows2fim**
1. Download the [flows2fim zip](https://github.com/ar-siddiqui/flows2fim/releases/download/v0.2.1/flows2fim-windows-amd64.zip)
2. Extract the .zip file's contents to `C:\OSGeo4W\bin\`

   ###  **Pull flow files**
   ```Powershell
   mkdir C:\reference_data\flow_files
   aws s3 sync s3://fimc-data/reference/nwm_return_period_flows C:\reference_data\flow_files
   ```

### 9. **Install HEC-RAS**
1. Download the [HEC-RAS v631 Setup executable](https://github.com/HydrologicEngineeringCenter/hec-downloads/releases/download/1.0.26/HEC-RAS_631_Setup.exe)
2. Follow the install instructions, all default. 
3. Open HEC-RAS once to accept the Terms and Conditions. 

### Notes on Setup:
- Using a Linux Operating System is untested.
- It is highly recommended to run all steps using the Windows Command Prompt Application, not the Windonws PowerShell application.

## **Configuration**
### Environment file
An `example.env` file is included within the root directory. First, make a copy of `example.env`, naming it `.env`. Then, update the values in the `.env` file.

### Configuration file 

The `config.yaml` file in the `/src` directory contains all other necessary configuration parameters. Please ensure filepaths, timeouts, endpoints, etc are up to date for your machine, and if not, modify the file to suit your specific requirements. 


## **Using `batch_ripple_pipeline.py` or `ripple_pipeline.py`**

The automation of the whole pipeline can be accomplished using one of two scripts. `ripple_pipeline.py` is used to process a single colelction, identically to the Jupyter Notebook steps. `batch_ripple_pipeline.py` is a wrapper around `ripple_pipeline.py` which will serially process a list (or single) of collections, as well as push the data to a specified S3 bucket. 

For Example:
```Powershell
(ripple1d_pipeline) C:\Users\<user name>\ripple1d_pipeline>python .\ripple_pipeline.py -c mip_02060004
```

or 

```Powershell
(ripple1d_pipeline) C:\Users\<user name>\ripple1d_pipeline>python .\batch_ripple_pipeline.py -l "C:\collection_lists\test_collections.lst"
```

## **Using Jupyter Notebooks**

### 1. **Access Notebooks**
   - **Option 1: Using VSCode**
     1. Open the notebook in VSCode.
     2. Point the kernel to the IPython kernel in your virtual environment.

   - **Option 2: Using Jupyter Lab**
     1. Start Jupyter Lab from your virtual environment:
        ```bash
        jupyter lab
        ```
     2. Open `localhost:8888` in your browser to access Jupyter Lab and open the notebooks.

### 2. **Update Notebooks Parameters**
   - In the parameters cell of the notebooks, define the `collection_name` variable to the collection you'd like to process.

### 3. **Execute and Export Notebooks as HTML**
   - Execute `setup_<collection_name>.ipynb` first and then `process_<collection_name>.ipynb` and finally `qc_<collection_name>.ipynb`
   - Once the notebooks are executed, export them as HTML files and move them into the working folder created for the collection.

### 4. **(Optional) Send for Quality Review**
   - After exporting, send the entire working folder for quality review.

## Outputs
Following outputs are produced for each batch that is processed:

`source_models`: Folder containing source models data, which were conflated and used as source for creating submodels for NWM reaches

`submodels`: Folders for extracted HEC-RAS submodels for NWM reaches that are used to create FIMs

`library`: Folder containing FIM rasters per reach and per flow and downstream boundary condition

`qc`: Folder containing data to evaluate quality of produced FIM library and rating curves

`error_report.xlsx`: Provide insight into the errors encountered during processing of each step

`ripple.gpkg`: Geopackage (SQLITE Database) containing records for reaches, models and rating curves

`start_reaches.csv`: Flows2FIM start file which can be used to create composite FIMs using Flows2FIM software

---
