"""
Data from here is used:
    - It is part of the Apache Superset tutorial
    - https://raw.githubusercontent.com/apache-superset/examples-data/master/tutorial_flights.csv
"""

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)

DATA_FILE = Path(__file__).absolute().parent / "tutorial_flights.zip"


def run_import(db_connect_uri: str) -> None:
    """Imports the flights into the table "flights" """

    logger.info("Import the file: %s", DATA_FILE)
    df = pd.read_csv(DATA_FILE, compression="zip", on_bad_lines="skip")
    # postgres doesn't like capitals or spaces
    df.columns = [c.lower() for c in df.columns]

    engine = create_engine(db_connect_uri)
    try:
        df.to_sql("flights", engine, index=False, method="multi", chunksize=1000)
    finally:
        engine.dispose()
