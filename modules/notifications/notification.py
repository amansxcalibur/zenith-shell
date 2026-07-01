import time
import random
from loguru import logger
from typing import Callable
from datetime import datetime
from expressive_shapes.shapes.shape_presets import (
    fan,
    gem,
    bun,
    pill,
    star,
    oval,
    arch,
    boom,
    heart,
    arrow,
    sunny,
    flower,
    shield,
    circle,
    square,
    slanted,
    diamond,
    triangle,
    pentagon,
    cookie_4,
    cookie_8,
    clamshell,
    ghost_ish,
    cookie_12,
    very_sunny,
    semicircle,
    pixel_circle,
    organic_blob,
    leaf_clover_4,
    leaf_clover_8,
    puffy_diamond,
    pixel_triangle,
)

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.notifications import Notifications, Notification
from fabric.utils import invoke_repeater

from modules.tile import TileSimple
from widgets.clipping_box import ClippingBox
from widgets.rounded_image import RoundedImage
from widgets.material_label import MaterialIconLabel
from widgets.shapes.expressive.morphing_shapes import ExpressiveShape
from utils.helpers import format_accel_to_keybind
import icons
from config.config import config

from .notification_group import NotificationGroup
from .common import NotificationConfig, NotificationNotifier

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gdk, GLib  # noqa: E402


class NotificationTile(TileSimple):
    def __init__(self, **kwargs):
        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Off",
            h_align="start",
        )
        self.state = None
        super().__init__(
            markup=icons.do_not_disturb_on.symbol(),
            label="Silent",
            status_label_widget=self.label,
            style_classes=["off"],
            **kwargs,
        )
        self.update_visual()

    def update_visual(self):
        if config.SILENT:
            self.remove_style_class("off")
            self.add_style_class("on")
            self.props.set_label("On")
        else:
            self.remove_style_class("on")
            self.add_style_class("off")
            self.props.set_label("Off")

    def handle_state_toggle(self, *_):
        # CHANGES CONFIG
        config.SILENT = not config.SILENT
        self.update_visual()
        return super().handle_state_toggle(*_)


