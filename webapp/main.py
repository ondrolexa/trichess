import logging
import os
import sqlite3
from datetime import timedelta

from flask import Flask, request
from flask_bootstrap import Bootstrap5
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
from sqlalchemy.engine import Engine
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

from webapp.log import configure_logging
from webapp.notifications import _send_push_notification_job, notification_queue

configure_logging()
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object("webapp.configuration.Config")
# No credentials: the API is bearer-only, browsers never send it cookies.
CORS(app, origins=app.config["CORS_ORIGINS"])
# The largest legitimate body is a ~1 KB slog; the Contact form's attachment
# is the one exception (_allow_contact_upload below).
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024

if app.config["TRUSTED_PROXY_HOPS"]:
    hops = app.config["TRUSTED_PROXY_HOPS"]
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=hops, x_proto=hops, x_host=hops)

# Rate limits for the login/sign-up routes (see views.py); keyed by client IP,
# which is only right behind a proxy with TRUSTED_PROXY_HOPS set.
limiter = Limiter(get_remote_address, app=app)


def _mirror_debug_for_cli():
    """The flask CLI resets app.debug from FLASK_DEBUG alone after importing
    the app, which silently dropped DEBUG=true for cron'd commands (e.g.
    resend-notifications sent real pushes). Mirror DEBUG into FLASK_DEBUG;
    an explicit FLASK_DEBUG still wins."""
    if app.config["DEBUG"]:
        os.environ.setdefault("FLASK_DEBUG", "1")


_mirror_debug_for_cli()


_proxy_warned = False


@app.before_request
def _warn_untrusted_proxy():
    """Behind a proxy without TRUSTED_PROXY_HOPS, email links are http:// and
    every client shares the proxy's IP for rate limits (one attacker locks
    everyone out of /login). Say so once per process."""
    global _proxy_warned
    if (
        not _proxy_warned
        and not app.config["TRUSTED_PROXY_HOPS"]
        and "X-Forwarded-For" in request.headers
    ):
        _proxy_warned = True
        logger.warning(
            "Request came through a proxy (X-Forwarded-For) but "
            "TRUSTED_PROXY_HOPS is 0: links are http:// and rate limits see "
            "the proxy's IP. Set TRUSTED_PROXY_HOPS (Traefik: 1)."
        )


@app.before_request
def _allow_contact_upload():
    """Raise the body limit for the Contact form only. Registered before
    CSRFProtect, whose own before_request reads the form first."""
    if request.endpoint == "contact":
        request.max_content_length = app.config["CONTACT_MAX_ATTACHMENT"] + 64 * 1024


# CSRF protection for cookie/session-authenticated HTML form routes. The /api/v1/*
# blueprint and the /token view are bearer-JWT-only (no cookies involved) and are
# exempted from it in views.py where they're registered.
csrf = CSRFProtect(app)


# Add security headers
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Uncomment the following line in production to enforce HTTPS
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


@app.errorhandler(404)
def handle_not_found(err):
    return "Not found", 404


@app.errorhandler(429)
def handle_rate_limited(err):
    return "Too many attempts. Please wait a minute and try again.", 429


@app.errorhandler(Exception)
def handle_unexpected_error(err):
    # Registering this handler is what stops uncaught non-HTTP exceptions from
    # propagating past Flask to the WSGI server (PROPAGATE_EXCEPTIONS=True
    # otherwise re-raises them once no handler is found). Flask's error-handler
    # lookup walks the raised exception's full MRO, so a bare Exception handler
    # also matches HTTPException subclasses (abort(), CSRFError, flask-restx's
    # .abort(), ...) unless they're passed through untouched here.
    if isinstance(err, HTTPException):
        return err
    logger.error(f"Unhandled exception: {err}", exc_info=True)
    return "Internal server error", 500


app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)

bs = Bootstrap5(app)  # bootstrap-flask
db = SQLAlchemy(app)  # flask-sqlalchemy


# Enable SQLite foreign key enforcement (tests and zero-config runs; a no-op
# for PostgreSQL, which always enforces foreign keys)
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    if not isinstance(dbapi_connection, sqlite3.Connection):
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


migrate = Migrate(app, db)
jwt = JWTManager(app)  # JWT

lm = LoginManager()
lm.init_app(app)
lm.login_view = "login"

__version__ = "0.5.4"


# notifications
def post_notification(username, text, title, gameid):
    """Queue a push notification — never blocks the caller on the ntfy.sh
    request. The debug-mode skip stays synchronous (checked here, not in
    the job) so nothing gets queued at all during local dev/tests."""
    if app.debug:
        logger.info("Notification skipped (debug): %s -> %s: %s", title, username, text)
        return
    notification_queue.enqueue(
        _send_push_notification_job, username, text, title, gameid
    )
