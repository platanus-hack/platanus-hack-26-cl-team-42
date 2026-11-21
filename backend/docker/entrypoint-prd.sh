#!/bin/bash
set -e

# migrate and collectstatic run in deploy/CI, not at container start.
exec gunicorn wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 120
