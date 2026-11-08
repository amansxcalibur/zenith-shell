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


_M = MaterialIcon

# Navigation / arrows
arrow_forward: MaterialIcon = _M("\ue5e1")
arrow_backward: MaterialIcon = _M("\ue2ea")
arrow_back: MaterialIcon = _M("\ue5c4")
arrow_circle_up: MaterialIcon = _M("\uf182")
arrow_circle_down: MaterialIcon = _M("\uf181")
arrow_circle_left: MaterialIcon = _M("\ueaa7")
arrow_circle_right: MaterialIcon = _M("\ueaaa")
arrow_drop_down_circle: MaterialIcon = _M("\ue5c6")
arrows_up_down_circle: MaterialIcon = _M("\ue600")
swap_vert: MaterialIcon = _M("\ue8d5")
expand_more: MaterialIcon = _M("\ue5cf")
expand_less: MaterialIcon = _M("\ue5ce")
chevron_right: MaterialIcon = _M("\ue5cc")

# Compass / positions
north: MaterialIcon = _M("\uf1e0")
north_east: MaterialIcon = _M("\uf1e1")
east: MaterialIcon = _M("\uf1df")
south_east: MaterialIcon = _M("\uf1e4")
south: MaterialIcon = _M("\uf1e3")
south_west: MaterialIcon = _M("\uf1e5")
west: MaterialIcon = _M("\uf1e6")
north_west: MaterialIcon = _M("\uf1e2")
center: MaterialIcon = _M("\ue3b4")

# Panels / apps
dashboard: MaterialIcon = _M("\ue871")
apps: MaterialIcon = _M("\ue5c3")
home: MaterialIcon = _M("\ue88a")
search: MaterialIcon = _M("\ue8b6")
settings: MaterialIcon = _M("\ue8b8")
wallpaper: MaterialIcon = _M("\ue1bc")
hide_image: MaterialIcon = _M("\uf022")
dictionary: MaterialIcon = _M("\uf539")
font: MaterialIcon = _M("\ue167")
monitor: MaterialIcon = _M("\uef5b")
bento: MaterialIcon = _M("\uf1f4")
pill: MaterialIcon = _M("\ue11f")
dock_bottom: MaterialIcon = _M("\uf7e6")
planet: MaterialIcon = _M("\uf387")
explosion: MaterialIcon = _M("\uf685")
editors_choice: MaterialIcon = _M("\uf528")
rocket_launch: MaterialIcon = _M("\ueb9b")
transition_push: MaterialIcon = _M("\uf50b")
toggle_orientation: MaterialIcon = _M("\uf2d5")

# Actions
add_material: MaterialIcon = _M("\ue145")
add_circle: MaterialIcon = _M("\ue147")
close: MaterialIcon = _M("\ue5cd")
check_material: MaterialIcon = _M("\ue5ca")
select_check_box: MaterialIcon = _M("\uf1fe")
edit_material: MaterialIcon = _M("\ue3c9")
content_copy: MaterialIcon = _M("\ue14d")
trash_material: MaterialIcon = _M("\ue872")
delete_sweep: MaterialIcon = _M("\ue16c")
clear_all: MaterialIcon = _M("\ue0b8")
mop: MaterialIcon = _M("\ue28d")
refresh: MaterialIcon = _M("\ue5d5")
sync_saved_locally: MaterialIcon = _M("\uf820")
open_in_full: MaterialIcon = _M("\uf1ce")
close_fullscreen: MaterialIcon = _M("\uf1cf")
drag_indicator: MaterialIcon = _M("\ue945")

# Files
folder_open: MaterialIcon = _M("\ue2c8")
folder_material: MaterialIcon = _M("\ue2c7")
image_material: MaterialIcon = _M("\ue3f4")
description: MaterialIcon = _M("\ue873")
code: MaterialIcon = _M("\ue86f")
info: MaterialIcon = _M("\ue88e")
warning: MaterialIcon = _M("\ue002")

