"""The standalone SSE service (sse/app.py).

Its seat check queries the database directly (SQLAlchemy Core, no webapp
import), so the fixture builds a real temporary SQLite database from
webapp.models' own metadata — a schema change that
breaks SEATED_SQL fails here — and tokens come from flask-jwt-extended
itself, so the PyJWT decoding stays compatible with what /play mints.
"""

import asyncio
from datetime import timedelta

import fakeredis
import pytest
from flask_jwt_extended import create_access_token, create_refresh_token
from sqlalchemy import create_engine, insert
from starlette.testclient import TestClient

from sse import app as sse
from webapp.events import _channel
from webapp.models import TriBoard, User, db

# Fixed ids, so tokens (whose `sub` is the user id) can be minted without
# the database; "mallory" has no row.
IDS = {"alice": 101, "bob": 102, "carol": 103, "eve": 104, "mallory": 999}


@pytest.fixture
def db_url(tmp_path):
    path = tmp_path / "trichess.db"
    engine = create_engine(f"sqlite:///{path}")
    db.metadata.create_all(engine)
    with engine.begin() as conn:
        ids = {}
        for name in ("alice", "bob", "carol", "eve"):
            ids[name] = conn.execute(
                insert(User.__table__).values(id=IDS[name], username=name, password="x")
            ).inserted_primary_key[0]
        for board_id, status in ((10, 1), (11, 2), (12, 0)):
            conn.execute(
                insert(TriBoard.__table__).values(
                    id=board_id,
                    owner_id=ids["alice"],
                    player_0_id=ids["alice"],
                    player_1_id=ids["bob"],
                    player_2_id=ids["carol"],
                    status=status,
                    slog="",
                )
            )
    engine.dispose()
    return f"sqlite:///{path}"


@pytest.fixture
def secret(app):
    return app.config["JWT_SECRET_KEY"]


def _token(app, username, **kwargs):
    with app.test_request_context():
        return create_access_token(identity=str(IDS[username]), **kwargs)


def _client(db_url, secret, **kwargs):
    application = sse.create_app(
        redis=fakeredis.FakeAsyncRedis(decode_responses=True),
        db_url=db_url,
        jwt_secret=secret,
        background=False,
        **kwargs,
    )
    return TestClient(application)


class TestChannel:
    def test_matches_publisher_format(self):
        channel = _channel(42)
        assert sse.board_id_from_channel(channel) == 42
        prefix, suffix = sse.CHANNEL_PATTERN.split("*")
        assert channel.startswith(prefix) and channel.endswith(suffix)

    def test_rejects_foreign_channels(self):
        assert sse.board_id_from_channel("trichess:board:x:moves") is None
        assert sse.board_id_from_channel("other:board:1:moves") is None


class TestDecodeToken:
    def test_valid_access_token(self, app, secret):
        assert sse.decode_token(_token(app, "alice"), secret) == IDS["alice"]

    def test_expired(self, app, secret):
        token = _token(app, "alice", expires_delta=timedelta(seconds=-1))
        assert sse.decode_token(token, secret) is None

    def test_wrong_secret(self, app):
        assert sse.decode_token(_token(app, "alice"), "other-secret" * 3) is None

    def test_refresh_token_rejected(self, app, secret):
        with app.test_request_context():
            token = create_refresh_token(identity=str(IDS["alice"]))
        assert sse.decode_token(token, secret) is None

    def test_garbage(self, secret):
        assert sse.decode_token("not-a-jwt", secret) is None

    def test_username_sub_from_before_ids_rejected(self, app, secret):
        with app.test_request_context():
            token = create_access_token(identity="alice")
        assert sse.decode_token(token, secret) is None


class TestSeated:
    def test_seated_on_active_and_finished(self, db_url):
        assert sse.seated(create_engine(db_url), IDS["bob"], 10)
        assert sse.seated(create_engine(db_url), IDS["carol"], 11)

    def test_not_seated(self, db_url):
        assert not sse.seated(create_engine(db_url), IDS["eve"], 10)

    def test_waiting_board_and_unknown_board(self, db_url):
        assert not sse.seated(create_engine(db_url), IDS["alice"], 12)
        assert not sse.seated(create_engine(db_url), IDS["alice"], 999)


