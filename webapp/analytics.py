"""Google Analytics 4: server-side helpers for the consent-gated tag that
static/analytics.js loads. Lobby and account events are queued in the
session here and sent by the next rendered page; the board page reports
gameplay milestones itself. See the help page's developer tab for the
event list.
"""

import hashlib
import hmac
from datetime import timedelta

from flask import g, request, session

from webapp.main import app
from webapp.models import Score, utcnow_naive


def track_event(name, **params):
    """Queue a GA4 event to be emitted by the next rendered page.

    Account/lobby actions all end in a redirect, so the event rides the
    session to the page that follows and is sent from the browser — under
    the visitor's own consent state, no server-side Measurement Protocol
    needed. In-game milestones are sent by analytics.js from the board
    page instead. Only non-identifying params belong in **params.
    """
    if not app.config["GA_MEASUREMENT_ID"]:
        return
    events = session.get("ga_events", [])
    events.append({"name": name, "params": params})
    session["ga_events"] = events[-10:]


def minutes_since(ts):
    """Whole minutes from naive-UTC *ts* to now (GA `wait_time`)."""
    if ts is None:
        return 0
    now = utcnow_naive()
    return max(0, int((now - ts).total_seconds() // 60))


def game_minutes(tb):
    """Whole minutes from a finished game's start to its last move."""
    if tb.started_at is None or tb.modified_at is None:
        return 0
    return max(0, int((tb.modified_at - tb.started_at).total_seconds() // 60))


def opponents(tb):
    """Board make-up for analytics: "bots" (2 bot seats), "mixed" (1) or
    "humans" — a browser viewer is always human, so it's their opponents."""
    return {2: "bots", 1: "mixed"}.get(tb.bot_count, "humans")


# GA user properties: rating classes (ratings start at 500, K=9) and rated
# games played; bot games are casual and never counted.
ELO_CLASSES = ((600, "Advanced"), (525, "Intermediate"), (0, "Novice"))
GAMES_PLAYED_TIERS = ((51, "51+"), (21, "21-50"), (6, "6-20"), (1, "1-5"), (0, "0"))

# A finished game opened this soon after its end still reports
# game_completed to a player who wasn't watching when it ended.
LATE_COMPLETION_WINDOW = timedelta(days=7)


def _classify(value, classes):
    return next(label for threshold, label in classes if value >= threshold)


def ga_config(game=None):
    """Per-page GA4 settings for _analytics.html, or None to omit the tag.

    `game` is the board page's context for analytics.js's trichessGame hooks.
    """
    events = session.pop("ga_events", [])
    if not app.config["GA_MEASUREMENT_ID"] or app.debug:
        return None
    authenticated = g.user is not None and g.user.is_authenticated
    if authenticated and g.user.is_admin:
        return None
    config = {
        "id": app.config["GA_MEASUREMENT_ID"],
        "content_group": request.endpoint or "",
        "user_id": None,
        "user_properties": {"logged_in": "yes" if authenticated else "no"},
        "events": events,
        "game": game,
    }
    if authenticated:
        # Opaque, stable per-user id: never the username/email or raw db id.
        config["user_id"] = hmac.new(
            app.config["SECRET_KEY"].encode(),
            f"ga-user-{g.user.id}".encode(),
            hashlib.sha256,
        ).hexdigest()[:32]
        rated_games = Score.query.filter_by(player_id=g.user.id).count()
        config["user_properties"].update(
            board_renderer=g.user.board or "",
            ui_theme=g.user.theme or "",
            piece_set=g.user.pieces or "",
            elo_class=_classify(g.user.rating or 0, ELO_CLASSES),
            games_played_tier=_classify(rated_games, GAMES_PLAYED_TIERS),
        )
    return config