class ActiveNotificationWidget(EventBox):
    _SHAPES = [
        fan,
        gem,
        bun,
        pill,
        star,
        oval,
        arch,
        boom,
        heart,
        arrow,
        sunny,
        flower,
        shield,
        circle,
        square,
        slanted,
        diamond,
        triangle,
        pentagon,
        cookie_4,
        cookie_8,
        clamshell,
        ghost_ish,
        cookie_12,
        very_sunny,
        semicircle,
        pixel_circle,
        organic_blob,
        leaf_clover_4,
        leaf_clover_8,
        puffy_diamond,
        pixel_triangle,
    ]

    def __init__(
        self,
        notification: Notification,
        timeout_callback: Callable,
        on_close_callback: Callable,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._notification = notification
        self._notification.shape = None
        self._timeout_callback = timeout_callback
        self._on_close_callback = on_close_callback
        self._on_press_connection = None
        self._closed_connection = None
        self._timeout_repeater_id = None
        self._scaled_pixbuf = None
        self.timestamp = datetime.now()
        self.urgency = notification.urgency

        body_container = Box(name="notification-box", orientation="v", spacing=10)
        content_box = Box(spacing=10)

        try:
            if image_pixbuf := self._notification.image_pixbuf:
                self._scaled_pixbuf = image_pixbuf.scale_simple(
                    NotificationConfig.IMAGE_SIZE,
                    NotificationConfig.IMAGE_SIZE,
                    GdkPixbuf.InterpType.BILINEAR,
                )
                content_box.add(
                    RoundedImage(
                        v_align="start",
                        pixbuf=self._scaled_pixbuf,
                        style="border-radius:16px;",
                    )
                )
            else:
                self._notification.shape = random.choice(self._SHAPES)
                content_box.add(
                    Box(
                        name="img-expander",
                        style_classes="expand",
                        v_align="start",
                        children=ExpressiveShape(shape=self._notification.shape),
                    )
                )
        except Exception as e:
            logger.error(f"Failed to resolve image_pixbuff: {e}")
            self._notification.shape = random.choice(self._SHAPES)
            content_box.add(
                Box(
                    name="img-expander",
                    style_classes="expand",
                    v_align="start",
                    children=ExpressiveShape(shape=self._notification.shape),
                )
            )

        # TODO: implement real Revealer with animations and Pango pixel length(?)
        self.revealer_btn_label = MaterialIconLabel(
            icon_text=icons.arrow_forward.symbol(),
            angle=-90,
        )
        self.revealer_btn = Button(
            name="notif-expander-btn",
            child=self.revealer_btn_label,
            on_clicked=self._on_notification_expanded,
        )

        match self.urgency:
            case 0 | 1:
                body_container.add_style_class("normal")
                self.revealer_btn.add_style_class("normal")
            case 2:
                body_container.add_style_class("critical")
                self.revealer_btn.add_style_class("critical")
            case _:
                logger.warning(f"Unknown notification urgency level {self.urgency}")

        self.notif_body_label = Label(
            label=self._notification.body,
            line_wrap="word-char",
            ellipsization="end",
            style_classes="body",
            max_chars_width=NotificationConfig.MAX_CHARS_PER_LINE,
            h_align="start",
        )
        self.notif_body_label.set_lines(NotificationConfig.LINE_LIMIT)

        content_box.add(
            Box(
                spacing=4,
                orientation="h",
                children=[
                    Box(
                        orientation="v",
                        children=[
                            Box(
                                spacing=6,
                                h_expand=True,
                                children=[
                                    Label(
                                        label=self._notification.app_name,
                                        h_align="start",
                                        v_expand=True,
                                        style_classes="app-name",
                                        ellipsization="end",
                                        max_chars_width=17,
                                    ),
                                    Box(
                                        style_classes=["notif-dot-separator"],
                                        v_align="center",
                                    ),
                                    Label(
                                        h_expand=True,
                                        label=self.timestamp.strftime("%H:%M"),
                                        h_align="start",
                                        style_classes="timestamp",
                                    ),
                                    self.revealer_btn,
                                ],
                            ),
                            Label(
                                label=self._notification.summary,
                                h_align="start",
                                v_expand=True,
                                style_classes="summary",
                                ellipsization="end",
                                max_chars_width=27,
                            ),
                            self.notif_body_label,
                        ],
                        h_expand=True,
                        v_expand=True,
                    )
                ],
                h_expand=True,
                v_expand=True,
            ).build(
                lambda box, _: box.pack_end(
                    Box(
                        v_expand=True,
                        orientation="v",
                        children=[
                            Button(
                                name="close-button-small",
                                child=MaterialIconLabel(
                                    name="close-label-small",
                                    icon_text=icons.close.symbol(),
                                ),
                                tooltip_text="Close",
                                style_classes="critical" if self.urgency == 2 else "",
                                on_clicked=lambda *_: self._notification.close(),
                            ),
                            Box(),
                        ],
                    ),
                    False,
                    False,
                    0,
                )
            ),
        )
        body_container.add(content_box)

        if actions := self._notification.actions:
            body_container.add(
                Box(
                    spacing=4,
                    orientation="h",
                    children=[
                        Button(
                            style_classes="action-button",
                            h_expand=True,
                            v_expand=True,
                            label=action.label,
                            on_clicked=lambda *_, action=action: action.invoke(),
                        )
                        for action in actions
                    ],
                )
            )
        self.add(body_container)

        self._on_press_connection = self.connect(
            "button-press-event", lambda *_: timeout_callback(self)
        )

        self._closed_connection = self._notification.connect(
            "closed", self._on_notification_closed
        )

        # GLib.timeout_add() wrapper
        self._timeout_repeater_id = (
            invoke_repeater(
                NotificationConfig.TIMEOUT,
                lambda: timeout_callback(self),
                initial_call=False,
            )
            if self.urgency in [0, 1]
            else None
        )

    def _on_notification_expanded(self, *_):
        self.revealer_btn_label.set_angle(
            90
            if self.notif_body_label.get_lines() == NotificationConfig.LINE_LIMIT
            else -90
        )
        self.notif_body_label.set_lines(
            100
            if self.notif_body_label.get_lines() == NotificationConfig.LINE_LIMIT
            else NotificationConfig.LINE_LIMIT
        )

        # cancel timeout repeater
        if self._timeout_repeater_id is not None:
            GLib.source_remove(self._timeout_repeater_id)
            self._timeout_repeater_id = None

    def _on_notification_closed(self, *_):
        try:
            if parent := self.get_parent():
                parent.remove(self)
            self._on_close_callback(self)
            self.destroy()
        except Exception as e:
            logger.error(f"Error in _on_notification_closed: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        # cancel timeout repeater
        if self._timeout_repeater_id is not None:
            GLib.source_remove(self._timeout_repeater_id)
            self._timeout_repeater_id = None

        # disconnect signals
        if self._on_press_connection:
            self.disconnect(self._on_press_connection)
            self._on_press_connection = None

        if self._closed_connection and self._notification:
            self._notification.disconnect(self._closed_connection)
            self._closed_connection = None

        # clear pixbuf reference
        self._scaled_pixbuf = None

        logger.debug("NotificationWidget cleaned up")


class NotificationManager:
    def __init__(self, **kwargs):
        super().__init__(
            **kwargs,
        )

        self.last_hover_time = 0
        self._notification_service = None
        self._active_notifications = []
        self._is_open = False  # single source of truth for panel visibility

        try:
            self._notification_service = Notifications()
            self._notification_service.connect(
                "notification_added", self._handle_notification_added
            )
        except Exception as e:
            logger.error(f"Failed to setup notification service: {e}")

        self._notification_sig_emittor = NotificationNotifier()

        self.viewport = Box(
            orientation="v",
            size=2,
            v_align="end",
            spacing=NotificationConfig.SPACING,
        )
        self._groups: dict[str, NotificationGroup] = {}  # keyed by app_name
        self.scrolled_window = ScrolledWindow(
            name="notification-scrolled-window",
            size=2,
            h_scrollbar_policy="external",
            v_scrollbar_policy="external",
            max_content_size=(
                NotificationConfig.WINDOW_MAX_WIDTH,
                NotificationConfig.WINDOW_MAX_HEIGHT,
            ),
            child=self.viewport,
        )

        self.notification_content = ClippingBox(
            name="notification-window-container", children=self.scrolled_window
        )

        self.active_notifications_box = Box(
            size=2, orientation="v", spacing=NotificationConfig.SPACING
        )

        # TODO
        self.silent_btn = Button(
            # name="notification-reveal-btn",
            child=MaterialIconLabel(
                name="notification-reveal-label", icon_text=icons.notifications.symbol()
            ),
            tooltip_text="Show/Hide notifications",
            on_clicked=lambda *_: self.handle_silent_state_toggle(),
        )
        self.clear_btn = Button(
            # name="notification-reveal-btn",
            child=MaterialIconLabel(
                name="notification-clear-label", icon_text=icons.trash_material.symbol()
            ),
            tooltip_text="Clear notifications",
            on_clicked=lambda *_: self.close_all_notifications(),
        )

        self.notification_history = Box(
            orientation="v",
            style=f"min-height:{NotificationConfig.WINDOW_MIN_HEIGHT}px; min-width:{NotificationConfig.WINDOW_MIN_WIDTH}px",
            h_expand=True,
            children=[
                Box(
                    spacing=NotificationConfig.SPACING,
                    children=[
                        Box(
                            orientation="v",
                            children=[
                                self.notification_content,
                            ],
                        ),
                    ],
                    v_align="start",
                ),
            ],
        )

        self.notification_history.get_controls = self.get_controls
        self.notification_history.register_keybindings = self.register_keybindings
        self.notification_history.unregister_keybindings = self.unregister_keybindings
        self.active_notifications_box.get_controls = self.get_controls

        self.notification_history.connect("map", self.on_map)
        self.notification_history.connect(
            "unmap", lambda *_: self.unregister_keybindings()
        )

    def on_map(self, widget):
        self.register_keybindings()
        if self._notification_sig_emittor.has_unread:
            self._notification_sig_emittor.has_unread = False
        if self._notification_sig_emittor.has_urgent_unread:
            self._notification_sig_emittor.has_urgent_unread = False

    def _keybindings(self):
        notif_bindings = config.bindings.modules.notifications
        return {
            # "d": self.del_last_notif, # kill last
            format_accel_to_keybind(
                notif_bindings["notifications.clear_all"]
            ): self.close_all_notifications,
        }

    def register_keybindings(self):
        window = self.notification_history.get_toplevel()
        for key, handler in self._keybindings().items():
            window.add_keybinding(key, lambda *_, h=handler: h())

    def unregister_keybindings(self):
        window = self.notification_history.get_toplevel()
        for key in self._keybindings().keys():
            window.remove_keybinding(key)

    # TODO: sync system
    def handle_silent_state_toggle(self, *_):
        return
        # CHANGES CONFIG
        # config.SILENT = not config.SILENT
        # if self.silent_btn is not None:
        #     self.silent_btn.add_style_class("active")

    def _handle_notification_added(self, source, notification_id: int):
        if not self._notification_service:
            return

        try:
            notification = self._notification_service.get_notification_from_id(
                notification_id
            )
            if not notification:
                logger.warning(f"Failed to get notification with ID: {notification_id}")
                return

            notification_widget = ActiveNotificationWidget(
                notification=notification,
                timeout_callback=self._move_to_revealer,
                on_close_callback=self.close_active_notification,
            )

            if config.SILENT or self._is_open:
                self._move_to_revealer(notification_widget=notification_widget)
            else:
                if (
                    len(self._active_notifications)
                    >= NotificationConfig.MAX_ACTIVE_NOTIFS
                ):
                    active_children = self.active_notifications_box.get_children()
                    self._move_to_revealer(active_children[len(active_children) - 1])
                self._active_notifications.append(notification_widget)
                self.active_notifications_box.pack_end(
                    notification_widget, True, None, 0
                )

            self._update_ui_state()

        except Exception as e:
            logger.error(f"Failed to handle notification: {e}")

    def close_active_notification(self, notification_widget: ActiveNotificationWidget):
        if notification_widget in self._active_notifications:
            self._active_notifications.remove(notification_widget)
            self.active_notifications_box.remove(notification_widget)

        self._update_ui_state()

    def _move_to_revealer(self, notification_widget: ActiveNotificationWidget) -> None:
        try:
            if notification_widget._on_press_connection:
                notification_widget.disconnect(notification_widget._on_press_connection)
                notification_widget._on_press_connection = None

            if notification_widget in self._active_notifications:
                self._active_notifications.remove(notification_widget)
                self.active_notifications_box.remove(notification_widget)

            app_name = notification_widget._notification.app_name

            if app_name not in self._groups:
                group = NotificationGroup(
                    app_name=app_name,
                    on_empty=self._remove_group,
                )
                self._groups[app_name] = group
                self.viewport.pack_end(group, True, None, 0)

            self._groups[app_name].add_widget(notification_widget)
            self._resort_viewport()

            # mark unread
            if not self.notification_history.get_mapped():
                if notification_widget.urgency in (1, 2):
                    if not self._notification_sig_emittor.has_unread:
                        self._notification_sig_emittor.has_unread = True
                    if (
                        not self._notification_sig_emittor.has_urgent_unread
                        and notification_widget.urgency == 2
                    ):
                        self._notification_sig_emittor.has_urgent_unread = True

            self._update_ui_state()

        except Exception as e:
            logger.error(f"Failed to move notification to revealer: {e}")

    def _remove_group(self, group: NotificationGroup) -> None:
        """Called by NotificationGroup when it becomes empty."""
        app_name = group.app_name
        if app_name in self._groups:
            del self._groups[app_name]
        if group.get_parent() is self.viewport:
            self.viewport.remove(group)
        self._update_ui_state()

    def _group_sort_key(self, group: NotificationGroup):
        # urgency DESC, latest timestamp DESC
        return (-group.max_urgency, -group.latest_timestamp.timestamp())

    def _resort_viewport(self) -> None:
        # urgency > recency
        groups = list(self._groups.values())
        groups.sort(key=self._group_sort_key)

        for group in self.viewport.get_children():
            self.viewport.remove(group)
        for group in groups:
            self.viewport.pack_end(group, True, None, 0)

    def _update_ui_state(self):
        widget = self.clear_btn.get_children()[0]
        icon = (
            icons.trash_material.symbol() if self._is_open else icons.trash_up.symbol()
        )
        widget.set_icon(icon)

    def _handle_hover_reveal(self, source, event):
        if (
            event.detail == Gdk.NotifyType.INFERIOR
        ):  # hovering to a child widget, don't toggle
            return

        now = time.time()
        if now - self.last_hover_time < 0.3:
            return  # ignore rapid flickers
        self.last_hover_time = now

        self.toggle_notification_stack_reveal()

    def _drain_active_into_groups(self) -> None:
        for notification_widget in self._active_notifications[:]:
            self._move_to_revealer(notification_widget)

    def open_notification_stack(self):
        self._is_open = True
        GLib.idle_add(self._drain_active_into_groups)
        self._update_ui_state()

    def close_notification_stack(self):
        self._is_open = False
        self._update_ui_state()

    def toggle_notification_stack_reveal(self):
        try:
            if not self._is_open:
                self.open_notification_stack()
            else:
                self.close_notification_stack()
        except Exception as e:
            logger.error(f"Failed to toggle notification stack: {e}")

    def close_all_notifications(self, *_) -> None:
        # iterate over a COPY!!!
        for widget in self._active_notifications[:]:
            try:
                widget._notification.close()
            except Exception:
                try:
                    self._active_notifications.remove(widget)
                    if widget.get_parent():
                        widget.get_parent().remove(widget)
                    widget.cleanup()
                    widget.destroy()
                except Exception as e:
                    logger.error(f"Failed to cleanup active notification: {e}")

        for group in list(self._groups.values()):
            group._dismiss_all()

        self._groups.clear()
        self._active_notifications.clear()
        self._update_ui_state()

    def get_notifications_box(self):
        return self.notification_history

    def get_active_notifications_box(self):
        return self.active_notifications_box

    def get_controls(self):
        return [self.clear_btn]

    def destroy(self):
        if self._notification_service:
            try:
                self._notification_service.disconnect_by_func(
                    self._handle_notification_added
                )
            except Exception:
                pass
            self._notification_service = None

        self.close_all_notifications()
        super().destroy()
