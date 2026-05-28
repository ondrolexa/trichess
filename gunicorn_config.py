import os

bind = f"0.0.0.0:{os.environ.get('PORT', 80)}"
workers = int(os.environ.get("GUNICORN_WORKERS", 4))
threads = int(os.environ.get("GUNICORN_THREADS", 2))
timeout = 120
preload_app = True
worker_tmp_dir = "/dev/shm"
