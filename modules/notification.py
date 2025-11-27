import time
from loguru import logger
from typing import Callable
from datetime import datetime

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer
from fabric.widgets.eventbox import EventBox
from widgets.rounded_image import RoundedImage
from fabric.widgets.x11 import X11Window as Window
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.notifications import Notifications, Notification
from fabric.utils import invoke_repeater

from modules.tile import Tile

import icons
from config.info import config
from utils.helpers import toggle_class

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gdk


class NotificationConfig:
    WIDTH = 360
    IMAGE_SIZE = 50
    TIMEOUT = 5 * 1000  # 5 seconds
    TRANSITION_DURATION = 250
    REVEALER_TRANSITION_TYPE = "slide-down"
    MAX_ACTIVE_NOTIFS = 2
    WINDOW_MIN_HEIGHT = 10
    WINDOW_MIN_WIDTH = 364
    WINDOW_MAX_HEIGHT = 700
    WINDOW_MAX_WIDTH = 1900
    SPACING = 3
    MARGIN = 3
    IMAGE_BORDER_RADIUS = 18
    SNAP_THRESHOLD = 50
    SILENT = config.SILENT


class NotificationTile(Tile):
    def __init__(self, **kwargs):
        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Off",
            h_align="start",
            ellipsization="end",
            max_chars_width=9,
        )
        self.state = None
        super().__init__(
            markup=icons.silent,
            label="Silent",
            props=self.label,
            style_classes=["off"],
            markup_style="margin-right:18px; margin-right:18px;",
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
        config.SILENT =  not  config.SILENT
        self.update_visual()
        return super().handle_state_toggle(*_)


class NotificationWidget(EventBox):
    def __init__(
        self,
        notification: Notification,
        timeout_callback: Callable,
        on_close_callback: Callable,
        **kwargs,
    ):
        super().__init__(**kwargs)

        self._notification = notification
        self._timeout_callback = timeout_callback
        self._on_close_callback = on_close_callback
        self._on_press_connection = None
        self._timeout_id = None
        self._scaled_pixbuf = None
        self.timestamp = datetime.now()

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
                content_box.add(
                    Label(name="notification-icon", v_align="start", markup=icons.blur)
                )
        except Exception as e:
            logger.error(f"Failed to resolve image_pixbuff: {e}")
            content_box.add(
                Label(name="notification-icon", v_align="start", markup=icons.blur)
            )

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
                                children=[
                                    Label(
                                        label=self._notification.app_name,
                                        h_align="start",
                                        v_expand=True,
                                        ellipsization="end",
                                        max_chars_width=27,
                                    )
                                    .build()
                                    .add_style_class("app-name")
                                    .unwrap(),
                                    Box(style_classes=["seperator"], v_align="center"),
                                    Label(
                                        label=self.timestamp.strftime("%H:%M"),
                                        h_align="end",
                                    )
                                    .build()
                                    .add_style_class("timestamp")
                                    .unwrap(),
                                ]
                            ),
                            Label(
                                label=self._notification.summary,
                                h_align="start",
                                v_expand=True,
                                ellipsization="end",
                                max_chars_width=27,
                            )
                            .build()
                            .add_style_class("summary")
                            .unwrap(),
                            Label(
                                label=self._notification.body,
                                line_wrap="word-char",
                                max_chars_width=27,
                                v_align="start",
                                h_align="start",
                            )
                            .build()
                            .add_style_class("body")
                            .unwrap(),
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
                                name="close-button",
                                child=Label(name="close-label", markup=icons.cancel),
                                tooltip_text="Exit",
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

        self._timeout_repeater_id = invoke_repeater(
            NotificationConfig.TIMEOUT,
            lambda: timeout_callback(self),
            initial_call=False,
        )

    def _on_notification_closed(self, *_):
        try:
            if parent := self.get_parent():
                parent.remove(self)
            self._on_close_callback()
            self.cleanup()
            self.destroy()
        except Exception as e:
            logger.error(f"Error in _on_notification_closed: {e}")
            try:
                self.cleanup()
            except:
                pass

    def cleanup(self):
        # cancel timeout repeater
        if self._timeout_repeater_id is not None:
            from gi.repository import GLib

            try:
                GLib.source_remove(self._timeout_repeater_id)
            except:
                pass
            self._timeout_repeater_id = None

        # disconnect signals
        if self._on_press_connection:
            try:
                self.disconnect(self._on_press_connection)
            except:
                pass
            self._on_press_connection = None

        if self._closed_connection and self._notification:
            try:
                self._notification.disconnect(self._closed_connection)
            except:
                pass
            self._closed_connection = None

        # clear pixbuf reference
        self._scaled_pixbuf = None

        logger.debug("NotificationWidget cleaned up")


