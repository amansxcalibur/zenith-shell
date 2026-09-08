from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .notification import ActiveNotificationWidget

import os
import bisect
import tempfile
from loguru import logger
from datetime import datetime
from functools import lru_cache

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
from services.animator import CubicBezierCurves
from utils.helpers import toggle_class
import icons

from .icon_resolver import IconResolver
from .common import NotificationConfig

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gtk, GLib, GObject  # type: ignore


_icon_resolver: IconResolver | None = None


def _get_icon_resolver() -> IconResolver:
    global _icon_resolver
    if _icon_resolver is None:
        _icon_resolver = IconResolver()
    return _icon_resolver


@lru_cache(maxsize=128)
def _resolve_icon_asset(app_name: str, app_icon: str, has_pixbuf: bool, size: int):
    resolver = _get_icon_resolver()

    for candidate in filter(None, [app_icon, resolver.get_icon(app_name or "")]):
        if candidate and candidate != "application-x-symbolic":
            return ("icon_name", candidate)

    if has_pixbuf:
        # only returning a token showing we should use the pixbuf
        return ("pixbuf", None)

    return ("fallback", None)


def _resolve_app_icon(notification: Notification, size: int = 28) -> Gtk.Widget:
    has_pixbuf = False
    try:
        pixbuf = notification.image_pixbuf
        has_pixbuf = pixbuf is not None
    except Exception:
        pixbuf = None

    asset_type, asset_value = _resolve_icon_asset(
        notification.app_name, notification.app_icon, has_pixbuf, size
    )

    if asset_type == "icon_name":
        img = Gtk.Image.new_from_icon_name(asset_value, Gtk.IconSize.INVALID)
        img.set_pixel_size(size)
        img.set_valign(Gtk.Align.CENTER)
        img.show()
        return img

    if asset_type == "pixbuf" and pixbuf:
        try:
            scaled = pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
            img = RoundedImage(
                pixbuf=scaled,
                style=f"border-radius:{size // 4}px;",
                v_align="center",
            )
            img.show()
            return img
        except Exception:
            logger.error("Failed to resolve pixbuf app icon")

    # fallback
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
            34
            if self.collapsed_page.get_orientation() == Gtk.Orientation.HORIZONTAL
            else 54
        )

    @property
    def expanded_height(self) -> int:
        page_diff = (
            self.expanded_page.get_preferred_height()[1]
            - self.collapsed_page.get_preferred_height()[1]
        )

        actions_height = 0
        if self._notification.actions and (
            self._stack.get_visible_child_name() == self.PAGE_EXPANDED
        ):
            actions_height = self._actions.get_preferred_height()[1] + 10  # margin-top

        # css related adding
        css_pads = 10  # from #notification-widget.contract

        h = self.get_preferred_height()[1] + max(0, page_diff) + actions_height
        return h + css_pads

    def __init__(self, notification: Notification, **kwargs):
        super().__init__(name="notification-widget", **kwargs)

        self._notification = notification
        self._closed_connection = None
        self._scaled_pixbuf = None
        self.timestamp = notification.time
        self.urgency = notification.urgency
        self._expanded_page_toggle_state = False

        self._image_path = self._resolve_image_path(notification)

        self.image_box = self._build_image_box()
        self.collapsed_page = self._build_collapsed_page(notification)
        self.expanded_page = self._build_expanded_page(notification)
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
            transition_duration=250,
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
        self._stack.add_named(self.expanded_page, self.PAGE_EXPANDED)
        self._stack.set_visible_child_name(self.PAGE_COLLAPSED)

        self.collapsed_page.show_all()
        self.expanded_page.show_all()

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

        if self._expanded_page_toggle_state and not expanded:
            # not preserving state cuz it introduces unnecessary
            # complexity to expanded height measurement
            self._on_toggle_expanded_page(self.revealer_btn, state=False)

    def _build_image_box(self) -> Box:
        box = Box(name="img-expander", v_align="start", style_classes="contract")
        if self._image_path is None:
            if hasattr(self._notification, "shape"):
                # wrapping in `Box` because adding padding to
                # img-expander messes up height measurement
                box.add(
                    Box(
                        name="notif-expressive-shape-container",
                        h_expand=True,
                        v_expand=True,
                        children=ExpressiveShape(shape=self._notification.shape),
                    )
                )
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
        time_text = datetime.fromtimestamp(self.timestamp).strftime("%H:%M")  # noqa: DTZ006
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
        expanded = not self._expanded_page_toggle_state if state is None else state
        self._expanded_page_toggle_state = expanded

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
                with tempfile.NamedTemporaryFile(
                    suffix=".png",
                    delete=False,
                    dir=tmp_dir,
                    prefix=f"notif-{notification.id}-",
                ) as tmp:
                    tmp_name = tmp.name
                pixbuf.savev(tmp_name, "png", [], [])
                return tmp_name
        except Exception:
            logger.error("Couldn't resolve image path")

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
            except Exception as e:
                logger.error(f"Failed to disconnect close connection handler: {e}")
            self._closed_connection = None

        self._scaled_pixbuf = None
        logger.debug("NotificationWidget cleaned up")


