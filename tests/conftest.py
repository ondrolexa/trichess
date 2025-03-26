import pytest

from trichess import Board, Player


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
