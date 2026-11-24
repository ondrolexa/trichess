"""Incremental Elo (ratings.record_game_rating) against the full replay
(ratings.get_rating_history), the rating_history table, rebuild-ratings and
deleting a rated game."""

import re
from datetime import datetime, timedelta

import pytest
from flask_jwt_extended import create_access_token

from engine import get_game
from tests.test_webapp import (
    _create_user,
    _login,
    _login_as_admin,
    _rows,
    _seated_board,
)
from webapp import ratings
from webapp.main import db
from webapp.models import RatingHistory, Score, TriBoard, User, utcnow_naive


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


@pytest.mark.parametrize(
    "before, scores",
    [
        ([500, 500, 500], [2.0, 0.0, 0.0]),
        ([620, 480, 530], [1.0, 1.0, 0.0]),
        ([450, 700, 515], [0.0, 2.0, 0.0]),
        ([600, 500, 400], [2 / 3, 2 / 3, 2 / 3]),
    ],
)
def test_elo_update_is_zero_sum(before, scores):
    after = ratings.elo_update(before, scores)
    assert sum(after) == pytest.approx(sum(before))


def test_elo_update_equal_players():
    r = ratings.STARTING_RATING
    k = ratings.ELO_K
    # A draw between equals changes nothing; a full win is +12/-6/-6 at K=9.
    assert ratings.elo_update([r, r, r], [2 / 3] * 3) == pytest.approx([r, r, r])
    assert ratings.elo_update([r, r, r], [2.0, 0.0, 0.0]) == pytest.approx(
        [r + 4 / 3 * k, r - 2 / 3 * k, r - 2 / 3 * k]
    )


def test_favourite_loses_more_than_underdog():
    strong, weak = ratings.elo_update([600, 400, 500], [0.0, 2.0, 0.0])[:2]
    assert 600 - strong > 0
    assert weak - 400 > 4 / 3 * ratings.ELO_K  # beat the odds: more than +12


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


# ---------------------------------------------------------------- status
NOW = datetime(2026, 11, 24, 12, 0)


def _days_ago(n):
    return NOW - timedelta(days=n)


def test_status_needs_the_minimum_of_rated_games():
    nine = ratings.rating_status([_days_ago(d) for d in range(9)], NOW)
    ten = ratings.rating_status([_days_ago(d) for d in range(10)], NOW)
    assert (nine.status, nine.window_games) == ("unrated", 9)
    assert (ten.status, ten.games) == ("rated", 10)
    assert ratings.rating_status([], NOW) == (ratings.UNRATED, 0, 0, None, False)


def test_status_provisional_until_established():
    few = ratings.rating_status([_days_ago(d) for d in range(29)], NOW)
    many = ratings.rating_status([_days_ago(d) for d in range(30)], NOW)
    assert few.status == many.status == "rated"
    assert few.provisional and not many.provisional


def test_status_inactive_after_a_year_without_a_rated_game():
    def status(idle):
        return ratings.rating_status(
            [_days_ago(idle + d) for d in range(10)], NOW
        ).status

    assert status(365) == "rated"
    assert status(366) == "inactive"
    # Idle for long enough that fewer than 10 games are left in the window.
    assert status(ratings.RATING_WINDOW_DAYS) == "unrated"


def test_status_window_counts_only_recent_games():
    dates = [_days_ago(ratings.RATING_WINDOW_DAYS + 1)] * 5 + [_days_ago(1)] * 9
    st = ratings.rating_status(dates, NOW)
    assert (st.status, st.games, st.window_games) == ("unrated", 14, 9)
    assert ratings.rating_status(dates + [_days_ago(2)], NOW).status == "rated"


def test_status_unknown_dates_count_as_very_old():
    st = ratings.rating_status([None] * 12, NOW)
    assert (st.status, st.games, st.last) == ("unrated", 12, None)


def test_status_minimum_is_read_at_call_time(monkeypatch):
    monkeypatch.setattr(ratings, "RATED_MIN_GAMES", 0)
    assert ratings.rating_status([], NOW).status == "rated"


def _rated_game(user, when):
    """A finished rated game of `user` against two throwaway opponents, with a
    Score row for `user` only (all the status looks at)."""
    others = [
        User.query.filter_by(username=n).first() or _create_user(n)
        for n in ("filler1", "filler2")
    ]
    tb = _seated_board([user, *others], 2)
    tb.modified_at = when
    db.session.add(Score(player_id=user.id, board_id=tb.id, score=2.0, tag="N"))
    db.session.commit()


def _history(user, n, idle=0):
    for i in range(n):
        _rated_game(user, utcnow_naive() - timedelta(days=idle + i))


def test_statuses_count_rated_games_not_bot_games(app):
    alice = _create_user("alice")
    bot1 = User.query.filter_by(username="Bot 1").first()
    bot2 = User.query.filter_by(username="Bot 2").first()
    _seated_board([alice, bot1, bot2], 2)  # a finished bot game: no Score rows
    _rated_game(alice, utcnow_naive())
    statuses = ratings.rating_statuses([alice.id, 9999])
    assert statuses[alice.id].games == 1
    assert statuses[9999].status == "unrated" and statuses[9999].games == 0


