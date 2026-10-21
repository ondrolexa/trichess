"""
When models change, update migrations
# DEVELOPMENT (against the dev PostgreSQL from docker-compose.dev.yml)
flask --app=webapp db migrate -m "Added user verification status"
flask --app=webapp db upgrade

# PRODUCTION
Rerun flask --app=webapp db upgrade with production database
(Revisions before the PostgreSQL switch are SQLite-era; databases are created
from the models or a dump and stamped at head, never replayed from base.)
"""

import hashlib
import hmac
import logging
import os
import secrets
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import yaml
from flask import abort, flash, g, jsonify, redirect, request, session, url_for
from flask import render_template as real_render_template
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    jwt_required,
)
from flask_login import current_user, login_required, login_user, logout_user
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

from engine import slog_summary
from webapp.api import blueprint as api
from webapp.api import get_user_rating_history, rebuild_ratings
from webapp.botplayer import maybe_trigger_bot
from webapp.email import (
    send_account_exists_email,
    send_contact_email,
    send_password_reset_email,
    send_verification_email,
)
from webapp.forms import (
    ContactForm,
    ForgotPasswordForm,
    LoginForm,
    NewGameForm,
    PasswordForm,
    ProfileForm,
    RegistrationForm,
    ResetPasswordForm,
)
from webapp.main import GAME, app, csrf, db, jwt, limiter, lm, post_notification
from webapp.main import __version__ as webapp_version
from webapp.maintenance import is_maintenance, set_maintenance
from webapp.models import Log, RatingHistory, Score, TriBoard, User, score_outcome
from webapp.token import (
    password_fingerprint,
    verify_password_reset_token,
    verify_verification_token,
)

logger = logging.getLogger(__name__)


@app.template_filter("strftime")
def _jinja2_filter_datetime(date, fmt="%b %d, %Y %H:%M:%S"):
    utc = date.replace(tzinfo=ZoneInfo("UTC"))
    native = utc.astimezone(ZoneInfo("Europe/Prague"))
    return native.strftime(fmt)


@app.template_filter("deltatime")
def _jinja2_filter_timedelta(date):
    utc = date.replace(tzinfo=ZoneInfo("UTC"))
    native = utc.astimezone(ZoneInfo("Europe/Prague"))
    now = datetime.now(tz=ZoneInfo("Europe/Prague")).replace(microsecond=0)
    return str(now - native) + " ago"


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


