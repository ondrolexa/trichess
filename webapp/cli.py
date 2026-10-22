"""The flask CLI commands (cron jobs and repairs), registered on import
(webapp/__init__.py)."""

import logging
import os
import subprocess
from datetime import timedelta
from pathlib import Path

import click

from engine import slog_summary
from engine.opening import BOOK_PATH, build_book, save_book
from webapp.botplayer import maybe_trigger_bot
from webapp.game_end import sweep_finalize
from webapp.main import app, db, post_notification
from webapp.maintenance import is_maintenance
from webapp.models import (
    GameStatus,
    Log,
    TriBoard,
    User,
    delete_board,
    utcnow_naive,
)
from webapp.ratings import rebuild_ratings

logger = logging.getLogger(__name__)


def resend_notification():
    """Send notification each 24 hours when on move"""
    if app.debug:
        logger.info("Resending skipped (debug)")
        return

    with app.app_context():
        # Reminders would only lead players to the maintenance page.
        if is_maintenance():
            logger.info("Resending skipped (maintenance)")
            return
        # modified_at holds naive UTC (server_default/onupdate now(), with the
        # postgres server pinned to timezone=UTC in docker-compose.yml).
        cutoff = utcnow_naive() - timedelta(days=1)
        boards = TriBoard.query.filter(
            TriBoard.status == GameStatus.ACTIVE, TriBoard.modified_at <= cutoff
        ).all()
        for tb in boards:
            # on_move counts the votes of an open vote too: the reminder goes
            # to whoever still has to answer it, not to its initiator.
            on_move = slog_summary(tb.slog or "").on_move
            user = db.session.get(User, tb.player_ids[on_move])
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
    cutoff = utcnow_naive() - timedelta(days=days)
    deleted = Log.query.filter(Log.created_at < cutoff).delete()
    db.session.commit()
    click.echo(f"Deleted {deleted} log entries older than {days} days")


def remove_bot_games(minutes):
    """Delete finished games with a bot player, and their Log rows, once
    older than `minutes`. minutes <= 0 disables deletion entirely.

    Bot games are casual (no Score rows, no rating impact — see
    GameBoard.post()'s board_has_bot guard) and unplayable once finished, so
    the default is a short grace period rather than opt-in: enabled out of
    the box, just long enough that a player who just finished watching the
    board doesn't have it vanish mid-glance.

    delete_board() also clears Score/RatingHistory rows (bot games have
    none) and deletes the board's Log rows rather than detaching them: with
    foreign keys enforced an orphaned board_id would violate the FK, and a
    removed bot game's logs aren't worth keeping.
    """
    if minutes <= 0:
        return 0

    cutoff = utcnow_naive() - timedelta(minutes=minutes)
    candidates = TriBoard.query.filter(
        TriBoard.status == GameStatus.FINISHED, TriBoard.modified_at < cutoff
    ).all()

    removed = 0
    for tb in candidates:
        if not tb.bot_count:
            continue
        delete_board(tb)
        removed += 1

    db.session.commit()
    return removed


@app.cli.command("remove-bot-games")
@click.option(
    "--minutes",
    default=app.config["BOT_GAMES_REMOVAL"],
    help="Delete finished bot games (and their logs) older than this many "
    "minutes. 0 disables deletion.",
)
def remove_bot_games_command(minutes):
    """Delete finished games with a bot player, and their logs, older than
    --minutes (BOT_GAMES_REMOVAL env var, default 15)."""
    removed = remove_bot_games(minutes)
    click.echo(f"Removed {removed} finished bot game(s) older than {minutes} minutes")


def purge_stalling_games(days, dry_run=False):
    """Delete active games nobody has moved in for more than `days` days,
    with their Log rows. days <= 0 disables deletion entirely.

    modified_at is bumped by every committed move or vote, so an old value
    means the player on move has stalled. Active games have no Score rows
    yet (cleared defensively anyway, for FK safety), so nobody's rating is
    affected. Returns the ids of the removed games — or, with dry_run, of
    the games that would be removed, leaving the database untouched.
    """
    if days <= 0:
        return []

    cutoff = utcnow_naive() - timedelta(days=days)
    stalled = (
        TriBoard.query.filter(
            TriBoard.status == GameStatus.ACTIVE, TriBoard.modified_at < cutoff
        )
        .order_by(TriBoard.id)
        .all()
    )
    ids = [tb.id for tb in stalled]
    if dry_run:
        return ids

    for tb in stalled:
        logger.info(
            f"purge_stalling: removing game {tb.id} idle since {tb.modified_at}"
        )
        delete_board(tb)

    db.session.commit()
    return ids


@app.cli.command("purge-stalling")
@click.option(
    "--days",
    default=365,
    help="Delete active games with no move for more than this many days. "
    "0 disables deletion.",
)
@click.option("--dry-run", is_flag=True, help="Only list the games, delete nothing.")
def purge_stalling_command(days, dry_run):
    """Delete active games where the player on move stalled for --days days."""
    ids = purge_stalling_games(days, dry_run=dry_run)
    listed = f": {', '.join(map(str, ids))}" if ids else ""
    if dry_run:
        click.echo(
            f"Would remove {len(ids)} stalling game(s) inactive for more than "
            f"{days} days{listed}"
        )
    else:
        click.echo(
            f"Removed {len(ids)} stalling game(s) inactive for more than "
            f"{days} days{listed}"
        )


@app.cli.command("build-opening-book")
def build_opening_book_command():
    """Rebuild instance/opening_book.json from finished games in the database."""
    slogs = [
        tb.slog
        for tb in TriBoard.query.filter_by(status=GameStatus.FINISHED).all()
        if tb.slog
    ]
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


@app.cli.command("rebuild-ratings")
def rebuild_ratings_command():
    """Recompute every rating and the rating history from all rated games.

    Ratings are otherwise updated incrementally as games finish; this is the
    repair path (and what deleting a rated game runs)."""
    players = rebuild_ratings()
    db.session.commit()
    click.echo(f"Rebuilt ratings and rating history for {players} player(s)")


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
    if is_maintenance():
        click.echo("Skipped: maintenance mode is on")
        return
    board_ids = [
        tb.id for tb in TriBoard.query.filter_by(status=GameStatus.ACTIVE).all()
    ]
    finalized = 0
    for board_id in board_ids:
        try:
            if sweep_finalize(board_id):
                finalized += 1
            else:
                maybe_trigger_bot(board_id, finalize=False)
        except Exception as err:
            # One board's failure (e.g. a transient Redis hiccup on the
            # publish/enqueue side, after the DB write already committed)
            # must not abort the sweep for every other board.
            logger.error(
                f"[bot-sweep] Failed processing board {board_id}: {err}",
                exc_info=True,
            )
    click.echo(f"Swept {len(board_ids)} active game(s), finalized {finalized}")
