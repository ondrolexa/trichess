import os

bind = f"0.0.0.0:{os.environ.get('PORT', 8080)}"
workers = int(os.environ.get("GUNICORN_WORKERS", 2))
# gthread lets each worker serve `threads` concurrent requests (under the
# default sync worker `threads` would be silently ignored). Board live
# updates (SSE) no longer run here: they're served by the async service in
# sse/app.py, which Traefik routes /api/v1/manager/board/events to — so no
# long-lived connection ever pins one of these threads.
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")
threads = int(os.environ.get("GUNICORN_THREADS", 4))
timeout = 120
preload_app = True
worker_tmp_dir = "/dev/shm"
# Gunicorn 26's runtime control socket (for its admin CLI) isn't used here,
# and its default locations (/run/user/<uid>/, then ./.gunicorn) aren't
# writable by the container's non-root user — it only logged
# "Control server error: Permission denied" on every start.
control_socket_disable = True