def _minutes_since(ts):
    """Whole minutes from naive-UTC *ts* to now (GA `wait_time`)."""
    if ts is None:
        return 0
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return max(0, int((now - ts).total_seconds() // 60))


def _game_minutes(tb):
    """Whole minutes from a finished game's start to its last move."""
    if tb.started_at is None or tb.modified_at is None:
        return 0
    return max(0, int((tb.modified_at - tb.started_at).total_seconds() // 60))


def _opponents(tb):
    """Board make-up for analytics: "bots" (2 bot seats), "mixed" (1) or
    "humans" — a browser viewer is always human, so it's their opponents."""
    bots = sum(
        1 for p in (tb.player_0, tb.player_1, tb.player_2) if p is not None and p.is_bot
    )
    return {2: "bots", 1: "mixed"}.get(bots, "humans")


# GA user properties: rating classes (ratings start at 500, K=9) and rated
# games played; bot games are casual and never counted.
ELO_CLASSES = ((600, "Advanced"), (525, "Intermediate"), (0, "Novice"))
GAMES_PLAYED_TIERS = ((51, "51+"), (21, "21-50"), (6, "6-20"), (1, "1-5"), (0, "0"))

# A finished game opened this soon after its end still reports
# game_completed to a player who wasn't watching when it ended.
LATE_COMPLETION_WINDOW = timedelta(days=7)


def _classify(value, classes):
    return next(label for threshold, label in classes if value >= threshold)


def _ga_config(game=None):
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


def render_template(*args, **kwargs):
    navailable = TriBoard.query.filter_by(status=0).count()
    base_dir = os.path.abspath(os.path.dirname(__file__))
    themes_dir = os.path.join(base_dir, "static/themes")
    default_theme_file = os.path.join(themes_dir, "default.yaml")

    if g.user is not None and g.user.is_authenticated:
        theme_name = g.user.theme
        # Validate theme name to prevent path traversal
        if (
            theme_name is None
            or "/" in theme_name
            or "\\" in theme_name
            or ".." in theme_name
        ):
            theme_file = default_theme_file
        else:
            theme_file = os.path.join(themes_dir, f"{theme_name}.yaml")
            # Ensure the path is still inside themes_dir
            if not os.path.abspath(theme_file).startswith(themes_dir + os.sep):
                theme_file = default_theme_file
    else:
        theme_file = default_theme_file
    with open(theme_file) as f:
        theme = yaml.safe_load(f)
    if "board" not in kwargs:
        kwargs["board"] = False
    ga_game = kwargs.pop("ga_game", None)

    return real_render_template(
        *args,
        **kwargs,
        navailable=navailable,
        theme=theme,
        version=webapp_version,
        ga_config=_ga_config(ga_game),
        maintenance=is_maintenance(),
        contact_enabled=contact_enabled(),
    )


@jwt.expired_token_loader
def expired_token_response(jwt_header, jwt_payload):
    return jsonify({"message": "Token has expired"}), 401


@jwt.user_lookup_loader
def jwt_user(jwt_header, jwt_payload):
    """The User a token's `sub` (the user id) names; None -> 401.

    Tokens from before ids were used (a username), and tokens of removed
    users, resolve to None. Bots are inactive accounts but play via tokens.
    """
    try:
        user = db.session.get(User, int(jwt_payload["sub"]))
    except KeyError, TypeError, ValueError:
        return None
    if user is None or not (user.active or user.is_bot):
        return None
    return user


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if request.form.get("action") == "login":
            return redirect(url_for("login"))
        elif request.form.get("action") == "logout":
            return redirect(url_for("logout"))
        elif request.form.get("action") == "register":
            return redirect(url_for("register"))
        else:
            return redirect(url_for("index"))
    if g.user.is_authenticated and not g.user.is_admin:
        return redirect(url_for("active_games"))
    return render_template("index.html")


@app.route("/games")
@login_required
def active_games():
    user_in = TriBoard.for_player(g.user.id)
    active = (
        TriBoard.query.filter_by(status=1)
        .filter(user_in)
        .order_by(TriBoard.modified_at.desc())
        .all()
    )
    # add onmove and voting attributes
    for game in active:
        summary = slog_summary(game.slog or "")
        game.onmove = summary.on_move
        game.voting = summary.voting_active
    return render_template(
        "games.html", games=active, uid=g.user.id, board=g.user.board
    )


GAMES_PER_PAGE = 50


def _paginate(query, arg="page"):
    return query.paginate(
        page=request.args.get(arg, 1, type=int),
        per_page=GAMES_PER_PAGE,
        error_out=False,
    )


@app.route("/archive")
@login_required
def archive():
    user_in = TriBoard.for_player(g.user.id)
    pagination = _paginate(
        TriBoard.query.filter_by(status=2)
        .filter(user_in)
        .order_by(TriBoard.modified_at.desc())
    )
    games = pagination.items
    scores = {
        (s.board_id, s.player_id): s.score
        for s in Score.query.filter(Score.board_id.in_([game.id for game in games]))
    }
    for game in games:
        for seat in range(3):
            player_id = getattr(game, f"player_{seat}_id")
            setattr(game, f"player_{seat}_score", scores.get((game.id, player_id), 0.0))
        game.moves = slog_summary(game.slog or "").move_number
    if request.args.get("page", 1, type=int) == 1:
        track_event("view_archive", context="list")
    return render_template(
        "archive.html", games=games, pagination=pagination, board=g.user.board
    )


@app.route("/rating")
@login_required
def rating():
    users = (
        User.query.filter_by(is_bot=False)
        .order_by(User.rating.desc())  # .filter(User.last_login is not None)
        .all()
    )
    # Finished games played and the latest one, per user: one grouped query
    # per seat column, merged.
    played = defaultdict(int)
    last_game = {}
    for seat in range(3):
        column = getattr(TriBoard, f"player_{seat}_id")
        rows = (
            db.session.query(
                column, db.func.count(TriBoard.id), db.func.max(TriBoard.modified_at)
            )
            .filter(TriBoard.status == 2, column.is_not(None))
            .group_by(column)
        )
        for user_id, count, last in rows:
            played[user_id] += count
            if user_id not in last_game or last > last_game[user_id]:
                last_game[user_id] = last
    # Score sums and win/coop/pass/loss counts, per user, from one query.
    totals = defaultdict(float)
    counts = defaultdict(lambda: {"win": 0, "coop": 0, "pass": 0, "loss": 0})
    for player_id, score, onmove, tag in db.session.query(
        Score.player_id, Score.score, Score.onmove, Score.tag
    ):
        totals[player_id] += score
        counts[player_id][score_outcome(score, onmove, tag)] += 1

    ratings = []
    pos = 1
    for user in users:
        user.score = totals[user.id]
        user.played_games = played[user.id]
        if user.played_games > 0:
            user.last_game = last_game[user.id]
            user.position = pos
            pos += 1
            user.counts = counts[user.id]
            ratings.append(user)
    return render_template("rating.html", ratings=ratings, uid=g.user.id)


@app.route("/join", methods=["GET", "POST"])
@login_required
def available_games():
    if request.method == "POST":
        delete = request.form.get("delete", type=int)
        if delete is not None:
            board = db.session.get(TriBoard, delete)
            if board and board.owner_id == g.user.id and board.status == 0:
                others = [
                    p
                    for p in (
                        board.player_0_id,
                        board.player_1_id,
                        board.player_2_id,
                    )
                    if p is not None and p != g.user.id
                ]
                if not others:
                    wait_time = _minutes_since(board.created_at)
                    db.session.delete(board)
                    db.session.commit()
                    track_event("game_cancelled", wait_time=wait_time)
            return redirect(url_for("available_games"))

        board_id = request.form.get("board", type=int)
        if board_id is not None:
            board = (
                db.session.query(TriBoard)
                # Concurrent joins of the same game serialise here. FOR NO KEY
                # UPDATE: the "Game started" log row may reference it meanwhile.
                .with_for_update(key_share=True)
                .filter_by(id=board_id, status=0)
                .first()
            )
            seat = request.form.get("seat")
            fill_bot = request.form.get("fill_bot")
            if board is None:
                flash("Game not found or already started", "error")
                return redirect(url_for("available_games"))
            seat_str = fill_bot if fill_bot is not None else seat
            if seat_str not in ("0", "1", "2"):
                flash("Invalid seat", "error")
                return redirect(url_for("available_games"))
            column = f"player_{seat_str}_id"
            if getattr(board, column) is not None:
                flash("Seat already taken", "error")
                return redirect(url_for("available_games"))
            seated = {board.player_0_id, board.player_1_id, board.player_2_id} - {None}
            if fill_bot is not None:
                if board.owner_id != g.user.id:
                    flash("Only the game owner can add a bot", "error")
                    return redirect(url_for("available_games"))
                newcomer = (
                    User.query.filter_by(is_bot=True)
                    .filter(User.id.notin_(seated))
                    .first()
                )
                if newcomer is None:
                    flash("No bot account available", "error")
                    return redirect(url_for("available_games"))
            else:
                # One seat per player: two seats for one user would map to a
                # single seat in the game (api._seat_map) and stall it.
                if g.user.id in seated:
                    flash("You already have a seat in this game", "warning")
                    return redirect(url_for("available_games"))
                newcomer = g.user
            setattr(board, column, newcomer.id)
            setattr(board, f"player_{seat_str}_accepted", True)
            if (
                (board.player_0_id is not None)
                and (board.player_1_id is not None)
                and (board.player_2_id is not None)
            ):
                board.status = 1
                board.started_at = datetime.now(timezone.utc)
                logger.log(
                    GAME,
                    "Game started",
                    extra={
                        "user_id": g.user.id,
                        "board_id": board.id,
                    },
                )
                # send notification to first player
                if not board.player_0.is_bot:
                    post_notification(
                        board.player_0.username,
                        f"The game {board.id} just started, it's your turn",
                        "Game started",
                        board.id,
                    )
            db.session.commit()
            if fill_bot is not None:
                track_event("bot_seat_added", seat=int(seat_str))
            else:
                track_event("game_join", seat=int(seat_str))
            if board.status == 1:
                track_event(
                    "game_started",
                    type=_opponents(board),
                    wait_time=_minutes_since(board.created_at),
                )
                maybe_trigger_bot(board.id)
            return redirect(url_for("available_games"))

        form = NewGameForm()
        if form.validate_on_submit():
            match form.seat.data:
                case "Seat 1":
                    board = TriBoard(
                        owner_id=g.user.id,
                        player_0_id=g.user.id,
                        player_0_accepted=True,
                    )
                case "Seat 2":
                    board = TriBoard(
                        owner_id=g.user.id,
                        player_1_id=g.user.id,
                        player_1_accepted=True,
                    )
                case "Seat 3":
                    board = TriBoard(
                        owner_id=g.user.id,
                        player_2_id=g.user.id,
                        player_2_accepted=True,
                    )
            db.session.add(board)
            db.session.commit()
            logger.log(
                GAME,
                "Game created",
                extra={
                    "user_id": g.user.id,
                    "board_id": board.id,
                },
            )
            track_event("game_created", seat=int(form.seat.data[-1]) - 1)
            flash("Game created successfuly!", "success")
            return redirect(url_for("available_games"))

        return redirect(url_for("available_games"))

    available = TriBoard.query.filter_by(status=0).all()
    form = NewGameForm()
    return render_template(
        "available.html", games=available, player_id=g.user.id, form=form
    )


@app.route("/play/<int:id>")
@login_required
def play(id):
    access_token = create_access_token(identity=str(g.user.id))
    user_in = TriBoard.for_player(g.user.id)
    tb = TriBoard.query.filter_by(id=id).filter(user_in).first()
    if tb:
        pieces_file = os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            f"static/pieces/{g.user.pieces}.yaml",
        )
        with open(pieces_file) as f:
            pieces_paths = yaml.safe_load(f)
        template = "board_ondro.html" if g.user.board == "ondro" else "board_filio.html"
        seat = next(i for i in range(3) if getattr(tb, f"player_{i}_id") == g.user.id)
        finished = tb.status == 2
        ga_game = {
            "board_id": tb.id,
            "seat": seat,
            "type": _opponents(tb),
            "renderer": "ondro" if g.user.board == "ondro" else "filio",
            # Seats move in order 0, 1, 2, so seat s has moved once more
            # than s moves were made.
            "has_moved": slog_summary(tb.slog or "").move_number > seat,
            # game_completed's duration: minutes since the start while the
            # game runs; start to last move once it's over.
            "started_minutes_ago": _minutes_since(tb.started_at),
            "duration": _game_minutes(tb) if finished else None,
            # A finished game seen for the first time soon after its end
            # still reports game_completed (once per browser).
            "finished_recently": finished
            and tb.modified_at is not None
            and tb.modified_at
            > datetime.now(timezone.utc).replace(tzinfo=None) - LATE_COMPLETION_WINDOW,
        }
        return render_template(
            template,
            id=id,
            access_token=access_token,
            pieces_paths=pieces_paths,
            board=True,
            ga_game=ga_game,
        )
    else:
        flash("You have no access to this game", "error")
        return redirect(url_for("active_games"))


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    form_profile = ProfileForm(
        email=g.user.email, theme=g.user.theme, board=g.user.board, pieces=g.user.pieces
    )
    form_password = PasswordForm(username=g.user.username)
    if form_profile.validate_on_submit():
        new_email = form_profile.email.data
        email_changed = new_email != g.user.email

        if email_changed:
            if User.query.filter(User.email == new_email, User.id != g.user.id).first():
                flash("Email already in use by another user.", "warning")
                return redirect(url_for("profile"))
            g.user.email = new_email
            g.user.email_verified = False
            send_verification_email(g.user)
            flash(
                "Email updated. Check your inbox to verify the new address.",
                "info",
            )

        for field in ("theme", "board", "pieces"):
            value = getattr(form_profile, field).data
            if getattr(g.user, field) != value:
                track_event("profile_pref_change", field=field, pref_value=value)
                setattr(g.user, field, value)
        db.session.commit()
        flash("Profile saved successfuly!", "success")
        return redirect(url_for("active_games"))
    user_in = TriBoard.for_player(g.user.id)
    active = TriBoard.query.filter_by(status=1).filter(user_in).all()
    archive = TriBoard.query.filter_by(status=2).filter(user_in).all()
    avg = sum([t.modified_at - t.started_at for t in archive], timedelta(0))
    if avg.total_seconds() > 0:
        avg = avg / len(archive)
        avg_length = str(avg - timedelta(microseconds=avg.microseconds)) + " hours"
    else:
        avg_length = "Unknown"

    if g.user.is_admin:
        selected_user_id = request.args.get("user_id", g.user.id, type=int)
        selected_user = db.session.get(User, selected_user_id) or g.user
        selected_user_id = selected_user.id
        users = User.query.order_by(User.username).all()
        rh_raw = get_user_rating_history(selected_user_id)
    else:
        selected_user_id = g.user.id
        selected_user = g.user
        users = []
        rh_raw = get_user_rating_history(g.user.id)

    rh_labels = []
    rh_values = []
    for dt, r in rh_raw:
        rh_labels.append(dt.strftime("%Y-%m-%d"))
        rh_values.append(round(r, 2))

    return render_template(
        "profile.html",
        form_profile=form_profile,
        form_password=form_password,
        username=g.user.username,
        rating=g.user.rating,
        score=g.user.score(),
        recent_score=g.user.recent_score(),
        active=len(active),
        archive=len(archive),
        avg_length=avg_length,
        stats=g.user.stats(),
        rating_history_labels=rh_labels,
        rating_history_values=rh_values,
        users=users,
        selected_user=selected_user,
        selected_user_id=selected_user_id,
    )


@app.route("/profile_password", methods=["GET", "POST"])
@login_required
def password():
    form_profile = ProfileForm(email=g.user.email, theme=g.user.theme)
    form_password = PasswordForm(username=g.user.username)
    if form_password.validate_on_submit():
        if check_password_hash(g.user.password, form_password.password.data):
            g.user.password = generate_password_hash(form_password.password_new.data)
            db.session.commit()
            flash("Password changed successfuly!", "success")
        return redirect(url_for("active_games"))
    return render_template(
        "profile.html",
        form_profile=form_profile,
        form_password=form_password,
        username=g.user.username,
        score=g.user.score(),
    )


@app.route("/help")
def help():
    return render_template("help.html")


# === Admin section ===


def delete_game(board):
    """Delete a game with everything that references it. A rated game's
    points and rating changes go with it: ratings are recomputed. The caller
    commits."""
    rated = Score.query.filter_by(board_id=board.id).count() > 0
    Score.query.filter_by(board_id=board.id).delete()
    Log.query.filter_by(board_id=board.id).delete()
    RatingHistory.query.filter_by(board_id=board.id).delete()
    db.session.delete(board)
    if rated:
        rebuild_ratings()


def remove_user(user):
    """Remove an account. One with games is anonymised instead of deleted, so
    games, scores and ratings stay consistent: its name, email and password
    are scrubbed and it can never log in again. It leaves the games still
    waiting for players (a game it waited in alone is deleted). The caller
    commits."""
    for board in TriBoard.query.filter_by(status=0).filter(
        TriBoard.for_player(user.id)
    ):
        for seat in range(3):
            if getattr(board, f"player_{seat}_id") == user.id:
                setattr(board, f"player_{seat}_id", None)
                setattr(board, f"player_{seat}_accepted", False)
        others = [
            p
            for p in (board.player_0_id, board.player_1_id, board.player_2_id)
            if p is not None
        ]
        if not others:
            delete_game(board)
        elif board.owner_id == user.id:
            board.owner_id = others[0]
    db.session.flush()
    in_games = (
        TriBoard.query.filter(
            TriBoard.for_player(user.id) | (TriBoard.owner_id == user.id)
        ).count()
        or Score.query.filter_by(player_id=user.id).count()
        or RatingHistory.query.filter_by(user_id=user.id).count()
    )
    if in_games:
        # Brackets and spaces fail RegistrationForm's username rule, so no
        # one can have registered this name first.
        user.username = f"[deleted {user.id}]"
        user.email = None
        user.email_verified = False
        user.password = generate_password_hash(secrets.token_hex(32))
        user.active = False
    else:
        Log.query.filter_by(user_id=user.id).delete()
        db.session.delete(user)


@app.route("/admin-games", methods=["GET", "POST"])
@login_required
def admin_games():
    if g.user.is_admin:
        if request.method == "POST":
            delete = request.form.get("delete", type=int)
            if delete is not None:
                board = db.session.get(TriBoard, delete)
                if board is not None:
                    delete_game(board)
                    db.session.commit()
                return redirect(url_for("admin_games"))
        else:
            available = (
                TriBoard.query.filter_by(status=0)
                .order_by(TriBoard.modified_at.desc())
                .all()
            )
            active_pages = _paginate(
                TriBoard.query.filter_by(status=1).order_by(
                    TriBoard.modified_at.desc()
                ),
                "active_page",
            )
            archive_pages = _paginate(
                TriBoard.query.filter_by(status=2).order_by(
                    TriBoard.modified_at.desc()
                ),
                "archive_page",
            )
            # add onmove attribute
            for game in active_pages.items + archive_pages.items:
                game.onmove = slog_summary(game.slog or "").on_move
            return render_template(
                "admin-games.html",
                available=available,
                active=active_pages.items,
                archive=archive_pages.items,
                active_pages=active_pages,
                archive_pages=archive_pages,
            )
    else:
        flash("You are not admin.", "error")
        return redirect(url_for("active_games"))


@app.route("/admin-users", methods=["GET", "POST"])
@login_required
def admin_users():
    if g.user.is_admin:
        if request.method == "POST":
            approve = request.form.get("approve", type=int)
            delete = request.form.get("delete", type=int)
            if approve is not None:
                user = User.query.filter_by(id=approve).first()
                if user is not None:
                    user.active = True
                    db.session.commit()
            elif delete is not None:
                user = db.session.get(User, delete)
                if user is not None and not user.is_admin and not user.is_bot:
                    remove_user(user)
                    db.session.commit()
            return redirect(url_for("admin_users"))
        else:
            waiting = (
                User.query.filter(User.id > 1).filter(User.active.is_(False)).all()
            )
            users = (
                User.query.filter(User.id > 1)
                .filter(User.active.is_(True))
                .filter_by(is_bot=False)
                .order_by(User.last_login.desc())
                .all()
            )
            return render_template("admin-users.html", users=users, waiting=waiting)
    else:
        flash("You are not admin.", "error")
        return redirect(url_for("active_games"))


# === User login methods ===


# Reachable for everyone during maintenance: assets, and logging in/out so
# the admin can still get in (non-admins are refused at login).
MAINTENANCE_OPEN_ENDPOINTS = {"static", "bootstrap.static", "login", "logout"}
MAINTENANCE_MESSAGE = "Maintenance in progress. Trichess will be back soon."
MAINTENANCE_RETRY_AFTER = {"Retry-After": "600"}


@app.before_request
def before_request():
    g.user = current_user
    if request.endpoint in MAINTENANCE_OPEN_ENDPOINTS:
        return None
    if g.user.is_authenticated and g.user.is_admin:
        return None
    if not is_maintenance():
        return None
    # JSON for the API (board JS, bots, tokens), a page for everything else.
    if request.path.startswith("/api/") or request.endpoint in ("token", "refresh"):
        return jsonify(message=MAINTENANCE_MESSAGE), 503, MAINTENANCE_RETRY_AFTER
    return (
        render_template("maintenance.html", message=MAINTENANCE_MESSAGE),
        503,
        MAINTENANCE_RETRY_AFTER,
    )


@app.route("/admin/maintenance", methods=["POST"])
@login_required
def maintenance_toggle():
    if not g.user.is_admin:
        abort(403)
    on = request.form.get("state") == "on"
    set_maintenance(on)
    logger.warning(f"Maintenance mode turned {'on' if on else 'off'} by admin")
    flash(
        "Maintenance mode is on: only you can use the app."
        if on
        else "Maintenance mode is off: the app is open again.",
        "warning" if on else "success",
    )
    return redirect(url_for("profile"))


@lm.user_loader
def load_user(id):
    return db.session.get(User, int(id))


LOGIN_FAILED = Markup(
    'Invalid username or password. <a href="/forgot">Forgot password?</a>'
)
_DUMMY_HASH = generate_password_hash(secrets.token_hex(16))


def _login_name():
    """Rate-limit key for guessing one account's password from many IPs."""
    return "login:" + (request.form.get("username") or "").lower()


@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute;50 per hour", methods=["POST"])
@limiter.limit("20 per hour", methods=["POST"], key_func=_login_name)
def login():
    if g.user is not None and g.user.is_authenticated:
        if g.user.is_admin:
            return redirect(url_for("index"))
        else:
            return redirect(url_for("active_games"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        # A hash check either way, so an unknown name doesn't answer faster.
        password_ok = check_password_hash(
            user.password if user is not None else _DUMMY_HASH, form.password.data
        )
        if user is not None and password_ok:
            if is_maintenance() and not user.is_admin:
                flash(MAINTENANCE_MESSAGE, "warning")
            elif user.active:
                g.user = user
                login_user(user)
                user.last_login = datetime.now(timezone.utc)
                db.session.commit()
                track_event("login", method="password")
                flash("Login successful!", "success")
                if user.is_admin:
                    return redirect(url_for("index"))
                else:
                    return redirect(url_for("active_games"))
            else:
                flash(LOGIN_FAILED, "danger")
        else:
            # Same message whether or not the username exists.
            flash(LOGIN_FAILED, "danger")
    return render_template("login.html", form=form)


@app.route("/forgot", methods=["GET", "POST"])
@limiter.limit("5 per minute;20 per hour", methods=["POST"])
def forgot():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user is not None:
            send_password_reset_email(user)
        flash(
            "If that email is registered, a password reset link has been sent.",
            "info",
        )
        return redirect(url_for("login"))
    return render_template("forgot_password.html", form=form)


@app.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    payload = verify_password_reset_token(token)
    user = db.session.get(User, payload[0]) if payload is not None else None
    # A token is single-use: it carries the password fingerprint at issue time.
    if user is None or password_fingerprint(user) != payload[1]:
        flash("Invalid or expired reset link. Please request a new one.", "danger")
        return redirect(url_for("forgot"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = generate_password_hash(form.password.data)
        db.session.commit()
        flash("Password reset successful! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html", form=form)


@app.route("/token", methods=["POST"])
@csrf.exempt
@limiter.limit("10 per minute;50 per hour")
def token():
    """Issue a JWT for username+password credentials.

    Restricted to API_TOKEN_USERS — direct API/token access is limited to
    trusted accounts; normal browser gameplay never calls this route (see
    /play/<id>, which mints its own token server-side).

    Accepts an OAuth2 "password" grant form body (what Swagger UI's
    Authorize dialog sends for the jsonWebToken scheme) or a plain JSON
    body {"username", "password"} for other API clients.
    """
    allowed = {
        u.strip() for u in app.config.get("API_TOKEN_USERS", "").split(",") if u.strip()
    }
    if request.form:
        username = request.form.get("username", "")
        password = request.form.get("password", "")
    else:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "")
        password = data.get("password", "")
    if username in allowed:
        user = User.query.filter_by(username=username).first()
        if user is not None and check_password_hash(user.password, password):
            access_token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))
            return jsonify(
                access_token=access_token,
                refresh_token=refresh_token,
                token_type="bearer",
            )
    return abort(404)


@app.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
@csrf.exempt
def refresh():
    user = get_current_user()
    return jsonify(access_token=create_access_token(identity=str(user.id)))


@app.route("/logout/")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


def _abandoned_signup(user):
    """A sign-up whose verification link (24 h) expired unused."""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1)
    return (
        not user.active
        and not user.email_verified
        and not user.is_bot
        and user.email is not None  # anonymised accounts keep their name
        and user.created_at is not None
        and user.created_at < cutoff
        and not TriBoard.query.filter(TriBoard.for_player(user.id)).count()
    )


def _flash_registered(email_queued):
    if email_queued:
        flash(
            "Registration successful! Check your email for the verification link.",
            "success",
        )
    else:
        flash(
            "Account created but verification email failed to send. "
            "You can contact admin for approval.",
            "warning",
        )


@app.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute;20 per hour", methods=["POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        existing = User.query.filter_by(username=form.username.data).first()
        if existing is not None and _abandoned_signup(existing):
            # A sign-up never verified in time doesn't hold its name forever.
            Log.query.filter_by(user_id=existing.id).delete()
            db.session.delete(existing)
            db.session.flush()
            existing = None
        if existing is not None:
            # Usernames are public (ratings page), so saying so leaks nothing.
            flash("Username already in use. Try another one.", "warning")
            return redirect(url_for("register"))

        owner = User.query.filter_by(email=form.email.data).first()
        if owner is not None:
            # Same answer as a new sign-up, so the form doesn't reveal which
            # emails have accounts; the address's owner is told instead.
            _flash_registered(send_account_exists_email(owner))
            return redirect(url_for("index"))

        hashed_password = generate_password_hash(form.password.data)
        new_user = User(
            username=form.username.data,
            password=hashed_password,
            email=form.email.data,
            theme="default",
            board="ondro",
            pieces="default",
            active=False,
        )
        db.session.add(new_user)
        db.session.commit()
        track_event("sign_up", method="email")
        _flash_registered(send_verification_email(new_user))
        return redirect(url_for("index"))
    return render_template("register.html", form=form)


@app.route("/verify/<token>")
def verify(token):
    user_id = verify_verification_token(token)
    if user_id is None:
        flash("Invalid or expired verification link.", "danger")
        return redirect(url_for("index"))
    user = db.session.get(User, user_id)
    if user is None or user.email is None or user.is_bot:
        # email None: an anonymised (removed) account, never to be reopened.
        flash("Invalid or expired verification link.", "danger")
        return redirect(url_for("index"))
    if user.active:
        if user.email_verified:
            flash("Account already verified.", "info")
        else:
            user.email_verified = True
            db.session.commit()
            flash("New email verified!", "success")
    else:
        user.active = True
        user.email_verified = True
        db.session.commit()
        track_event("email_verified")
        flash("Email verified! You can now log in.", "success")
    return redirect(url_for("login"))


def contact_enabled():
    return bool(app.config["CONTACT_EMAILS"] and app.config["MAIL_SERVER"])


def _contact_user():
    """Rate-limit key: per player, not per IP."""
    user = g.get("user")
    return (
        f"contact:{user.id}"
        if user is not None and user.is_authenticated
        else "contact"
    )


@app.route("/contact", methods=["GET", "POST"])
@limiter.limit("3 per hour;10 per day", methods=["POST"], key_func=_contact_user)
@login_required
def contact():
    if not contact_enabled():
        abort(404)
    if g.user.is_admin:
        # The admins are the recipients.
        return redirect(url_for("index"))
    form = ContactForm()
    if form.validate_on_submit():
        file = form.attachment.data or None
        queued = send_contact_email(g.user, form.subject.data, form.message.data, file)
        logger.warning(
            "Contact message from %s: %s",
            g.user.username,
            form.subject.data,
            extra={"user_id": g.user.id},
        )
        track_event("contact_sent", has_attachment="yes" if file else "no")
        if queued:
            flash("Your message was sent to the admins.", "success")
        else:
            flash("Sorry, your message could not be sent. Try again later.", "warning")
        return redirect(url_for("active_games"))
    return render_template("contact.html", form=form)


@app.errorhandler(413)
def request_too_large(err):
    if request.endpoint == "contact":
        flash("Attachment too large (max 1 MB).", "danger")
        return redirect(url_for("contact"))
    return "Request too large", 413


# register API blueprint (bearer-JWT-only, no cookies — CSRF doesn't apply)
app.register_blueprint(api, url_prefix="/api/v1")
csrf.exempt(api)
