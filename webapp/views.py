"""
When changed update migrations

flask --app=webapp/main.py db migrate -m "Added rating to User"
flask --app=webapp/main.py db upgrade

Rerun flask --app=webapp/main.py db upgrade with production database
"""

import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import requests
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
from gunicorn.sock import ssl_wrap_socket
from sqlalchemy.sql.expression import func
from werkzeug.security import check_password_hash, generate_password_hash

from webapp.api import blueprint as api
from webapp.forms import (
    LoginForm,
    NewGameForm,
    PasswordForm,
    ProfileForm,
    RegistrationForm,
)
from webapp.main import app, db, jwt, lm, post_notification
from webapp.models import Score, TriBoard, User


@app.template_filter("strftime")
def _jinja2_filter_datetime(date, fmt="%b %d, %Y %H:%M:%S"):
    utc = date.replace(tzinfo=ZoneInfo("UTC"))
    native = utc.astimezone(ZoneInfo("Europe/Prague"))
    return native.strftime(fmt)


@app.template_filter("deltatime")
def _jinja2_filter_timedelta(date):
    utc = date.replace(tzinfo=ZoneInfo("UTC"))
    native = utc.astimezone(ZoneInfo("Europe/Prague"))
    now = datetime.now().replace(microsecond=0).astimezone(ZoneInfo("Europe/Prague"))
    return str(now - native) + " ago"


def add_onmove(games):
    for game in games:
        slog = game.slog
        moves = [
            slog[i : i + 4] for i in range(0, len(slog), 4) if slog[i] not in ["S", "R"]
        ]
        game.onmove = len(moves) % 3


def render_template(*args, **kwargs):
    navailable = TriBoard.query.filter_by(status=0).count()
    if g.user is not None and g.user.is_authenticated:
        theme_file = os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            f"static/themes/{g.user.theme}.yaml",
        )
    else:
        theme_file = os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            "static/themes/default.yaml",
        )
    with open(theme_file) as f:
        theme = yaml.safe_load(f)
    if "board" not in kwargs:
        kwargs["board"] = False

    return real_render_template(*args, **kwargs, navailable=navailable, theme=theme)


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
        game.player_0_score = (
            Score.query.filter_by(board_id=game.id, player_id=game.player_0_id)
            .first()
            .score
        )
        game.player_1_score = (
            Score.query.filter_by(board_id=game.id, player_id=game.player_1_id)
            .first()
            .score
        )
        game.player_2_score = (
            Score.query.filter_by(board_id=game.id, player_id=game.player_2_id)
            .first()
            .score
        )
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
            board = TriBoard.query.filter_by(id=int(request.form.get("board"))).first()
            match request.form.get("seat"):
                case "0":
                    board.player_0_id = g.user.id
                    board.player_0_accepted = True
                case "1":
                    board.player_1_id = g.user.id
                    board.player_1_accepted = True
                case "2":
                    board.player_2_id = g.user.id
                    board.player_2_accepted = True
            if (
                (board.player_0_id is not None)
                and (board.player_1_id is not None)
                and (board.player_2_id is not None)
            ):
                board.status = 1
                board.started_at = datetime.now()
                # send notification to first player
                post_notification(
                    board.player_0.username,
                    f"The game {board.id} just started, it's your turn",
                    "Game started",
                    board.id,
                    board.player_0.board,
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
        return render_template(
            "play.html",
            id=id,
            access_token=access_token,
            pieces_paths=pieces_paths,
            board=True,
        )
    else:
        flash("You have no access to this game", "error")
        return redirect(url_for("active"))


@app.route("/playlx/<id>")
@login_required
def playlx(id):
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
        return render_template(
            "playlx.html",
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
        g.user.email = form_profile.email.data
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
        g.user = User.query.filter_by(username=form.username.data).first()
        if g.user is not None:
            print(g.user.active)
            if g.user.active and check_password_hash(
                g.user.password, form.password.data
            ):
                login_user(g.user)
                g.user.last_login = datetime.now()
                db.session.commit()
                flash("Login successful!", "success")
                if g.user.id == 1:
                    return redirect(url_for("index"))
                else:
                    return redirect(url_for("active"))
            else:
                flash("Invalid username or password", "danger")
    return render_template("login.html", form=form)


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
        exists = User.query.filter_by(username=form.username.data).first()
        if exists is None:
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
            flash(
                "User added successfuly! Please wait for account approval before login.",
                "success",
            )
            # notify admin
            try:
                requests.post(
                    "https://ntfy.mykuna.eu/trichess_ondro",
                    data=f"User {form.username.data} applied for account".encode(
                        "utf-8"
                    ),
                    headers={
                        "Title": "New account",
                        "Click": "https://trichess.mykuna.eu/admin-users",
                    },
                )
            except requests.exceptions.ConnectionError:
                pass
            return redirect(url_for("index"))
        else:
            flash("Username already exists. Try another one.", "error")
            return redirect(url_for("register"))
    return render_template("register.html", form=form)


# register API blueprint
app.register_blueprint(api, url_prefix="/api/v1")
