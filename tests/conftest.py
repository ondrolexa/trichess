import pytest

from trichess import Board


@pytest.fixture
def board():
    return Board()
