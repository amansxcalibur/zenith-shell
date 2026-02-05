from icons.icon import Icon


class NerdIcon(Icon):
    __slots__ = ("family",)

    def __init__(self, symbol: str, *, family="Symbols Nerd Font"):
        super().__init__(symbol)
        self.family = family

    def markup(self) -> str:
        return f"<span font-family='{self.family}'>{self._symbol}</span>"


# Panels
apps: str = "&#xf1fd;"
dashboard: str = "&#xea87;"
chat: str = "&#xf59f;"
wallpapers: str = "&#xeb01;"
windows: str = "&#xefe6;"

# Bar
colorpicker: str = "&#xebe6;"
media: str = "&#xf00d;"

# Toolbox

toolbox: str = "&#xebca;"  # toolbox
ssfull: str = "&#xeaea;"  # camera
ssregion: str = "&#xf201;"  # camera
screenrecord: str = "&#xeafa;"  # video
ocr: str = "&#xfcc3;"  # text-recognition

# Circles
temp: str = "&#xeb38;"
disk: str = chr(0xF1632)
memory: str = chr(0xF01A7)
cpu: str = chr(0xF4BC)

# battery
bat_low: str = chr(0xF007A)
bat_charging: str = chr(0xF0085)
bat_full: str = chr(0xF120F)

# AIchat
reload: str = "&#xf3ae;"
detach: str = "&#xea99;"

# Wallpapers
add: str = "&#xeb0b;"
sort: str = "&#xeb5a;"
circle: str = "&#xf671;"

# Chevrons
chevron_up: str = "&#xea62;"
chevron_down: str = "&#xea5f;"
chevron_left: str = "&#xea60;"
chevron_right: str = "&#xea61;"

# Power
lock: str = chr(0xF023)
suspend: str = chr(0xF0904)
logout: str = chr(0xF0343)
reboot: str = chr(0xEAD2)
shutdown: str = chr(0xF011)

# Power Manager
power_saving: str = "&#xed4f;"
power_balanced: str = "&#xfa77;"
power_performance: str = "&#xec45;"
charging: str = chr(0xEFEF)
discharging: str = chr(0xEFE9)
alert: str = "&#xefb4;"

# Applets
wifi_0: str = "&#xeba3;"
wifi_1: str = "&#xeba4;"
wifi_2: str = "&#xeba5;"
wifi_3: str = "&#xeb52;"
world: str = "&#xeb54;"
world_off: str = "&#xf1ca;"
night: str = "&#xeaf8;"
coffee: str = "&#xef0e;"
notifications: str = chr(0xF0F3)
trash_up: str = chr(0xEF90)
trash: str = chr(0xF0A79)

wifi_off: str = "&#xecfa;"
bluetooth_off: str = "&#xeceb;"
night_off: str = "&#xf162;"
notifications_off: str = "&#xece9;"

notifications_clear: str = "&#xf814;"

# Bluetooth
bluetooth_connected: str = "&#xecea;"
bluetooth_disconnected: str = "&#xf081;"

# Player
# pause: str = "&#xf690;"
# play: str = chr(0xf691)
stop: str = "&#xf695;"
skip_back: str = "&#xf693;"
skip_forward: str = "&#xf694;"
# prev: str = "&#xf697;"
# next: str = "&#xf696;"
shuffle: str = "&#xf000;"
repeat: str = "&#xeb72;"
music: str = "&#xeafc;"
rewind_backward_5: str = "&#xfabf;"
rewind_forward_5: str = "&#xfac7;"

# Volume
vol_off: str = chr(0xEEE8)
vol_mute: str = chr(0xF026)
vol_medium: str = chr(0xF027)
# vol_high: str = "&#xeb51;"
vol_high: str = chr(0xF028)

mic: str = "&#xeaf0;"
mic_mute: str = "&#xed16;"

# Overview
circle_plus: str = "&#xea69;"

# Pins
copy_plus: str = "&#xfdae;"
paperclip: str = "&#xeb02;"

# Confirm
accept: str = "&#xea5e;"
# cancel: str = "&#xeb55;"
# cancel: str = chr(0xEA76)

# Config
config: str = "&#xeb20;"

# Icons
firefox: str = chr(0xF0239)
chromium: str = chr(0xF268)
spotify: str = chr(0xF1BC)
# disc: str = chr(0xede9)
disc_off: str = "&#xf118;"
silent: str = chr(0xF0376)

# Brightness
brightness_low: str = "&#xeb7d;"
brightness_medium: str = "&#xeb7e;"
brightness_high: str = "&#xeb30;"

# Misc
dot: str = "&#xf698;"
palette: str = chr(0xEB01)
cloud_off: str = "&#xed3e;"
loader: str = "&#xeca3;"
radar: str = "&#xf017;"
emoji: str = "&#xeaf7;"
trisquel: str = chr(0xF344)
alien: str = chr(0xF089A)
material: str = chr(0xF0986)

# Music
next: str = chr(0xF0F27)
next_fill: str = chr(0xF04AD)
previous: str = chr(0xF0F28)
previous_fill: str = chr(0xF04AE)
pause: str = chr(0xF04C)
play: str = chr(0xF04B)
shuffle: str = chr(0xF074)
disable_shuffle: str = chr(0xF049E)
headphones: str = chr(0xEE58)

# Weather
humidity: str = chr(0xE275)
wind: str = chr(0xE27E)
pressure: str = chr(0xF084D)

# Settings
settings: str = chr(0xF013)
# blur: str = chr(0xf00b5)
edit: str = chr(0xF01F)

# Vertical
toggle_horizontal: str = chr(0xF0885)


# Parameters
font_family: str = " "
font_weight: str = "normal"

span: str = f"<span font-family='{font_family}' font-weight='{font_weight}'>"

exceptions: list[str] = ["font_family", "font_weight", "span"]


def materialize_icons() -> None:
    g = globals()
    for name, value in list(g.items()):
        if name.startswith("__"):
            continue
        if isinstance(value, str):
            g[name] = NerdIcon(value)


materialize_icons()
