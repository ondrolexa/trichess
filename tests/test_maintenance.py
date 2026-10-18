"""Maintenance mode (webapp/maintenance.py, the before_request gate and the
admin toggle in webapp/views.py, and the paused background jobs)."""

from flask_jwt_extended import create_access_token

from tests.test_botplayer import _bots, _make_board
from tests.test_webapp import _create_user, _login, _login_as_admin
from webapp import botplayer, main
from webapp.main import db
from webapp.maintenance import is_maintenance, set_maintenance
from webapp.models import User


def test_off_by_default(app, client):
    assert not is_maintenance()
    assert client.get("/help").status_code == 200


def test_anonymous_gets_maintenance_page(app, client):
    set_maintenance(True)
    resp = client.get("/help")
    assert resp.status_code == 503
    assert resp.headers["Retry-After"]
    assert "Maintenance in progress" in resp.get_data(as_text=True)


def test_logged_in_user_gets_maintenance_page(app, client):
    _create_user()
    _login(client)
    set_maintenance(True)
    assert client.get("/games").status_code == 503


def test_admin_passes_and_sees_banner(app, client):
    _login_as_admin(client)
    set_maintenance(True)
    resp = client.get("/games")
    assert resp.status_code == 200
    assert "Maintenance mode is on" in resp.get_data(as_text=True)


def test_login_page_and_assets_stay_reachable(app, client):
    set_maintenance(True)
    page = client.get("/login")
    assert page.status_code == 200
    assert "Only administrators can sign in" in page.get_data(as_text=True)
    assert client.get("/static/common.css").status_code == 200


def test_non_admin_cannot_log_in(app, client):
    _create_user()
    set_maintenance(True)
    _login(client)
    with client.session_transaction() as sess:
        assert "_user_id" not in sess


def test_admin_can_log_in(app, client):
    set_maintenance(True)
    _login_as_admin(client)
    assert client.get("/games").status_code == 200


def test_api_gets_json_503(app, client):
    alice = _create_user()
    set_maintenance(True)
    with app.test_request_context():
        token = create_access_token(identity=str(alice.id))
    resp = client.get(
        "/api/v1/game/info?slog=&view_pid=0",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 503
    assert resp.get_json()["message"].startswith("Maintenance in progress")


def test_admin_toggles_on_and_off(app, client):
    _login_as_admin(client)
    resp = client.post("/admin/maintenance", data={"state": "on"})
    assert resp.status_code == 302
    assert is_maintenance()
    assert "Turn off maintenance" in client.get("/profile").get_data(as_text=True)
    client.post("/admin/maintenance", data={"state": "off"})
    assert not is_maintenance()


def test_non_admin_cannot_toggle(app, client):
    _create_user()
    _login(client)
    assert client.post("/admin/maintenance", data={"state": "on"}).status_code == 403
    assert not is_maintenance()


def test_toggle_card_only_on_admin_profile(app, client):
    _create_user()
    _login(client)
    assert "Maintenance mode" not in client.get("/profile").get_data(as_text=True)


class TestPausedJobs:
    def _bot_board(self):
        bot1, bot2 = _bots()
        alice = User.query.filter_by(username="alice").first() or _create_user()
        return _make_board(alice, {0: bot1, 1: alice, 2: bot2})

    def test_bot_not_triggered(self, app):
        tb = self._bot_board()
        set_maintenance(True)
        botplayer.maybe_trigger_bot(tb.id)
        assert len(botplayer.bot_queue) == 0

    def test_queued_bot_job_does_nothing(self, app):
        tb = self._bot_board()
        set_maintenance(True)
        botplayer.run_bot_move(tb.id)
        db.session.refresh(tb)
        assert tb.slog == ""

    def test_reminders_skipped(self, app, monkeypatch):
        calls = []
        monkeypatch.setattr(main, "post_notification", lambda *a: calls.append(a))
        set_maintenance(True)
        app.debug = False
        try:
            main.resend_notification()
        finally:
            app.debug = True
        assert calls == []

    def test_bot_sweep_skipped(self, app):
        tb = self._bot_board()
        set_maintenance(True)
        result = app.test_cli_runner().invoke(args=["bot-sweep"])
        assert "Skipped" in result.output
        assert len(botplayer.bot_queue) == 0
        set_maintenance(False)
        app.test_cli_runner().invoke(args=["bot-sweep"])
        assert len(botplayer.bot_queue) == 1
        assert tb.id
