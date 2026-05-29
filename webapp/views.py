"""
When changed update migrations
# DEVELOPEMENT
flask --app=webapp db migrate -m "Added user verification status"
# add op.execute("PRAGMA foreign_keys=OFF") and op.execute("PRAGMA foreign_keys=ON")
# before and after upgrade and downgrade functions in migration script
flask --app=webapp db upgrade

# PRODUCTION
Rerun flask --app=webapp db upgrade with production database
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import yaml
from flask import abort, flash, g, jsonify, redirect
from flask import render_template as real_render_template
from flask import request, url_for
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from flask_login import current_user, login_required, login_user, logout_user
from markupsafe import Markup
from werkzeug.security import check_password_hash, generate_password_hash

from engine import GameAPI
from webapp.api import blueprint as api
from webapp.email import send_password_reset_email, send_verification_email
from webapp.forms import (
    ForgotPasswordForm,
    LoginForm,
    NewGameForm,
    PasswordForm,
    ProfileForm,
    RegistrationForm,
    ResetPasswordForm,
)
from webapp.main import __version__ as webapp_version
from webapp.main import app, db, jwt, lm, post_notification
from webapp.models import Score, TriBoard, User
from webapp.token import verify_password_reset_token, verify_verification_token

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


def add_onmove(games):
    for game in games:
        slog = game.slog
        moves = [
            slog[i : i + 4]
            for i in range(0, len(slog), 4)
            if slog[i] not in ["S", "R", "r", "s"]
        ]
        game.onmove = len(moves) % 3


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

    return real_render_template(
        *args, **kwargs, navailable=navailable, theme=theme, version=webapp_version
    )


@jwt.expired_token_loader
def expired_token_response(jwt_header, jwt_payload):
    return jsonify({"message": "Token has expired"}), 401


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
    return render_template("index.html")


@app.route("/games")
@login_required
def active():
    user_in = db.or_(
        TriBoard.player_0_id == g.user.id,
        TriBoard.player_1_id == g.user.id,
        TriBoard.player_2_id == g.user.id,
    )
    active = (
        TriBoard.query.filter_by(status=1)
        .filter(user_in)
        .order_by(TriBoard.modified_at.desc())
        .all()
    )
    add_onmove(active)
    return render_template(
        "games.html", games=active, uid=g.user.id, board=g.user.board
    )


@app.route("/archive")
@login_required
def archive():
    user_in = db.or_(
        TriBoard.player_0_id == g.user.id,
        TriBoard.player_1_id == g.user.id,
        TriBoard.player_2_id == g.user.id,
    )
    archive = (
        TriBoard.query.filter_by(status=2)
        .filter(user_in)
        .order_by(TriBoard.modified_at.desc())
        .all()
    )
    for game in archive:
        score_0 = Score.query.filter_by(
            board_id=game.id, player_id=game.player_0_id
        ).first()
        game.player_0_score = score_0.score if score_0 is not None else 0.0

        score_1 = Score.query.filter_by(
            board_id=game.id, player_id=game.player_1_id
        ).first()
        game.player_1_score = score_1.score if score_1 is not None else 0.0

        score_2 = Score.query.filter_by(
            board_id=game.id, player_id=game.player_2_id
        ).first()
        game.player_2_score = score_2.score if score_2 is not None else 0.0
        ga = GameAPI(0)
        ga.replay_from_slog(game.slog)
        game.moves = ga.move_number
    return render_template("archive.html", games=archive, board=g.user.board)


@app.route("/rating")
@login_required
def rating():
    users = User.query.order_by(  # .filter(User.last_login is not None)
        User.rating.desc()
    ).all()
    ratings = []
    pos = 1
    for user in users:
        user.score = sum([s.score for s in user.scores])
        user_in = db.or_(
            TriBoard.player_0_id == user.id,
            TriBoard.player_1_id == user.id,
            TriBoard.player_2_id == user.id,
        )
        boards = (
            TriBoard.query.filter_by(status=2)
            .filter(user_in)
            .order_by(TriBoard.modified_at.desc())
        )
        user.played_games = len(boards.all())
        if user.played_games > 0:
            user.last_game = boards.first().modified_at
            user.counts = {"win": 0, "coop": 0, "pass": 0, "loss": 0}
            user.position = pos
            pos += 1
            user.counts = user.stats()
            ratings.append(user)
    return render_template("rating.html", ratings=ratings, uid=g.user.id)


@app.route("/join", methods=["GET", "POST"])
@login_required
def available():
    if request.method == "POST":
        delete = request.form.get("delete", None)
        if delete is None:
            board = request.form.get("board", None)
            if board is not None:
                board = TriBoard.query.filter_by(id=int(board)).first()
                seat = request.form.get("seat")
                if board is None:
                    flash("Game not found", "error")
                    return redirect(url_for("available"))
                match seat:
                    case "0":
                        if board.player_0_id is not None:
                            flash("Seat already taken", "error")
                            return redirect(url_for("available"))
                        board.player_0_id = g.user.id
                        board.player_0_accepted = True
                    case "1":
                        if board.player_1_id is not None:
                            flash("Seat already taken", "error")
                            return redirect(url_for("available"))
                        board.player_1_id = g.user.id
                        board.player_1_accepted = True
                    case "2":
                        if board.player_2_id is not None:
                            flash("Seat already taken", "error")
                            return redirect(url_for("available"))
                        board.player_2_id = g.user.id
                        board.player_2_accepted = True
                if (
                    (board.player_0_id is not None)
                    and (board.player_1_id is not None)
                    and (board.player_2_id is not None)
                ):
                    board.status = 1
                    board.started_at = datetime.now(timezone.utc)
                    # send notification to first player
                    post_notification(
                        board.player_0.username,
                        f"The game {board.id} just started, it's your turn",
                        "Game started",
                        board.id,
                    )
                db.session.commit()
            return redirect(url_for("active"))
        else:
            board = TriBoard.query.filter_by(id=delete).first()
            db.session.delete(board)
            db.session.commit()
            return redirect(url_for("available"))
    else:
        available = TriBoard.query.filter_by(status=0).all()
    return render_template("available.html", games=available, player_id=g.user.id)


@app.route("/new", methods=["GET", "POST"])
@login_required
def new():
    form = NewGameForm()
    if form.validate_on_submit():
        match form.seat.data:
            case "Player 1":
                board = TriBoard(
                    owner_id=g.user.id,
                    player_0_id=g.user.id,
                    player_0_accepted=True,
                )
            case "Player 2":
                board = TriBoard(
                    owner_id=g.user.id,
                    player_1_id=g.user.id,
                    player_1_accepted=True,
                )
            case "Player 3":
                board = TriBoard(
                    owner_id=g.user.id,
                    player_2_id=g.user.id,
                    player_2_accepted=True,
                )
        db.session.add(board)
        db.session.commit()
        flash("Game created successfuly!", "success")
        return redirect(url_for("available"))
    return render_template("new.html", form=form)


@app.route("/play/<id>")
@login_required
def play(id):
    access_token = create_access_token(identity=g.user.username)
    user_in = db.or_(
        TriBoard.player_0_id == g.user.id,
        TriBoard.player_1_id == g.user.id,
        TriBoard.player_2_id == g.user.id,
    )
    tb = TriBoard.query.filter_by(id=id).filter(user_in).first()
    if tb:
        pieces_file = os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            f"static/pieces/{g.user.pieces}.yaml",
        )
        with open(pieces_file) as f:
            pieces_paths = yaml.safe_load(f)
        template = "board_ondro.html" if g.user.board == "ondro" else "board_filio.html"
        return render_template(
            template,
            id=id,
            access_token=access_token,
            pieces_paths=pieces_paths,
            board=True,
        )
    else:
        flash("You have no access to this game", "error")
        return redirect(url_for("active"))


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

        g.user.theme = form_profile.theme.data
        g.user.board = form_profile.board.data
        g.user.pieces = form_profile.pieces.data
        db.session.commit()
        flash("Profile saved successfuly!", "success")
        return redirect(url_for("active"))
    user_in = db.or_(
        TriBoard.player_0_id == g.user.id,
        TriBoard.player_1_id == g.user.id,
        TriBoard.player_2_id == g.user.id,
    )
    active = TriBoard.query.filter_by(status=1).filter(user_in).all()
    archive = TriBoard.query.filter_by(status=2).filter(user_in).all()
    avg = sum([t.modified_at - t.started_at for t in archive], timedelta(0))
    if avg.total_seconds() > 0:
        avg = avg / len(archive)
        avg_length = str(avg - timedelta(microseconds=avg.microseconds)) + " hours"
    else:
        avg_length = "Unknown"

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
        return redirect(url_for("active"))
    return render_template(
        "profile.html",
        form_profile=form_profile,
        form_password=form_password,
        username=g.user.username,
        score=g.user.score(),
    )


@app.route("/help")
@login_required
def help():
    return render_template("rules.html")


# === Admin section ===


@app.route("/admin-games", methods=["GET", "POST"])
@login_required
def admin_games():
    if g.user.id == 1:
        if request.method == "POST":
            delete = request.form.get("delete", None)
            if delete is not None:
                board = TriBoard.query.filter_by(id=delete).first()
                db.session.delete(board)
                db.session.commit()
                return redirect(url_for("admin_games"))
        else:
            available = (
                TriBoard.query.filter_by(status=0)
                .order_by(TriBoard.modified_at.desc())
                .all()
            )
            active = (
                TriBoard.query.filter_by(status=1)
                .order_by(TriBoard.modified_at.desc())
                .all()
            )
            archive = (
                TriBoard.query.filter_by(status=2)
                .order_by(TriBoard.modified_at.desc())
                .all()
            )
            add_onmove(active)
            add_onmove(archive)
            return render_template(
                "admin-games.html", available=available, active=active, archive=archive
            )
    else:
        flash("You are not admin.", "error")
        return redirect(url_for("active"))


@app.route("/admin-users", methods=["GET", "POST"])
@login_required
def admin_users():
    if g.user.id == 1:
        if request.method == "POST":
            approve = request.form.get("approve", None)
            delete = request.form.get("delete", None)
            if approve is not None:
                user = User.query.filter_by(id=approve).first()
                user.active = True
                db.session.commit()
            elif delete is not None:
                user = User.query.filter_by(id=delete).first()
                db.session.delete(user)
                db.session.commit()
            return redirect(url_for("admin_users"))
        else:
            waiting = User.query.filter(User.id > 1).filter(User.active == 0).all()
            users = (
                User.query.filter(User.id > 1)
                .filter(User.active == 1)
                .order_by(User.last_login.desc())
                .all()
            )
            return render_template("admin-users.html", users=users, waiting=waiting)
    else:
        flash("You are not admin.", "error")
        return redirect(url_for("active"))


# === User login methods ===


@app.before_request
def before_request():
    g.user = current_user


@lm.user_loader
def load_user(id):
    return User.query.get(int(id))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user is not None and g.user.is_authenticated:
        if g.user.id == 1:
            return redirect(url_for("index"))
        else:
            return redirect(url_for("active"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user is not None and check_password_hash(user.password, form.password.data):
            if user.active:
                g.user = user
                login_user(user)
                user.last_login = datetime.now(timezone.utc)
                db.session.commit()
                flash("Login successful!", "success")
                if user.id == 1:
                    return redirect(url_for("index"))
                else:
                    return redirect(url_for("active"))
            else:
                flash("Invalid username or password", "danger")
        elif user is not None:
            flash(
                Markup('Wrong password. <a href="/forgot">Forgot password?</a>'),
                "danger",
            )
        else:
            flash("Invalid username or password", "danger")
    return render_template("login.html", form=form)


@app.route("/forgot", methods=["GET", "POST"])
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
    user_id = verify_password_reset_token(token)
    if user_id is None:
        flash("Invalid or expired reset link. Please request a new one.", "danger")
        return redirect(url_for("forgot"))
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "danger")
        return redirect(url_for("forgot"))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password = generate_password_hash(form.password.data)
        db.session.commit()
        flash("Password reset successful! You can now log in.", "success")
        return redirect(url_for("login"))
    return render_template("reset_password.html", form=form)


@app.route("/token", methods=["POST"])
def token():
    """Request from client app to return JWT token"""
    json = request.get_json()
    username = json.get("username", "")
    if username:
        user = User.query.filter_by(username=username).first()
        if user is not None and check_password_hash(
            user.password, json.get("password", "")
        ):
            access_token = create_access_token(identity=username)
            refresh_token = create_refresh_token(identity=username)
            return jsonify(access_token=access_token, refresh_token=refresh_token)
    return abort(404)


@app.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    username = get_jwt_identity()
    if username:
        access_token = create_access_token(identity=username)
        return jsonify(access_token=access_token)
    return abort(404)


@app.route("/logout/")
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data, active=True).first():
            flash("Username already in use. Try another one.", "warning")
            return redirect(url_for("register"))

        if User.query.filter_by(email=form.email.data).first():
            flash("Email already registered. Please use a different email.", "warning")
            return redirect(url_for("register"))

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
        if send_verification_email(new_user):
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
        return redirect(url_for("index"))
    return render_template("register.html", form=form)


@app.route("/verify/<token>")
def verify(token):
    user_id = verify_verification_token(token)
    if user_id is None:
        flash("Invalid or expired verification link.", "danger")
        return redirect(url_for("index"))
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "danger")
        return redirect(url_for("index"))
    if user.active:
        if user.email_verified:
            flash("Account already verified.", "info")
        else:
            user.email_verified = True
            db.session.commit()
            flash("New email verified!", "success")
    else:
        if (
            User.query.filter_by(username=user.username, active=True)
            .filter(User.id != user.id)
            .first()
        ):
            flash(
                "This username has already been activated by another user. "
                "Please register again with a different username.",
                "warning",
            )
            db.session.delete(user)
            db.session.commit()
            return redirect(url_for("login"))
        user.active = True
        user.email_verified = True
        db.session.commit()
        flash("Email verified! You can now log in.", "success")
    return redirect(url_for("login"))


# register API blueprint
app.register_blueprint(api, url_prefix="/api/v1")