class TestEndpointErrors:
    def test_missing_id(self, app, db_url, secret):
        resp = _client(db_url, secret).get(sse.EVENTS_PATH)
        assert resp.status_code == 400

    def test_bad_token(self, app, db_url, secret):
        resp = _client(db_url, secret).get(f"{sse.EVENTS_PATH}?id=10&jwt=nope")
        assert resp.status_code == 401

    def test_unknown_user(self, app, db_url, secret):
        token = _token(app, "mallory")
        resp = _client(db_url, secret).get(f"{sse.EVENTS_PATH}?id=10&jwt={token}")
        assert resp.status_code == 401

    def test_not_seated(self, app, db_url, secret):
        token = _token(app, "eve")
        resp = _client(db_url, secret).get(f"{sse.EVENTS_PATH}?id=10&jwt={token}")
        assert resp.status_code == 404

    def test_cors_header_only_for_allowed_origin(self, app, db_url, secret):
        client = _client(db_url, secret, allowed_origins=["http://localhost:8080"])
        ok = client.get(sse.EVENTS_PATH, headers={"Origin": "http://localhost:8080"})
        assert ok.headers["access-control-allow-origin"] == "http://localhost:8080"
        other = client.get(sse.EVENTS_PATH, headers={"Origin": "http://evil.test"})
        assert "access-control-allow-origin" not in other.headers


class TestBroker:
    def test_fan_out_by_board(self):
        broker = sse.Broker()
        a, b, c = broker.subscribe(1), broker.subscribe(1), broker.subscribe(2)
        broker.publish(1, "ping")
        assert a.get_nowait() == "ping" and b.get_nowait() == "ping"
        assert c.empty()

    def test_broadcast_and_unsubscribe(self):
        broker = sse.Broker()
        a, b = broker.subscribe(1), broker.subscribe(2)
        broker.broadcast(sse.HEARTBEAT)
        assert a.get_nowait() is sse.HEARTBEAT and b.get_nowait() is sse.HEARTBEAT
        broker.unsubscribe(1, a)
        broker.unsubscribe(2, b)
        assert broker.subscribers == {}

    def test_full_queue_drops_instead_of_raising(self):
        broker = sse.Broker()
        queue = broker.subscribe(1)
        for _ in range(sse.QUEUE_SIZE + 3):
            broker.publish(1, "ping")
        assert queue.qsize() == sse.QUEUE_SIZE


async def _run_response(broker, receive):
    sent = []

    async def send(message):
        sent.append(message)

    response = sse.SSEResponse(broker, 7, {})
    task = asyncio.create_task(response({"type": "http"}, receive, send))
    await asyncio.sleep(0.01)
    return task, sent


def _bodies(sent):
    return [m["body"].decode() for m in sent if m["type"] == "http.response.body"]


class TestSSEResponse:
    @pytest.mark.asyncio
    async def test_streams_until_close_then_unsubscribes(self):
        broker = sse.Broker()
        never = asyncio.Event()

        async def receive():
            await never.wait()

        task, sent = await _run_response(broker, receive)
        assert broker.connections == 1
        broker.publish(7, '{"slog_length": 4}')
        broker.broadcast(sse.HEARTBEAT)
        broker.broadcast(sse.CLOSE)
        await asyncio.wait_for(task, 1)

        assert sent[0]["status"] == 200
        assert _bodies(sent) == [
            ": connected\n\n",
            'data: {"slog_length": 4}\n\n',
            ": heartbeat\n\n",
            "",
        ]
        assert broker.connections == 0

    @pytest.mark.asyncio
    async def test_client_disconnect_unsubscribes(self):
        broker = sse.Broker()
        gone = asyncio.Event()

        async def receive():
            await gone.wait()
            return {"type": "http.disconnect"}

        task, _ = await _run_response(broker, receive)
        assert broker.connections == 1
        gone.set()
        await asyncio.wait_for(task, 1)
        assert broker.connections == 0


class TestListenRedis:
    @pytest.mark.asyncio
    async def test_published_ping_reaches_subscriber(self):
        redis = fakeredis.FakeAsyncRedis(decode_responses=True)
        broker = sse.Broker()
        queue = broker.subscribe(5)
        task = asyncio.create_task(sse.listen_redis(redis, broker))
        try:
            await asyncio.sleep(0.05)  # let the PSUBSCRIBE land
            await redis.publish(_channel(5), '{"slog_length": 8}')
            assert await asyncio.wait_for(queue.get(), 1) == '{"slog_length": 8}'
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_heartbeat_reaches_every_stream(self):
        broker = sse.Broker()
        a, b = broker.subscribe(1), broker.subscribe(2)
        task = asyncio.create_task(sse.heartbeat(broker, 0.01))
        try:
            assert await asyncio.wait_for(a.get(), 1) is sse.HEARTBEAT
            assert await asyncio.wait_for(b.get(), 1) is sse.HEARTBEAT
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
