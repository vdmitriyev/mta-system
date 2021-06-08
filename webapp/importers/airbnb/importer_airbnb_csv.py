'''
    It is basically copy of the code from here:
        - https://github.com/vdmitriyev/uol-data-analytics/tree/master/python-csv-airbnb

    settings.py file is required
'''
import os
from pathlib import Path
import requests
import pandas as pd
import urllib.parse as urlparse

def download(url, force_download=False):
    """ Downloads given URL and saves a local file"""

    cur_dir = Path(__file__).absolute().parent
    DATA_DIR = os.path.join(cur_dir, 'data')
    if not os.path.exists(DATA_DIR):
        print('[i] create following folder: {0}'.format(DATA_DIR))
        os.makedirs(DATA_DIR)

    r = requests.get(url, stream=True)

    if r.status_code == 200:
        _urlparse = urlparse.urlparse(url)
        f_name = os.path.join(DATA_DIR, os.path.basename(_urlparse.path))
        if (not os.path.exists(f_name) or force_download):
            print('[i] start download for of the url: {}'.format(url))
            print('[i] target file: {}'.format(f_name))
            with open(f_name, 'wb') as fd:
                for chunk in r.iter_content(chunk_size=1024):
                    fd.write(chunk)
            print('[i] finish download')
    else:
        print('[e] Wrong request status code: {0}'.format(r.status_code))

    return f_name


def download_data():
    #
    # date to download (for simplification)
    #
    date_to_download = '2020-03-17'

    # listings
    listings = "http://data.insideairbnb.com/germany/be/berlin/{date}/data/listings.csv.gz".format(date=date_to_download)
    listings = download(listings, False)

    # calendar
    calendar = "http://data.insideairbnb.com/germany/be/berlin/{date}/data/calendar.csv.gz".format(date=date_to_download)
    calendar = download(calendar, False)

    # reviews
    reviews = "http://data.insideairbnb.com/germany/be/berlin/{date}/data/reviews.csv.gz".format(date=date_to_download)
    reviews = download(reviews, False)

    # listings (good for visualisations)
    listings_vis = "http://data.insideairbnb.com/germany/be/berlin/{date}/visualisations/listings.csv".format(date=date_to_download)
    listings_vis = download(listings_vis, False)

    # Summary Review data and Listing ID (to facilitate time based analytics and visualisations linked to a listing)
    reviews_vis = "http://data.insideairbnb.com/germany/be/berlin/{date}/visualisations/reviews.csv".format(date=date_to_download)
    reviews_vis = download(reviews_vis, False)

    # neighbourhoods
    neighbourhoods = "http://data.insideairbnb.com/germany/be/berlin/{date}/visualisations/neighbourhoods.csv".format(date=date_to_download)
    neighbourhoods = download(neighbourhoods, False)

def get_db_connection():
    ''' Get connection to database '''

    import settings as settings

    DB_CONNECT_URI_TEMPLATE = 'postgresql://{user}:{password}@{server}/{database}'
    db_connect_uri = DB_CONNECT_URI_TEMPLATE.format(user=settings.DB_USER_NAME,
                                                    password=settings.DB_USER_PASSWORD,
                                                    server=settings.DB_SERVER,
                                                    database=settings.DB_NAME)

def import_into_table(csv_fname, table_name, db_connect_uri = None):

    if db_connect_uri is None:
        db_connect_uri = get_db_connection()

    print ('[i] Importing following file into database: {0}'.format(csv_fname))

    if csv_fname[-3:].lower() == 'csv':
        df = pd.read_csv(csv_fname)
    else:
        df = pd.read_csv(csv_fname, compression='gzip', error_bad_lines=False)

    df.columns = [c.lower() for c in df.columns] #postgres doesn't like capitals or spaces
    print (df.columns)

    from sqlalchemy import create_engine
    engine = create_engine(db_connect_uri)

    #df.to_sql(table_name, engine)
    df.to_sql(table_name, engine, method = 'multi')

def run_import(db_connect_uri = None):
    ''' Runs default import '''

    if db_connect_uri is None:
        db_connect_uri = get_db_connection()

    #import_into_table(fname='tutorial_flights.zip', table_name='flights', data_format = 'ZIP')
    # downloads data first
    download_data()

    cur_dir = Path(__file__).absolute().parent
    # uncomment if needed
    import_into_table(csv_fname = os.path.join(cur_dir, 'data/listings.csv'),
                      table_name = 'airbnb_listings_berlin_summary',
                      db_connect_uri = db_connect_uri)

    # you will need to unzip following archive
    #import_into_table(csv_fname='data/zips/listings.csv/listings.csv', table_name='airbnb_listings_full_01')
    import_into_table(csv_fname = os.path.join(cur_dir,'data/listings.csv.gz'),
                      table_name = 'airbnb_listings_berlin_full',
                      db_connect_uri = db_connect_uri)

    # uncomment if needed
    import_into_table(csv_fname = os.path.join(cur_dir,'data/reviews.csv'),
                      table_name = 'airbnb_reviews_berlin_summary',
                      db_connect_uri = db_connect_uri)

    # you will need to unzip following archive
    #import_into_table(csv_fname='data/zips/reviews.csv/reviews.csv', table_name='airbnb_reviews_full_01')
    import_into_table(csv_fname = os.path.join(cur_dir,'data/reviews.csv.gz'),
                      table_name = 'airbnb_reviews_berlin_full',
                      db_connect_uri = db_connect_uri)

    # uncomment if needed
    import_into_table(csv_fname = os.path.join(cur_dir,'data/neighbourhoods.csv'),
                      table_name = 'airbnb_neighbourhoods_berlin',
                      db_connect_uri = db_connect_uri)

    #
    # this job could last very long, never succeed until now
    #
    # import_into_table(csv_fname = 'data/zips/calendar.csv/calendar.csv',
    #                   table_name = 'airbnb_calendar_01',
    #                   db_connect_uri = db_connect_uri)

if __name__ == '__main__':
    run_import()
