from pathlib import Path
from loguru import logger

from config.info import HOME_DIR
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
        hex_color = ensure_vibrancy(raw_color)

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
