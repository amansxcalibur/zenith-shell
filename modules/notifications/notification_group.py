from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .notification import ActiveNotificationWidget

import os
import tempfile
from loguru import logger
from typing import Callable
from datetime import datetime

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer
from fabric.notifications.service import Notification

from widgets.rounded_image import RoundedImage
from widgets.material_label import MaterialIconLabel
from widgets.clipping_box import AnimatedClippingBox
from widgets.shapes.expressive.morphing_shapes import ExpressiveShape
from utils.helpers import toggle_class
import icons

from .icon_resolver import IconResolver
from .common import NotificationConfig

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gtk, GLib


_icon_resolver: "IconResolver | None" = None


def _get_icon_resolver() -> "IconResolver":
    global _icon_resolver
    if _icon_resolver is None:
        _icon_resolver = IconResolver()
    return _icon_resolver


def _resolve_app_icon(notification, size: int = 28) -> Gtk.Widget:
    resolver = _get_icon_resolver()

    # try app_icon string first (sometimes it's a valid named icon)
    for candidate in filter(
        None,
        [
            notification.app_icon,
            resolver.get_icon(notification.app_name or ""),
        ],
    ):
        if candidate and candidate != "application-x-symbolic":
            img = Gtk.Image.new_from_icon_name(candidate, Gtk.IconSize.INVALID)
            img.set_pixel_size(size)
            img.set_valign(Gtk.Align.CENTER)
            img.show()
            return img

    # image_pixbuf last resort
    try:
        pixbuf = notification.image_pixbuf
        if pixbuf:
            scaled = pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
            img = RoundedImage(
                pixbuf=scaled,
                style=f"border-radius:{size // 4}px;",
                v_align="center",
            )
            img.show()
            return img
    except Exception:
        pass

    # blur glyph
    fallback = MaterialIconLabel(
        name="notification-icon",
        icon_text=icons.blur.symbol(),
        v_align="center",
    )
    fallback.show()
    return fallback