class NotificationGroup(AnimatedClippingBox):
    # dont look at me funny now. I was tired trying to figure out what went wrong with @Signal
    __gsignals__ = {  # noqa: RUF012
        "timestamp-change": (GObject.SignalFlags.RUN_LAST, None, (int,)),
    }

    @property
    def count(self) -> int:
        return len(self._widgets)

    @property
    def max_urgency(self) -> int:
        return self._max_urgency

    @property
    def latest_timestamp(self) -> float:
        return self._latest_timestamp

    @staticmethod
    def _set_widget_expand_style(widget: NotificationWidget, expanded: bool) -> None:
        add_class, remove_class = (
            ("expand", "contract") if expanded else ("contract", "expand")
        )
        toggle_class(widget.image_box, remove_class, add_class)
        toggle_class(widget, remove_class, add_class)

    def __init__(
        self, app_name: str, on_empty: callable[[NotificationGroup], None], **kwargs
    ):
        super().__init__(
            name="notif-group-container",
            orientation="v",
            max_height=AnimatedClippingBox._COLLAPSED_HEIGHT_DEFAULT,
            duration=0.25,
            contracting_bezier_curve=CubicBezierCurves.EXPRESSIVE,
            expanding_bezier_curve=CubicBezierCurves.EMPHASIS,
            max_overshoot_value=30,
            **kwargs,
        )
        self.app_name = app_name
        self._on_empty = on_empty
        self._widgets: list[NotificationWidget] = []
        self._notif_ids: set[int] = set()
        self._max_urgency = 0
        self._latest_timestamp = 0.0
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
            angle=-90,  # pointing down = collapsed
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
        if notif.id in self._notif_ids:
            return

        new_widget = NotificationWidget(notification=notif)

        if self._expanded:
            new_widget.set_expanded(True)
            self._set_widget_expand_style(new_widget, True)
        else:
            new_widget.add_style_class("contract")

        new_widget.connect("destroy", self._on_widget_destroyed)

        insert_key = self._sort_key(new_widget)
        keys = [self._sort_key(w) for w in self._widgets]
        idx = bisect.bisect_right(keys, insert_key)

        timestamp_changed = new_widget.timestamp > self._latest_timestamp
        self._latest_timestamp = max(self._latest_timestamp, new_widget.timestamp)
        self._max_urgency = max(self._max_urgency, new_widget.urgency)
        self._notif_ids.add(notif.id)

        self._widgets.insert(idx, new_widget)
        self._children_box.pack_end(new_widget, True, None, 0)

        gtk_position = len(self._widgets) - 1 - idx
        self._children_box.reorder_child(new_widget, gtk_position)

        self._sync_header()
        self._refresh_height()

        if timestamp_changed:
            self.emit("timestamp-change", new_widget.timestamp)

    def remove_widget(self, widget: NotificationWidget) -> None:
        if widget in self._widgets:
            self._widgets.remove(widget)
            self._notif_ids.discard(widget._notification.id)

        if widget.get_parent() is self._children_box:
            self._children_box.remove(widget)

        if not self._widgets:
            self._max_urgency = 0
            self._latest_timestamp = 0.0
        else:
            if widget.urgency >= self._max_urgency:
                self._max_urgency = max(w.urgency for w in self._widgets)
            if widget.timestamp >= self._latest_timestamp:
                self._latest_timestamp = max(w.timestamp for w in self._widgets)

        self._sync_header()
        self._refresh_height()
        if not self._widgets:
            self._on_empty(self)

    def _resort(self) -> None:
        self._widgets.sort(key=self._sort_key, reverse=True)

    def _sort_key(self, w: NotificationWidget):
        return (-w.urgency, -w.timestamp)

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
        self.timestamp_label.set_label(
            datetime.fromtimestamp(self.latest_timestamp).strftime("%H:%M")  # noqa: DTZ006
        )
        if top:
            self._sync_icon(top._notification)

    def _top_widget(self) -> NotificationWidget | None:
        return self._widgets[0] if self._widgets else None

    def _sync_icon(self, notification: Notification, size: int = 28) -> None:
        source_key = str(notification.id)
        if source_key == self._current_icon_source:
            return
        self._current_icon_source = source_key

        for child in self._icon_slot.get_children():
            self._icon_slot.remove(child)

        self._icon_slot.add(_resolve_app_icon(notification, size))

    def get_icon(self):
        # cached
        return _resolve_app_icon(self._widgets[0]._notification, 18)

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
        widgets_h = sum(w.expanded_height for w in self._widgets)

        widget_count = len(self._widgets)
        inner_gaps = max(0, widget_count - 1) * self._children_box.get_spacing()
        outer_gap = self.get_spacing() if widget_count > 0 else 0

        # from #notif-group-children-box.contract > :last-child > :last-child
        css_pad = -5
        return h + outer_gap + widgets_h + inner_gaps + css_pad

    def _on_header_allocated(self, widget, allocation) -> None:
        h = allocation.height
        if h > 0 and h != self._collapsed_height:
            self._collapsed_height = h
            if not self._expanded:
                self.set_max_height(h)  # snap, no animation, keeps it in sync at rest

    def _toggle_expand(self, btn, state: bool | None = None) -> None:
        self._expanded = state if state is not None else not self._expanded
        self._toggle_icon.set_angle(90 if self._expanded else -90)

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
                logger.error("Failed to close notification")

    def _on_widget_destroyed(self, widget: NotificationWidget) -> None:
        self.remove_widget(widget)
