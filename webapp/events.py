"""Redis pub/sub fanout for "a move/vote was just persisted" push
notifications to any open game-board page (webapp/static/ondro.js only —
webapp/static/filio.js has its own renderer and doesn't use this).

Deliberately Flask-independent (reads REDIS_URL straight from os.environ, no
`current_app`/`app` import), mirroring webapp/notifications.py's shape — but
this is pub/sub, not an RQ queue: webapp/api.py's GameBoard.post() calls
publish_board_move() synchronously right after db.session.commit(), a
fire-and-forget PUBLISH with no worker/job involved. The consumer is the
standalone async SSE service in sse/app.py (GET
/api/v1/manager/board/events), which holds one pattern subscription per
process and fans pings out to every open board tab.
"""

import json
import os

from redis import Redis

_redis = Redis.from_url(
    os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True,
)


def _channel(board_id: int) -> str:
    """One pub/sub channel per board id. sse/app.py subscribes to these by
    pattern (CHANNEL_PATTERN) — keep the two formats in sync."""
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
