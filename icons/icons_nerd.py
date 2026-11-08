from icons.icon import Icon


class NerdIcon(Icon):
    __slots__ = ("family",)

    def __init__(self, symbol: str, *, family="Symbols Nerd Font"):
        super().__init__(symbol)
        self.family = family

    def markup(self) -> str:
        return f"<span font-family='{self.family}'>{self._symbol}</span>"


_N = NerdIcon

# Panels
apps: NerdIcon = _N("\uf1fd")
dashboard: NerdIcon = _N("\uea87")
chat: NerdIcon = _N("\uf59f")
wallpapers: NerdIcon = _N("\ueb01")
windows: NerdIcon = _N("\uefe6")

# Bar
colorpicker: NerdIcon = _N("\uebe6")
media: NerdIcon = _N("\uf00d")

# Toolbox
toolbox: NerdIcon = _N("\uebca")
ssfull: NerdIcon = _N("\ueaea")
ssregion: NerdIcon = _N("\uf201")
screenrecord: NerdIcon = _N("\ueafa")
ocr: NerdIcon = _N("\ufcc3")

# Metrics
temp: NerdIcon = _N("\ueb38")

# Battery / power
bat_low: NerdIcon = _N("\U000f007a")
bat_charging: NerdIcon = _N("\U000f0085")
bat_full: NerdIcon = _N("\U000f120f")
charging: NerdIcon = _N("\uefef")
discharging: NerdIcon = _N("\uefe9")
power_saving: NerdIcon = _N("\ued4f")
power_balanced: NerdIcon = _N("\ufa77")
power_performance: NerdIcon = _N("\uec45")
alert: NerdIcon = _N("\uefb4")

# AI chat
reload: NerdIcon = _N("\uf3ae")
detach: NerdIcon = _N("\uea99")

# Wallpapers
add: NerdIcon = _N("\ueb0b")
sort: NerdIcon = _N("\ueb5a")
circle: NerdIcon = _N("\uf671")
palette: NerdIcon = _N("\ueb01")

# Chevrons
chevron_right: NerdIcon = _N("\uea61")
chevron_up: NerdIcon = _N("\uea62")
chevron_down: NerdIcon = _N("\uea5f")
chevron_left: NerdIcon = _N("\uea60")

# Network
wifi_1: NerdIcon = _N("\ueba4")
wifi_2: NerdIcon = _N("\ueba5")
wifi_3: NerdIcon = _N("\ueb52")
wifi_off: NerdIcon = _N("\uecfa")
bluetooth_off: NerdIcon = _N("\ueceb")
radar: NerdIcon = _N("\uf017")
wifi_0: NerdIcon = _N("\ueba3")
world: NerdIcon = _N("\ueb54")
world_off: NerdIcon = _N("\uf1ca")
bluetooth_connected: NerdIcon = _N("\uecea")
bluetooth_disconnected: NerdIcon = _N("\uf081")

# Toggles
night_off: NerdIcon = _N("\uf162")
notifications: NerdIcon = _N("\uf0f3")
notifications_off: NerdIcon = _N("\uece9")
notifications_clear: NerdIcon = _N("\uf814")
night: NerdIcon = _N("\ueaf8")
coffee: NerdIcon = _N("\uef0e")
trash_up: NerdIcon = _N("\uef90")
trash: NerdIcon = _N("\U000f0a79")

# Player
play: NerdIcon = _N("\uf04b")
pause: NerdIcon = _N("\uf04c")
stop: NerdIcon = _N("\uf695")
next: NerdIcon = _N("\U000f0f27")
next_fill: NerdIcon = _N("\U000f04ad")
previous: NerdIcon = _N("\U000f0f28")
previous_fill: NerdIcon = _N("\U000f04ae")
skip_back: NerdIcon = _N("\uf693")
skip_forward: NerdIcon = _N("\uf694")
shuffle: NerdIcon = _N("\uf074")
disable_shuffle: NerdIcon = _N("\U000f049e")
repeat: NerdIcon = _N("\ueb72")
music: NerdIcon = _N("\ueafc")
rewind_backward_5: NerdIcon = _N("\ufabf")
rewind_forward_5: NerdIcon = _N("\ufac7")
disc_off: NerdIcon = _N("\uf118")

# Volume
mic: NerdIcon = _N("\ueaf0")
vol_off: NerdIcon = _N("\ueee8")
vol_mute: NerdIcon = _N("\uf026")
vol_medium: NerdIcon = _N("\uf027")
vol_high: NerdIcon = _N("\uf028")
mic_mute: NerdIcon = _N("\ued16")
silent: NerdIcon = _N("\U000f0376")

# Overview / pins
circle_plus: NerdIcon = _N("\uea69")
copy_plus: NerdIcon = _N("\ufdae")
paperclip: NerdIcon = _N("\ueb02")
accept: NerdIcon = _N("\uea5e")
config: NerdIcon = _N("\ueb20")
edit: NerdIcon = _N("\uf01f")

# App logos
firefox: NerdIcon = _N("\U000f0239")
chromium: NerdIcon = _N("\uf268")
spotify: NerdIcon = _N("\uf1bc")
trisquel: NerdIcon = _N("\uf344")
alien: NerdIcon = _N("\U000f089a")
material: NerdIcon = _N("\U000f0986")

# Display
brightness_low: NerdIcon = _N("\ueb7d")
brightness_medium: NerdIcon = _N("\ueb7e")
brightness_high: NerdIcon = _N("\ueb30")

# Misc
dot: NerdIcon = _N("\uf698")
cloud_off: NerdIcon = _N("\ued3e")
loader: NerdIcon = _N("\ueca3")
emoji: NerdIcon = _N("\ueaf7")
toggle_horizontal: NerdIcon = _N("\U000f0885")
