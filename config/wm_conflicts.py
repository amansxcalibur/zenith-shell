"""Ask i3/sway which keybindings clash, so includes and $mod need no parsing of our own.

Standard library only: the installer imports this before the virtualenv exists.
"""

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

I3_DUPLICATE = re.compile(
    r'state mask (0x[0-9a-fA-F]+) with (keysym|keycode) (\S+), command "(.*)"'
)
# Sway accepts these as overrides, so only its debug log mentions them
SWAY_OVERWRITE = re.compile(r"Overwriting binding '(.+?)'.* to `(.*)` from `(.*)`")
X11_MODIFIERS = {
    0x1: "Shift",
    0x4: "Control",
    0x8: "Mod1",
    0x10: "Mod2",
    0x20: "Mod3",
    0x40: "Mod4",
    0x80: "Mod5",
}


@dataclass(frozen=True)
class KeybindingConflict:
    key: str
    commands: tuple[str, ...]  # i3 names only the later binding, sway names both


def parse_i3_output(output: str) -> list[KeybindingConflict]:
    conflicts = {}
    for mask, kind, key, command in I3_DUPLICATE.findall(output):
        modifiers = [
            name for bit, name in X11_MODIFIERS.items() if int(mask, 16) & bit
        ]
        name = key if kind == "keysym" else f"keycode {key}"
        conflicts[(mask, kind, key)] = KeybindingConflict(
            "+".join([*modifiers, name]), (command,)
        )
    return list(conflicts.values())


def parse_sway_output(output: str) -> list[KeybindingConflict]:
    conflicts = {}
    for key, new, old in SWAY_OVERWRITE.findall(output):
        conflicts[key] = KeybindingConflict(key, (new, old))
    return list(conflicts.values())


def _check(command: list[str], env: dict[str, str]) -> str:
    try:
        result = subprocess.run(
            command,
            check=False,  # i3 exits 1 on the conflicts we are looking for
            env=env,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout + result.stderr


def find_wm_conflicts(
    wm: str, config_path: Path | None = None
) -> list[KeybindingConflict]:
    """Conflicts in the config `wm` would load. Nothing from it is executed."""
    if not shutil.which(wm):
        return []

    path_args = ["-c", str(config_path)] if config_path else []
    env = os.environ.copy()
    if wm == "i3":
        return parse_i3_output(_check(["i3", "-C", *path_args], env))

    # Sway starts a backend even to validate; a headless one works without a session
    for name in ("WAYLAND_DISPLAY", "DISPLAY", "SWAYSOCK", "I3SOCK"):
        env.pop(name, None)
    env.update(WLR_BACKENDS="headless", WLR_RENDERER="pixman")
    with tempfile.TemporaryDirectory() as runtime_dir:
        env["XDG_RUNTIME_DIR"] = runtime_dir
        return parse_sway_output(_check(["sway", "-d", "-C", *path_args], env))
