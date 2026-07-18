import os

bind = f"0.0.0.0:{os.environ.get('PORT', 80)}"
workers = int(os.environ.get("GUNICORN_WORKERS", 4))
# sync (gunicorn's default when worker_class is unset) handles exactly 1
# request per worker for its entire duration — `threads` below would be
# silently ignored under sync. A single open SSE connection (see
# webapp/events.py) would then pin a whole worker process for as long as
# the browser tab stays open. gthread (built into gunicorn, no new
# dependency) lets each worker serve `threads` concurrent requests, so a
# handful of long-lived SSE streams (each mostly blocked waiting on Redis)
# can share a worker alongside ordinary page/API requests without
# starving them.
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")
threads = int(os.environ.get("GUNICORN_THREADS", 8))
timeout = 120
preload_app = True
worker_tmp_dir = "/dev/shm"
