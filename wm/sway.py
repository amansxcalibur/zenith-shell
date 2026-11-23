import os

from loguru import logger

from config import namespaces
from config.info import SHELL_NAME

from services.i3 import I3, get_i3_connection

from wm.i3 import I3WM

# blurred in glass mode
GLASS_LAYERS = (
    namespaces.DOCK,
    namespaces.TOP_BAR,
    namespaces.TOP_PILL,
    namespaces.POPUP,
    namespaces.PILL,
    namespaces.FLYING,
    namespaces.OSD,
)
GLASS_BLUR = (
    "blur_passes 3",
    "blur_radius 5",
    "blur_noise 0.02",
    "blur_saturation 1.15",
)


class SwayWM(I3WM):
    name = "sway"
    exec_flags = ""

    _swayfx: bool | None = None

    @property
    def is_swayfx(self) -> bool:
        # remembered once the WM answers, asked again if it couldn't
        if self._swayfx is not None:
            return self._swayfx
        from fabric.i3.service import I3MessageType

        try:
            reply = get_i3_connection().send_command("", I3MessageType.GET_VERSION)
        except Exception as e:  # no WM to ask
            logger.debug("Could not query the window manager: {}", e)
            return False
        if not reply.is_ok or not isinstance(reply.reply, dict):
            return False
        self._swayfx = (
            "sway_original_version" in reply.reply
            and reply.reply.get("variant") == "sway"
        )
        return self._swayfx

    @property
    def label(self) -> str:
        return "SwayFX" if self.is_swayfx else "Sway"

    @property
    def can_round_corners(self) -> bool:
        return self.is_swayfx

    @property
    def can_blur(self) -> bool:
        return self.is_swayfx

    def _live(self, command: str):
        # only when we're the running session, not the installer writing it from i3
        if os.environ.get("SWAYSOCK"):
            I3.send_command(command)

    def _dock_lines(self, gaps_config) -> list[str]:
        return []

    def _border_lines(self, border_config) -> list[str]:
        radius = border_config.get("props.corner_radius")
        if radius is None or not self.is_swayfx:
            return []
        self._live(f"corner_radius {radius}")
        return ["# swayfx", "# swayfx only", f"corner_radius {radius}", ""]

    def _rule_lines(self) -> list[str]:
        from wm import glass_mode

        lines = []
        config_block = [
            "# floating settings win",
            f'for_window [app_id="{SHELL_NAME}-settings"] {{',
            "    floating enable",
            "    border none",
        ]
        if glass_mode():
            # no corner_radius here: swayfx only has the global one, and setting
            # it in for_window leaks to every window opened after
            config_block.extend(
                [
                    "    # swayfx only: glass mode",
                    "    shadows disable",
                    "    blur enable",
                ]
            )
        elif self.is_swayfx:
            config_block.extend(
                [
                    "    # swayfx only",
                    "    shadows disable",
                    "    blur disable",
                ]
            )
        config_block.append("}")
        lines.append("\n".join(config_block))

        if glass_mode():
            # for the shell's file choosers (agenda image, wallpaper folder)
            lines.append(
                f'for_window [app_id="{SHELL_NAME}-core" title="^Select "] {{\n'
                "    shadows disable\n"
                "    blur enable\n"
                "}"
            )

            # ignore_transparent keeps the blur to what each surface paints, so
            # the dock's holes and the pill's corners stay clear
            lines.append("")
            lines.append("# swayfx only: glass mode")
            for layer in GLASS_LAYERS:
                effects = (
                    f'layer_effects "{layer}" '
                    "'blur enable; blur_ignore_transparent enable'"
                )
                lines.append(effects)
                self._live(effects)
            # frosted rather than see-through. swayfx only takes these
            # globally, so windows it blurs get them too; this file is
            # included after conf-swayfx.d, so it wins over the user's values
            for setting in GLASS_BLUR:
                lines.append(setting)
                self._live(setting)
        elif os.environ.get("SWAYSOCK") and self.is_swayfx:
            # the rules above outlive a restart until sway reloads its config
            for layer in GLASS_LAYERS:
                I3.send_command(f"layer_effects \"{layer}\" 'blur disable'")

        return lines
