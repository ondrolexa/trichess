import os

workers = int(os.environ.get("GUNICORN_PROCESSES", "2"))
threads = int(os.environ.get("GUNICORN_THREADS", "4"))
bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:80")
