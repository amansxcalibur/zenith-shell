import os
import re
from pathlib import Path

from wm.legacy import has_legacy_config

# wm -> (display server, backend class)
BACKENDS = {
    "i3": ("x11", "wm.i3:I3WM"),
    "sway": ("wayland", "wm.sway:SwayWM"),
    "hyprland": ("wayland", "wm.hyprland:HyprlandWM"),
}

# under ~/.config
CONFIG_FILES = {
    "i3": "i3/config",
    "sway": "sway/config",
    "hyprland": "hypr/hyprland.lua",
}


def detect_session() -> str | None:
    desktop = f"{os.environ.get('XDG_CURRENT_DESKTOP', '')} {os.environ.get('DESKTOP_SESSION', '')}".lower()
    # first, SWAYSOCK can be a leftover
    if "hyprland" in desktop:
        return "hyprland"
    # sway sets I3SOCK too, so it goes first
    if os.environ.get("SWAYSOCK") or "sway" in desktop:
        return "sway"
    if os.environ.get("I3SOCK") or re.search(r"\bi3\b", desktop):
        return "i3"
    return None


SHELL_EXEC = r"^\s*exec\w*\b.*\bzenith-shell\b"



def has_autostart(wm: str) -> bool:
    try:
        text = (Path.home() / ".config" / CONFIG_FILES[wm]).read_text(errors="ignore")
    except OSError:
        return False
    # only our include counts, so legacy installs still get migrated
    pattern = r"^\s*include\s+\S*zenith\.d/"
    if wm == "hyprland":
        # not the binds, those use hl.dsp
        pattern = r"""^(?!\s*--).*\bhl\.exec_cmd\(\s*["'][^"']*\bzenith-shell["']"""
    return re.search(pattern, text, re.MULTILINE) is not None


def needs_sync(wm: str) -> bool:
    return not has_autostart(wm) or has_legacy_config(wm)


def bootstrap_wm() -> str | None:
    # the installer sets this to write one WM's config from any session (see config.bootstrap)
    return os.environ.get("ZENITH_BOOTSTRAP_WM")
