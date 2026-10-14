"""Board live-update stream: ``GET /api/v1/manager/board/events?id=&jwt=``.

Run with ``uvicorn sse.app:app --port 8090``. The reverse proxy (Traefik)
routes only this path here; every other request stays on gunicorn.

Why a separate async service: under gunicorn's gthread worker every open
board tab pinned one thread (and one Redis pubsub connection) for as long
as the tab stayed open, capping concurrent viewers at workers x threads.
Here each connection is a coroutine waiting on an ``asyncio.Queue`` and the
whole process shares a single Redis pattern subscription:

    Flask publish_board_move() --PUBLISH trichess:board:<id>:moves-->
    Redis --PSUBSCRIBE (one per process)--> Broker --> Queue per open tab

Auth matches the old Flask route: the page's JWT in the ``jwt`` query
parameter (EventSource can't set headers), checked with the same
JWT_SECRET_KEY, plus one read-only SQL lookup that the user is seated at
that board (status 1 active or 2 finished, so a tab open when the game ends
still gets the final ping).
"""

import asyncio
import contextlib
import logging
import os
from pathlib import Path

import jwt
from dotenv import load_dotenv
from redis import asyncio as aioredis
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Route

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger("trichess.sse")

EVENTS_PATH = "/api/v1/manager/board/events"
# Must match webapp/events.py's _channel() (asserted in tests/test_sse.py).
CHANNEL_PATTERN = "trichess:board:*:moves"
QUEUE_SIZE = 8

HEARTBEAT = object()
CLOSE = object()


def _secret(name):
    """Same fail-closed rule as webapp/configuration.py's _secret()."""
    value = os.environ.get(name)
    if value:
        return value
    debug = os.environ.get("DEBUG", "false").lower() == "true" or os.environ.get(
        "FLASK_DEBUG", ""
    ).lower() in ("1", "true")
    if not debug:
        raise RuntimeError(f"{name} must be set (see README) unless DEBUG=true")
    return "dev-only-insecure-key"


def board_id_from_channel(channel: str) -> int | None:
    """``trichess:board:42:moves`` -> 42, or None for anything else."""
    parts = channel.split(":")
    if len(parts) != 4 or parts[:2] != ["trichess", "board"] or parts[3] != "moves":
        return None
    try:
        return int(parts[2])
    except ValueError:
        return None


def decode_token(raw: str, secret: str) -> str | None:
    """Username from a flask-jwt-extended access token, or None if invalid,
    expired, or not an access token."""
    try:
        claims = jwt.decode(raw, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None
    if claims.get("type") != "access":
        return None
    sub = claims.get("sub")
    return sub if isinstance(sub, str) else None


# "user" quoted: a reserved word in PostgreSQL (harmless in SQLite).
USER_EXISTS_SQL = text('SELECT 1 FROM "user" WHERE username = :username LIMIT 1')
SEATED_SQL = text("""
SELECT 1 FROM triboard b JOIN "user" u ON u.username = :username
WHERE b.id = :board_id AND b.status IN (1, 2)
  AND u.id IN (b.player_0_id, b.player_1_id, b.player_2_id)
LIMIT 1
""")


def user_exists(engine: Engine, username: str) -> bool:
    with engine.connect() as conn:
        row = conn.execute(USER_EXISTS_SQL, {"username": username}).first()
    return row is not None


def seated(engine: Engine, username: str, board_id: int) -> bool:
    """True if *username* sits at active/finished board *board_id* — the
    read-only equivalent of TriBoard.for_player() + status 1/2."""
    with engine.connect() as conn:
        row = conn.execute(
            SEATED_SQL, {"username": username, "board_id": board_id}
        ).first()
    return row is not None


class Broker:
    """In-memory fan-out: board id -> the queues of its open streams."""

    def __init__(self):
        self.subscribers: dict[int, set[asyncio.Queue]] = {}

    def subscribe(self, board_id: int) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.subscribers.setdefault(board_id, set()).add(queue)
        return queue

    def unsubscribe(self, board_id: int, queue: asyncio.Queue) -> None:
        queues = self.subscribers.get(board_id)
        if queues is None:
            return
        queues.discard(queue)
        if not queues:
            del self.subscribers[board_id]

    def publish(self, board_id: int, item) -> None:
        for queue in self.subscribers.get(board_id, ()):
            _offer(queue, item)

    def broadcast(self, item) -> None:
        for queues in self.subscribers.values():
            for queue in queues:
                _offer(queue, item)

    @property
    def connections(self) -> int:
        return sum(len(q) for q in self.subscribers.values())


def _offer(queue: asyncio.Queue, item) -> None:
    # A full queue belongs to a client that stopped reading; pings only mean
    # "refetch the board", so dropping one is harmless.
    with contextlib.suppress(asyncio.QueueFull):
        queue.put_nowait(item)


async def listen_redis(redis, broker: Broker, max_backoff: float = 30.0) -> None:
    """Single PSUBSCRIBE for the whole process, fanned out via *broker*.

    Pings published while the subscription was down are lost, so after a
    reconnect every open stream is closed: browsers reconnect, and ondro.js's
    onopen handler resyncs the board from the API.
    """
    backoff = 1.0
    reconnecting = False
    while True:
        pubsub = redis.pubsub()
        try:
            await pubsub.psubscribe(CHANNEL_PATTERN)
            if reconnecting:
                logger.warning("Redis subscription restored; closing streams")
                broker.broadcast(CLOSE)
            backoff = 1.0
            async for message in pubsub.listen():
                if message["type"] != "pmessage":
                    continue
                board_id = board_id_from_channel(_text(message["channel"]))
                if board_id is not None:
                    broker.publish(board_id, _text(message["data"]))
        except asyncio.CancelledError:
            raise
        except Exception as err:
            logger.error("Redis subscription lost: %s", err)
        finally:
            with contextlib.suppress(Exception):
                await pubsub.aclose()
        reconnecting = True
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, max_backoff)


