from pathlib import Path
from loguru import logger

from config.info import HOME_DIR
import icons.icons_material as icons
from utils.colors import get_css_variable, hex_to_rgb01

from fabric.i3.widgets import get_i3_connection

CONFIG_GLOB_PATH = Path.home() / ".config/i3/conf.d"


import colorsys

# Temporary workaround until my rounded-corners i3 patch is ready and picom shadows work as expected.
def ensure_vibrancy(hex_color: str, min_brightness=0.8, min_saturation=0.5) -> str:
    """Boosts brightness and saturation to ensure it stands out against backgrounds."""
    hex_color = hex_color.lstrip('#')
    
    # Hex -> RGB -> HSV
    r, g, b = hex_to_rgb01(hex_color=hex_color)
    h, s, v = colorsys.rgb_to_hsv(r/255, g/255, b/255)
    
    # Boost brightness and saturation if they are below threshold
    new_v = max(v, min_brightness)
    new_s = max(s, min_saturation)
    
    # HSV -> RGB -> Hex
    r, g, b = colorsys.hsv_to_rgb(h, new_s, new_v)
    return "#{:02x}{:02x}{:02x}".format(int(r*255), int(g*255), int(b*255))

def i3_border_setter(hex_color: str = None):
    if hex_color is None:
        raw_color = get_css_variable(
            f"{HOME_DIR}/fabric/styles/colors.css", "--primary"
        )
        # hex_color = ensure_vibrancy(raw_color)
        hex_color = raw_color

    logger.debug("Setting i3 focused border color to {}", hex_color)

    CONFIG_GLOB_PATH.mkdir(parents=True, exist_ok=True)

    border_conf = f"""client.focused          {hex_color} {hex_color} {hex_color} {hex_color}
# client.focused_inactive #ff0000 #ff0000 #ff0000 #ff0000
# client.unfocused        #ff0000 #ff0000 #ff0000 #ff0000
# client.urgent           #ff0000 #ff0000 #ff0000 #ff0000
"""

    with open(CONFIG_GLOB_PATH / "borders.conf", "w") as f:
        f.write(border_conf)

    try:
        i3_resp = get_i3_connection().send_command("reload")
        success = all(
            r.get("success", False) for r in i3_resp.reply if isinstance(r, dict)
        )
        if not success:
            logger.error("i3 config failed to reload: {}", i3_resp.reply)
    except Exception as e:
        logger.error("Error reloading i3 config: {}", e)


from dataclasses import dataclass

@dataclass(frozen=True)
class KeyBinding:
    action: str
    key: str
    command: str | None = None   # None → handled internally
    title: str | None = None     # for settings UI
    scope: str = "global"        # global | player | wifi | etc
    icon: str = '\ue11f'


I3_KEYBINDINGS = [
    KeyBinding(
        action="pill.open",
        key="$mod+d",
        command='fabric-cli exec zenith "pill.open()"',
        title="Open Pill",
        icon=icons.pill.symbol(),
    ),
    KeyBinding(
        action="pill.toggle_power_menu",
        key="$mod+p",
        command='fabric-cli exec zenith "pill.toggle_power_menu()"',
        title="Toggle Power Menu",
        icon=icons.power.symbol(),
    ),
    KeyBinding(
        action="pill.cycle_modes",
        key="Shift+$mod+m",
        command='fabric-cli exec zenith "pill.cycle_modes()"',
        title="Cycle Pill Modes",
        icon=icons.pill.symbol(),
    ),
    KeyBinding(
        action="notifications.toggle",
        key="$mod+n",
        command='fabric-cli exec zenith "top_pill.toggle_notification()"',
        title="Toggle Notifications",
        icon = icons.notifications.symbol(),
    ),
    KeyBinding(
        action="top_bar.toggle_detach",
        key="$mod+Shift+n",
        command='fabric-cli exec zenith "top_bar.toggle_detach()"',
        title="Toggle Controls Mode",
        icon = icons.arrows_up_down_circle.symbol(),
    ),
    KeyBinding(
        action="dock.toggle",
        key="$mod+Escape",
        command='fabric-cli exec zenith "dockBar.toggle_visibility()"',
        title="Toggle Dock Visibility",
        icon=icons.dock_bottom.symbol()
    ),
    KeyBinding(
        action="pill.toggle_player",
        key="$mod+u",
        command='fabric-cli exec zenith "pill.toggle_player()"',
        title="Toggle Player",
        icon=icons.disc.symbol(),
    ),
]

PLAYER_KEYBINDINGS = [
    KeyBinding(
        action="player.play_pause",
        key="p",
        command=None,
        title="Play / Pause",
        scope="player",
        icon=icons.play_pause.symbol(),
    ),
    KeyBinding(
        action="player.prev",
        key="j",
        command=None,
        title="Previous Track",
        scope="player",
        icon=icons.skip_prev.symbol(),
    ),
    KeyBinding(
        action="player.skip_backward",
        key="k",
        command=None,
        title="Seek Backward",
        scope="player",
        icon=icons.fast_rewind.symbol(),
    ),
    KeyBinding(
        action="player.skip_forward",
        key="l",
        command=None,
        title="Seek Forward",
        scope="player",
        icon=icons.fast_forward.symbol(),
    ),
    KeyBinding(
        action="player.next",
        key="semicolon",
        command=None,
        title="Next Track",
        scope="player",
        icon=icons.skip_next.symbol(),
    ),
    KeyBinding(
        action="player.switch_next",
        key="Tab",
        command=None,
        title="Next Player",
        scope="player",
        icon=icons.transition_push.symbol(),
    ),
    KeyBinding(
        action="player.switch_prev",
        key="Shift+ISO_Left_Tab",
        command=None,
        title="Previous Player",
        scope="player",
        icon=icons.transition_push.symbol()
    ),
]

WIFI_KEYBINDINGS = [
    KeyBinding(
        action="wifi.rescan",
        key="r",
        command=None,
        title="Rescan Wi-Fi Networks",
        scope="wifi",
        icon=icons.wifi.symbol(),
    ),
]


def validate_keybindings(bindings: list[KeyBinding]) -> None:
    seen_keys = set()

    for b in bindings:
        if not b.key:
            raise ValueError(f"Missing key for action {b.action}")

        if b.key in seen_keys:
            raise ValueError(f"Duplicate keybinding: {b.key}")

        seen_keys.add(b.key)

def generate_i3_keybinds(bindings: list[KeyBinding]) -> str:
    lines = []

    for b in bindings:
        lines.append(f"bindsym {b.key} exec {b.command}")

    return "\n".join(lines)

def i3_keybinds_setter():
    logger.debug("Setting i3 keybinds")

    CONFIG_GLOB_PATH.mkdir(parents=True, exist_ok=True)

    try:
        validate_keybindings(I3_KEYBINDINGS)
        config = generate_i3_keybinds(I3_KEYBINDINGS)

        with open(CONFIG_GLOB_PATH / "keybinds.conf", "w") as f:
            f.write(config)

        resp = get_i3_connection().send_command("reload")
        if not all(r.get("success", False) for r in resp.reply):
            logger.error("i3 reload failed: {}", resp.reply)

    except Exception as e:
        logger.error("Failed to apply keybindings: {}", e)
