import logging
import os
import sqlite3
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
from flask import Flask
from flask_bootstrap import Bootstrap5
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect
from sqlalchemy import event
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


def _mirror_debug_for_cli():
    """The flask CLI resets app.debug from FLASK_DEBUG alone after importing
    the app, which silently dropped DEBUG=true for cron'd commands (e.g.
    resend-notifications sent real pushes). Mirror DEBUG into FLASK_DEBUG;
    an explicit FLASK_DEBUG still wins."""
    if app.config["DEBUG"]:
        os.environ.setdefault("FLASK_DEBUG", "1")


_mirror_debug_for_cli()

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

__version__ = "0.5.1"


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
    from webapp.maintenance import is_maintenance
    from webapp.models import TriBoard, User

    with app.app_context():
        # Reminders would only lead players to the maintenance page.
        if is_maintenance():
            logger.info("Resending skipped (maintenance)")
            return
        # modified_at holds naive UTC (server_default/onupdate now(), with the
        # postgres server pinned to timezone=UTC in docker-compose.yml).
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
        boards = TriBoard.query.filter(
            TriBoard.status == 1, TriBoard.modified_at <= cutoff
        ).all()
        for tb in boards:
            slog = tb.slog or ""
            moves = [
                slog[i : i + 4]
                for i in range(0, len(slog), 4)
                if slog[i] not in ["S", "R", "r", "s"]
            ]
            user = db.session.get(User, getattr(tb, f"player_{len(moves) % 3}_id"))
            # notify next player
            if user is not None and not user.is_bot:
                logger.info(
                    f"resend_notification: notifying {user.username} about game {tb.id}"
                )
                post_notification(
                    user.username,
                    f"It's still your turn in game {tb.id}",
                    "Your turn reminder",
                    tb.id,
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

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    deleted = Log.query.filter(Log.created_at < cutoff).delete()
    db.session.commit()
    click.echo(f"Deleted {deleted} log entries older than {days} days")


BOT_GAMES_REMOVAL = int(os.environ.get("BOT_GAMES_REMOVAL", 15))


def remove_bot_games(minutes):
    """Delete finished games with a bot player, and their Log rows, once
    older than `minutes`. minutes <= 0 disables deletion entirely.

    Bot games are casual (no Score rows, no rating impact — see
    GameBoard.post()'s board_has_bot guard) and unplayable once finished, so
    the default is a short grace period rather than opt-in: enabled out of
    the box, just long enough that a player who just finished watching the
    board doesn't have it vanish mid-glance.

    Score rows are cleared defensively (bot games shouldn't have any, but
    this is what actually makes the delete FK-safe in general, not a
    hypothetical-only check). Log rows referencing the board are deleted too
    (not just detached): PRAGMA foreign_keys=ON means an orphaned board_id
    would otherwise violate the FK, and a removed bot game's logs aren't
    worth keeping.
    """
    if minutes <= 0:
        return 0

    from webapp.models import Log, Score, TriBoard

    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
        minutes=minutes
    )
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
    "--minutes",
    default=BOT_GAMES_REMOVAL,
    help="Delete finished bot games (and their logs) older than this many "
    "minutes. 0 disables deletion.",
)
def remove_bot_games_command(minutes):
    """Delete finished games with a bot player, and their logs, older than
    --minutes (BOT_GAMES_REMOVAL env var, default 15)."""
    removed = remove_bot_games(minutes)
    click.echo(f"Removed {removed} finished bot game(s) older than {minutes} minutes")


@app.cli.command("build-opening-book")
def build_opening_book_command():
    """Rebuild instance/opening_book.json from finished games in the database."""
    from engine.opening import BOOK_PATH, build_book, save_book
    from webapp.models import TriBoard

    slogs = [tb.slog for tb in TriBoard.query.filter_by(status=2).all() if tb.slog]
    book = build_book(slogs)
    save_book(book, BOOK_PATH)
    click.echo(f"Wrote opening book from {len(slogs)} finished games to {BOOK_PATH}")