# Notifications
notifications: MaterialIcon = _M("\ue7f4")
notifications_off: MaterialIcon = _M("\uece9")
notifications_clear: MaterialIcon = _M("\uf814")
do_not_disturb_on: MaterialIcon = _M("\ue644")

# Network
wifi: MaterialIcon = _M("\ue63e")
wifi_1: MaterialIcon = _M("\ue4ca")
wifi_2: MaterialIcon = _M("\ue4d9")
wifi_3: MaterialIcon = _M("\uef16")
wifi_4: MaterialIcon = _M("\uef10")
wifi_off: MaterialIcon = _M("\uecfa")
lan: MaterialIcon = _M("\ueb2f")
link_off: MaterialIcon = _M("\ue16f")
key: MaterialIcon = _M("\ue73c")
globe_2_question: MaterialIcon = _M("\U000fffb6")
radar: MaterialIcon = _M("\uf04e")

# Bluetooth
bluetooth: MaterialIcon = _M("\ue1a7")
bluetooth_off: MaterialIcon = _M("\ueceb")
bluetooth_searching: MaterialIcon = _M("\ue1aa")

# Media / player
disc: MaterialIcon = _M("\ue019")
play_material: MaterialIcon = _M("\ue037")
pause_material: MaterialIcon = _M("\ue034")
play_pause: MaterialIcon = _M("\uf137")
skip_prev: MaterialIcon = _M("\ue045")
skip_next: MaterialIcon = _M("\ue044")
fast_rewind: MaterialIcon = _M("\ue020")
fast_forward: MaterialIcon = _M("\ue01f")
shuffle_material: MaterialIcon = _M("\ue043")
music_note: MaterialIcon = _M("\ue405")
music_off: MaterialIcon = _M("\ue440")

# Audio
volume_up: MaterialIcon = _M("\ue050")
volume_down: MaterialIcon = _M("\ue04d")
volume_off: MaterialIcon = _M("\ue04f")
mic: MaterialIcon = _M("\ue029")
mic_off: MaterialIcon = _M("\ue02b")
headphones: MaterialIcon = _M("\uf01f")
headset_mic: MaterialIcon = _M("\ue311")
speaker: MaterialIcon = _M("\ue32d")
tv: MaterialIcon = _M("\ue333")
layers: MaterialIcon = _M("\ue53b")

# Display
brightness: MaterialIcon = _M("\ue3ab")
brightness_material: MaterialIcon = _M("\ue3ab")
brightness_low: MaterialIcon = _M("\uf7e8")
brightness_medium: MaterialIcon = _M("\ue3ab")
brightness_high: MaterialIcon = _M("\ue1ac")
contrast: MaterialIcon = _M("\ueb37")
blur: MaterialIcon = _M("\ue3a5")
night_off: MaterialIcon = _M("\uf162")

# Power
power: MaterialIcon = _M("\ue63c")
lock: MaterialIcon = _M("\ue897")
suspend: MaterialIcon = _M("\uef44")
logout: MaterialIcon = _M("\ue9ba")
reboot: MaterialIcon = _M("\uf053")
shutdown: MaterialIcon = _M("\ue8ac")
balance: MaterialIcon = _M("\ueaf6")
energy_savings_leaf: MaterialIcon = _M("\uec1a")

# Metrics
battery: MaterialIcon = _M("\uf304")
battery_charging: MaterialIcon = _M("\uf250")
cpu: MaterialIcon = _M("\ue322")
disk: MaterialIcon = _M("\uf20e")
memory: MaterialIcon = _M("\uf720")
device_thermostat: MaterialIcon = _M("\ue1ff")
speed: MaterialIcon = _M("\ue9e4")
monitoring: MaterialIcon = _M("\uf190")
leaderboard: MaterialIcon = _M("\uf20c")

# Time
history: MaterialIcon = _M("\ue889")
schedule: MaterialIcon = _M("\ue8b5")

# Weather
humidity: MaterialIcon = _M("\uf163")
wind: MaterialIcon = _M("\uefd8")
pressure: MaterialIcon = _M("\ue94d")
