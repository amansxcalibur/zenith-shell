import os
from pathlib import Path

from loguru import logger

from config.config import config, ConfigNode
from config.info import ROOT_DIR
from config.bindings import (
    KeyBinding,
    apply_keybinding_overrides,
    I3_KEYBINDINGS,
)

from utils.colors import get_css_variable


def write_atomic(path: Path, text: str):
    temp_path = path.with_suffix(".tmp")
    with open(temp_path, "w") as f:
        f.write(text)
    os.replace(temp_path, path)


def get_configured_keybindings() -> list[KeyBinding]:
    try:
        i3_config_node: ConfigNode = config.get_node("bindings.i3")
        overrides = i3_config_node.get_all()
    except AttributeError:
        logger.error("Failed to load wm keybind overrides")
        overrides = {}
    return apply_keybinding_overrides(I3_KEYBINDINGS, overrides)


def get_theme_color() -> str | None:
    colors_css = ROOT_DIR / "styles" / "colors.css"
    if not colors_css.exists():
        return None
    return get_css_variable(str(colors_css), "--primary")
