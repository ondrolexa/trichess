from flask import abort, flash, g, jsonify, redirect, render_template, request, url_for
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt_identity,
    jwt_required,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from webapp import app, db, lm
from webapp.forms import LoginForm, NewGameForm, RegistrationForm
from webapp.models import TriBoard, User


@app.template_filter("strftime")
def _jinja2_filter_datetime(date, fmt=None):
    native = date.replace(tzinfo=None)
    format = "%b %d, %Y %H:%M:%S"
    return native.strftime(format)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        if request.form.get("action") == "login":
            return redirect(url_for("login"))
        else:
            return redirect(url_for("logout"))
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
    return render_template("games.html", games=active, viewer=g.user.id)


@app.route("/created", methods=["GET", "POST"])
@login_required
def created():
    if request.method == "POST":
        board = TriBoard.query.filter_by(id=request.form.get("board")).first()
        db.session.delete(board)
        db.session.commit()
        return redirect(url_for("created"))
    else:
        user_in = db.or_(
            TriBoard.player_0_id == g.user.id,
            TriBoard.player_1_id == g.user.id,
            TriBoard.player_2_id == g.user.id,
        )
        waiting = (
            TriBoard.query.filter_by(status=0)
            .filter(user_in)
            .order_by(TriBoard.created_at.desc())
            .all()
        )
    return render_template("created.html", games=waiting)


@app.route("/join", methods=["GET", "POST"])
@login_required
def available():
    if request.method == "POST":
        board = TriBoard.query.filter_by(id=request.form.get("board")).first()
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
        db.session.commit()
        return redirect(url_for("active"))
    else:
        user_not_in = db.and_(
            db.or_(
                TriBoard.player_0_id != g.user.id, TriBoard.player_0_id == db.null()
            ),
            db.or_(
                TriBoard.player_1_id != g.user.id, TriBoard.player_1_id == db.null()
            ),
            db.or_(
                TriBoard.player_2_id != g.user.id, TriBoard.player_2_id == db.null()
            ),
        )
        available = (
            TriBoard.query.filter_by(status=0)
            .filter(TriBoard.owner_id != g.user.id)
            .filter(user_not_in)
            .all()
        )
    return render_template("available.html", games=available)


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
                    slog=form.slog.data,
                )
            case "Player 2":
                board = TriBoard(
                    owner_id=g.user.id,
                    player_1_id=g.user.id,
                    player_1_accepted=True,
                    slog=form.slog.data,
                )
            case "Player 3":
                board = TriBoard(
                    owner_id=g.user.id,
                    player_2_id=g.user.id,
                    player_2_accepted=True,
                    slog=form.slog.data,
                )
        db.session.add(board)
        db.session.commit()
        flash("Game created successfuly!", "success")
        return redirect(url_for("created"))
    return render_template("new.html", form=form)


@app.route("/play/<id>")
@login_required
def play(id):
    access_token = create_access_token(identity=g.user.username)
    tb = TriBoard.query.filter_by(id=id).first()
    pid = {
        tb.player_0.username: 0,
        tb.player_1.username: 1,
        tb.player_2.username: 2,
    }
    view_pid = pid[g.user.username]
    return render_template(
        "play.html",
        id=id,
        view_pid=view_pid,
        access_token=access_token,
    )


@app.route("/playlx/<id>")
@login_required
def playlx(id):
    access_token = create_access_token(identity=g.user.username)
    tb = TriBoard.query.filter_by(id=id).first()
    pid = {
        tb.player_0.username: 0,
        tb.player_1.username: 1,
        tb.player_2.username: 2,
    }
    view_pid = pid[g.user.username]
    return render_template(
        "playlx.html",
        id=id,
        view_pid=view_pid,
        access_token=access_token,
    )


# === User login methods ===


@app.before_request
def before_request():
    g.user = current_user


@lm.user_loader
def load_user(id):
    return User.query.get(int(id))


@app.route("/register", methods=["GET", "POST"])
@login_required
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = generate_password_hash(form.password.data)
        new_user = User(
            username=form.username.data,
            password=hashed_password,
        )
        db.session.add(new_user)
        db.session.commit()
        flash("User added successfuly!", "success")
        return redirect(url_for("index"))
    return render_template("register.html", form=form)


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
        if g.user is not None and check_password_hash(
            g.user.password, form.password.data
        ):
            login_user(g.user)
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
