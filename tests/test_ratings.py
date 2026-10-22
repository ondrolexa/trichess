"""Incremental Elo (ratings.record_game_rating) against the full replay
(ratings.get_rating_history), the rating_history table, rebuild-ratings and
deleting a rated game."""

import pytest
from flask_jwt_extended import create_access_token

from engine import get_game
from tests.test_webapp import _create_user, _login_as_admin, _seated_board
from webapp import ratings
from webapp.main import db
from webapp.models import RatingHistory, Score, TriBoard, User


def _post(app, client, tb, user, slog):
    with app.test_request_context():
        token = create_access_token(identity=str(user.id))
    return client.post(
        "/api/v1/manager/board",
        json={"id": tb.id, "slog": slog},
        headers={"Authorization": f"Bearer {token}"},
    )


def _resign_game(app, client, players, winner_seat):
    """A finished rated game: everyone but `winner_seat` accepts resignation."""
    tb = _seated_board(players, 1)
    for _ in range(3):
        db.session.refresh(tb)
        ga = get_game(0, tb.slog)
        seat = ga.on_move
        slog = ga.resignation_vote(seat != winner_seat)
        assert _post(app, client, tb, players[seat], slog).status_code == 200
    db.session.refresh(tb)
    assert tb.status == 2
    return tb


def _final_ratings():
    return {uid: points[-1][1] for uid, points in ratings.get_rating_history().items()}


@pytest.fixture
def players(app):
    return [_create_user(n) for n in ("alice", "bob", "carol", "dave")]


def test_incremental_ratings_match_full_replay(app, client, players):
    alice, bob, carol, dave = players
    _resign_game(app, client, [alice, bob, carol], winner_seat=0)
    _resign_game(app, client, [dave, alice, bob], winner_seat=0)
    _resign_game(app, client, [carol, dave, alice], winner_seat=2)

    replay = _final_ratings()
    for user in players:
        db.session.refresh(user)
        assert user.rating == pytest.approx(replay[user.id])
    # One history row per player per game, ending at the current rating.
    assert RatingHistory.query.count() == 9
    alice_history = ratings.get_user_rating_history(alice.id)
    assert len(alice_history) == 3
    assert alice_history[-1][1] == pytest.approx(alice.rating)


def test_winner_gains_and_others_lose(app, client, players):
    alice, bob, carol, _ = players
    _resign_game(app, client, [alice, bob, carol], winner_seat=1)
    for user in (alice, bob, carol):
        db.session.refresh(user)
    assert bob.rating > ratings.STARTING_RATING > alice.rating
    assert alice.rating == pytest.approx(carol.rating)


def test_bot_game_changes_no_rating(app, client):
    alice, bob = _create_user("alice"), _create_user("bob")
    bot = User.query.filter_by(username="Bot 1").one()
    tb = _seated_board([alice, bob, bot], 1)
    for vote, user in ((True, alice), (True, bob), (False, bot)):
        slog = get_game(0, tb.slog).resignation_vote(vote)
        assert _post(app, client, tb, user, slog).status_code == 200
        db.session.refresh(tb)
    assert tb.status == 2
    assert RatingHistory.query.count() == 0
    assert {u.rating for u in (alice, bob)} == {ratings.STARTING_RATING}


def test_rebuild_ratings_reproduces_incremental_state(app, client, players):
    alice, bob, carol, dave = players
    _resign_game(app, client, [alice, bob, carol], winner_seat=0)
    _resign_game(app, client, [dave, alice, bob], winner_seat=1)
    before = {u.id: u.rating for u in User.query}
    history_before = [
        (h.user_id, h.board_id, h.rating)
        for h in RatingHistory.query.order_by(RatingHistory.id)
    ]

    result = app.test_cli_runner().invoke(args=["rebuild-ratings"])

    assert result.exit_code == 0, result.output
    db.session.expire_all()
    for user in User.query:
        assert user.rating == pytest.approx(before[user.id])
    history_after = [
        (h.user_id, h.board_id, h.rating)
        for h in RatingHistory.query.order_by(RatingHistory.id)
    ]
    assert len(history_after) == len(history_before)
    for (u1, b1, r1), (u2, b2, r2) in zip(history_before, history_after):
        assert (u1, b1) == (u2, b2) and r1 == pytest.approx(r2)


def test_profile_chart_reads_rating_history(app, client, players):
    alice, bob, carol, _ = players
    _resign_game(app, client, [alice, bob, carol], winner_seat=0)
    db.session.refresh(alice)
    client.post("/login", data={"username": "alice", "password": "password123"})

    html = client.get("/profile").get_data(as_text=True)

    assert f"{round(alice.rating, 2)}" in html.split("var values")[1][:200]


def test_admin_deleting_a_rated_game_removes_its_points(app, client, players):
    alice, bob, carol, dave = players
    first = _resign_game(app, client, [alice, bob, carol], winner_seat=0)
    _resign_game(app, client, [dave, alice, bob], winner_seat=0)
    _login_as_admin(client)

    client.post("/admin-games", data={"delete": first.id})

    db.session.expire_all()
    assert db.session.get(TriBoard, first.id) is None
    assert Score.query.filter_by(board_id=first.id).count() == 0
    assert RatingHistory.query.filter_by(board_id=first.id).count() == 0
    # Carol played only the deleted game: back to the starting rating.
    assert db.session.get(User, carol.id).rating == ratings.STARTING_RATING
    replay = _final_ratings()
    for user in (alice, bob, dave):
        assert db.session.get(User, user.id).rating == pytest.approx(replay[user.id])
