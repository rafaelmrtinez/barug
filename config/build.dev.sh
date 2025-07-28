#!/usr/bin/env bash

# Please do not remove or modify this file.
# It is used to set up the development environment for the Barug project.
# This script installs the required Python packages and collects static files.
# It is essential for the proper functioning of the project in a development setting.
# By: raffa

set -o errexit

python3 -m pip install -r requirements.txt

python3 manage.py collectstatic --no-input