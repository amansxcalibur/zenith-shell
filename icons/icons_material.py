from icons.icon import Icon


class MaterialIcon(Icon):
    __slots__ = ("family", "weight")

    def __init__(self, symbol: str, *, family="Material Symbols Rounded", weight=400):
        super().__init__(symbol)
        self.family = family
        self.weight = weight

    def markup(self) -> str:
        return (
            f"<span font-family='{self.family}' "
            f"font-weight='{self.weight}'>"
            f"{self._symbol}</span>"
        )


# dashboard
arrow_forward: str = "\ue5e1"


wifi_off: str = "&#xecfa;"
night_off: str = "&#xf162;"
notifications_off: str = "&#xece9;"
notifications: str = "\ue7f4"
notifications_clear: str = "&#xf814;"

do_not_disturb_on: str = "\ue644"

pill: str = "\ue11f"
dock_bottom: str = "\uf7e6"
power: str = "\ue63c"
dashboard: str = "\ue871"
wallpaper: str = "\ue1bc"
apps: str = "\ue5c3"
dictionary: str = "\uf539"
brightness_material: str = "\ue3ab"
font: str = "\ue167"
monitor: str = "\uef5b"
home: str = "\ue88a"
search: str = "\ue8b6"
settings: str = "\ue8b8"
edit_material: str = "\ue3c9"

explosion: str = "\uf685"
editors_choice: str = "\uf528"
bento: str = "\uf1f4"

east: str = "\uf1df"
north_east: str = "\uf1e1"
north: str = "\uf1e0"
south: str = "\uf1e3"
south_east: str = "\uf1e4"
west: str = "\uf1e6"
north_west: str = "\uf1e2"
south_west: str = "\uf1e5"
center: str = "\ue3b4"

select_check_box: str = "\uf1fe"
rocket_launch: str = "\ueb9b"

arrows_up_down_circle: str = "\ue600"

arrow_drop_down_circle: str = "\ue5c6"

arrow_circle_up: str = "\uf182"
arrow_circle_down: str = "\uf181"
arrow_circle_right: str = "\ueaaa"
arrow_circle_left: str = "\ueaa7"

play_pause: str = "\uf137"
skip_prev: str = "\ue045"
skip_next: str = "\ue044"
fast_rewind: str = "\ue020"
fast_forward: str = "\ue01f"
transition_push: str = "\uf50b"
headphones: str = "\uf01f"

# Bluetooth
bluetooth: str = "\ue1a7"
bluetooth_off: str = "&#xeceb;"
bluetooth_searching: str = "\ue1aa"

radar: str = "\uf04e"

close: str = "\ue5cd"
trash_material: str = "\ue872"

# player
disc: str = "\ue019"
play_material: str = "\ue037"
pause_material: str = "\ue034"
shuffle_material: str = "\ue043"

# Weather
humidity: str = "\uf163"
wind: str = "\uefd8"
pressure: str = "\ue94d"

# Power
lock: str = "\ue897"
suspend: str = "\uef44"
logout: str = "\ue9ba"
reboot: str = "\uf053"
shutdown: str = "\ue8ac"

# spotify : str = "\uf2d5"

# controls
brightness: str = "\ue3ab"
# vol_medium: str = "\ue04d"

# metrics
battery: str = "\uf304"
battery_charging: str = "\uf250"
cpu: str = "\ue322"
disk: str = "\uf20e"
memory: str = "\uf720"

blur: str = "\ue3a5"
refresh: str = "\ue5d5"
sync_saved_locally: str = "\uf820"

# wifi
wifi: str = "\ue63e"
wifi_1: str = "\ue4ca"
wifi_2: str = "\ue4d9"
wifi_3: str = "\uef16"
wifi_4: str = "\uef10"

# Vertical
toggle_orientation: str = "\uf2d5"

# Parameters
font_family: str = "Material Symbols Rounded"
font_weight: str = "normal"

# Pango markup btw
span: str = f"<span font-family='{font_family}' font-weight='{font_weight}'>"

exceptions: list[str] = ["font_family", "font_weight", "span"]


def materialize_icons() -> None:
    g = globals()
    for name, value in list(g.items()):
        if name.startswith("__"):
            continue
        if isinstance(value, str):
            g[name] = MaterialIcon(value)


materialize_icons()
