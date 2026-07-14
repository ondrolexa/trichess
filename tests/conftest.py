import os

# Must be set before webapp is ever imported (here, or by any test module —
# conftest.py always loads first). webapp.main's module-level
# `db = SQLAlchemy(app)` reads SQLALCHEMY_DATABASE_URI once at import time
# and permanently caches the resulting engine on the app object; setting it
# later via flask_app.config.update() (as the `app` fixture below still also
# does, for clarity/defense-in-depth) has NO effect on which engine is
# actually used — flask-sqlalchemy's own docs: "changes to application
# config after this call will not be reflected." Without this env var, every
# test run against the `app`/`client` fixtures was silently creating and
# dropping tables against the real instance/trichess.db.
os.environ["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

import pytest

from engine import Board, GameAPI, Player


@pytest.fixture
def app():
    """Flask app configured for testing, with a fresh in-memory DB per test."""
    from webapp import app as flask_app
    from webapp import db

    flask_app.config.update(
        TESTING=True,
        DEBUG=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        # Never let tests touch the real SMTP/notification services configured in .env.
        MAIL_SERVER="",
    )
    flask_app.debug = True
    with flask_app.app_context():
        # Defense-in-depth: refuse to run against anything but an in-memory
        # db, so a future regression here fails loudly instead of silently
        # wiping the real database again (see the os.environ note above).
        engine_url = str(db.engine.url)
        assert "memory" in engine_url, (
            "Test fixture is NOT bound to an in-memory database "
            f"(got {engine_url!r}) — refusing to run create_all()/drop_all() "
            "to avoid wiping real data."
        )
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def game() -> GameAPI:
    return GameAPI(view_pid=0)


@pytest.fixture
def game_with_one_move() -> GameAPI:
    ga = GameAPI(view_pid=0)
    ga.make_move(152, 142)
    return ga


@pytest.fixture
def slog1():
    return "BNDLGCICNILICOFMCGCIOCLDGNILCFEGLIKJGOKGBGDINFMFKGCKDIHGOGIJDNEMDEIJNBLBBOCMIJKIODNFFOGLKIGIOHKLINJMGIGDOBKDEODNGBIDNEJGCNELIDOANFMECKALOAIDMEHODOCNBHBJHOMEDLEKBJALNALCCMDKAHCHMELEAODOHGLENDLEDKFJCIDINCMDCNAOFCGEKJJKDNDIAIBIKDHADIDFEDFCKLKHDFLBCHKHOFNDFMHJEGGHJGKHAOCNICJCKHGDDODEFCGDLDOCDEHAJCLB"


@pytest.fixture
def slog2():
    return "GNGLCGDGNBMBFNGMBHBINFLHDNDMGCHCNIMIBNBLDGEGMBLCGLGKBICILCKDGMGLCIDINDMEHNJLDFFFNAMABOFMAIBIOAAOGOEMBGAINCMCCNCLsXAXsXXAsDXX"


@pytest.fixture
def slog3():
    return "GNGLCGDGNBMBFNGMBHBINFLHDNDMGCHCNIMIBNBLDGEGMBLCGLGKBICILCKDGMGLCIDINDMEHNJLDFFFNAMABOFMAIBIOAAOGOEMBGAI"


@pytest.fixture
def slog4():
    return "FOEMFDHDNGLIDNDLGBEFNBMBINJMBHBJNHLHGOHMCGCHOFMIGNGMDFDGNDLFEOGNDGEGOCLEENGJEEGGMIJJHMEJFCDFNFMFGNFMCFFELFKGHNHMEDGBNALABOIAGBHAKGJHFMDKEFFGLHKIDKGNFGIAOGMHGNGOHDHEODKDGOMI"


@pytest.fixture
def board():
    return Board()


@pytest.fixture
def player0():
    return Player(0)


@pytest.fixture
def player1():
    return Player(1)


@pytest.fixture
def player2():
    return Player(2)
