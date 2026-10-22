"""3-player Elo ratings: the incremental update when a rated game ends,
and the full replay (rating history, `flask rebuild-ratings`).

Rated games are finished games without a bot seat; their Score rows (out of
2.0 per game) are the input.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import aliased

from webapp.main import db
from webapp.models import (
    GameStatus,
    RatingHistory,
    Score,
    TriBoard,
    User,
    utcnow_naive,
)

ELO_K = 9.0  # rating change per point of surprise
ELO_SCALE = 400.0  # 400 rating points = 10x expected strength
STARTING_RATING = 500.0


def elo_update(ratings, scores):
    """3-player Elo: the three players' new ratings after one game, from their
    ratings before it and their scores in it (out of 2.0)."""
    q = [10 ** (r / ELO_SCALE) for r in ratings]
    total = sum(q)
    return [r + ELO_K * (s - qi / total) for r, s, qi in zip(ratings, scores, q)]


def _rated_games():
    """Every rated (bot-free) finished game in rating order:
    (board_id, finished_at, (p0, p1, p2), (s0, s1, s2))."""
    S0 = aliased(Score, name="s0")
    S1 = aliased(Score, name="s1")
    S2 = aliased(Score, name="s2")
    # Games with a bot seat don't create Score rows (see GameBoard.post()'s
    # board_has_bot guard) — excluding them here too, not just via missing
    # Score rows, matters: an included-but-scoreless board would COALESCE to
    # "everyone scored 0", which the Elo update reads as a real (and wrong)
    # result rather than "this game doesn't count".
    bot_ids = select(User.id).where(User.is_bot)
    stmt = (
        select(
            TriBoard.id,
            TriBoard.modified_at,
            TriBoard.player_0_id,
            TriBoard.player_1_id,
            TriBoard.player_2_id,
            func.coalesce(S0.score, 0),
            func.coalesce(S1.score, 0),
            func.coalesce(S2.score, 0),
        )
        .outerjoin(
            S0, and_(TriBoard.id == S0.board_id, TriBoard.player_0_id == S0.player_id)
        )
        .outerjoin(
            S1, and_(TriBoard.id == S1.board_id, TriBoard.player_1_id == S1.player_id)
        )
        .outerjoin(
            S2, and_(TriBoard.id == S2.board_id, TriBoard.player_2_id == S2.player_id)
        )
        .where(
            TriBoard.status == GameStatus.FINISHED,
            TriBoard.player_0_id.notin_(bot_ids),
            TriBoard.player_1_id.notin_(bot_ids),
            TriBoard.player_2_id.notin_(bot_ids),
        )
        .order_by(TriBoard.modified_at, TriBoard.id)
    )
    for board_id, ts, p0, p1, p2, s0, s1, s2 in db.session.execute(stmt):
        yield board_id, ts or datetime.min, (p0, p1, p2), (s0, s1, s2)


def get_rating_history():
    """Replay every rated game from scratch: {user_id: [(timestamp, rating),
    ...]} for every player of at least one. The source of truth that the
    incremental updates (record_game_rating) must agree with."""
    ratings = {}
    history = defaultdict(list)
    for _, ts, ids, scores in _rated_games():
        before = [ratings.get(i, STARTING_RATING) for i in ids]
        for i, rating in zip(ids, elo_update(before, scores)):
            ratings[i] = rating
            history[i].append((ts, rating))
    return dict(history)


def record_game_rating(tb, scores):
    """Apply one just-finished rated game to its players' ratings and rating
    history, in the caller's transaction (it commits).

    The three users' rows are locked first, in id order, so two games ending
    at once can't both start from the same old rating. FOR NO KEY UPDATE, so
    log rows naming these users (DBHandler, own connection) aren't blocked.
    """
    ids = tb.player_ids
    users = {
        u.id: u
        for u in db.session.query(User)
        .filter(User.id.in_(ids))
        .order_by(User.id)
        .with_for_update(key_share=True)
    }
    before = [
        users[i].rating if users[i].rating is not None else STARTING_RATING for i in ids
    ]
    now = utcnow_naive()
    for i, rating in zip(ids, elo_update(before, [scores[s] for s in range(3)])):
        users[i].rating = rating
        db.session.add(
            RatingHistory(user_id=i, board_id=tb.id, rating=rating, created_at=now)
        )


def rebuild_ratings():
    """Recompute every rating and the whole rating history from all rated
    games (after a rated game is deleted, or to repair). Caller commits."""
    ratings = {}
    db.session.query(RatingHistory).delete()
    for board_id, ts, ids, scores in _rated_games():
        before = [ratings.get(i, STARTING_RATING) for i in ids]
        for i, rating in zip(ids, elo_update(before, scores)):
            ratings[i] = rating
            db.session.add(
                RatingHistory(
                    user_id=i, board_id=board_id, rating=rating, created_at=ts
                )
            )
    for user in User.query.filter_by(is_bot=False):
        user.rating = ratings.get(user.id, STARTING_RATING)
    return len(ratings)


def get_user_rating_history(user_id):
    """[(timestamp, rating), ...] after each of the user's rated games;
    empty if they have none."""
    return [
        (h.created_at, h.rating)
        for h in RatingHistory.query.filter_by(user_id=user_id).order_by(
            RatingHistory.created_at, RatingHistory.id
        )
    ]
