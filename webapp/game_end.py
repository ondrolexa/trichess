"""Finishing a game: classify how it ended, record each player's Score
(unless a bot sat in, which makes the game casual and unrated), update
ratings, and tell the players.

GameBoard.post() runs it after every committed move or vote; sweep_finalize()
also covers boards that are over without a new move (bot-sweep, bot jobs).

How a game ends is GameAPI.endgame(), checked in this order: a draw vote
all 3 accepted, a resignation vote exactly 2 accepted, threefold repetition,
and then, when the player on move has no legal move, checkmate if their king
is attacked, otherwise stalemate.

Points per game (GameAPI.outcome_scores), 2.0 in all, by Score tag:
  N checkmate    2.0 split by how many pieces each player attacks the
                 mated king with
  R resignation  2.0 to the one player who declined
  D draw, S stalemate, T repetition   2/3 each

A game with any bot seat is casual: no Score rows, no rating change, and no
notifications to the bot accounts.
"""

import logging

from engine import get_game
from webapp.events import publish_board_move
from webapp.log import GAME
from webapp.main import app, db, post_notification
from webapp.models import GameStatus, Score, TriBoard
from webapp.ratings import record_game_rating

logger = logging.getLogger(__name__)


def bot_notification_flags(players):
    """Return (board_has_bot, notify_players) for a game's 3 seats.

    Games with a bot seat are casual: no Score rows, no rating impact, no
    pointless notifications to a bot's own (unmonitored) username. A solo
    human playing against 2 bots additionally has its own notifications
    suppressed by default (see Config.SINGLE_PLAYER_NOTIFICATIONS).
    """
    board_has_bot = any(p.is_bot for p in players.values())
    single_player_vs_bots = sum(p.is_bot for p in players.values()) == 2
    notify_players = (
        not single_player_vs_bots or app.config["SINGLE_PLAYER_NOTIFICATIONS"]
    )
    return board_has_bot, notify_players


# How each endgame kind is recorded: Score.tag and the GAME log label.
ENDGAMES = {
    "draw": "D",
    "resignation": "R",
    "checkmate": "N",
    "stalemate": "S",
    "repetition": "T",
}


def _endgame_messages(kind, ga, players, scores, board_id):
    """(seat, "Game over" text) for every seat, in notification order."""
    if kind == "resignation":
        resigned = ga.voting.results(kind="resign")
        winner = ({0, 1, 2} - set(resigned)).pop()
        return [(winner, f"You win in game {board_id} by resignation")] + [
            (uid, f"You lost in game {board_id} by resignation") for uid in resigned
        ]
    if kind == "checkmate":
        loser = players[ga.on_move].username
        return [
            (uid, f"You lost in game {board_id}")
            if uid == ga.on_move
            else (
                uid,
                f"{loser} lost in game {board_id}. Your score is {scores[uid]:g}",
            )
            for uid in scores
        ]
    text = {
        "draw": f"Draw agreed in game {board_id}",
        "stalemate": f"The game {board_id} ended in a stalemate",
        "repetition": f"The game {board_id} ended in a threefold repetition",
    }[kind]
    return [(uid, text) for uid in scores]


def finalize_if_finished(
    tb, ga, players, board_has_bot, notify_players, actor_user=None
):
    """If *ga* (the board's current replayed state) is over, mark *tb*
    finished and run the same scoring/notification/logging that a live
    move ending the game goes through. Returns the endgame kind classifying
    how it ended, or None if the game isn't actually over.

    *actor_user* is the User to credit the GAME log line to; None when
    called from an automated sweep rather than a live request. Caller is
    responsible for the eventual db.session.commit().
    """
    kind = ga.endgame()
    if kind is None:
        return None
    tb.status = GameStatus.FINISHED
    tag = ENDGAMES[kind]
    scores = ga.outcome_scores(kind)
    if not board_has_bot:
        for uid, value in scores.items():
            db.session.add(
                Score(
                    player_id=players[uid].id,
                    board_id=tb.id,
                    score=value,
                    tag=tag,
                    onmove=uid == ga.on_move,
                )
            )
    if notify_players:
        for uid, text in _endgame_messages(kind, ga, players, scores, tb.id):
            if not players[uid].is_bot:
                post_notification(players[uid].username, text, "Game over", tb.id)
    logger.log(
        GAME,
        f"Game finished — tag {tag} ({kind})",
        extra={
            "user_id": actor_user.id if actor_user is not None else None,
            "board_id": tb.id,
        },
    )
    if not board_has_bot:
        record_game_rating(tb, scores)
    return kind


def sweep_finalize(board_id):
    """If board_id's current position is already game-over, finalize it
    (status/scores/notifications/log) without requiring a new move to be
    POSTed. Returns True if it just finalized, False if the game is still
    ongoing (or the board doesn't exist / isn't active).

    Used by bot_sweep_command (self-heals a board stuck at status=1 whose
    slog already replays to a terminal position — e.g. a legacy game that
    predates a since-added endgame rule) and maybe_trigger_bot (so a bot is
    never asked to search for a move on a position that's already over).
    """
    tb = db.session.get(TriBoard, board_id)
    if tb is None or tb.status != GameStatus.ACTIVE:
        return False
    ga = get_game(0, tb.slog)
    players = tb.players
    board_has_bot, notify_players = bot_notification_flags(players)
    endgame_kind = finalize_if_finished(tb, ga, players, board_has_bot, notify_players)
    if endgame_kind is None:
        return False
    db.session.commit()
    publish_board_move(tb.id, len(tb.slog))
    return True