def _pg_dump(url, path):
    """pg_dump the PostgreSQL database at `url` as plain SQL into `path`.

    Plain SQL without owner/privilege statements, so the postgres
    container's docker-entrypoint-initdb.d can load it into an empty
    database as whatever POSTGRES_USER it runs with. Credentials go through
    libpq's env vars, never argv (visible in the process list).
    """
    env = dict(os.environ)
    for var, value in (
        ("PGHOST", url.host),
        ("PGPORT", url.port),
        ("PGUSER", url.username),
        ("PGPASSWORD", url.password),
    ):
        if value is not None:
            env[var] = str(value)
    try:
        subprocess.run(
            [
                "pg_dump",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(path),
                url.database,
            ],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as err:
        raise click.ClickException(
            "pg_dump not found (install postgresql-client)"
        ) from err
    except subprocess.CalledProcessError as err:
        raise click.ClickException(f"pg_dump failed: {err.stderr.strip()}") from err


def dump_db(path=None):
    """Write a plain-SQL dump of the database to `path` (default trichess.sql
    in the instance folder) and return the path written. In the compose files
    instance/ is also the postgres container's docker-entrypoint-initdb.d, so
    an empty database initialises itself from the latest dump.

    Written to a .tmp file first and renamed into place, so a crash mid-dump
    never leaves a truncated *.sql where postgres' initdb would load it.
    """
    path = Path(path or Path(app.instance_path) / "trichess.sql")
    tmp = path.with_name(path.name + ".tmp")
    url = db.engine.url
    try:
        if url.get_backend_name() == "postgresql":
            _pg_dump(url, tmp)
        else:
            conn = db.engine.raw_connection()
            try:
                with open(tmp, "w") as f:
                    for line in conn.iterdump():
                        f.write(f"{line}\n")
            finally:
                conn.close()
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    return path


@app.cli.command("dump-db")
@click.option(
    "--file",
    "file",
    type=click.Path(dir_okay=False),
    default=None,
    help="Output file (default: instance/trichess.sql)",
)
def dump_db_command(file):
    """Write a SQL dump of the database (default instance/trichess.sql)."""
    path = dump_db(file)
    click.echo(f"Dumped database to {path}")


@app.cli.command("sqlite-to-postgres")
@click.option(
    "--sqlite",
    "sqlite_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
    help="Legacy SQLite database to copy (opened read-only)",
)
def sqlite_to_postgres_command(sqlite_path):
    """One-time copy of the legacy SQLite database into the (empty)
    PostgreSQL database — see README's cut-over runbook."""
    from webapp.sqlite_migrate import sqlite_to_postgres

    sqlite_to_postgres(app, db, sqlite_path)


@app.cli.command("bot-sweep")
def bot_sweep_command():
    """Re-trigger any active game whose on-move seat is a bot, and finalize
    any active game whose position is already game-over.

    The re-trigger half is a safety net for maybe_trigger_bot()'s normal
    move/vote-triggered path — covers a queued job lost to e.g. a Redis
    restart, which nothing else would ever re-trigger. The finalize half
    self-heals a board stuck at status=1 whose slog already replays to a
    terminal position (e.g. a legacy game that predates a since-added
    endgame rule, or simply never got another move to trigger the check) —
    covers boards on a human's turn too, which maybe_trigger_bot alone
    can't reach. Meant to run every few minutes via cron.
    """
    from webapp.api import sweep_finalize
    from webapp.botplayer import maybe_trigger_bot
    from webapp.maintenance import is_maintenance
    from webapp.models import TriBoard

    if is_maintenance():
        click.echo("Skipped: maintenance mode is on")
        return
    board_ids = [tb.id for tb in TriBoard.query.filter_by(status=1).all()]
    finalized = 0
    for board_id in board_ids:
        try:
            if sweep_finalize(board_id):
                finalized += 1
            else:
                maybe_trigger_bot(board_id)
        except Exception as err:
            # One board's failure (e.g. a transient Redis hiccup on the
            # publish/enqueue side, after the DB write already committed)
            # must not abort the sweep for every other board.
            logger.error(f"[bot-sweep] Failed processing board {board_id}: {err}")
    click.echo(f"Swept {len(board_ids)} active game(s), finalized {finalized}")
