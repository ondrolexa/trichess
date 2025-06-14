import pytest

from engine import Board, GameAPI, Player


@pytest.fixture
def api():
    ga = GameAPI(0)
    return ga


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
