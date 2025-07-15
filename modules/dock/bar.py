from fabric.widgets.box import Box
from fabric.widgets.overlay import Overlay
from fabric.widgets.x11 import X11Window as Window
from fabric.widgets.label import Label
from modules.dock.module_overlay import HoverOverlay, HolePlaceholder
from fabric.widgets.eventbox import EventBox
from utils.helpers import toggle_class
import time
import gi

from modules.dock.layout_manager import LayoutManager

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gdk, Gtk

SPACING = 0


class DockBar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="dock-bar",
            layer="bottom",
            geometry="bottom",
            type_hint="dock",
            margin="0px",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            **kwargs,
        )

        self.init_modules()
        self.layout_manager = LayoutManager(self)
        self.layout_manager.init_layout()

        self.hole_state = False
        self.add_keybinding("Escape", lambda *_: self.close())

    def init_modules(self):
        module_widths = [250, 120, 55, 180]
        self.visual_modules = [
            Box(style=f"border:white solid 1px; border-radius:20px; min-width:{w}px;")
            for w in module_widths
        ]
        self.placeholders = [
            HolePlaceholder(target=mod, edge_flag=(i == len(self.visual_modules) - 2))
            for i, mod in enumerate(self.visual_modules)
        ]

        self.hover_overlay_row = Box(
            style="min-height:40px;",
            spacing=SPACING,
            h_expand=True,
            children=[
                HoverOverlay(target_box=mod, hole_box=hole, id=i)
                for i, (mod, hole) in enumerate(
                    zip(self.visual_modules, self.placeholders)
                )
            ],
        )

        for i, module in enumerate(self.hover_overlay_row.children):
            module.connect("hole-index", self.handle_hover)

        self.pill = Box(name="vert")

        self.edge_fallback = EventBox(
            h_expand=True,
            child=Box(h_expand=True, style="background-color:orange"),
            events=["enter-notify"],
        )
        self.edge_fallback.connect(
            "enter-notify-event", lambda w, e: self.set_hole_state(w, e, False)
        )
        self.hover_overlay_row.add(self.edge_fallback)

    def open(self):
        toggle_class(self.pill, "contractor", "expand")
        toggle_class(self.layout_manager.pill_container, "contractor", "expander")
        self.bool = True

    def close(self):
        toggle_class(self.pill, "expand", "contractor")
        toggle_class(self.layout_manager.pill_container, "expander", "contractor")
        self.bool = False

    def set_hole_state(self, source, event, state: bool):
        self.layout_manager.set_hole_state(source, event, state)

    def handle_hover(self, source, id: int):
        self.layout_manager.handle_hover(source, id)
