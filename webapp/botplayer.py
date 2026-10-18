"""Background bot mover: enqueues and executes bot moves/vote responses.

Named separately from engine.bot (the move/vote *decision* logic) to keep
"decide what to play" and "wire it into the webapp/DB/queue" apart.
"""

import logging
import os

from flask_jwt_extended import create_access_token
from redis import Redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus

from engine import choose_move, choose_vote, get_game, slog_summary
from engine.bot import MAX_DEPTH, MIN_SOUND_DEPTH
from webapp.main import GAME, app, db
from webapp.maintenance import is_maintenance
from webapp.models import TriBoard, User

logger = logging.getLogger(__name__)

_redis = Redis.from_url(os.environ.get("REDIS_URL", "redis://localhost:6379/0"))
bot_queue = Queue("bot", connection=_redis)

BOT_DEPTH = int(os.environ.get("BOT_DEPTH", MIN_SOUND_DEPTH))
if BOT_DEPTH < MIN_SOUND_DEPTH:
    # Below MIN_SOUND_DEPTH the search never simulates the 2nd of the bot's
    # 2 opponents at all. Clamp rather than play unsound moves.
    logger.error(
        f"BOT_DEPTH={BOT_DEPTH} is below MIN_SOUND_DEPTH={MIN_SOUND_DEPTH} "
        "(bot would be blind to its 2nd opponent's replies) — clamping up."
    )
    BOT_DEPTH = MIN_SOUND_DEPTH
# BOT_DEPTH always completes; with a time budget (seconds, 0 = off) the
# search keeps deepening up to BOT_MAX_DEPTH while the budget lasts.
BOT_TIME_LIMIT = float(os.environ.get("BOT_TIME_LIMIT", 2.0))
BOT_MAX_DEPTH = int(os.environ.get("BOT_MAX_DEPTH", MAX_DEPTH))


def _seat_players(tb):
    return {0: tb.player_0, 1: tb.player_1, 2: tb.player_2}


# A job for one board and turn that is still waiting or running: enqueueing
# it again would only search the same move twice (and lose with a 409).
_PENDING = {
    JobStatus.QUEUED,
    JobStatus.STARTED,
    JobStatus.DEFERRED,
    JobStatus.SCHEDULED,
}


def maybe_trigger_bot(board_id: int, finalize: bool = True) -> None:
    """Enqueue a bot-move job if the player currently on move is a bot.

    Cheap read done here (not inside the job) so ordinary all-human games
    never touch Redis.

    With `finalize` (callers that haven't just checked it themselves), runs
    sweep_finalize() first: a bot should never be asked to search for a move
    on a position that's already game-over (e.g. a board that reached a
    since-added endgame rule — like threefold repetition — before that rule
    existed, and never got another move to trigger the check).

    One job per board and turn (job id from the slog length): while it's
    queued or running, triggering again — e.g. bot-sweep every 5 minutes
    over a backlog — doesn't add a duplicate.
    """
    from webapp.api import sweep_finalize

    # Bots pause during maintenance; bot-sweep (cron) re-triggers them after.
    if is_maintenance():
        return
    if finalize and sweep_finalize(board_id):
        return
    tb = db.session.get(TriBoard, board_id)
    if tb is None or tb.status != 1:
        return
    slog = tb.slog or ""
    on_move = _seat_players(tb).get(slog_summary(slog).on_move)
    if on_move is None or not on_move.is_bot:
        return
    job_id = f"bot-{board_id}-{len(slog)}"
    try:
        if Job.fetch(job_id, connection=bot_queue.connection).get_status() in _PENDING:
            return
    except NoSuchJobError:
        pass
    bot_queue.enqueue(run_bot_move, board_id, job_id=job_id)


def run_bot_move(board_id: int) -> None:
    """RQ job body: compute the bot's move/vote and persist it.

    Persists through the real POST /api/v1/manager/board endpoint (via the
    Flask test client, in-process — no real network hop) instead of
    duplicating GameBoard.post()'s scoring/notification/rating logic here.
    """
    with app.app_context():
        # A job queued just before maintenance started: drop it quietly
        # (its POST would get 503 anyway); bot-sweep re-queues it after.
        if is_maintenance():
            return
        tb = db.session.get(TriBoard, board_id)
        if tb is None or tb.status != 1:
            return
        ga = get_game(0, tb.slog)
        move_id = f"{(ga.move_number + 1):03d}"
        players = _seat_players(tb)
        bot = players.get(ga.on_move)
        if bot is None or not bot.is_bot:
            return

        try:
            logger.log(
                GAME,
                "Bot str  " + move_id,
                extra={"user_id": bot.id, "board_id": board_id},
            )
            if ga.voting.needed():
                vote = choose_vote(ga, depth=BOT_DEPTH)
                if vote is None:
                    return
                new_slog = (
                    ga.resignation_vote(vote)
                    if ga.voting.kind == "resign"
                    else ga.draw_vote(vote)
                )
            else:
                move = choose_move(
                    ga,
                    depth=BOT_DEPTH,
                    time_limit=BOT_TIME_LIMIT or None,
                    max_depth=BOT_MAX_DEPTH,
                )
                if move is None:
                    return
                from_gid, m, promo_label = move
                ga.make_move(from_gid, m["tgid"], promo_label)
                new_slog = ga.slog
        except Exception as err:
            logger.error(
                f"[run_bot_move] Failed to compute a move for board {board_id}: {err}"
            )
            return

        token = create_access_token(identity=str(bot.id))
        response = app.test_client().post(
            "/api/v1/manager/board",
            json={"id": board_id, "slog": new_slog},
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code != 200:
            logger.error(
                f"[run_bot_move] Persisting board {board_id} failed: "
                f"{response.status_code} {response.get_data(as_text=True)}"
            )
        else:
            logger.log(
                GAME,
                "Bot end  " + move_id,
                extra={"user_id": bot.id, "board_id": board_id},
            )
