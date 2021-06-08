'''
    Data from here is used:
        - It is part of the Apache Superset tutorial
        - https://raw.githubusercontent.com/apache-superset/examples-data/master/tutorial_flights.csv
'''
import os
import pandas as pd
from pathlib import Path

def get_db_connection():
    ''' Get connection to database '''

    import settings as settings
    DB_CONNECT_URI_TEMPLATE = 'postgresql://{user}:{password}@{server}/{database}'
    db_connect_uri = DB_CONNECT_URI_TEMPLATE.format(user=settings.DB_USER_NAME,
                                                    password=settings.DB_USER_PASSWORD,
                                                    server=settings.DB_SERVER,
                                                    database=settings.DB_NAME)

def import_into_table(fname, table_name, sep=',', data_format='CSV', db_connect_uri = None):

    print ('[i] Importing following file into database: {0}'.format(fname))

    if data_format.upper() == 'CSV':
        df = pd.read_csv(fname, sep=sep)
    if data_format.upper() == 'GZIP':
        df = pd.read_csv(fname, compression='gzip', error_bad_lines=False)
    if data_format.upper() == 'ZIP':
        df = pd.read_csv(fname, compression='zip', error_bad_lines=False)

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
    import_into_table(fname=os.path.join(cur_dir, 'tutorial_flights.zip'), table_name='flights',
                      data_format = 'ZIP', db_connect_uri = db_connect_uri)

if __name__ == '__main__':
    run_import()