class NotificationWidget(Box):
    PAGE_COLLAPSED = "collapsed"
    PAGE_EXPANDED = "expanded"

    @property
    def collapsed_height(self) -> int:
        return (
            38
            if self.collapsed_page.get_orientation() == Gtk.Orientation.HORIZONTAL
            else 54
        )

    @property
    def expanded_height(self) -> int:
        # switch stack instantly for a measurement probe, not the real transition
        self._stack.set_transition_duration(0)
        self._stack.set_visible_child_name(self.PAGE_EXPANDED)
        _, h = self.get_preferred_height()
        self._stack.set_visible_child_name(self.PAGE_COLLAPSED)
        self._stack.set_transition_duration(NotificationConfig.TRANSITION_DURATION)
        return h

    def __init__(self, notification: Notification, **kwargs):
        super().__init__(name="notification-widget", **kwargs)

        self._notification = notification
        self._closed_connection = None
        self._scaled_pixbuf = None
        self.timestamp = datetime.now()
        self.urgency = notification.urgency
        self.toggler = False

        self._image_path = self._resolve_image_path(notification)

        self.image_box = self._build_image_box()
        self.collapsed_page = self._build_collapsed_page(notification)
        expanded_page = self._build_expanded_page(notification)
        self._actions = Box(
            spacing=4,
            orientation="h",
            style="margin-top: 10px;",
            children=[
                Button(
                    style_classes="action-button",
                    h_expand=True,
                    v_expand=True,
                    label=action.label,
                    on_clicked=lambda *_, action=action: action.invoke(),
                )
                for action in self._notification.actions
            ],
        )
        self._actions_revealer = Revealer(
            transition_duration=150,
            transition_type="slide-up",
            child=self._actions,
            child_revealed=False,
        )

        match self.urgency:
            case 0 | 1:
                self.add_style_class("normal")
                self.image_box.add_style_class("normal")
                self.revealer_btn.add_style_class("normal")
            case 2:
                self.add_style_class("critical")
                self.image_box.add_style_class("critical")
                self.revealer_btn.add_style_class("critical")
            case _:
                logger.warning(f"Unknown notification urgency level {self.urgency}")

        # main stack
        self._stack = Stack(
            transition_duration=150,
            transition_type="crossfade",
            interpolate_size=True,
            h_expand=True,
        )
        self._stack.set_vhomogeneous(False)
        self._stack.set_hhomogeneous(True)
        self._stack.add_named(self.collapsed_page, self.PAGE_COLLAPSED)
        self._stack.add_named(expanded_page, self.PAGE_EXPANDED)
        self._stack.set_visible_child_name(self.PAGE_COLLAPSED)

        self.collapsed_page.show_all()
        expanded_page.show_all()

        self._closed_connection = notification.connect(
            "closed", self._on_notification_closed
        )

        self.add(
            Box(
                orientation="v",
                h_expand=True,
                children=[
                    Box(
                        h_expand=True,
                        spacing=10,
                        children=[self.image_box, self._stack],
                    ),
                    self._actions_revealer,
                ],
            )
        )

        self._on_toggle_expanded_page(self.revealer_btn, state=False)

    def set_expanded(self, expanded: bool) -> None:
        self._stack.set_visible_child_name(
            self.PAGE_EXPANDED if expanded else self.PAGE_COLLAPSED
        )

    def _build_image_box(self) -> Box:
        box = Box(name="img-expander", v_align="start", style_classes="contract")
        if self._image_path is None:
            if hasattr(self._notification, "shape"):
                box.add(ExpressiveShape(shape=self._notification.shape))
        else:
            box.set_style(f'background-image: url("{self._image_path}")')
        return box

    def _build_collapsed_page(self, notification: Notification) -> Box:
        summary = notification.summary or ""
        body = notification.body or ""
        max_c = NotificationConfig.MAX_CHARS_PER_COLLAPSED_LINE
        long_summary = len(summary) > max_c

        self._collapsed_summary = Label(
            h_align="start",
            ellipsization="end",
            max_chars_width=max_c,
            style_classes=["notif-summary"],
            label=summary,
        )
        self._collapsed_body = Label(
            h_align="start",
            h_expand=True,
            ellipsization="end",
            line_wrap="word-char",
            max_chars_width=max_c if long_summary else (max_c - len(summary)),
            style_classes=["notif-body"],
            label=body,
        )

        return Box(
            name="notif-collapsed-page",
            orientation="v" if long_summary else "h",
            v_align="center",
            spacing=0 if long_summary else 4,
            children=[self._collapsed_summary, self._collapsed_body],
        )

    def _build_expanded_page(self, notification: Notification) -> Box:
        summary = notification.summary or ""
        body = notification.body or ""
        time_text = self.timestamp.strftime("%H:%M")
        max_c = NotificationConfig.MAX_CHARS_PER_LINE

        # expander button
        self.revealer_btn_label = MaterialIconLabel(
            icon_text=icons.arrow_forward.symbol(), angle=-90
        )
        self.revealer_btn = Button(
            name="notif-expander-btn",
            v_align="start",
            child=self.revealer_btn_label,
            on_clicked=self._on_toggle_expanded_page,
        )

        # dot separator
        self.separator = Revealer(
            child=Box(style_classes=["notif-dot-separator"], v_align="center"),
            child_revealed=True,
            transition_duration=150,
            transition_type="crossfade",
        )

        # expanded
        self._expanded_summary_short = Box(
            spacing=6,
            children=[
                Label(
                    h_align="start",
                    ellipsization="end",
                    max_chars_width=max_c - 11,
                    style_classes=["notif-summary"],
                    label=summary,
                ),
                self.separator,
            ],
        )
        expanded_body_short = Label(
            h_align="start",
            ellipsization="end",
            max_chars_width=max_c,
            line_wrap="word-char",
            style_classes=["notif-body"],
            label=body,
        )
        expanded_body_short.set_lines(NotificationConfig.LINE_LIMIT)

        expanded_summary_long = Label(
            h_align="start",
            ellipsization="end",
            max_chars_width=max_c,
            style_classes=["notif-summary"],
            label=summary,
        )
        expanded_body_long = Label(
            h_align="start",
            max_chars_width=max_c,
            line_wrap="word-char",
            style_classes=["notif-body"],
            label=body,
        )

        self._expanded_short = Box(
            orientation="v",
            children=[self._expanded_summary_short, expanded_body_short],
        )
        self._expanded_long = Box(
            orientation="v",
            children=[expanded_summary_long, expanded_body_long],
        )

        self._expanded_stack = Stack(
            transition_duration=150,
            transition_type="crossfade",
            interpolate_size=True,
            children=[self._expanded_short, self._expanded_long],
        )
        self._expanded_stack.set_homogeneous(False)

        close_btn = Button(
            name="close-button-small",
            v_align="start",
            child=MaterialIconLabel(
                name="close-label-small",
                icon_text=icons.close.symbol(),
            ),
            tooltip_text="Close",
            style_classes="critical" if self.urgency == 2 else "",
            on_clicked=lambda *_: (
                self._notification.close()
                if hasattr(self._notification, "close")
                else None
            ),
        )

        self._timestamp_label = Label(
            label=time_text,
            h_align="start",
            h_expand=True,
            style_classes=["notif-timestamp"],
        )
        self.top_row = Box(h_expand=True, children=[self._timestamp_label])

        return Box(
            name="notif-expanded-page",
            orientation="h",
            h_expand=True,
            spacing=10,
            children=[
                Box(
                    orientation="v",
                    spacing=2,
                    h_expand=True,
                    v_align="center",
                    children=[self.top_row, self._expanded_stack],
                ),
                Box(
                    style="margin-left: -38px;",
                    spacing=6,
                    children=[self.revealer_btn, close_btn],
                ),
            ],
        )

    def _on_toggle_expanded_page(self, btn, state: bool | None = None):
        expanded = (
            not self.toggler if state is None else state
        )  # expanding → show long; collapsing → show short
        self.toggler = expanded

        self.revealer_btn_label.set_angle(90 if expanded else -90)

        if expanded:
            self.separator.unreveal()
            self._actions_revealer.reveal()
            self._expanded_stack.set_visible_child(self._expanded_long)
            self.top_row.set_style("transition: all 0.15s linear; margin: 2px;")
        else:
            self.separator.reveal()
            self._actions_revealer.unreveal()
            _, summary_w = self._expanded_summary_short.get_preferred_width()
            left_margin = summary_w + 8
            self.top_row.set_style(
                f"transition: all 0.15s linear;margin: 2px 2px -23px {left_margin}px;"
            )
            self._expanded_stack.set_visible_child(self._expanded_short)

    def _resolve_image_path(self, notification) -> str | None:
        try:
            if pixbuf := self._notification.image_pixbuf:
                scaled = pixbuf.scale_simple(
                    NotificationConfig.IMAGE_SIZE,
                    NotificationConfig.IMAGE_SIZE,
                    GdkPixbuf.InterpType.BILINEAR,
                )
                pixbuf = scaled or pixbuf
                tmp_dir = "/tmp/zenith-shell/notif-imgs"
                os.makedirs(tmp_dir, exist_ok=True)
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".png",
                    delete=False,
                    dir=tmp_dir,
                    prefix=f"notif-{notification.id}-",
                )
                tmp.close()
                pixbuf.savev(tmp.name, "png", [], [])
                return tmp.name
        except Exception:
            logger.error("Couldn't resolve image path")
            pass

        return None

    def _on_notification_closed(self, *_):
        try:
            self.destroy()
        except Exception as e:
            logger.error(f"NotificationWidget destroy failed: {e}")
        finally:
            self.cleanup()

    def cleanup(self):
        if self._closed_connection is not None and self._notification is not None:
            try:
                self._notification.disconnect(self._closed_connection)
            except Exception:
                pass
            self._closed_connection = None

        self._scaled_pixbuf = None
        logger.debug("NotificationWidget cleaned up")


