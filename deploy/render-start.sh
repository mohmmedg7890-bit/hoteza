#!/bin/sh
set -eu
# Free Render instances have no shell or pre-deploy command. Run one-time
# initialization before the web worker starts; do not add multiple instances.
python manage.py migrate --noinput
python manage.py createcachetable
python manage.py bootstrap_owner
exec python -m gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 2 --timeout 60 --access-logfile - --error-logfile -
