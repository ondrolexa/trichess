"""Google Analytics 4: server-side helpers for the consent-gated tag that
static/analytics.js loads. Lobby and account events are queued in the
session here and sent by the next rendered page; the board page reports
gameplay milestones itself. The event catalogue below is the single list of
what may be sent; the help page's developer tab documents it.
"""

import hashlib
import hmac
from datetime import timedelta

from flask import g, request, session

from engine import slog_summary
from webapp.main import app
from webapp.models import GameStatus, Score, utcnow_naive

# Events queued by track_event(), with the parameters each may carry.
# Naming: object_action in the past tense (GA's recommended login/sign_up
# kept), one name per concept across events, units in time parameters.
SERVER_EVENTS = {
    "login": frozenset({"method"}),
    "sign_up": frozenset({"method"}),
    "email_verified": frozenset(),
    "contact_sent": frozenset({"has_attachment"}),
    "pref_changed": frozenset({"pref", "pref_value", "previous_value"}),
    "game_created": frozenset({"seat"}),
    "game_joined": frozenset({"seat"}),
    "bot_seat_added": frozenset({"seat"}),
    "game_cancelled": frozenset({"wait_minutes"}),
    "bot_game_deleted": frozenset({"total_turns", "duration_minutes"}),
    "archive_viewed": frozenset({"context"}),
}

# Events static/analytics.js sends itself (documentation; JS isn't checked).
# Board events also carry BOARD_COMMON.
BOARD_COMMON = frozenset({"game_type", "board_renderer", "seat"})
BROWSER_EVENTS = {
    "prefs_snapshot": frozenset({"board_renderer", "ui_theme", "piece_set"}),
    "game_started": frozenset({"wait_minutes"}),
    "first_move": frozenset(),
    "vote_cast": frozenset({"kind"}),
    "game_completed": frozenset(
        {"endgame", "duration_minutes", "total_turns", "placement", "points"}
    ),
    "archive_viewed": frozenset({"context"}),
}

# User model column -> GA parameter name of the display preferences.
PREF_PARAMS = {"board": "board_renderer", "theme": "ui_theme", "pieces": "piece_set"}


def track_event(name, **params):
    """Queue a GA4 event to be emitted by the next rendered page.

    Account/lobby actions all end in a redirect, so the event rides the
    session to the page that follows and is sent from the browser — under
    the visitor's own consent state, no server-side Measurement Protocol
    needed. In-game milestones are sent by analytics.js from the board
    page instead. Only non-identifying params belong in **params.

    Raises ValueError for an event or parameter missing from SERVER_EVENTS,
    even with analytics off, so a typo fails the tests instead of quietly
    starting a new GA event.
    """
    allowed = SERVER_EVENTS.get(name)
    if allowed is None:
        raise ValueError(f"unknown GA event {name!r}")
    if unknown := set(params) - allowed:
        raise ValueError(f"GA event {name!r}: unknown params {sorted(unknown)}")
    if not app.config["GA_MEASUREMENT_ID"]:
        return
    events = session.get("ga_events", [])
    events.append({"name": name, "params": params})
    session["ga_events"] = events[-10:]


def minutes_since(ts):
    """Whole minutes from naive-UTC *ts* to now."""
    if ts is None:
        return 0
    return minutes_between(ts, utcnow_naive())


def minutes_between(start, end):
    """Whole minutes from *start* to *end* (naive UTC), 0 if either is unset."""
    if start is None or end is None:
        return 0
    return max(0, int((end - start).total_seconds() // 60))


def game_type(tb):
    """Board make-up: "bots" (2 bot seats), "mixed" (1) or "humans" — a
    browser viewer is always human, so it's their opponents."""
    return {2: "bots", 1: "mixed"}.get(tb.bot_count, "humans")


def board_renderer(user):
    return "ondro" if user.board == "ondro" else "filio"


# GA user properties: rating classes (ratings start at 500, K=9) and rated
# games played; bot games are casual and never counted.
ELO_CLASSES = ((600, "Advanced"), (525, "Intermediate"), (0, "Novice"))
GAMES_PLAYED_TIERS = ((51, "51+"), (21, "21-50"), (6, "6-20"), (1, "1-5"), (0, "0"))

# A game opened this soon after it started (game_started) or ended
# (game_completed) still reports it to a player who wasn't watching then.
LATE_WINDOW = timedelta(days=7)


def _classify(value, classes):
    return next(label for threshold, label in classes if value >= threshold)


def board_context(tb, user):
    """The board page's game context for analytics.js's trichessGame hooks."""
    seat = tb.seat_of(user.id)
    active = tb.status == GameStatus.ACTIVE
    finished = tb.status == GameStatus.FINISHED
    since = utcnow_naive() - LATE_WINDOW
    return {
        "board_id": tb.id,
        "seat": seat,
        "game_type": game_type(tb),
        "board_renderer": board_renderer(user),
        # Seats move in order 0, 1, 2, so seat s has moved once more than
        # s moves were made.
        "has_moved": slog_summary(tb.slog or "").move_number > seat,
        # game_started: once per player, on their first view of a game that
        # started recently; wait_minutes is creation to start.
        "started_recently": active
        and tb.started_at is not None
        and tb.started_at > since,
        "wait_minutes": minutes_between(tb.created_at, tb.started_at),
        # game_completed's duration_minutes: minutes since the start while
        # the game runs; start to last move once it's over.
        "started_minutes_ago": minutes_since(tb.started_at),
        "duration_minutes": minutes_between(tb.started_at, tb.modified_at)
        if finished
        else None,
        # A finished game seen for the first time soon after its end still
        # reports game_completed (once per browser).
        "finished_recently": finished
        and tb.modified_at is not None
        and tb.modified_at > since,
    }


def ga_config(game=None):
    """Per-page GA4 settings for _analytics.html, or None to omit the tag.

    `game` is the board page's board_context() for analytics.js.
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
        # Player class only: it segments every event. Display preferences
        # go as prefs_snapshot event params instead (see "prefs").
        "user_properties": {"logged_in": "yes" if authenticated else "no"},
        "prefs": None,
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
            elo_class=_classify(g.user.rating or 0, ELO_CLASSES),
            games_played_tier=_classify(rated_games, GAMES_PLAYED_TIERS),
        )
        config["prefs"] = {
            "board_renderer": board_renderer(g.user),
            "ui_theme": g.user.theme or "",
            "piece_set": g.user.pieces or "",
        }
    return config
