import os
import re

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


def bootstrap_wm() -> str | None:
    # the installer sets this to write one WM's config from any session (see config.bootstrap)
    return os.environ.get("ZENITH_BOOTSTRAP_WM")
