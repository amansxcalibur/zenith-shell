import os
import re

from config.wm_conflicts import find_wm_conflicts
from installer.paths import HOME, SHELL_NAME
from installer.state import load_state
from installer.system import have
from installer.ui import RED, choose, info, panel


# window manager -> feature set of dependencies it needs
WM_FEATURE = {"i3": "x11", "sway": "wayland"}


def current_wm() -> str | None:
    desktop = f"{os.environ.get('XDG_CURRENT_DESKTOP', '')} {os.environ.get('DESKTOP_SESSION', '')}".lower()
    if os.environ.get("SWAYSOCK") or "sway" in desktop:
        return "sway"
    if os.environ.get("I3SOCK") or re.search(r"\bi3\b", desktop):
        return "i3"
    return None


def resolve_wms(choice: str) -> list[str]:
    """--wm explicit > (previously installed + current session) > WMs found on PATH > ask."""
    if choice == "all":
        return list(WM_FEATURE)
    if choice in WM_FEATURE:
        return [choice]
    wms = list(load_state().get("wms", []))
    current = current_wm()
    if current and current not in wms:
        wms.append(current)
    if not wms:
        wms = [wm for wm in WM_FEATURE if have(wm)]
    if not wms:
        picked = choose(
            "Which window manager should Zenith be set up for?", ["i3", "sway", "all"]
        )
        if picked:
            wms = list(WM_FEATURE) if picked == "all" else [picked]
    return sorted(set(wms), key=list(WM_FEATURE).index)


def wm_autostart_configured(wm: str) -> bool:
    try:
        text = (HOME / ".config" / wm / "config").read_text(errors="ignore")
    except OSError:
        return False
    return (
        re.search(rf"^\s*exec\w*\b.*\b{SHELL_NAME}\s*$", text, re.MULTILINE) is not None
    )


CONFLICT_FIX = (
    "rebind the key in zenith-shell settings (Keybindings tab) or remove it from "
    "your window manager config, then reload the window manager"
)


def keybinding_conflicts(wms: list[str]) -> dict:
    found = {wm: find_wm_conflicts(wm) for wm in wms}
    return {wm: conflicts for wm, conflicts in found.items() if conflicts}


def conflict_lines(conflicts) -> list[str]:
    return [
        f"{conflict.key}: {' / '.join(conflict.commands)}" for conflict in conflicts
    ]


def report_keybinding_conflicts(wms: list[str]) -> int:
    """Report only, the user picks which binding keeps the key."""
    conflicts = keybinding_conflicts(wms)
    for wm, found in conflicts.items():
        panel(
            f"{wm} has conflicting keybindings",
            [
                *conflict_lines(found),
                "",
                "Zenith's launcher or other shortcuts may not work until this is fixed.",
            ],
            RED,
        )
    if conflicts:
        info(f"Fix with:  {CONFLICT_FIX}")
    return 1 if conflicts else 0
