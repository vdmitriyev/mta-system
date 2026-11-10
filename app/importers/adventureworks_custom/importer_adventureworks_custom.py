"""
Data from here is used:
    - AnventureWorks2017
    - https://github.com/bcafferky/shared/blob/master/PythonSQLDW/PythonSQLDW.zip
    - https://github.com/microsoft/sql-server-samples/tree/master/samples/databases/adventure-works/data-warehouse-install-script
"""

import os
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

SEP_DEFAULT = ";"


def get_db_connection():
    """Get connection to database"""

    import settings as settings

    DB_CONNECT_URI_TEMPLATE = "postgresql://{user}:{password}@{server}/{database}"
    db_connect_uri = DB_CONNECT_URI_TEMPLATE.format(
        user=settings.DB_USER_NAME,
        password=settings.DB_USER_PASSWORD,
        server=settings.DB_SERVER,
        database=settings.DB_NAME,
    )
    return db_connect_uri, f"{settings.DB_SERVER}:{settings.DB_NAME}"


def import_into_table(csv_fname, table_name, sep=SEP_DEFAULT, db_connect_uri=None):

    print(f"{datetime.now()} importing following file into database: {csv_fname}")

    if csv_fname[-3:].lower() == "csv":
        df = pd.read_csv(csv_fname, sep=sep)
    else:
        df = pd.read_csv(csv_fname, compression="gzip", on_bad_lines="skip")

    # postgres doesn't like capitals or spaces
    df.columns = [upper_case_to_underscore(c) for c in df.columns]
    print(f"Columns of the table:{df.columns}")

    from sqlalchemy import create_engine

    engine = create_engine(db_connect_uri)
    df.to_sql(table_name, engine, index=False, method="multi", chunksize=10000)


def upper_case_to_underscore(_input):
    """Changes the all capital letters in the input to underscore"""

    result = "".join("_" + ch.lower() if ch.isupper() else ch for ch in _input)
    if not _input.startswith("_"):
        result = result.lstrip("_")
    return result


def run_import(db_connect_uri=None):
    """Runs default import"""

    db_info = None
    if db_connect_uri is None:
        db_connect_uri, db_info = get_db_connection()

    print(f"{datetime.now()} use database: {db_info}")

    cur_dir = Path(__file__).absolute().parent
    data_dir = os.path.join(cur_dir, "data")
    if not os.path.exists(data_dir):
        print(f"{datetime.now()} unzip data")
        from zipfile import ZipFile

        data_zip = os.path.join(cur_dir, "data.zip")
        with ZipFile(data_zip, "r") as zip_bundle:
            zip_bundle.extractall(data_dir)

    mapping_csv_to_tbl = [
        {"csv": "DimCurrency.csv", "table": "dim_currency", "sep": ","},
        {"csv": "DimCustomer.csv", "table": "dim_customer", "sep": ","},
        {"csv": "DimDate.csv", "table": "dim_date", "sep": ","},
        {"csv": "DimGeography.csv", "table": "dim_geography", "sep": ","},
        {"csv": "DimProductCategory.csv", "table": "dim_product_category", "sep": ","},
        {
            "csv": "DimProductSubcategory.csv",
            "table": "dim_product_subcategory",
            "sep": ",",
        },
        {"csv": "DimSalesTerritory.csv", "table": "dim_sales_territory", "sep": ","},
        {"csv": "DimProduct.csv", "table": "dim_product", "sep": "|"},
        {"csv": "FactInternetSales.csv", "table": "fact_internet_sales", "sep": ","},
    ]

    errors = []
    for item in mapping_csv_to_tbl:
        try:
            sep_current = SEP_DEFAULT
            if "sep" in item:
                sep_current = item["sep"]

            import_into_table(
                csv_fname=os.path.join(data_dir, item["csv"]),
                table_name=item["table"],
                sep=sep_current,
                db_connect_uri=db_connect_uri,
            )
        except Exception as ex:
            print(traceback.format_exc())
            errors.append(ex)

    if len(errors) > 0:
        raise Exception(errors)


if __name__ == "__main__":
    run_import()
