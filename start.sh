#!/bin/sh
set -e
# Bring the database schema up to date before anything uses it (no-op when
# already at head). A failing migration stops the container instead of
# serving against an outdated schema. Postgres is up by now: compose's
# depends_on waits for its health check.
flask --app=webapp db upgrade
supercronic /code/crontab &
exec gunicorn --config gunicorn_config.py --preload webapp:app
