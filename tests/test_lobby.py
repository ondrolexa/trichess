"""The /join lobby: creating, joining, bot seats and cancelling games."""

import logging

import pytest

from webapp.main import db
from webapp.models import GameStatus, Log, TriBoard, User

from .test_webapp import _create_user, _login


def _flashes(client):
    with client.session_transaction() as sess:
        return [message for _, message in sess.pop("_flashes", [])]


def _bots():
    return User.query.filter_by(is_bot=True).order_by(User.id).all()


@pytest.fixture(autouse=True)
def _game_logs(caplog):
    # pytest leaves the root logger at WARNING; GAME (25) rows need INFO.
    caplog.set_level(logging.INFO)


@pytest.fixture
def alice(app, client):
    user = _create_user("alice")
    _login(client, "alice")
    _flashes(client)  # drop the login message
    return user


def _waiting_board(owner, seat=0):
    board = TriBoard(owner_id=owner.id)
    board.assign_seat(seat, owner)
    db.session.add(board)
    db.session.commit()
    return board


class TestCreate:
    def test_creates_waiting_game_in_chosen_seat(self, client, alice):
        client.post("/join", data={"seat": "Seat 2"})
        board = TriBoard.query.one()
        assert board.status == GameStatus.WAITING
        assert board.owner_id == alice.id
        assert board.player_ids == [None, alice.id, None]
        assert board.player_1_accepted is True
        assert _flashes(client) == ["Game created successfuly!"]
        assert Log.query.filter_by(message="Game created", board_id=board.id).count()

    def test_invalid_form_creates_nothing(self, client, alice):
        client.post("/join", data={"seat": "Seat 9"})
        assert TriBoard.query.count() == 0


class TestTakeSeat:
    def test_join_free_seat(self, client, alice):
        board = _waiting_board(_create_user("bob"))
        client.post("/join", data={"board": board.id, "seat": "2"})
        db.session.refresh(board)
        assert board.player_ids[2] == alice.id
        assert board.player_2_accepted is True
        assert board.status == GameStatus.WAITING

    @pytest.mark.parametrize(
        "data, message",
        [
            ({"seat": "0"}, "Seat already taken"),
            ({"seat": "3"}, "Invalid seat"),
            ({"seat": None}, "Invalid seat"),
            ({"fill_bot": "1"}, "Only the game owner can add a bot"),
        ],
    )
    def test_refusals(self, client, alice, data, message):
        board = _waiting_board(_create_user("bob"))
        data = {k: v for k, v in data.items() if v is not None}
        client.post("/join", data={"board": board.id, **data})
        assert _flashes(client) == [message]
        db.session.refresh(board)
        assert alice.id not in board.player_ids

    def test_unknown_or_started_game(self, client, alice):
        client.post("/join", data={"board": 999, "seat": "1"})
        assert _flashes(client) == ["Game not found or already started"]

    def test_second_seat_for_same_player_refused(self, client, alice):
        board = _waiting_board(alice)
        client.post("/join", data={"board": board.id, "seat": "1"})
        assert _flashes(client) == ["You already have a seat in this game"]
        db.session.refresh(board)
        assert board.player_ids == [alice.id, None, None]

    def test_owner_adds_free_bot(self, client, alice):
        board = _waiting_board(alice)
        bot1, bot2 = _bots()
        client.post("/join", data={"board": board.id, "fill_bot": "1"})
        db.session.refresh(board)
        assert board.player_ids == [alice.id, bot1.id, None]

    def test_no_bot_account_left(self, client, alice):
        board = _waiting_board(alice)
        bot1, bot2 = _bots()
        board.assign_seat(1, bot1)
        bot2.is_bot = False  # the only other bot is taken
        db.session.commit()
        client.post("/join", data={"board": board.id, "fill_bot": "2"})
        assert _flashes(client) == ["No bot account available"]
        db.session.refresh(board)
        assert board.player_ids[2] is None

    def test_last_seat_starts_game_and_tells_seat_0(
        self, app, client, alice, monkeypatch
    ):
        from webapp import views

        calls = []
        monkeypatch.setattr(views, "post_notification", lambda *a: calls.append(a))
        bob = _create_user("bob")
        board = _waiting_board(bob)
        board.assign_seat(1, _create_user("carol"))
        db.session.commit()

        client.post("/join", data={"board": board.id, "seat": "2"})

        db.session.refresh(board)
        assert board.status == GameStatus.ACTIVE
        assert board.is_full
        assert calls == [
            (
                "bob",
                f"The game {board.id} just started, it's your turn",
                "Game started",
                board.id,
            )
        ]
        assert Log.query.filter_by(message="Game started", board_id=board.id).count()


class TestCancel:
    def test_owner_alone_deletes_it_and_keeps_its_logs(self, client, alice):
        client.post("/join", data={"seat": "Seat 1"})
        board_id = TriBoard.query.one().id
        client.post("/join", data={"delete": board_id})
        assert db.session.get(TriBoard, board_id) is None
        created = Log.query.filter_by(message="Game created").one()
        assert created.board_id is None  # detached, not deleted

    def test_not_once_someone_joined(self, client, alice):
        board = _waiting_board(alice)
        board.assign_seat(1, _create_user("bob"))
        db.session.commit()
        client.post("/join", data={"delete": board.id})
        assert db.session.get(TriBoard, board.id) is not None

    def test_only_the_owner(self, client, alice):
        board = _waiting_board(_create_user("bob"))
        client.post("/join", data={"delete": board.id})
        assert db.session.get(TriBoard, board.id) is not None


class TestAdminRequired:
    def test_page_redirects_non_admin_with_message(self, client, alice):
        resp = client.get("/admin-games")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/games")
        assert _flashes(client) == ["You are not admin."]

    @pytest.mark.parametrize("path", ["/admin-games", "/admin-users"])
    def test_form_post_from_non_admin_is_403(self, client, alice, path):
        assert client.post(path, data={"delete": alice.id}).status_code == 403
        assert db.session.get(User, alice.id) is not None
