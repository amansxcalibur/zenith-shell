# dashboard
wifi: str = "\ue63e"
arrow_forward: str = "\ue5e1"
bluetooth: str = "\ue1a7"

wifi_off: str = "&#xecfa;"
bluetooth_off: str = "&#xeceb;"
night_off: str = "&#xf162;"
notifications_off: str = "&#xece9;"

notifications_clear: str = "&#xf814;"

# player
disc : str = "\ue019"

# spotify : str = "\uf2d5"

# controls
brightness: str = "&#xe3ab;"
# vol_medium: str = "\ue04d"

# metrics
battery: str = "\uf304"
battery_charging: str = "\uf250"

blur: str = "\ue3a5"

# Vertical
toggle_orientation: str = "\uf2d5"


# Parameters
font_family: str = 'Material Symbols Rounded'
font_weight: str = 'normal'

# Pango markup btw
span: str = f"<span font-family='{font_family}' font-weight='{font_weight}'>"

exceptions: list[str] = ['font_family', 'font_weight', 'span']

def apply_span() -> None:
    global_dict = globals()
    for key in global_dict:
        if key not in exceptions and not key.startswith('__'):
            global_dict[key] = f"{span}{global_dict[key]}</span>"

apply_span()