from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.utils.helpers import exec_shell_command_async

from modules.notifications.notification import NotificationNotifier
from widgets.clipping_box import ClippingBox
from widgets.material_label import MaterialIconLabel
from utils.cursor import add_hover_cursor
from utils.colors import bind_theme
import icons

import gi

gi.require_version("Gray", "0.1")
from gi.repository import Gray, Gtk, Gdk, GdkPixbuf, GLib  # type: ignore


class NotificationIndicator(Box):
    def __init__(self, vertical: bool = False):
        # vertical: the button takes the rail's width, the icon stays centred
        # with the unread dot next to it
        super().__init__(orientation="v" if vertical else "h")
        self.unread_notif_indicator = Box(
            name="notif-unread-indicator",
            v_align="start",
            h_align="end",
        )
        self.overlayed_widget = Box(
            children=[
                Box(h_expand=True),
                self.unread_notif_indicator,
            ],
        )
        self.notification_notifier = NotificationNotifier()
        self.notification_notifier.connect(
            "notify::has-unread", self._on_unread_notification_prop_change
        )
        self.notification_notifier.connect(
            "notify::has-urgent-unread", self._on_unread_notification_prop_change
        )

        self.overlay = Overlay(
            child=MaterialIconLabel(
                name="systray-notif-icon",
                font_size=18,
                icon_text=icons.material.notifications.symbol(),
            ),
            overlays=self.overlayed_widget,
            h_align="center" if vertical else None,
        )
        self.overlay.set_overlay_pass_through(self.overlayed_widget, True)

        self.children = add_hover_cursor(
            Button(
                name="systray-notif-btn",
                child=self.overlay,
                on_clicked=lambda: exec_shell_command_async(
                    'fabric-cli exec zenith "top_pill.toggle_notification()"'
                ),
            )
        )

    def _on_unread_notification_prop_change(self, *_):
        if self.notification_notifier.has_unread:
            self.unread_notif_indicator.add_style_class("unread")
            if self.notification_notifier.has_urgent_unread:
                self.unread_notif_indicator.add_style_class("urgent")
        else:
            self.unread_notif_indicator.remove_style_class("unread")
            self.unread_notif_indicator.remove_style_class("urgent")


class SystemTray(Box):
    def __init__(self, pixel_size: int = 20, vertical: bool = False, **kwargs) -> None:
        super().__init__(
            name="systray",
            orientation=("v" if vertical else "h"),
            **kwargs,
        )
        self.pixel_size = pixel_size
        self._path_themes: dict[str, Gtk.IconTheme] = {}
        self.watcher = Gray.Watcher()
        self.watcher.connect("item-added", self.on_item_added)

        self.clipper = ClippingBox(
            name="systray-clipper",
            spacing=1,
            orientation=("v" if vertical else "h"),
        )
        self.clipper.add(NotificationIndicator(vertical=vertical))

        self.spacer = Box(name="systray-spacer")
        self.clipper.add(self.spacer)

        self.add(self.clipper)

    def on_item_added(self, _, identifier: str):
        item = self.watcher.get_item_for_identifier(identifier)
        item_button = self.do_bake_item_button(item)
        item.connect("removed", lambda *args: self.on_item_removed(item_button))
        self.clipper.add(item_button)
        item_button.show_all()
        # self.spacer.set_visible(True)

    def on_item_removed(self, item_button):
        item_button.destroy()
        # if len(self.clipper.get_children()) <= 2:
        #     self.spacer.set_visible(False)

    def _item_pixbuf(self, item: Gray.Item) -> GdkPixbuf.Pixbuf | None:
        pixmaps = item.get_icon_pixmaps()
        pixmap = (
            Gray.get_pixmap_for_pixmaps(pixmaps, self.pixel_size) if pixmaps else None
        )
        if pixmap is not None:
            try:
                return pixmap.as_pixbuf(self.pixel_size, GdkPixbuf.InterpType.HYPER)
            except GLib.Error as e:
                logger.warning(f"[Systray] Bad pixmap for {item.get_id()}: {e}")

        default_theme = Gtk.IconTheme.get_default()
        themes = [default_theme]
        theme_path = item.get_icon_theme_path()
        if theme_path:
            themes.insert(0, self._theme_for_path(theme_path))

        icon_name = item.get_icon_name()
        attempts = [(theme, icon_name) for theme in themes if icon_name]
        attempts.append((default_theme, "image-missing"))

        for theme, name in attempts:
            try:
                return theme.load_icon(
                    name, self.pixel_size, Gtk.IconLookupFlags.FORCE_SIZE
                )
            except GLib.Error:
                continue
        return None

    def _theme_for_path(self, path: str) -> Gtk.IconTheme:
        # one theme per search path; building one per item re-scans the directory
        if path not in self._path_themes:
            theme = Gtk.IconTheme.new()
            theme.prepend_search_path(path)
            self._path_themes[path] = theme
        return self._path_themes[path]

    def do_bake_item_button(self, item: Gray.Item) -> Gtk.Button:
        button = Gtk.Button()

        button.connect(
            "button-press-event",
            lambda button, event: self.on_button_click(button, item, event),
        )

        button.set_image(Gtk.Image.new_from_pixbuf(self._item_pixbuf(item)))
        button.set_name("tray-button")
        return button

    def on_button_click(self, button, item: Gray.Item, event):
        if event.button == Gdk.BUTTON_PRIMARY:  # Left click
            try:
                item.activate(event.x, event.y)
            except Exception as e:
                logger.error(f"Error activating item: {e}")
        elif event.button == Gdk.BUTTON_SECONDARY:  # Right click
            menu = item.get_menu()
            if menu:
                menu.set_name("system-tray-menu")
                bind_theme(menu)
                menu.popup_at_widget(
                    button,
                    Gdk.Gravity.SOUTH,
                    Gdk.Gravity.NORTH,
                    event,
                )
            else:
                item.context_menu(event.x, event.y)
