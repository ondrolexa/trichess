import fakeredis
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from engine import get_game
from webapp import events
from webapp.main import db
from webapp.models import TriBoard, User


def _create_user(username, active=True):
    user = User(username=username, password=generate_password_hash("pw"), active=active)
    db.session.add(user)
    db.session.commit()
    return user


def _make_board(owner, seats, slog="", status=1):
    tb = TriBoard(
        owner_id=owner.id,
        player_0_id=seats[0].id,
        player_0_accepted=True,
        player_1_id=seats[1].id,
        player_1_accepted=True,
        player_2_id=seats[2].id,
        player_2_accepted=True,
        status=status,
        slog=slog,
    )
    db.session.add(tb)
    db.session.commit()
    return tb


class TestPublishBoardMove:
    def test_publish_reaches_a_subscriber(self, monkeypatch):
        fake = fakeredis.FakeStrictRedis(decode_responses=True)
        monkeypatch.setattr(events, "_redis", fake)
        pubsub = fake.pubsub()
        pubsub.subscribe(events._channel(42))
        pubsub.get_message(timeout=1)  # discard the subscribe-confirmation message

        events.publish_board_move(42, 7)

        msg = pubsub.get_message(timeout=1)
        assert msg["data"] == '{"slog_length": 7}'


class TestSubscribeBoardEvents:
    def test_yields_heartbeat_when_idle(self, monkeypatch):
        fake = fakeredis.FakeStrictRedis(decode_responses=True)
        monkeypatch.setattr(events, "_redis", fake)

        gen = events.subscribe_board_events(99, heartbeat_interval=0.05)
        assert next(gen) == ": heartbeat\n\n"

    def test_yields_a_published_message(self, monkeypatch):
        fake = fakeredis.FakeStrictRedis(decode_responses=True)
        monkeypatch.setattr(events, "_redis", fake)

        gen = events.subscribe_board_events(99, heartbeat_interval=5)
        # Prime the subscription before publishing, mirroring how a real
        # SSE connection subscribes well before any move happens.
        next(gen)
        events.publish_board_move(99, 3)
        assert next(gen) == 'data: {"slog_length": 3}\n\n'


class TestGameBoardPostPublishesEvent:
    def test_move_publishes_board_event(self, monkeypatch, app, client):
        from webapp import api

        published = []
        monkeypatch.setattr(
            api,
            "publish_board_move",
            lambda board_id, slog_length: published.append((board_id, slog_length)),
        )

        alice = _create_user("alice")
        bob = _create_user("bob")
        carol = _create_user("carol")
        tb = _make_board(alice, {0: alice, 1: bob, 2: carol}, slog="")

        ga = get_game(0, "")
        for hex in ga.board:
            if hex.has_piece and hex.piece.player.pid == 0:
                gid = ga.pos2gid[hex.pos]
                targets = ga.valid_moves(gid)
                if targets:
                    ga.make_move(gid, targets[0]["tgid"])
                    break

        with app.test_request_context():
            token = create_access_token(identity=alice.username)

        resp = client.post(
            "/api/v1/manager/board",
            json={"id": tb.id, "slog": ga.slog},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert published == [(tb.id, len(ga.slog))]


class TestBoardEventsAuth:
    def test_requires_token(self, client, app):
        resp = client.get("/api/v1/manager/board/events?id=1")
        assert resp.status_code in (401, 422)

    def test_rejects_non_participant(self, client, app):
        alice = _create_user("alice")
        bob = _create_user("bob")
        carol = _create_user("carol")
        eve = _create_user("eve")
        tb = _make_board(alice, {0: alice, 1: bob, 2: carol})

        with app.test_request_context():
            token = create_access_token(identity=eve.username)

        resp = client.get(f"/api/v1/manager/board/events?id={tb.id}&jwt={token}")
        assert resp.status_code == 404

    def test_rejects_missing_board(self, client, app):
        alice = _create_user("alice")
        with app.test_request_context():
            token = create_access_token(identity=alice.username)

        resp = client.get(f"/api/v1/manager/board/events?id=999999&jwt={token}")
        assert resp.status_code == 404