class NotificationManager(Window):
    def __init__(self, **kwargs):
        super().__init__(
            layer="top",
            type_hint="notification",
            geometry="top",
            visible=True,
            all_visible=True,
            **kwargs,
        )
        self._drag_state = {
            "dragging": False,
            "offset_x": 0,
            "offset_y": 0,
            "start_pos": None,
        }
        self.last_hover_time = 0
        self._notification_service = None
        self._active_notifications = []

        try:
            self._notification_service = Notifications()
            self._notification_service.connect(
                "notification_added", self._handle_notification_added
            )
        except Exception as e:
            logger.error(f"Failed to setup notification service: {e}")

        self.viewport = Box(
            orientation="v",
            size=2,
            v_align="end",
            spacing=NotificationConfig.SPACING,
        )
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

        self.revealer = Revealer(
            child=Box(
                name="notification-window-container", children=self.scrolled_window
            ),
            transition_duration=NotificationConfig.TRANSITION_DURATION,
            transition_type=NotificationConfig.REVEALER_TRANSITION_TYPE,
        )

        self.active_notifications_box = Box(
            size=2, orientation="v", spacing=NotificationConfig.SPACING
        )

        self.reveal_btn = Button(
            name="notification-reveal-btn",
            child=Label(name="notification-reveal-label", markup=icons.notifications),
            tooltip_text="Show/Hide notifications",
            on_clicked=lambda *_: self.toggle_notification_stack_reveal(),
            visible=False,
        )
        self.clear_btn = Button(
            name="notification-reveal-btn",
            child=Label(name="notification-clear-label", markup=icons.trash),
            tooltip_text="Show/Hide notifications",
            on_clicked=lambda *_: self.close_all_notifications(),
            visible=False,
        )

        self.hover_area = EventBox(
            events="enter-notify",
            child=Box(style="min-height:2px;"),
        )

        self.children = Box(
            orientation="v",
            style=f"min-height:{NotificationConfig.WINDOW_MIN_HEIGHT}px; min-width:{NotificationConfig.WINDOW_MIN_WIDTH}px",
            h_expand=True,
            children=[
                self.hover_area,
                Box(
                    spacing=NotificationConfig.SPACING,
                    style=f"margin: {NotificationConfig.MARGIN}px;",
                    children=[
                        Box(
                            v_align="start",
                            children=self.clear_btn,
                        ),
                        Box(
                            orientation="v",
                            children=[
                                self.revealer,
                                self.active_notifications_box,
                            ],
                        ),
                        Box(
                            v_align="start",
                            children=self.reveal_btn,
                        ),
                    ],
                    v_align="start",
                ),
                # Button(child=Label(label='delete'), on_clicked=self.close_all_notifications)
            ],
        )

        self.hover_area.connect("enter-notify-event", self._handle_hover_reveal)

        # drag events
        self.connect("button-press-event", self.on_button_press)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("button-release-event", self.on_button_release)

    def on_button_press(self, widget, event):
        if event.button == 1:  # Left mouse button
            self._drag_state["dragging"] = True
            win_x, win_y = self.get_position()
            self._drag_state["offset_x"] = event.x_root - win_x
            self._drag_state["offset_y"] = event.y_root - win_y
            self._drag_state["start_pos"] = (win_x, win_y)

    def on_motion(self, widget, event):
        if not self._drag_state["dragging"]:
            return

        new_x = int(event.x_root - self._drag_state["offset_x"])
        new_y = int(event.y_root - self._drag_state["offset_y"])
        self.move(new_x, new_y)

    def on_button_release(self, widget, event):
        if event.button != 1 or not self._drag_state["dragging"]:
            return

        self._drag_state["dragging"] = False

        screen = Gdk.Display.get_default().get_monitor_at_window(self.get_window())
        geo = screen.get_geometry()
        win_x, win_y = self.get_position()
        win_w, win_h = self.get_size()

        left_x = 0
        right_x = geo.width - win_w
        center_x = (geo.width - win_w) // 2

        POSITIONS = {center_x: "top", left_x: "top-left", right_x: "top-right"}

        # snap
        target_x = min(POSITIONS.keys(), key=lambda x: abs(win_x - x))
        self.set_geometry(POSITIONS[target_x])

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

            notification_widget = NotificationWidget(
                notification=notification,
                timeout_callback=self._move_to_revealer,
                on_close_callback=self._update_ui_state,
            )

            if not config.SILENT:
                if (
                    len(self._active_notifications)
                    >= NotificationConfig.MAX_ACTIVE_NOTIFS
                ):
                    active_children = self.active_notifications_box.get_children()
                    self._move_to_revealer(
                        active_children[len(active_children)-1]
                    )
                self._active_notifications.append(notification_widget)
                self.active_notifications_box.pack_end(notification_widget, True, None, 0)
            else:
                self._move_to_revealer(notification_widget=notification_widget)
            self._update_ui_state()

        except Exception as e:
            logger.error(f"Failed to handle notification: {e}")

    def _move_to_revealer(self, notification_widget: NotificationWidget):
        try:
            if notification_widget._on_press_connection:
                notification_widget.disconnect(notification_widget._on_press_connection)
                notification_widget._on_press_connection = None

            if notification_widget in self._active_notifications:
                self._active_notifications.remove(notification_widget)
                self.active_notifications_box.remove(notification_widget)

            # flex tape fix
            if notification_widget.get_parent() is not self.viewport:
                self.viewport.pack_end(notification_widget, True, None, 0)
            else:
                logger.debug("Skipping re-add: widget already in viewport")

            self._update_ui_state()

        except Exception as e:
            logger.error(f"Failed to move notification to revealer: {e}")

    def _update_ui_state(self):
        # active_notifications[] isnt updated yet
        has_active_notifications = len(self.active_notifications_box.get_children()) > 0
        has_revealed_notifications = self.revealer.child_revealed

        if has_revealed_notifications:
            widget = self.clear_btn.get_children()[0]
            widget.set_markup(icons.trash)
            toggle_class(widget, "trash-up-icon-adjust", "trash-icon-adjust")
        else:
            widget = self.clear_btn.get_children()[0]
            widget.set_markup(icons.trash_up)
            toggle_class(widget, "trash-icon-adjust", "trash-up-icon-adjust")

        should_show_button = has_active_notifications or has_revealed_notifications
        self.reveal_btn.set_visible(should_show_button)
        self.clear_btn.set_visible(should_show_button)

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

    def toggle_notification_stack_reveal(self):
        try:
            if not self.revealer.child_revealed:
                self.revealer.reveal()
            else:
                self.revealer.unreveal()

            self._update_ui_state()

        except Exception as e:
            logger.error(f"Failed to toggle revealer: {e}")

    def close_all_notifications(self, *_):
        # iterate over a COPY!!
        for notification_widget in self._active_notifications[:]:
            try:
                # self._active_notifications.remove(notification_widget)
                notification_widget._notification.close()
            except Exception as e:
                try:
                    if notification_widget in self._active_notifications:
                        self._active_notifications.remove(notification_widget)
                    if notification_widget.get_parent():
                        notification_widget.get_parent().remove(notification_widget)
                    notification_widget.cleanup()
                    notification_widget.destroy()
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup notification: {cleanup_error}")

        for notification_widget in self.viewport.get_children()[:]:
            try:
                notification_widget._notification.close()
            except Exception as e:
                try:
                    if notification_widget.get_parent():
                        notification_widget.get_parent().remove(notification_widget)
                    notification_widget.cleanup()
                    notification_widget.destroy()
                except Exception as cleanup_error:
                    logger.error(f"Failed to cleanup revealed notification: {cleanup_error}")        

        self._active_notifications.clear()

        self._update_ui_state()

    def destroy(self):
        if self._notification_service:
            try:
                self._notification_service.disconnect_by_func(
                    self._handle_notification_added
                )
            except:
                pass
            self._notification_service = None

        self.close_all_notifications()
        super().destroy()
