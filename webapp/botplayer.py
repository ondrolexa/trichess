"""Background bot mover: enqueues and executes bot moves/vote responses.

Named separately from engine.bot (the move/vote *decision* logic) to keep
"decide what to play" and "wire it into the webapp/DB/queue" apart.
"""

import logging
import os

from flask_jwt_extended import create_access_token
from redis import Redis
from rq import Queue

from engine import choose_move, choose_vote, get_game
from engine.bot import MIN_SOUND_DEPTH
from webapp.main import GAME, app, db
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


def _seat_players(tb):
    return {0: tb.player_0, 1: tb.player_1, 2: tb.player_2}


def maybe_trigger_bot(board_id: int) -> None:
    """Enqueue a bot-move job if the player currently on move is a bot.

    Cheap read done here (not inside the job) so ordinary all-human games
    never touch Redis.

    Checks sweep_finalize() first: a bot should never be asked to search for
    a move on a position that's already game-over (e.g. a board that reached
    a since-added endgame rule — like threefold repetition — before that
    rule existed, and never got another move to trigger the check).
    """
    from webapp.api import sweep_finalize

    if sweep_finalize(board_id):
        return
    tb = db.session.get(TriBoard, board_id)
    if tb is None or tb.status != 1:
        return
    ga = get_game(0, tb.slog)
    players = _seat_players(tb)
    on_move = players.get(ga.on_move)
    if on_move is not None and on_move.is_bot:
        bot_queue.enqueue(run_bot_move, board_id)


def run_bot_move(board_id: int) -> None:
    """RQ job body: compute the bot's move/vote and persist it.

    Persists through the real POST /api/v1/manager/board endpoint (via the
    Flask test client, in-process — no real network hop) instead of
    duplicating GameBoard.post()'s scoring/notification/rating logic here.
    """
    with app.app_context():
        tb = db.session.get(TriBoard, board_id)
        if tb is None or tb.status != 1:
            return
        ga = get_game(0, tb.slog)
        players = _seat_players(tb)
        bot = players.get(ga.on_move)
        if bot is None or not bot.is_bot:
            return

        try:
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
                move = choose_move(ga, depth=BOT_DEPTH)
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

        token = create_access_token(identity=bot.username)
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
                "Bot move made",
                extra={"user_id": bot.id, "board_id": board_id},
            )
