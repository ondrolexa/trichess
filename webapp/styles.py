"""Board colour themes (static/themes) and piece sets (static/pieces): one
YAML file per name. Names come from the files that exist, so a stored
preference can never point outside those folders; an unknown one falls
back to "default".
"""

import functools
import os

import yaml

STYLE_DIRS = {
    kind: os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", kind)
    for kind in ("themes", "pieces")
}


@functools.cache
def style_names(kind):
    """Sorted names of the *kind* ("themes" or "pieces") YAML files."""
    return sorted(
        name
        for name, ext in map(os.path.splitext, os.listdir(STYLE_DIRS[kind]))
        if ext == ".yaml"
    )


@functools.cache
def load_style(kind, name):
    """The parsed YAML of theme or piece set *name*, else of "default"."""
    if name not in style_names(kind):
        name = "default"
    with open(os.path.join(STYLE_DIRS[kind], f"{name}.yaml")) as f:
        return yaml.safe_load(f)
