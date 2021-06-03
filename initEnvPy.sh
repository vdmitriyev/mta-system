#!/bin/bash

python3 -m venv .venv
source .venv/bin/activate
# make sure the right pip is used
# $ which pip
# update pip
#pip install --upgrade pip
pip install -r requirements/requirements.txt
pip install -r requirements/requirements-prod.txt