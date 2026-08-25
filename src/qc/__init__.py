import logging

import pandas as pd

from .flows2fim import run_flows2fim
from .jobs_report import create_failed_jobs_report, create_timedout_jobs_report
from .purge import delete_reach_data
from .utils import *

# Allows displaying the full content in cells
pd.set_option("display.max_colwidth", None)
# Display all rows
# pd.set_option('display.max_rows', None)
pd.set_option("display.max_columns", None)


logging.basicConfig(level=logging.INFO)
