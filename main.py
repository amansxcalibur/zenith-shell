from fabric import Application
from fabric.widgets.x11 import X11Window as Window

Window.toggle_visibility = lambda self: self.set_visible(not self.is_visible())

from fabric.utils import get_relative_path, monitor_file

from modules.core.pill import Pill
from modules.corners import Corners
from modules.core.dock.bar import DockBar
from modules.notifications import NotificationPopup
from modules.notification import NotificationManager
from modules.core.shell_window_manager import ShellWindowManager
# from modules.notification_bar import NotificationBar

from config.info import SHELL_NAME
from config.i3_config import i3_border_setter

from gi.repository import GLib

import setproctitle

if __name__ == "__main__":
    setproctitle.setproctitle(SHELL_NAME)
    GLib.set_prgname(SHELL_NAME)
    pill = Pill()
    dockBar = DockBar(pill=pill)
    pill.set_role("pill")
    dockBar.set_title("fabric-dock")
    window_manager = ShellWindowManager(pill = pill, dockBar = dockBar)
    controls_notification = NotificationPopup()
    notification = NotificationManager()
    corners = Corners()
    # notif_bar = NotificationBar()

    app_kwargs = {
        "pill": pill,
        "dockBar": dockBar,
        "corners": corners,
        "controls_notification": controls_notification,
        "notification": notification,
        # "notification-bar": notif_bar,
        "open_inspector": False,
    }

    app = Application(SHELL_NAME, **app_kwargs)

    def set_css(*args):
        app.set_stylesheet_from_file(get_relative_path("./main.css"))
        i3_border_setter()

    app.style_monitor = monitor_file(get_relative_path("./styles"))
    app.style_monitor.connect("changed", set_css)
    set_css()

    app.run()
