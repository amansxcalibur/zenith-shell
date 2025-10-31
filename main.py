from fabric import Application
from fabric.widgets.x11 import X11Window as Window

Window.toggle_visibility = lambda self: self.set_visible(not self.is_visible())

from fabric.utils import get_relative_path, monitor_file

from modules.pill import Pill
from modules.dock.bar import DockBar
from modules.notifications import NotificationPopup
from modules.notification import NotificationManager
# from modules.notification_bar import NotificationBar

from config.info import SHELL_NAME

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

import setproctitle

if __name__ == "__main__":
    setproctitle.setproctitle(SHELL_NAME)
    pill = Pill()
    dockBar = DockBar()
    pill.set_role("pill")
    dockBar.set_title("fabric-dock")
    pill_size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
    pill_size_group.add_widget(dockBar.pill)
    pill_size_group.add_widget(pill.pill_container)
    controls_notification = NotificationPopup()
    notification = NotificationManager()
    # notif_bar = NotificationBar()

    app_kwargs = {
        "pill": pill,
        "dockBar": dockBar,
        "controls_notification": controls_notification,
        "notification": notification,
        # "notification-bar": notif_bar,
        "open_inspector": False,
    }

    app = Application(SHELL_NAME, **app_kwargs)

    def set_css(*args):
        app.set_stylesheet_from_file(get_relative_path("./main.css"))

    app.style_monitor = monitor_file(get_relative_path("./styles"))
    app.style_monitor.connect("changed", set_css)
    set_css()

    app.run()

    # corner = Corners()
    # app_corner = Application('corners', corner)
    # app_corner.set_stylesheet_from_file(get_relative_path("./styles/corner.css"))
    # app_corner.run()