# ----------------------------------------------------------------- pages
@pytest.fixture
def league(app):
    """alice: 12 games (rated, provisional); bob: 35 (established); carol: 3
    (unrated); dave: 10 games, the newest 400 days ago (inactive)."""
    users = {n: _create_user(n) for n in ("alice", "bob", "carol", "dave")}
    users["alice"].rating, users["bob"].rating = 520.0, 510.0
    users["carol"].rating, users["dave"].rating = 497.0, 530.0
    db.session.commit()
    _history(users["alice"], 12)
    _history(users["bob"], 35)
    _history(users["carol"], 3)
    _history(users["dave"], 10, idle=400)
    return users


def test_standings_rated_then_unrated_then_inactive(app, client, league):
    _login(client, "alice")
    html = client.get("/rating").get_data(as_text=True)

    at = {n: html.index(f">{n}<") for n in ("alice", "bob", "carol", "dave")}
    unrated_heading = html.index('<h4 class="mt-4 mb-1">Unrated</h4>')
    assert "fewer than 10 rated games in the last 26 months" in html
    inactive_heading = html.index('<h4 class="mt-4 mb-1">Inactive</h4>')
    # alice (520) before bob (510); then unrated carol; then inactive dave.
    assert at["alice"] < at["bob"] < unrated_heading < at["carol"]
    assert at["carol"] < inactive_heading < at["dave"]
    # Only rated players are ranked.
    assert _rows(html) == ["1", "2"]
    # "?" while under 30 games: alice yes, bob no.
    alice_row = html[at["alice"] : at["bob"]]
    bob_row = html[at["bob"] : unrated_heading]
    assert "<sup" in alice_row and "<sup" not in bob_row
    # The unrated rating is hidden, the inactive one is shown.
    assert "497" not in html and "530" in html
    # Games = rated games.
    assert re.search(r"<td><span>12</span></td>", html)
    assert re.search(r"<td><span>35</span></td>", html)


@pytest.mark.parametrize("name", ["alice", "carol", "dave"])
def test_standings_highlight_own_row_in_every_block(app, client, league, name):
    _login(client, name)
    html = client.get("/rating").get_data(as_text=True)
    # The highlighted row is the own one: no other row starts in between.
    assert re.search(r'<tr class="table-active">(?:(?!<tr).)*?>%s<' % name, html, re.S)


def test_standings_hide_empty_blocks_and_bot_only_players(app, client):
    alice = _create_user("alice")
    bob = _create_user("bob")
    bot1 = User.query.filter_by(username="Bot 1").first()
    bot2 = User.query.filter_by(username="Bot 2").first()
    _history(alice, 10)
    _seated_board([bob, bot1, bot2], 2)  # bob only has a casual game
    _login(client, "alice")
    html = client.get("/rating").get_data(as_text=True)
    assert ">Unrated</h4>" not in html and ">Inactive</h4>" not in html
    assert ">bob<" not in html
    assert _rows(html) == ["1"]


def test_lobby_and_games_show_the_status_instead_of_the_number(app, client, league):
    alice, carol, dave = league["alice"], league["carol"], league["dave"]
    bot1 = User.query.filter_by(username="Bot 1").first()
    waiting = TriBoard(
        owner_id=alice.id,
        status=0,
        player_0_id=alice.id,
        player_1_id=carol.id,
        player_2_id=dave.id,
    )
    active = TriBoard(
        owner_id=alice.id,
        status=1,
        slog="",
        player_0_id=alice.id,
        player_1_id=carol.id,
        player_2_id=bot1.id,
    )
    db.session.add_all([waiting, active])
    db.session.commit()
    _login(client, "alice")

    lobby = client.get("/join").get_data(as_text=True)
    assert "alice (<span" in lobby and ">520?<" in lobby  # provisional
    assert ">unrated<" in lobby and "497" not in lobby  # carol
    assert ">530<" in lobby and "Inactive" in lobby  # dave, the number kept

    games = client.get("/games").get_data(as_text=True)
    # Rated players show the number, unrated players and bots just the name.
    assert "alice (<span" in games and ">520?<" in games
    assert "carol" in games and "unrated" not in games and "497" not in games
    assert "Bot 1</" in games and ">bot<" not in games


@pytest.mark.parametrize(
    "name, text",
    [
        ("alice", "520.00?"),
        ("bob", "510.00"),
        ("carol", "497.00? (3 of 10 games)"),
        ("dave", "530.00 (inactive)"),
    ],
)
def test_profile_shows_the_own_number_with_its_status(app, client, league, name, text):
    _login(client, name)
    html = client.get("/profile").get_data(as_text=True)
    assert f'<div class="fs-5 fw-semibold">{text}</div>' in html


def test_rating_display_texts():
    st = ratings.rating_status
    assert ratings.rating_display(
        541.4, st([_days_ago(d) for d in range(30)], NOW)
    ) == ("541", "")
    assert (
        ratings.rating_display(541.4, st([_days_ago(d) for d in range(12)], NOW))[0]
        == "541?"
    )
    assert ratings.rating_display(497.0, st([_days_ago(1)], NOW))[0] == "unrated"
    assert ratings.rating_display(None, st([], NOW))[0] == "unrated"
