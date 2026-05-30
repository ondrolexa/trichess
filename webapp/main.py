import logging
import os
from datetime import datetime, timedelta

import click
import requests
from flask import Flask
from flask_bootstrap import Bootstrap5
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

# Custom GAME log level (between INFO and WARNING)
GAME = 25
logging.addLevelName(GAME, "GAME")


class DBHandler(logging.Handler):
    """Write log records to the Log table via SQLAlchemy."""

    def emit(self, record):
        try:
            from flask import current_app

            from webapp.models import Log, db

            _ = current_app._get_current_object()
        except (RuntimeError, AttributeError):
            return
        # Use the existing app context — no nested push so the session stays alive
        entry = Log(
            level=record.levelname,
            message=self.format(record),
            module=record.module,
            user_id=getattr(record, "user_id", None),
            board_id=getattr(record, "board_id", None),
        )
        db.session.add(entry)


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Attach DBHandler to the root logger (catches all child loggers)
db_handler = DBHandler()
db_handler.setLevel(GAME)
logging.getLogger().addHandler(db_handler)

app = Flask(__name__)
allowed_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5000").split(",")
CORS(app, origins=allowed_origins, supports_credentials=True)

# Configuration of application, see configuration.py, choose one and uncomment.
app.config.from_object("webapp.configuration.Config")


# Add security headers
@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    # Uncomment the following line in production to enforce HTTPS
    # response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    return response


app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)

bs = Bootstrap5(app)  # bootstrap-flask
db = SQLAlchemy(app)  # flask-sqlalchemy


# Enable SQLite foreign key enforcement
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


migrate = Migrate(app, db)
jwt = JWTManager(app)  # JWT

lm = LoginManager()
lm.init_app(app)
lm.login_view = "login"

__version__ = "0.2.0"


# notifications
def post_notification(username, text, title, gameid):
    if app.debug:
        logger.info("Notification skipped (debug): %s -> %s: %s", title, username, text)
        return
    click = f"https://trichess.mykuna.eu/play/{gameid}"
    try:
        requests.post(
            f"https://ntfy.mykuna.eu/trichess_{username}",
            data=text.encode("utf-8"),
            headers={
                "Title": title,
                "Click": click,
            },
        )
    except requests.exceptions.ConnectionError:
        logger.error("Connection error during notification post.")

    except Exception as err:
        logger.error(f"Unexpected post notification error: {err}, type: {type(err)}")


# Background jobs
def resend_notification():
    """Send notification each 24 hours when on move"""
    if app.debug:
        logger.info("Resending skipped (debug)")
        return
    with app.app_context():
        with db.engine.connect() as connection:
            result = connection.execute(
                text(
                    "SELECT * FROM triboard WHERE status=1 AND datetime(modified_at) <= datetime('now', '-1 day');"
                )
            )
            rows = result.mappings().all()
            for r in rows:
                slog = r["slog"]
                moves = [
                    slog[i : i + 4]
                    for i in range(0, len(slog), 4)
                    if slog[i] not in ["S", "R", "r", "s"]
                ]
                onmove = f"player_{len(moves) % 3}_id"
                user = (
                    connection.execute(
                        text("SELECT * FROM user WHERE id = :user_id;"),
                        {"user_id": r[onmove]},
                    )
                    .mappings()
                    .first()
                )
                # notify next player
                if user is not None:
                    logger.info(
                        f"resend_notification: notifying {user["username"]} about game {r["id"]}"
                    )
                    post_notification(
                        user["username"],
                        f"It's still your turn in game {r['id']}",
                        "Your turn reminder",
                        r["id"],
                    )


@app.cli.command("resend-notifications")
def resend_notifications_command():
    """Send notifications to players on move for games inactive >24h."""
    resend_notification()


@app.cli.command("purge-logs")
@click.option("--days", default=90, help="Delete logs older than this many days")
def purge_logs(days):
    """Delete log entries older than specified number of days."""
    from webapp.models import Log

    cutoff = datetime.utcnow() - timedelta(days=days)
    deleted = Log.query.filter(Log.created_at < cutoff).delete()
    db.session.commit()
    click.echo(f"Deleted {deleted} log entries older than {days} days")