async def heartbeat(broker: Broker, interval: float) -> None:
    """Periodic SSE comment on every stream, so proxies keep idle ones open."""
    while True:
        await asyncio.sleep(interval)
        broker.broadcast(HEARTBEAT)


def _text(value) -> str:
    return value.decode() if isinstance(value, bytes) else value


async def stream_events(queue: asyncio.Queue):
    """SSE wire chunks for one connection, until CLOSE arrives."""
    yield ": connected\n\n"
    while True:
        item = await queue.get()
        if item is CLOSE:
            return
        if item is HEARTBEAT:
            yield ": heartbeat\n\n"
        else:
            yield f"data: {item}\n\n"


class SSEResponse(Response):
    """Streams one subscriber queue and unsubscribes when either side ends.

    Not Starlette's StreamingResponse: under ASGI spec 2.4 (uvicorn) that
    only notices a gone client when a write fails, i.e. up to a heartbeat
    later, and cleanup then depends on generator finalization. Here a
    disconnect is read from ``receive`` directly and cleanup is a ``finally``.
    """

    media_type = "text/event-stream"

    def __init__(self, broker: Broker, board_id: int, headers: dict):
        # Mirrors StreamingResponse.__init__: no self.body, so init_headers()
        # doesn't add a Content-Length that would end the stream.
        self.status_code = 200
        self.background = None
        self.init_headers(headers)
        self.broker = broker
        self.board_id = board_id

    async def __call__(self, scope, receive, send):
        queue = self.broker.subscribe(self.board_id)
        try:
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": self.raw_headers,
                }
            )
            pump = asyncio.create_task(self._pump(queue, send))
            watch = asyncio.create_task(_wait_disconnect(receive))
            try:
                await asyncio.wait({pump, watch}, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in (pump, watch):
                    task.cancel()
                await asyncio.gather(pump, watch, return_exceptions=True)
            if pump.done() and not pump.cancelled() and pump.exception() is None:
                # Server-side close (CLOSE sentinel): finish the HTTP response.
                with contextlib.suppress(OSError):
                    await send(
                        {"type": "http.response.body", "body": b"", "more_body": False}
                    )
        finally:
            self.broker.unsubscribe(self.board_id, queue)

    async def _pump(self, queue, send):
        async for chunk in stream_events(queue):
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk.encode(),
                    "more_body": True,
                }
            )


async def _wait_disconnect(receive):
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return


def create_app(
    *,
    redis=None,
    db_url: str | None = None,
    jwt_secret: str | None = None,
    heartbeat_interval: float | None = None,
    allowed_origins: list[str] | None = None,
    background: bool = True,
) -> Starlette:
    """Build the ASGI app. Keyword overrides exist for tests."""
    # Same database URL as the Flask app (shared .env / compose env). The
    # engine connects lazily, so building it at import costs nothing.
    engine = create_engine(
        db_url
        or os.environ.get(
            "SQLALCHEMY_DATABASE_URI", f"sqlite:///{ROOT / 'instance' / 'trichess.db'}"
        ),
        pool_pre_ping=True,
    )
    jwt_secret = jwt_secret or _secret("JWT_SECRET_KEY")
    if heartbeat_interval is None:
        heartbeat_interval = float(os.environ.get("SSE_HEARTBEAT_INTERVAL", 15))
    if allowed_origins is None:
        allowed_origins = [
            o.strip()
            for o in os.environ.get("CORS_ORIGINS", "").split(",")
            if o.strip()
        ]
    if redis is None:
        redis = aioredis.Redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
    broker = Broker()

    def cors(request: Request) -> dict:
        # Only needed when the page and this service are on different
        # origins (local dev with SSE_URL set); production is same-origin.
        origin = request.headers.get("origin")
        if origin and origin in allowed_origins:
            return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
        return {}

    async def board_events(request: Request) -> Response:
        headers = cors(request)
        try:
            board_id = int(request.query_params["id"])
        except KeyError, ValueError:
            return PlainTextResponse("Bad request", 400, headers=headers)
        username = decode_token(request.query_params.get("jwt", ""), jwt_secret)
        if username is None or not await asyncio.to_thread(
            user_exists, engine, username
        ):
            return PlainTextResponse("Unauthorized", 401, headers=headers)
        if not await asyncio.to_thread(seated, engine, username, board_id):
            return PlainTextResponse("Not found", 404, headers=headers)
        headers.update({"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        return SSEResponse(broker, board_id, headers)

    async def health(request: Request) -> Response:
        return PlainTextResponse(f"ok {broker.connections}")

    @contextlib.asynccontextmanager
    async def lifespan(app):
        tasks = []
        if background:
            tasks = [
                asyncio.create_task(listen_redis(redis, broker)),
                asyncio.create_task(heartbeat(broker, heartbeat_interval)),
            ]
        try:
            yield
        finally:
            broker.broadcast(CLOSE)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await redis.aclose()
            engine.dispose()

    app = Starlette(
        routes=[
            Route(EVENTS_PATH, board_events),
            Route("/healthz", health),
        ],
        lifespan=lifespan,
    )
    app.state.broker = broker
    return app


app = create_app()
