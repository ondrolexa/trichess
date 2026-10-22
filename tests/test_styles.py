"""webapp.styles: theme and piece-set YAML, by name, never by path."""

import pytest

from webapp.styles import load_style, style_names


def test_names_come_from_the_yaml_files():
    assert "default" in style_names("themes")
    assert "night" in style_names("themes")
    assert style_names("pieces") == sorted(style_names("pieces"))


@pytest.mark.parametrize("kind", ["themes", "pieces"])
@pytest.mark.parametrize("name", [None, "", "nope", "../themes/night", "/etc/passwd"])
def test_unknown_or_path_like_names_fall_back_to_default(kind, name):
    assert load_style(kind, name) == load_style(kind, "default")


def test_known_name_loads_its_own_file():
    assert load_style("themes", "night") != load_style("themes", "default")
