"""RQ job bodies for outbound notifications the app shouldn't block a
request on: ntfy.sh push notifications and outgoing SMTP email.

Deliberately Flask-independent (reads REDIS_URL/MAIL_* straight from
os.environ, no `current_app`/`app` import) — this module runs inside the RQ
worker process, and the caller-facing wrappers (webapp/main.py's
post_notification, webapp/email.py's send_email) already do the one cheap,
synchronous check that's actually worth doing before enqueueing (debug
mode / MAIL_SERVER configured), so the job bodies here don't need any app
context at all.

Kept on its own "notifications" queue, separate from webapp/botplayer.py's
"bot" queue, so a slow bot search can't sit in front of a time-sensitive
notification in the same worker's queue order — see docker-compose.yml's
`rq worker notifications bot ...`.
"""

import logging
import os
import smtplib
from email.message import EmailMessage

import requests
from redis import Redis
from rq import Queue

logger = logging.getLogger(__name__)

_redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
notification_queue = Queue("notifications", connection=_redis)


def _send_push_notification_job(username, text, title, gameid):
    click = f"https://trichess.mykuna.eu/play/{gameid}"
    try:
        requests.post(
            f"https://ntfy.mykuna.eu/trichess_{username}",
            data=text.encode("utf-8"),
            headers={
                "Title": title,
                "Click": click,
            },
            timeout=(3, 5),
        )
    except requests.exceptions.ConnectionError:
        logger.error("Connection error during notification post.")
    except Exception as err:
        logger.error(f"Unexpected post notification error: {err}, type: {type(err)}")


def _send_email_job(to, subject, body):
    server = os.environ.get("MAIL_SERVER", "")
    if not server:
        logger.warning(
            "MAIL_SERVER not configured — skipping email to %s: %s", to, subject
        )
        return

    port = int(os.environ.get("MAIL_PORT", 587))
    username = os.environ.get("MAIL_USERNAME", "")
    password = os.environ.get("MAIL_PASSWORD", "")
    use_tls = os.environ.get("MAIL_USE_TLS", "true").lower() == "true"
    sender = os.environ.get("MAIL_DEFAULT_SENDER", "")

    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)

    try:
        with smtplib.SMTP(server, port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(msg)
        logger.info("Email sent to %s", to)
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
