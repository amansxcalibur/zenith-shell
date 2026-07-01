from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.utils.helpers import exec_shell_command_async

from modules.notifications.notification import NotificationNotifier
from widgets.clipping_box import ClippingBox
from widgets.material_label import MaterialIconLabel
from utils.cursor import add_hover_cursor
from config.config import config
import icons

import gi

gi.require_version("Gray", "0.1")
from gi.repository import Gray, Gtk, Gdk, GdkPixbuf, GLib


class NotificationIndicator(Box):
    def __init__(self):
        super().__init__()
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
                font_size=18,
                icon_text=icons.notifications.symbol(),
            ),
            overlays=self.overlayed_widget,
        )
        self.overlay.set_overlay_pass_through(self.overlayed_widget, True)
        self.children = Box(
            children=[
                add_hover_cursor(
                    Button(
                        name="systray-notif-btn",
                        child=self.overlay,
                        on_clicked=lambda: exec_shell_command_async(
                            'fabric-cli exec zenith "top_pill.toggle_notification()"'
                        ),
                    )
                ),
                # spacer
                Box(
                    style=""
                    "background-color:var(--surface-semi-bright); "
                    "min-width: 2px; "
                    "margin: 3px 4px 3px 0px; "
                    "border-radius: 4px;"
                ),
            ]
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
    def __init__(self, pixel_size: int = 20, **kwargs) -> None:
        super().__init__(
            name="systray",
            orientation=("v" if config.VERTICAL else "h"),
            **kwargs,
        )
        self.set_visible(False)  # Initially hidden when empty.
        self.pixel_size = pixel_size
        self.watcher = Gray.Watcher()
        self.watcher.connect("item-added", self.on_item_added)
        self.clipper = ClippingBox(
            name='systray-clipper',
            spacing=1,
            orientation=("v" if config.VERTICAL else "h"),
        )
        self.clipper.add(NotificationIndicator())
        self.add(self.clipper)

    def _update_visibility(self):
        # Update visibility based on the number of child widgets.
        self.set_visible(len(self.get_children()) > 0)

    def on_item_added(self, _, identifier: str):
        item = self.watcher.get_item_for_identifier(identifier)
        item_button = self.do_bake_item_button(item)
        item.connect(
            "removed", lambda *args: (item_button.destroy(), self._update_visibility())
        )
        self.clipper.add(item_button)
        item_button.show_all()
        self._update_visibility()

    def do_bake_item_button(self, item: Gray.Item) -> Gtk.Button:
        button = Gtk.Button()

        button.connect(
            "button-press-event",
            lambda button, event: self.on_button_click(button, item, event),
        )

        pixmap = Gray.get_pixmap_for_pixmaps(item.get_icon_pixmaps(), self.pixel_size)

        try:
            if pixmap is not None:
                pixbuf = pixmap.as_pixbuf(self.pixel_size, GdkPixbuf.InterpType.HYPER)
            else:
                icon_name = item.get_icon_name()
                icon_theme_path = item.get_icon_theme_path()

                # Use custom theme path if available
                if icon_theme_path:
                    custom_theme = Gtk.IconTheme.new()
                    custom_theme.prepend_search_path(icon_theme_path)
                    try:
                        pixbuf = custom_theme.load_icon(
                            icon_name,
                            self.pixel_size,
                            Gtk.IconLookupFlags.FORCE_SIZE,
                        )
                    except GLib.Error:
                        # Fallback to default theme if custom path fails
                        pixbuf = Gtk.IconTheme.get_default().load_icon(
                            icon_name,
                            self.pixel_size,
                            Gtk.IconLookupFlags.FORCE_SIZE,
                        )
                else:
                    pixbuf = Gtk.IconTheme.get_default().load_icon(
                        icon_name,
                        self.pixel_size,
                        Gtk.IconLookupFlags.FORCE_SIZE,
                    )
        except GLib.Error:
            # Fallback to 'image-missing' icon
            pixbuf = Gtk.IconTheme.get_default().load_icon(
                "image-missing",
                self.pixel_size,
                Gtk.IconLookupFlags.FORCE_SIZE,
            )

        button.set_image(Gtk.Image.new_from_pixbuf(pixbuf))
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
                menu.popup_at_widget(
                    button,
                    Gdk.Gravity.SOUTH,
                    Gdk.Gravity.NORTH,
                    event,
                )
            else:
                item.context_menu(event.x, event.y)
