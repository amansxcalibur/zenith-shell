from config.config import config
from config.i3.utils import (
    ensure_i3_paths,
    generate_i3_general_config,
    generate_i3_keybinds_config,
    add_shell_startup_to_i3_config,
    generate_i3_border_theme_config,
)

def bootstrap(runtime: bool = False):
    """
    Safe setup:
    - creates zenith directories
    - writes config.json if missing
    - generates i3 configs
    """

    # zenith owned paths (ConfigManager does it auto during init)
    config._ensure_directories()

    ensure_i3_paths()

    add_shell_startup_to_i3_config()

    # Generate i3 config files (NO reload during install)
    generate_i3_keybinds_config(reload=runtime)
    generate_i3_general_config(reload=runtime)
    generate_i3_border_theme_config(reload=runtime)

if __name__=="__main__":
    bootstrap()