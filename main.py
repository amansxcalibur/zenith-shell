import fabric
from fabric import Application
from fabric.utils import get_relative_path

import config.info as info
from modules.dock_bar import DockBar
from modules.corners import Corners
from modules.notch import Notch

if __name__ == "__main__":
    notch = Notch()
    dockBar = DockBar()
    notch.set_role("notch")
    dockBar.notch = notch
    notification = None

    if info.VERTICAL:
        from modules.notifications import NotificationPopup

        notification = NotificationPopup()
        dockBar.set_title("fabric-dock")
        # make the window consume all vertical space
        monitor = dockBar._display.get_primary_monitor()
        rect = monitor.get_geometry()
        scale = monitor.get_scale_factor()
        dockBar.set_size_request(0, rect.height * scale)
        dockBar.show_all()
        notch.show_all()
        # bar.set_keep_above(True)

    app_kwargs = {
        "notch": notch,
        "dockBar": dockBar,
        "open_inspector": False,
    }

    if notification:
        app_kwargs["notification"] = notification

    app = Application("bar-example", **app_kwargs)

    def set_css():
        app.set_stylesheet_from_file(get_relative_path("./main.css"))

    app.set_css = set_css
    app.set_css()

    app.run()

    # corner = Corners()
    # app_corner = Application('corners', corner)
    # app_corner.set_stylesheet_from_file(get_relative_path("./styles/corner.css"))
    # app_corner.run()