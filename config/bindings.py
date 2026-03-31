from dataclasses import dataclass, replace
from collections.abc import Iterable, Mapping

from .info import SHELL_NAME
import icons.icons_material as icons  # type: ignore[attr-defined]


@dataclass(frozen=True)
class KeyBinding:
    action: str
    key: str
    command: str | None = None  # None -> handled internally
    title: str | None = None  # for settings UI
    scope: str = "global"  # global | player | wifi | etc
    icon: str = "\ue11f"


I3_KEYBINDINGS = [
    KeyBinding(
        action="pill.open",
        key="$mod+d",
        command=f'fabric-cli exec {SHELL_NAME} "pill.open()"',
        title="Open Pill",
        scope="i3",
        icon=icons.pill.symbol(),
    ),
    KeyBinding(
        action="pill.toggle_power_menu",
        key="$mod+p",
        command=f'fabric-cli exec {SHELL_NAME} "pill.toggle_power_menu()"',
        title="Toggle Power Menu",
        scope="i3",
        icon=icons.power.symbol(),
    ),
    KeyBinding(
        action="pill.cycle_modes",
        key="$mod+Shift+m",
        command=f'fabric-cli exec {SHELL_NAME} "pill.cycle_modes()"',
        title="Cycle Pill Modes",
        scope="i3",
        icon=icons.pill.symbol(),
    ),
    KeyBinding(
        action="notifications.toggle",
        key="$mod+n",
        command=f'fabric-cli exec {SHELL_NAME} "top_pill.toggle_notification()"',
        title="Toggle Notifications",
        scope="i3",
        icon=icons.notifications.symbol(),
    ),
    KeyBinding(
        action="top_bar.toggle_detach",
        key="$mod+Shift+n",
        command=f'fabric-cli exec {SHELL_NAME} "top_bar.toggle_detach()"',
        title="Toggle Controls Mode",
        scope="i3",
        icon=icons.arrows_up_down_circle.symbol(),
    ),
    KeyBinding(
        action="dock.toggle",
        key="$mod+Escape",
        command=f'fabric-cli exec {SHELL_NAME} "dockBar.toggle_visibility()"',
        title="Toggle Dock Visibility",
        scope="i3",
        icon=icons.dock_bottom.symbol(),
    ),
    KeyBinding(
        action="pill.toggle_player",
        key="$mod+u",
        command=f'fabric-cli exec {SHELL_NAME} "pill.toggle_player()"',
        title="Toggle Player",
        scope="i3",
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
        icon=icons.transition_push.symbol(),
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

WALLPAPER_KEYBINDINGS = [
    KeyBinding(
        action="wallpaper.scheme_prev",
        key="Shift+Up",
        command=None,
        title="Previous scheme",
        scope="wallpaper",
        icon=icons.arrow_circle_up.symbol(),
    ),
    KeyBinding(
        action="wallpaper.scheme_next",
        key="Shift+Down",
        command=None,
        title="Next scheme",
        scope="wallpaper",
        icon=icons.arrow_circle_down.symbol(),
    ),
    KeyBinding(
        action="wallpaper.scheme_open",
        key="Shift+Right",
        command=None,
        title="Open scheme list",
        scope="wallpaper",
        icon=icons.arrow_drop_down_circle.symbol(),
    ),
    KeyBinding(
        action="wallpaper.move_up",
        key="Up",
        command=None,
        title="Move up",
        scope="wallpaper",
        icon=icons.north.symbol(),
    ),
    KeyBinding(
        action="wallpaper.move_down",
        key="Down",
        command=None,
        title="Move down",
        scope="wallpaper",
        icon=icons.south.symbol(),
    ),
    KeyBinding(
        action="wallpaper.move_left",
        key="Left",
        command=None,
        title="Move left",
        scope="wallpaper",
        icon=icons.west.symbol(),
    ),
    KeyBinding(
        action="wallpaper.move_right",
        key="Right",
        command=None,
        title="Move right",
        scope="wallpaper",
        icon=icons.east.symbol(),
    ),
    KeyBinding(
        action="wallpaper.activate",
        key="Enter",
        command=None,
        title="Set wallpaper",
        scope="wallpaper",
        icon=icons.select_check_box.symbol(),
    ),
]

LAUNCHER_KEYBINDINGS = [
    KeyBinding(
        action="launcher.mod_prev",
        key="Shift+Left",
        command=None,
        title="Previous mode",
        scope="launcher",
        icon=icons.arrow_circle_left.symbol(),
    ),
    KeyBinding(
        action="launcher.mode_next",
        key="Shift+Right",
        command=None,
        title="Next mode",
        scope="launcher",
        icon=icons.arrow_circle_right.symbol(),
    ),
    KeyBinding(
        action="launcher.move_up",
        key="Up",
        command=None,
        title="Move up",
        scope="launcher",
        icon=icons.north.symbol(),
    ),
    KeyBinding(
        action="launcher.move_down",
        key="Down",
        command=None,
        title="Move down",
        scope="launcher",
        icon=icons.south.symbol(),
    ),
    KeyBinding(
        action="launcher.activate",
        key="Enter",
        command=None,
        title="Launch App/Cmd",
        scope="launcher",
        icon=icons.rocket_launch.symbol(),
    ),
]

NOTIFICATIONS_KEYBINDINGS = [
    KeyBinding(
        action="notifications.clear_all",
        key="Shift+d",
        command=None,
        title="Clear all notifications",
        scope="notifications",
        icon=icons.trash_material.symbol(),
    ),
]


KEYBINDING_GROUPS: dict[str, list[KeyBinding]] = {
    "i3": I3_KEYBINDINGS,
    "player": PLAYER_KEYBINDINGS,
    "wifi": WIFI_KEYBINDINGS,
    "wallpaper": WALLPAPER_KEYBINDINGS,
    "launcher": LAUNCHER_KEYBINDINGS,
    "notifications": NOTIFICATIONS_KEYBINDINGS,
}


def get_all_keybindings_default() -> list[KeyBinding]:
    bindings: list[KeyBinding] = []
    for group in KEYBINDING_GROUPS.values():
        bindings.extend(group)
    return bindings


def apply_keybinding_overrides(
    bindings: Iterable[KeyBinding],
    overrides: Mapping[str, str] | None,
) -> list[KeyBinding]:
    if not overrides:
        return list(bindings)

    if hasattr(overrides, "get_all"):
        overrides = overrides.get_all()

    return [
        replace(b, key=overrides[b.action]) if b.action in overrides else b
        for b in bindings
    ]


def hydrate_binding_config(bindings: dict) -> dict:
    i3_dict = bindings.setdefault("i3", {})
    modules_dict = bindings.setdefault("modules", {})

    for binding in get_all_keybindings_default():
        if binding.scope == "i3":
            i3_dict.setdefault(binding.action, binding.key)
        elif binding.scope is not None:
            modules_dict.setdefault(binding.scope, {}).setdefault(
                binding.action, binding.key
            )

    return bindings


def build_resolved_binding_instances(
    bindings_data: dict,
) -> dict[str, dict[str, KeyBinding]]:
    i3_overrides = bindings_data.get("i3", {})
    modules_overrides = bindings_data.get("modules", {})

    resolved = {}
    for scope, base_bindings in KEYBINDING_GROUPS.items():
        overrides = i3_overrides if scope == "i3" else modules_overrides.get(scope, {})
        resolved[scope] = {
            b.action: replace(b, key=overrides.get(b.action, b.key))
            for b in base_bindings
        }

    return resolved  # dict[scope, dict[action, KeyBinding]]
