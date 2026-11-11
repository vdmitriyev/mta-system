#!/bin/sh
set -e

# Create or update the SQLite database and add the initial data.
# The app adds the default UI visibility settings on start.
python -m app.cli db-upgrade
python -m app.cli import-data-exercises

exec "$@"
