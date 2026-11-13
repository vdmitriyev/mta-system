"""
Data from here is used:
    - AdventureWorks2017
    - https://github.com/bcafferky/shared/blob/master/PythonSQLDW/PythonSQLDW.zip
    - https://github.com/microsoft/sql-server-samples/tree/master/samples/databases/adventure-works/data-warehouse-install-script
"""

import logging
from pathlib import Path
from zipfile import ZipFile

import pandas as pd
from sqlalchemy import create_engine

logger = logging.getLogger(__name__)

CUR_DIR = Path(__file__).absolute().parent

# (CSV file, table, separator)
TABLES = [
    ("DimCurrency.csv", "dim_currency", ","),
    ("DimCustomer.csv", "dim_customer", ","),
    ("DimDate.csv", "dim_date", ","),
    ("DimGeography.csv", "dim_geography", ","),
    ("DimProductCategory.csv", "dim_product_category", ","),
    ("DimProductSubcategory.csv", "dim_product_subcategory", ","),
    ("DimSalesTerritory.csv", "dim_sales_territory", ","),
    ("DimProduct.csv", "dim_product", "|"),
    ("FactInternetSales.csv", "fact_internet_sales", ","),
]


def upper_case_to_underscore(_input: str) -> str:
    """Changes capital letters to an underscore and the small letter: DimDate -> dim_date"""

    result = "".join("_" + ch.lower() if ch.isupper() else ch for ch in _input)
    if not _input.startswith("_"):
        result = result.lstrip("_")
    return result


def import_into_table(csv_fname, table_name: str, sep: str, engine) -> None:
    logger.info("Import the file: %s", csv_fname)
    df = pd.read_csv(csv_fname, sep=sep)
    # postgres doesn't like capitals or spaces
    df.columns = [upper_case_to_underscore(c) for c in df.columns]
    df.to_sql(table_name, engine, index=False, method="multi", chunksize=1000)


def run_import(db_connect_uri: str, data_dir: Path = None) -> None:
    """Imports the AdventureWorks tables. Raises an exception with all errors at the end."""

    data_dir = data_dir or CUR_DIR / "data"
    if not data_dir.exists():
        with ZipFile(CUR_DIR / "data.zip", "r") as zip_bundle:
            zip_bundle.extractall(data_dir)

    engine = create_engine(db_connect_uri)
    errors = []
    try:
        for csv_name, table_name, sep in TABLES:
            try:
                import_into_table(data_dir / csv_name, table_name, sep, engine)
            except Exception as error:
                logger.exception("Import of %s failed", csv_name)
                errors.append(error)
    finally:
        engine.dispose()

    if errors:
        raise errors[0]
