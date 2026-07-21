from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash

from engine import get_game
from webapp.main import db
from webapp.models import TriBoard, User


def _create_user(username, active=True):
    user = User(username=username, password=generate_password_hash("pw"), active=active)
    db.session.add(user)
    db.session.commit()
    return user


def _make_board(owner, seats, slog="", status=1):
    tb = TriBoard(
        owner_id=owner.id,
        player_0_id=seats[0].id,
        player_0_accepted=True,
        player_1_id=seats[1].id,
        player_1_accepted=True,
        player_2_id=seats[2].id,
        player_2_accepted=True,
        status=status,
        slog=slog,
    )
    db.session.add(tb)
    db.session.commit()
    return tb


def _login(app, username):
    with app.test_request_context():
        return create_access_token(identity=username)


class TestGameBoardGetViewPidOverride:
    def _setup(self, app):
        alice = _create_user("alice")
        bob = _create_user("bob")
        carol = _create_user("carol")
        tb = _make_board(alice, {0: alice, 1: bob, 2: carol})
        return tb

    def test_no_override_matches_callers_own_seat(self, app, client):
        tb = self._setup(app)
        token = _login(app, "bob")

        resp = client.get(
            f"/api/v1/manager/board?id={tb.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["view_pid"] == 1
        expected = get_game(1, "").gid2hex
        assert data["gid2code"] == [
            expected[gid].pos.code for gid in range(len(expected))
        ]

    def test_view_pid_override_changes_gid2code_only(self, app, client):
        tb = self._setup(app)
        token = _login(app, "bob")

        resp = client.get(
            f"/api/v1/manager/board?id={tb.id}&view_pid=2",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        # view_pid field still reflects the caller's own seat, not the override
        assert data["view_pid"] == 1

        expected = get_game(2, "").gid2hex
        assert data["gid2code"] == [
            expected[gid].pos.code for gid in range(len(expected))
        ]

        default_resp = client.get(
            f"/api/v1/manager/board?id={tb.id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert data["gid2code"] != default_resp.get_json()["gid2code"]

    def test_out_of_range_view_pid_rejected(self, app, client):
        tb = self._setup(app)
        token = _login(app, "bob")

        resp = client.get(
            f"/api/v1/manager/board?id={tb.id}&view_pid=7",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 400
