from typing import Callable, Iterable, Any
from abc import ABC, abstractmethod
from dataclasses import dataclass

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.eventbox import EventBox

from widgets.clipping_box import ClippingBox
from widgets.material_label import MaterialFontLabel

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk


class BaseWidget(ABC):
    """Base class for all custom widgets with common patterns"""

    def __init__(self):
        self.container = None
        self._build_ui()

    @abstractmethod
    def _build_ui(self):
        """Build the widget UI - must be implemented by subclasses"""
        pass

    def get_widget(self):
        """Get the root container widget"""
        return self.container


class LayoutBuilder:
    """Utility class for building common layouts"""

    def section(
        heading: str,
        body: Gtk.Widget | Iterable[Gtk.Widget],
        heading_size: int = 18,
    ) -> EventBox:
        box = Box(orientation="v", spacing=5)

        heading_label = MaterialFontLabel(
            text=heading,
            style_classes="section-heading",
            h_align="start",
            slnt=0.0,
            wght=450,
            font_size=heading_size,
        )
        box.add(heading_label)

        if isinstance(body, Gtk.Widget):
            box.add(body)
        else:
            for child in body:
                box.add(child)

        event_box = EventBox(child=box)

        event_box.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK |
            Gdk.EventMask.LEAVE_NOTIFY_MASK
        )

        anim_id = None
        current = {"wght": 450.0, "slnt": 0.0}
        target = {"wght": 450.0, "slnt": 0.0}

        STEP = 0.45          # speed (0–1)
        INTERVAL = 16        # ~60fps

        def animate():
            nonlocal anim_id

            done = True
            for k in current:
                delta = target[k] - current[k]
                if abs(delta) > 0.5:
                    current[k] += delta * STEP
                    done = False
                else:
                    current[k] = target[k]

            heading_label.set_variations(
                wght=current["wght"],
                slnt=current["slnt"],
            )

            if done:
                anim_id = None
                return False

            return True

        def start_animation():
            nonlocal anim_id
            if anim_id is None:
                anim_id = GLib.timeout_add(INTERVAL, animate)

        def on_enter(_widget, _event):
            target["wght"] = 700.0
            target["slnt"] = -10.0
            start_animation()
            return False

        def on_leave(_widget, event):
            if event.detail == Gdk.NotifyType.INFERIOR:
                return False

            target["wght"] = 450.0
            target["slnt"] = 0.0
            start_animation()
            return False

        event_box.connect("enter-notify-event", on_enter)
        event_box.connect("leave-notify-event", on_leave)

        return event_box


    @staticmethod
    def labeled_slider(
        parent: Box,
        label: str,
        min_val: float,
        max_val: float,
        step: float,
        default: float,
        callback: Callable = None,
    ) -> Scale:
        scale_box = Box(orientation="h", spacing=10)
        scale_box.pack_start(
            Label(style_classes=["variation-type-label"], label=f"{label}:"),
            False,
            False,
            0,
        )

        scale = Scale(
            name="control-slider-mui",
            style_classes=["variation-scale"],
            orientation="h",
            min_value=min_val,
            max_value=max_val,
            increments=(step, step),
            h_expand=True,
        )
        scale.set_value(default)

        if callback:
            scale.connect("value-changed", callback)

        scale_box.pack_start(scale, True, True, 0)
        parent.pack_start(scale_box, False, False, 0)

        return scale

    @staticmethod
    def framed_container(
        label: str, child, label_align: tuple = (0.1, 0.4)
    ) -> Gtk.Frame:
        frame = Gtk.Frame(label=label)
        frame.set_label_align(*label_align)
        frame.add(child)
        return frame

    @staticmethod
    def settings_list(bindings: Iterable, row_factory: Callable) -> ClippingBox:
        container = ClippingBox(
            style_classes="settings-list-container",
            orientation="v",
            spacing=3,
        )

        for binding in bindings:
            container.add(row_factory(binding))

        return container


@dataclass
class TabConfig:
    id: str
    label: str
    icon: str
    widget_factory: Callable
    category: str = None
    _widget: Any = None

    @property
    def widget(self):
        """Lazy-load the widget on first access"""
        if self._widget is None:
            self._widget = self.widget_factory()
        return self._widget


@dataclass
class SliderConfig:
    name: str
    min_val: float
    max_val: float
    step: float
    default: float = 0


class SliderControlMixin:
    def __init__(self):
        self.scales = {}
        self._updating = False

    def create_sliders(
        self, parent: Box, configs: list[SliderConfig], callback: Callable
    ):
        for config in configs:
            self.scales[config.name] = LayoutBuilder.labeled_slider(
                parent=parent,
                label=config.name,
                min_val=config.min_val,
                max_val=config.max_val,
                step=config.step,
                default=config.default,
                callback=callback,
            )

    def batch_update_sliders(self, updates: dict):
        self._updating = True
        try:
            for name, value in updates.items():
                if name in self.scales:
                    self.scales[name].set_value(value)
        finally:
            self._updating = False

    def get_slider_values(self) -> dict:
        return {name: scale.get_value() for name, scale in self.scales.items()}


class SectionBuilderMixin:
    def build_section(
        self, title: str | None, bindings: Iterable, row_factory: Callable
    ) -> Box:
        section_box = Box(
            style_classes="settings-section-container",
            orientation="v",
            spacing=6,
        )

        if title:
            section_box.add(
                Label(
                    label=title,
                    style_classes="section-subheading",
                    h_align="start",
                )
            )

        if bindings:
            section_box.add(LayoutBuilder.settings_list(bindings, row_factory))

        return section_box