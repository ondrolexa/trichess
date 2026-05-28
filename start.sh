#!/bin/sh
supercronic /code/crontab &
exec gunicorn --config gunicorn_config.py --preload webapp:app
