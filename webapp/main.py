import logging
import os
from datetime import datetime, timedelta

import click
from flask import Flask
from flask_bootstrap import Bootstrap5
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from werkzeug.exceptions import HTTPException

from webapp.notifications import _send_push_notification_job, notification_queue

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
        except RuntimeError, AttributeError:
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
        try:
            db.session.commit()
        except Exception:
            # A logging failure must never mask/replace the exception that
            # triggered this log record in the first place.
            db.session.rollback()


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


# Enable SQLite foreign key enforcement
@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    # WAL allows concurrent readers alongside a writer, reducing "database is
    # locked" errors now that the RQ worker is a 2nd process writing to the
    # same SQLite file alongside gunicorn's multiple worker processes.
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


migrate = Migrate(app, db)
jwt = JWTManager(app)  # JWT

lm = LoginManager()
lm.init_app(app)
lm.login_view = "login"

__version__ = "0.3.1"


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
                if user is not None and not user["is_bot"]:
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


BOT_GAMES_REMOVAL = int(os.environ.get("BOT_GAMES_REMOVAL", 0))


def remove_bot_games(days):
    """Delete finished games with a bot player, and their Log rows, once
    older than `days`. days <= 0 (the default, 0) is a no-op — deletion is
    opt-in only, never on by default.

    Score rows are cleared defensively (bot games shouldn't have any — see
    GameBoard.post()'s board_has_bot guard — but this is what actually
    makes the delete FK-safe in general, not a hypothetical-only check).
    Log rows referencing the board are deleted too (not just detached):
    PRAGMA foreign_keys=ON means an orphaned board_id would otherwise
    violate the FK, and a removed bot game's logs aren't worth keeping.
    """
    if days <= 0:
        return 0

    from webapp.models import Log, Score, TriBoard

    cutoff = datetime.utcnow() - timedelta(days=days)
    candidates = TriBoard.query.filter(
        TriBoard.status == 2, TriBoard.modified_at < cutoff
    ).all()

    removed = 0
    for tb in candidates:
        if not any(p.is_bot for p in (tb.player_0, tb.player_1, tb.player_2)):
            continue
        Score.query.filter_by(board_id=tb.id).delete()
        Log.query.filter_by(board_id=tb.id).delete()
        db.session.delete(tb)
        removed += 1

    db.session.commit()
    return removed


@app.cli.command("remove-bot-games")
@click.option(
    "--days",
    default=BOT_GAMES_REMOVAL,
    help="Delete finished bot games (and their logs) older than this many "
    "days. 0 (default) disables deletion.",
)
def remove_bot_games_command(days):
    """Delete finished games with a bot player, and their logs, older than
    --days (BOT_GAMES_REMOVAL env var, default 0 = disabled)."""
    removed = remove_bot_games(days)
    click.echo(f"Removed {removed} finished bot game(s) older than {days} days")


@app.cli.command("build-opening-book")
def build_opening_book_command():
    """Rebuild instance/opening_book.json from finished games in the database."""
    from engine.opening import BOOK_PATH, build_book, save_book
    from webapp.models import TriBoard

    slogs = [tb.slog for tb in TriBoard.query.filter_by(status=2).all() if tb.slog]
    book = build_book(slogs)
    save_book(book, BOOK_PATH)
    click.echo(f"Wrote opening book from {len(slogs)} finished games to {BOOK_PATH}")


@app.cli.command("bot-sweep")
def bot_sweep_command():
    """Re-trigger any active game whose on-move seat is a bot.

    Safety net for maybe_trigger_bot()'s normal move/vote-triggered path —
    covers a queued job lost to e.g. a Redis restart, which nothing else
    would ever re-trigger. Meant to run every few minutes via cron.
    """
    from webapp.botplayer import maybe_trigger_bot
    from webapp.models import TriBoard

    board_ids = [tb.id for tb in TriBoard.query.filter_by(status=1).all()]
    for board_id in board_ids:
        maybe_trigger_bot(board_id)
    click.echo(f"Swept {len(board_ids)} active game(s)")
