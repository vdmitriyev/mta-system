"""
Data of Inside Airbnb (Berlin). Based on:
    - https://github.com/vdmitriyev/uol-data-analytics/tree/master/python-csv-airbnb
"""

import logging
import os
import urllib.parse as urlparse
from pathlib import Path

import pandas as pd
import requests
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).absolute().parent / "data"
BASE_URL = "http://data.insideairbnb.com/germany/be/berlin/{date}/"
DEFAULT_DATE = "2023-09-16"

# (path below BASE_URL, table)
FILES = [
    ("visualisations/listings.csv", "airbnb_listings_berlin_summary"),
    ("data/listings.csv.gz", "airbnb_listings_berlin_full"),
    ("visualisations/reviews.csv", "airbnb_reviews_berlin_summary"),
    ("data/reviews.csv.gz", "airbnb_reviews_berlin_full"),
    ("visualisations/neighbourhoods.csv", "airbnb_neighbourhoods_berlin"),
]


def download(url: str, force_download: bool = False) -> str | None:
    """Downloads the URL into the data folder. Returns the file name (None on error)."""

    os.makedirs(DATA_DIR, exist_ok=True)
    f_name = os.path.join(DATA_DIR, os.path.basename(urlparse.urlparse(url).path))
    if os.path.exists(f_name) and not force_download:
        return f_name

    response = requests.get(url, stream=True, timeout=120)
    if response.status_code != 200:
        logger.error("Download of %s failed: %s", url, response.status_code)
        return None

    logger.info("Download %s into %s", url, f_name)
    with open(f_name, "wb") as fd:
        for chunk in response.iter_content(chunk_size=65536):
            fd.write(chunk)
    return f_name


def import_into_table(csv_fname: str, table_name: str, engine) -> None:
    logger.info("Import the file: %s", csv_fname)
    if csv_fname.lower().endswith("csv"):
        df = pd.read_csv(csv_fname)
    else:
        df = pd.read_csv(csv_fname, compression="gzip", on_bad_lines="skip")

    # postgres doesn't like capitals or spaces
    df.columns = [c.lower() for c in df.columns]
    df.to_sql(table_name, engine, method="multi", chunksize=1000)


def run_import(db_connect_uri: str, date_to_download: str = DEFAULT_DATE) -> None:
    """Downloads the Airbnb files and imports them"""

    base_url = BASE_URL.format(date=date_to_download)
    engine = create_engine(db_connect_uri)
    try:
        for path, table_name in FILES:
            f_name = download(base_url + path)
            if f_name is None:
                raise Exception(
                    f"Was not able to download the data from: {base_url + path}"
                )
            import_into_table(f_name, table_name, engine)
    finally:
        engine.dispose()
