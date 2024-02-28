#!/bin/bash

cd ..
python3 -m venv .venv
source .venv/bin/activate

# make sure the right pip is used > `which pip`
pip install --upgrade pip
pip install --upgrade uv

uv pip install -r requirements/requirements.txt
uv pip install -r requirements/requirements-prod.txt