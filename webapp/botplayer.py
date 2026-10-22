"""Background bot mover: enqueues and executes bot moves/vote responses.

Named separately from engine.bot (the move/vote *decision* logic) to keep
"decide what to play" and "wire it into the webapp/DB/queue" apart.
"""

import logging

from flask_jwt_extended import create_access_token
from redis import Redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job, JobStatus

from engine import choose_move, choose_vote, get_game, slog_summary
from webapp.game_end import sweep_finalize
from webapp.log import GAME
from webapp.main import app, db
from webapp.maintenance import is_maintenance
from webapp.models import GameStatus, TriBoard

logger = logging.getLogger(__name__)

_redis = Redis.from_url(app.config["REDIS_URL"])
bot_queue = Queue("bot", connection=_redis)

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
    # Bots pause during maintenance; bot-sweep (cron) re-triggers them after.
    if is_maintenance():
        return
    if finalize and sweep_finalize(board_id):
        return
    tb = db.session.get(TriBoard, board_id)
    if tb is None or tb.status != GameStatus.ACTIVE:
        return
    slog = tb.slog or ""
    on_move = tb.players.get(slog_summary(slog).on_move)
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
        if tb is None or tb.status != GameStatus.ACTIVE:
            return
        ga = get_game(0, tb.slog)
        move_id = f"{(ga.move_number + 1):03d}"
        players = tb.players
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
                vote = choose_vote(ga, depth=app.config["BOT_DEPTH"])
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
                    depth=app.config["BOT_DEPTH"],
                    time_limit=app.config["BOT_TIME_LIMIT"] or None,
                    max_depth=app.config["BOT_MAX_DEPTH"],
                )
                if move is None:
                    return
                from_gid, m, promo_label = move
                ga.make_move(from_gid, m["tgid"], promo_label)
                new_slog = ga.slog
        except Exception as err:
            logger.error(
                f"[run_bot_move] Failed to compute a move for board {board_id}: {err}",
                exc_info=True,
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
