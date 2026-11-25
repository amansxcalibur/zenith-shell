import os
import re
import json
import shutil
import subprocess
from pathlib import Path
from loguru import logger

from fabric.hyprland.service import Hyprland

from config import namespaces
from config.config import config
from config.bindings import KeyBinding
from config.wm_conflicts import find_wm_conflicts
from config.info import CONFIG_FILE, ROOT_DIR, SHELL_NAME

from wm.base import WindowManager
from wm.common import get_configured_keybindings, get_theme_color, write_atomic

SYSTEM_CONFIG = Path("/usr/share/hypr/hyprland.lua")
DEFAULT_MOD = "SUPER"
MOD_VARIABLE = re.compile(
    r"""^\s*(?:local\s+)?(?:main_?)?mod(?:_?key|ifier)?\s*=\s*["']([^"']+)["']""",
    re.IGNORECASE | re.MULTILINE,
)


def get_chord(keys: str) -> set[str]:
    return set(keys.lower().replace(" ", "").split("+"))


def adapt_system_config(text: str, bindings: list[KeyBinding]) -> str:
    """Drop the default binds that would fire along with ours."""
    our_chords = [get_chord(b.key.replace("$mod", DEFAULT_MOD)) for b in bindings]
    lines = []
    for line in text.splitlines():
        bind = re.match(r'hl\.bind\(mainMod \.\. " \+ ([^"]+)"', line)
        if bind and get_chord(f"{DEFAULT_MOD}+{bind.group(1)}") in our_chords:
            line = f"-- replaced by {SHELL_NAME}: {line}"
        lines.append(line)
    return "\n".join(lines) + "\n"


