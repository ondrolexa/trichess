import pytest


def test_min(dem):
    assert dem.min == pytest.approx(508.242681917153)