class NotificationGroup(AnimatedClippingBox):
    @property
    def count(self) -> int:
        return len(self._widgets)

    @property
    def max_urgency(self) -> int:
        return max((w.urgency for w in self._widgets), default=0)

    @property
    def latest_timestamp(self) -> datetime:
        return max((w.timestamp for w in self._widgets), default=datetime.min)

    @staticmethod
    def _set_widget_expand_style(widget: NotificationWidget, expanded: bool) -> None:
        add_class, remove_class = (
            ("expand", "contract") if expanded else ("contract", "expand")
        )
        toggle_class(widget.image_box, remove_class, add_class)
        toggle_class(widget, remove_class, add_class)

    def __init__(
        self, app_name: str, on_empty: Callable[["NotificationGroup"], None], **kwargs
    ):
        super().__init__(
            name="notif-group-container",
            orientation="v",
            max_height=AnimatedClippingBox._COLLAPSED_HEIGHT_DEFAULT,
            **kwargs,
        )

        self.app_name = app_name
        self._on_empty = on_empty
        self._widgets: list[NotificationWidget] = []
        self._expanded = False  # start collapsed
        self._current_icon_source: str | None = None

        self._icon_slot = Box(
            v_align="center", style="min-width:28px; min-height:28px;"
        )

        self._count_label = Label(
            style_classes=["notif-group-count"],
            label="",
            visible=False,
        )
        self._count_label.set_no_show_all(True)

        self._toggle_icon = MaterialIconLabel(
            icon_text=icons.arrow_forward.symbol(),
            angle=90,  # starts pointing right = collapsed
        )
        self._toggle_btn = Button(
            name="notif-group-toggle-btn",
            v_align="start",
            child=Box(children=[self._count_label, self._toggle_icon]),
            on_clicked=self._toggle_expand,
        )
        self._dismiss_btn = Button(
            name="notif-group-clear-btn",
            child=Box(
                spacing=4,
                children=[
                    Label(label="Clear"),
                    MaterialIconLabel(icon_text=icons.mop.symbol()),
                ],
            ),
            tooltip_text="Dismiss all",
            on_clicked=self._dismiss_all,
        )

        self.timestamp_label = Label(
            h_expand=True,
            label="",
            h_align="start",
            style_classes=["timestamp"],
        )
        self.time_revealer = Revealer(
            transition_duration=NotificationConfig.TRANSITION_DURATION,
            transition_type="crossfade",
            child=Box(
                spacing=6,
                children=[
                    Box(
                        style_classes=["notif-dot-separator"],
                        v_align="center",
                    ),
                    self.timestamp_label,
                ],
            ),
            child_revealed=True,
        )

        self._top_row = Box(
            spacing=6,
            children=[
                self._icon_slot,
                Box(
                    spacing=6,
                    h_expand=True,
                    children=[
                        Label(
                            label=app_name,
                            style_classes=["notif-group-app-name"],
                            h_align="start",
                            ellipsization="end",
                            max_chars_width=20,
                        ),
                        self.time_revealer,
                    ],
                ),
                self._toggle_btn,
                self._dismiss_btn,
            ],
        )

        self._header = Box(
            name="notif-group-header",
            orientation="v",
            spacing=4,
            children=[self._top_row],
        )

        # children live directly in this box, always visible
        self._children_box = Box(
            name="notif-group-children-box",
            orientation="v",
        )

        self._collapsed_height = AnimatedClippingBox._COLLAPSED_HEIGHT_DEFAULT

        self.add(self._header)
        self.add(self._children_box)

        self._header.connect("size-allocate", self._on_header_allocated)

        # init collapsed state
        GLib.idle_add(lambda: self._toggle_expand(self._toggle_btn, self._expanded))

    def add_widget(self, widget: ActiveNotificationWidget) -> None:
        notif = widget._notification

        def add():
            # guard against duplicate notification ids
            if any(w._notification.id == notif.id for w in self._widgets):
                return
            new_widget = NotificationWidget(notification=notif)
            if self._expanded:
                new_widget.set_expanded(True)
                self._set_widget_expand_style(new_widget, True)
            else:
                new_widget.add_style_class("contract")
            new_widget.connect("destroy", self._on_widget_destroyed)
            self._widgets.append(new_widget)
            self._resort()
            self._rebuild_children_box()
            self._sync_header()
            self._refresh_height()

        GLib.idle_add(add)

    def remove_widget(self, widget: NotificationWidget) -> None:
        if widget in self._widgets:
            self._widgets.remove(widget)
        if widget.get_parent() is self._children_box:
            self._children_box.remove(widget)
        self._sync_header()
        self._refresh_height()
        if not self._widgets:
            self._on_empty(self)

    def _resort(self) -> None:
        self._widgets.sort(key=self._sort_key, reverse=True)

    def _sort_key(self, w: NotificationWidget):
        return (-w.urgency, -w.timestamp.timestamp())

    def _rebuild_children_box(self) -> None:
        for child in self._children_box.get_children():
            self._children_box.remove(child)
        for widget in self._widgets:
            self._children_box.pack_end(widget, True, None, 0)

    def _sync_header(self) -> None:
        n = self.count

        self._count_label.set_label(str(n) if n > 1 else "")
        self._count_label.set_visible(n > 1)

        if self.max_urgency == 2:
            self._toggle_btn.add_style_class("critical")
        else:
            self._toggle_btn.remove_style_class("critical")

        top = self._top_widget()
        self.timestamp_label.set_label(self.latest_timestamp.strftime("%H:%M"))
        if top:
            self._sync_icon(top._notification)

    def _top_widget(self) -> NotificationWidget | None:
        return self._widgets[0] if self._widgets else None

    def _sync_icon(self, notification, size: int = 28) -> None:
        # keyed by notification id so repeated _sync_header calls
        # on the same top widget don't re-resolve the icon.
        source_key = str(notification.id)
        if source_key == self._current_icon_source:
            return
        self._current_icon_source = source_key

        for child in self._icon_slot.get_children():
            self._icon_slot.remove(child)

        self._icon_slot.add(_resolve_app_icon(notification, size))

    def _refresh_height(self) -> None:
        if self._expanded:
            self.refresh()
        else:
            self.set_max_height(self._compute_collapsed_height())

    def _compute_collapsed_height(self) -> int:
        _, h = self._header.get_preferred_height()
        for widget in self._widgets[-1:-3:-1]:
            h += widget.collapsed_height
        return h

    def _compute_expanded_height(self) -> int:
        _, h = self._header.get_preferred_height()
        for widget in self._widgets:
            h += widget.expanded_height
        return h

    def _on_header_allocated(self, widget, allocation) -> None:
        h = allocation.height
        if h > 0 and h != self._collapsed_height:
            self._collapsed_height = h
            if not self._expanded:
                self.set_max_height(h)  # snap, no animation, keeps it in sync at rest

    def _toggle_expand(self, btn, state: bool | None = None) -> None:
        self._expanded = state if state is not None else not self._expanded
        self._toggle_icon.set_angle(-90 if self._expanded else 90)

        if self._expanded:
            self._children_box.remove_style_class("contract")
        else:
            self._children_box.add_style_class("contract")

        for widget in self._widgets:
            self._set_widget_expand_style(widget, self._expanded)

        self.time_revealer.set_reveal_child(not self._expanded)

        if self._expanded:
            target = self._compute_expanded_height()
            for widget in self._widgets:
                widget.set_expanded(True)  # now kick off the real Stack transition
            self.expand(target)
        else:
            target = self._compute_collapsed_height()
            for widget in self._widgets:
                widget.set_expanded(False)
            self.collapse(target)

    def _dismiss_all(self, *_) -> None:
        for widget in self._widgets[:]:
            try:
                widget._notification.close()
            except Exception:
                pass

    def _on_widget_destroyed(self, widget: NotificationWidget) -> None:
        self.remove_widget(widget)
