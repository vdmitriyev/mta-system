#!/bin/sh
set -e

# Create or update the SQLite database and add the initial data.
# The app adds the default UI visibility settings on start.
flask db upgrade
flask import-data-exercises

exec "$@"
