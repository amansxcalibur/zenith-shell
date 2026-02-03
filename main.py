import os
import setproctitle
from gi.repository import GLib

from fabric import Application
from fabric.widgets.x11 import X11Window as Window

Window.toggle_visibility = lambda self: self.set_visible(not self.is_visible())

from fabric.utils import get_relative_path, monitor_file

from modules.corners import Corners
from modules.core.top.bar import TopBar
from modules.core.top.pill import TopPill
from modules.core.bottom.pill import Pill
from modules.wallpaper import WallpaperService
from modules.core.bottom.dock.bar import DockBar
from modules.transient_window import TransientWindow
from modules.core.bottom.shell_window_manager import ShellWindowManager
from modules.core.top.shell_window_manager import ShellTopWindowManager

from config.info import config, SHELL_NAME, HOME_DIR, ROOT_DIR
from config.i3.utils import (
    generate_i3_general_config,
    generate_i3_keybinds_config,
    generate_i3_border_theme_config,
)


def normalize_path():
    # for shutil checks and whatnot
    extra_paths = [
        os.path.join(HOME_DIR, ".local/bin"),
        os.path.join(HOME_DIR, ".cargo/bin"),
    ]

    current_path = os.environ.get("PATH", "").split(os.path.pathsep)

    for p in reversed(extra_paths):
        if p not in current_path:
            current_path.insert(0, p)

    os.environ["PATH"] = os.path.pathsep.join(current_path)


# def load_gresources():
#     # Behold over-engineer. All this to load a whopping 10kb worth imgs...
#     # Maybe I should just stick with the css injection.
#     resource_path = get_relative_path("zenith.gresource")

#     if not os.path.exists(resource_path):
#         logger.error(
#             "[Zenith] ERROR: GResource bundle not found:\n"
#             f"  {resource_path}\n\n"
#             "You probably forgot to run:\n"
#             "  glib-compile-resources zenith.gresource.xml\n"
#         )
#         return False

#     resource = Gio.Resource.load(resource_path)
#     Gio.resources_register(resource)
#     return True


if __name__ == "__main__":
    setproctitle.setproctitle(SHELL_NAME + "-core")
    GLib.set_prgname(SHELL_NAME + "-core")

    normalize_path()
    # load_gresources() # Not pushing resource binaries (until I make an install script)

    config._ensure_directories()

    # set wallpaper and init service
    WallpaperService().initialize()

    # set i3 keybinds. Don't reload yet
    generate_i3_keybinds_config()
    generate_i3_general_config()

    pill = Pill()
    dockBar = DockBar(pill=pill)
    bottom_window_manager = ShellWindowManager(pill=pill, dockBar=dockBar)

    controls_transient_window = TransientWindow()

    top_pill = TopPill()
    top_bar = TopBar(pill=top_pill)
    top_window_manager = ShellTopWindowManager(pill=top_pill, dockBar=top_bar)

    corners = None
    if config.corners.enable:
        corners = Corners(config.corners.props.radius)

    app_kwargs = {
        "pill": pill,
        "dockBar": dockBar,
        "corners": corners,
        "controls_notification": controls_transient_window,
        "open_inspector": False,
    }

    app = Application(SHELL_NAME, **app_kwargs)

    def set_css(*args):
        app.set_stylesheet_from_file(
            get_relative_path("./main.css"),
            # feast on juggad
            exposed_functions={
                "mute_slider_img": lambda: f"background-image: url('{ROOT_DIR}/icons/mute.png');",
                "volume_slider_img": lambda: f"background-image: url('{ROOT_DIR}/icons/volume.png');",
                "brightness_slider_img": lambda: f"background-image: url('{ROOT_DIR}/icons/brightness.png');",
            },
        )
        # relaods i3wm
        generate_i3_border_theme_config(reload=True)

    app.style_monitor = monitor_file(get_relative_path("./styles"))
    app.style_monitor.connect("changed", set_css)
    set_css()

    app.run()
