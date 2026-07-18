"""Redis pub/sub fanout for "a move/vote was just persisted" push
notifications to any open game-board page (webapp/static/ondro.js only —
webapp/static/filio.js has its own renderer and doesn't use this).

Deliberately Flask-independent (reads REDIS_URL straight from os.environ, no
`current_app`/`app` import), mirroring webapp/notifications.py's shape — but
this is pub/sub, not an RQ queue: webapp/api.py's GameBoard.post() calls
publish_board_move() synchronously right after db.session.commit(), a
fire-and-forget PUBLISH with no worker/job involved. The consumer is
webapp/api.py's board_events() SSE route: one long-lived
subscribe_board_events() generator per open browser tab.
"""

import json
import os

from redis import Redis

_redis = Redis.from_url(
    os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True,
)

# Overridable the same way GUNICORN_WORKERS/THREADS are, for ops tuning
# against whatever idle-connection timeout sits in front (Traefik).
HEARTBEAT_INTERVAL = float(os.environ.get("SSE_HEARTBEAT_INTERVAL", 15))


def _channel(board_id: int) -> str:
    """One pub/sub channel per board id."""
    return f"trichess:board:{board_id}:moves"


def publish_board_move(board_id: int, slog_length: int) -> None:
    """Fire a "board_id changed" ping at any subscribed SSE connections.

    Payload is intentionally minimal — subscribers never render from it,
    they always refetch full state via the existing authenticated
    GET /api/v1/manager/board. slog_length (chars, 4 per persisted move or
    vote) is a monotonically increasing counter the client uses to tell
    "have I already synced past this" — e.g. to skip a redundant refresh
    when this ping is just the echo of the same tab's own just-submitted
    move/vote — without needing to trust the payload for rendering.
    """
    _redis.publish(_channel(board_id), json.dumps({"slog_length": slog_length}))


def subscribe_board_events(
    board_id: int, heartbeat_interval: float = HEARTBEAT_INTERVAL
):
    """Yield raw SSE wire chunks (strings) for one board's subscribers.

    Uses pubsub.get_message(timeout=...) polling rather than the blocking
    listen() iterator, so a periodic ": heartbeat\\n\\n" SSE comment (keeps
    an intermediary proxy from closing an otherwise-idle connection) is
    interleaved with real messages for free: get_message(timeout=N) blocks
    up to N seconds waiting for a message and returns None on timeout, so
    this loop emits a heartbeat at most every heartbeat_interval seconds
    when idle, or a `data:` line as soon as a move/vote is published.
    """
    pubsub = _redis.pubsub()
    channel = _channel(board_id)
    pubsub.subscribe(channel)
    try:
        while True:
            message = pubsub.get_message(
                timeout=heartbeat_interval, ignore_subscribe_messages=True
            )
            if message is None:
                yield ": heartbeat\n\n"
            else:
                yield f"data: {message['data']}\n\n"
    finally:
        pubsub.unsubscribe(channel)
        pubsub.close()