class HyprlandWM(WindowManager):
    name = "hyprland"
    label = "Hyprland"
    keybind_hint = "Enter them like $mod+Shift+n :)"
    can_round_corners = True
    can_blur = True

    def __init__(self):
        self.config_dir = Path.home() / ".config/hypr"
        self.config_path = self.config_dir / "hyprland.lua"
        self.generated_path = self.config_dir / f"{SHELL_NAME}.lua"

    def _ensure_lua_config(self) -> bool:
        if self.config_path.exists():
            return True
        # a hyprland.lua would shadow it
        if (self.config_dir / "hyprland.conf").exists():
            logger.warning("{} only supports hyprland.lua", SHELL_NAME)
            return False
        logger.warning("Creating a new config at {}", self.config_path)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        text = ""
        if SYSTEM_CONFIG.is_file():
            text = adapt_system_config(
                SYSTEM_CONFIG.read_text(), get_configured_keybindings()
            )
        self.config_path.write_text(text)
        return True

    def _append_to_config(self, comment: str, line: str):
        if line in self.config_path.read_text():
            return
        logger.info("Adding {!r} to {}", line, self.config_path)
        with open(self.config_path, "a") as f:
            f.write(f"\n-- {comment}\n{line}\n")

    def add_autostart(self):
        if self._ensure_lua_config():
            self._append_to_config(
                f"{SHELL_NAME} startup",
                f'hl.on("hyprland.start", function() hl.exec_cmd("{SHELL_NAME}-shell") end)',
            )

    def get_mod(self) -> str:
        match = MOD_VARIABLE.search(self.config_path.read_text())
        return match.group(1) if match else DEFAULT_MOD

    def build_keybind_lines(self) -> list[str]:
        mod = self.get_mod()
        lines = [
            "-- keybinds",
            "local function bind(keys, command)",
            "    -- one bad key shouldn't take the rest down",
            "    pcall(hl.bind, keys, hl.dsp.exec_cmd(command), { description = command })",
            "end",
        ]
        for b in get_configured_keybindings():
            keys = json.dumps(b.key.replace("$mod", mod))
            command = json.dumps(b.command, ensure_ascii=False)
            lines.append(f"bind({keys}, {command})")
        return [*lines, ""]

    def build_general_lines(self) -> list[str]:
        lines = []

        gaps = config.get_node("i3.gaps")
        if gaps.get("enabled"):
            inner, outer = gaps.get("props.inner"), gaps.get("props.outer")
            lines += [
                "-- gaps",
                # gaps_in counts once per neighbour
                (
                    f"hl.config({{ general = {{ gaps_in = {inner // 2}, "
                    f"gaps_out = {outer + inner} }} }})"
                ),
                "",
            ]

        borders = config.get_node("i3.borders")
        if borders.get("enabled"):
            lines += [
                "-- borders",
                "hl.config({",
                f"    general = {{ border_size = {borders.get('props.border_width')} }},",
                f"    decoration = {{ rounding = {borders.get('props.corner_radius')} }},",
                "})",
                (
                    f'hl.window_rule({{ name = "{SHELL_NAME}-floating", '
                    "match = { float = true }, border_size = 0 })"
                ),
            ]
            if borders.get("props.smart_borders"):
                lines.append(
                    f'hl.window_rule({{ name = "{SHELL_NAME}-smart-borders", '
                    'match = { float = false, workspace = "w[tv1]" }, border_size = 0 })'
                )
            lines.append("")

        color = get_theme_color() if borders.get("matugen") else None
        if color:
            lines += [
                "-- theme",
                f'hl.config({{ general = {{ col = {{ active_border = "{color}" }} }} }})',
                "",
            ]

        return lines

    def build_rule_lines(self) -> list[str]:
        from wm import glass_mode

        is_glass = glass_mode()
        lines = [
            "-- floating settings win",
            "hl.window_rule({",
            f'    name = "{SHELL_NAME}-settings",',
            f'    match = {{ class = "^{SHELL_NAME}-settings$" }},',
            "    float = true,",
            "    border_size = 0,",
            "    no_shadow = true,",
            f"    no_blur = {'false' if is_glass else 'true'},",
            "})",
            "",
            "-- floating file choosers",
            "hl.window_rule({",
            f'    name = "{SHELL_NAME}-file-choosers",',
            f'    match = {{ class = "^{SHELL_NAME}-core$", title = "^Select .*" }},',
            "    float = true,",
            "    no_shadow = true,",
            "})",
            "",
            "-- the shell animates its own surfaces",
            (
                f'hl.layer_rule({{ name = "{SHELL_NAME}-layers", '
                f'match = {{ namespace = "^{SHELL_NAME}-.*" }}, no_anim = true }})'
            ),
            "",
            "-- or the old wallpaper fades out on top of the new one",
            (
                f'hl.layer_rule({{ name = "{SHELL_NAME}-wallpaper", '
                'match = { namespace = "^wallpaper$" }, no_anim = true })'
            ),
            "",
        ]
        if not is_glass:
            return lines

        layers = "|".join(namespaces.GLASS_LAYERS)
        return [
            *lines,
            "-- glass mode",
            'if not hl.get_config("decoration.blur.enabled") then',
            "    -- keep it to the shell",
            (
                f'    hl.window_rule({{ name = "{SHELL_NAME}-only-blur", '
                f'match = {{ class = "negative:^{SHELL_NAME}-.*" }}, no_blur = true }})'
            ),
            "end",
            "hl.config({ decoration = { blur = {",
            "    enabled = true,",
            "    size = 5,",
            "    passes = 3,",
            "    noise = 0.02,",
            "    vibrancy = 0.15,",
            "} } })",
            "hl.layer_rule({",
            f'    name = "{SHELL_NAME}-glass",',
            f'    match = {{ namespace = "^({layers})$" }},',
            "    blur = true,",
            "    ignore_alpha = 0.05,",
            "})",
            "",
        ]

    def build_config(self) -> str:
        lines = [
            "-- CAUTION: This file has been auto-generated by Zenith Shell.",
            "-- Any manual changes WILL BE OVERWRITTEN on the next startup.",
            "-- Use Settings instead, or edit:",
            f"--   {CONFIG_FILE}",
            f"--   {ROOT_DIR}/wm/hyprland.py",
            "",
            *self.build_keybind_lines(),
            *self.build_rule_lines(),
            *self.build_general_lines(),
        ]
        return "\n".join(lines)

    def _write_config(self):
        try:
            if not self._ensure_lua_config():
                return
            # pcall so deleting the file doesn't break their config
            self._append_to_config(
                f"{SHELL_NAME} keybinds, gaps, borders and rules, put your overrides below",
                f'pcall(require, "{SHELL_NAME}")',
            )
            text = self.build_config()
            path = self.generated_path
            if path.exists() and path.read_text() == text:
                return
            write_atomic(path, text)
            logger.info("Wrote {}", path)
            self.reload()
        except Exception as e:
            logger.error("Failed to generate the {} config: {}", self.name, e)

    def write_keybinds(self, reload: bool = False):
        self._write_config()

    def write_general(self, reload: bool = False):
        self._write_config()

    def write_theme(self, color: str | None = None, reload: bool = False):
        self._write_config()

    def reload(self):
        # the installer writes from other sessions too
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            Hyprland.send_command("reload config-only")

    def exit_session(self):
        if shutil.which("hyprshutdown"):
            subprocess.Popen(["hyprshutdown"], start_new_session=True)
            return
        Hyprland.send_command("dispatch hl.dsp.exit()")

    def get_pointer_position(self, event) -> tuple[float, float]:
        # the event's own shifts as the pill moves
        pos = json.loads(Hyprland.send_command("j/cursorpos").reply)
        return pos["x"], pos["y"]

    def find_conflicts(self, config_path=None) -> list:
        return find_wm_conflicts(self.name, config_path)

    def build_workspaces(self, vertical: bool = False):
        from modules.workspaces.workspaces import Workspaces
        from modules.workspaces.hyprland import HyprlandWorkspaces

        return Workspaces(HyprlandWorkspaces, vertical=vertical)

    def build_active_window(self):
        from modules.workspaces.workspaces import ActiveWindow
        from modules.workspaces.hyprland import HyprlandActiveWindow

        return ActiveWindow(HyprlandActiveWindow)
