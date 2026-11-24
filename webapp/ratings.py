"""3-player Elo ratings: the incremental update when a rated game ends,
and the full replay (rating history, `flask rebuild-ratings`).

Rated games are finished games without a bot seat; their Score rows (out of
2.0 per game) are the input.

Whether a rating is *shown* is a separate, derived status (`rating_status()`):
unrated until RATED_MIN_GAMES rated games, inactive after a year without one.
It never changes a rating, so there is nothing to rebuild or migrate. There is
deliberately no rating floor, no "opponents must be rated" rule and no
experience-adaptive K (RATINGS.md section 9 shows why).
"""

from collections import defaultdict, namedtuple
from datetime import datetime, timedelta

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

# Rating status (derived on read, see rating_status()). Looked up at call time,
# so tests can monkeypatch them.
RATED_MIN_GAMES = 10  # rated games (in the window) before a rating is shown
ESTABLISHED_GAMES = 30  # below this a shown rating carries a "?"
RATING_WINDOW_DAYS = 792  # 26 months: older games no longer count towards the minimum
INACTIVE_DAYS = 365  # rated, but no rated game for this long

UNRATED, RATED, INACTIVE = "unrated", "rated", "inactive"

# status: UNRATED / RATED / INACTIVE; games: all rated games ever; window_games:
# those inside the window; last: newest rated game (None if there is none);
# provisional: rated, but fewer than ESTABLISHED_GAMES games in the window.
RatingStatus = namedtuple("RatingStatus", "status games window_games last provisional")


def rating_status(dates, now=None):
    """Status of a player from the finish times of their rated games.

    Fewer than RATED_MIN_GAMES games in the last RATING_WINDOW_DAYS: unrated.
    Otherwise inactive if the newest game is older than INACTIVE_DAYS, else
    rated. A None date (old rows) counts as very old.
    """
    now = now or utcnow_naive()
    dates = list(dates)
    cutoff = now - timedelta(days=RATING_WINDOW_DAYS)
    window_games = sum(1 for d in dates if d is not None and d >= cutoff)
    known = [d for d in dates if d is not None]
    last = max(known) if known else None
    if window_games < RATED_MIN_GAMES:
        status = UNRATED
    elif last is not None and now - last > timedelta(days=INACTIVE_DAYS):
        status = INACTIVE
    else:
        status = RATED
    provisional = status == RATED and window_games < ESTABLISHED_GAMES
    return RatingStatus(status, len(dates), window_games, last, provisional)


def rated_game_rows(user_ids=None):
    """(player_id, score, onmove, tag, finished_at) for every Score row of a
    finished game, i.e. one row per player per rated game (bot games have no
    Score rows). `user_ids` limits it to those players."""
    stmt = (
        select(
            Score.player_id, Score.score, Score.onmove, Score.tag, TriBoard.modified_at
        )
        .join(TriBoard, TriBoard.id == Score.board_id)
        .where(TriBoard.status == GameStatus.FINISHED)
    )
    if user_ids is not None:
        stmt = stmt.where(Score.player_id.in_(list(user_ids)))
    return db.session.execute(stmt).all()


def rating_statuses(user_ids=None, now=None):
    """{user_id: RatingStatus} for the given players (default: everyone with a
    rated game). A requested player without any rated game is unrated, 0 games."""
    dates = defaultdict(list)
    for player_id, _, _, _, finished in rated_game_rows(user_ids):
        dates[player_id].append(finished)
    for uid in user_ids or ():
        dates.setdefault(uid, [])
    return {uid: rating_status(ds, now) for uid, ds in dates.items()}


def rating_display(rating, st):
    """(text, tooltip) for a rating next to a name in a list (lobby, games):
    the number, a "?" while provisional, or "unrated"."""
    number = f"{rating if rating is not None else STARTING_RATING:.0f}"
    if st.status == UNRATED:
        return "unrated", f"{st.window_games} of {RATED_MIN_GAMES} rated games"
    if st.status == INACTIVE:
        return number, f"Inactive: no rated game for {INACTIVE_DAYS} days"
    if st.provisional:
        return number + "?", f"Provisional: fewer than {ESTABLISHED_GAMES} rated games"
    return number, ""


def profile_rating_text(rating, st):
    """The player's own rating for their profile: always the number, with what
    its status means."""
    number = f"{rating if rating is not None else STARTING_RATING:.2f}"
    if st.status == UNRATED:
        return f"{number}? ({st.window_games} of {RATED_MIN_GAMES} games)"
    if st.status == INACTIVE:
        return f"{number} (inactive)"
    return number + ("?" if st.provisional else "")


def elo_update(ratings, scores):
    """3-player Elo: the three players' new ratings after one game, from their
    ratings before it and their scores in it.

    Scores are out of 2.0 per game (GameAPI.outcome_scores(): the 3 scores
    sum to 2), so player i's expected score is 2 * e_i, where
    e_i = 10^(r_i / ELO_SCALE) / sum_j 10^(r_j / ELO_SCALE) is their share
    (the 3 shares sum to 1). Then r_i += ELO_K * (s_i - 2 * e_i): zero-sum,
    the changes of one game add up to 0. (Until 0.5.5 the expectation was
    e_i, which added ELO_K to the total with every game; see ELO_PROBLEM.md.)
    """
    q = [10 ** (r / ELO_SCALE) for r in ratings]
    total = sum(q)
    return [r + ELO_K * (s - 2 * qi / total) for r, s, qi in zip(ratings, scores, q)]


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
