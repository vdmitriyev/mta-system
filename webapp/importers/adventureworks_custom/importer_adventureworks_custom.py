'''
    Data from here is used:
        - AnventureWorks2017
        - https://github.com/bcafferky/shared/blob/master/PythonSQLDW/PythonSQLDW.zip
        - https://github.com/microsoft/sql-server-samples/tree/master/samples/databases/adventure-works/data-warehouse-install-script
'''

import os
from pathlib import Path
import pandas as pd

def get_db_connection():
    ''' Get connection to database '''

    import settings as settings

    DB_CONNECT_URI_TEMPLATE = 'postgresql://{user}:{password}@{server}/{database}'
    db_connect_uri = DB_CONNECT_URI_TEMPLATE.format(user=settings.DB_USER_NAME,
                                                    password=settings.DB_USER_PASSWORD,
                                                    server=settings.DB_SERVER,
                                                    database=settings.DB_NAME)

def import_into_table(csv_fname, table_name, sep=',', db_connect_uri = None):

    print ('[i] Importing following file into database: {0}'.format(csv_fname))

    if csv_fname[-3:].lower() == 'csv':
        df = pd.read_csv(csv_fname, sep=sep)
    else:
        df = pd.read_csv(csv_fname, compression='gzip', error_bad_lines=False)

    df.columns = [c.lower() for c in df.columns] # postgres doesn't like capitals or spaces
    print (df.columns)

    from sqlalchemy import create_engine
    engine = create_engine(db_connect_uri)

    #df.to_sql(table_name, engine)
    df.to_sql(table_name, engine, index=False, method = 'multi')

def run_import(db_connect_uri = None):
    ''' Runs default import '''

    if db_connect_uri is None:
        db_connect_uri = get_db_connection()

    cur_dir = Path(__file__).absolute().parent
    data_dir = os.path.join(cur_dir, 'data')
    if not os.path.exists(data_dir):
        print ('[i] Unzip data')
        from zipfile import ZipFile
        data_zip = os.path.join(cur_dir, 'data.zip')
        with ZipFile(data_zip, 'r') as zip_bundle:
                zip_bundle.extractall(data_dir)

    import_into_table(csv_fname= os.path.join(data_dir, 'DimCurrency.csv'), table_name='DimCurrency', db_connect_uri=db_connect_uri)
    import_into_table(csv_fname= os.path.join(data_dir, 'DimCustomer.csv'), table_name='DimCustomer', db_connect_uri=db_connect_uri)
    import_into_table(csv_fname= os.path.join(data_dir, 'DimDate.csv'), table_name='DimDate', db_connect_uri=db_connect_uri)
    import_into_table(csv_fname= os.path.join(data_dir, 'DimGeography.csv'), table_name='DimGeography', db_connect_uri=db_connect_uri)
    import_into_table(csv_fname= os.path.join(data_dir, 'DimProductCategory.csv'), table_name='DimProductCategory', db_connect_uri=db_connect_uri)
    import_into_table(csv_fname= os.path.join(data_dir, 'DimProductSubcategory.csv'), table_name='DimProductSubcategory', db_connect_uri=db_connect_uri)
    import_into_table(csv_fname= os.path.join(data_dir, 'DimSalesTerritory.csv'), table_name='DimSalesTerritory', db_connect_uri=db_connect_uri)
    import_into_table(csv_fname= os.path.join(data_dir, 'DimProduct.csv'), table_name='DimProduct', sep = '|', db_connect_uri=db_connect_uri)

    import_into_table(csv_fname= os.path.join(data_dir, 'FactInternetSales.csv'), table_name='FactInternetSales', db_connect_uri=db_connect_uri)

if __name__ == '__main__':
    run_import()
