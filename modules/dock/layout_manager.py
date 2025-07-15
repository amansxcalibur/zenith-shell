import time
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.overlay import Overlay
from gi.repository import GLib, Gtk
from utils.helpers import toggle_class

SPACING = 0


class LayoutManager:
    def __init__(self, dock):
        self.dock = dock

    def init_layout(self):
        self.dock.hole = Box(name="hori")
        self.dock.starter_box = Box(name="start", h_expand=True)
        self.dock.ender_box = Box(name="end", h_expand=True)
        self.dock.starter_box.last_hover_time = time.monotonic()

        self.dock.main_hole = Box(
            name="dock-place",
            children=[
                self.dock.starter_box,
                Box(
                    h_expand=True,
                    orientation="v",
                    children=[
                        self.dock.hole,
                        Box(v_expand=True, style="background-color:black"),
                    ],
                ),
                self.dock.ender_box,
            ],
            style="min-height:40px;",
        )

        self.dock.placeholder_row = Box(style="min-height:40px;", h_expand=True)
        for i, module in enumerate(self.dock.placeholders):
            if i < len(self.dock.placeholders) - 1:
                self.dock.placeholder_row.add(module)
                self.dock.placeholder_row.add(
                    Box(name="spacer", style=f"min-width:{SPACING}px;")
                )
            else:
                self.dock.placeholder_row.add(self.dock.main_hole)
                self.dock.placeholder_row.add(
                    Box(h_expand=True, style="background-color:yellow;")
                )

        self.dock._dock_overlay = Overlay(
            child=self.dock.placeholder_row,
            overlays=self.dock.hover_overlay_row,
            h_expand=True,
        )

        self.dock.event_wrapper = EventBox(
            child=self.dock._dock_overlay,
            events=["enter-notify", "leave-notify"],
            h_expand=True,
        )
        self.dock.event_wrapper.connect(
            "enter-notify-event", lambda w, e: self.set_hole_state(w, e, True)
        )
        self.dock.event_wrapper.connect(
            "leave-notify-event", lambda w, e: self.set_hole_state(w, e, False)
        )

        self.dock.start = Box(h_expand=True, children=self.dock.event_wrapper)
        self.dock.end = Box(
            h_expand=True,
            children=[Box(style="background-color:purple;", h_expand=True)],
        )
        self.pill_container = Box(
            name="hori",
            orientation="v",
            children=[self.dock.pill, Box(name="bottom", v_expand=True)],
        )

        self.dock.children = Box(
            name="main", children=[self.dock.start, self.pill_container, self.dock.end]
        )

        size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
        size_group.add_widget(self.dock.start)
        size_group.add_widget(self.dock.end)

    def set_hole_state(self, source, event, state: bool):
        if not state:
            self.dock.starter_box.add_style_class("start")
            self.dock.ender_box.add_style_class("end")
            self.dock.starter_box.set_style("min-width:0px; background-color:black")
            toggle_class(self.dock.starter_box, "expander", "contractor")
            toggle_class(self.dock.ender_box, "expander", "contractor")
            self.dock.hole.set_style(
                "min-height:0px; min-width:0px; margin-top:0px;"
                "transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1),"
                "min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1), margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1)"
            )
            self.dock.hole_state = False

    def handle_hover(self, source, id: int):
        self.dock.starter_box.last_hover_time = time.monotonic()
        for i, overlay in enumerate(self.dock.hover_overlay_row.children[:-1]):
            overlay.last_hover_time = time.monotonic()
            self._apply_hover_effects(i, overlay, id)
        self._update_spacers(source._id, id)
        self.dock.hole_state = True

    def _apply_hover_effects(self, i, overlay, id):
        if id < 0:
            return

        if i < id:
            if overlay.width == 0:
                overlay.width = overlay.get_allocation().width
            width = overlay.width if i != id - 1 else overlay.width - 20
            style = f"min-width:{width}px;"
            if self.dock.hole_state:
                style += " transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
            overlay._hole.set_style(style)

        elif i > id:
            style = "min-width:0px; background-color:transparent;"
            if self.dock.hole_state:
                style += " transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
            overlay._hole.set_style(style)

        elif i == id:
            self._handle_main_hole(i, overlay)

    def _handle_main_hole(self, i, overlay):
        main_hole_width = overlay.width + (40 if i != 0 else 0)

        if i == 0:
            self.dock.starter_box.remove_style_class("start")
            self.dock.ender_box.remove_style_class("end")
            self.dock.main_hole.set_style(
                f"min-height:0px; min-width:{overlay.width}px; margin-top:0px;"
            )
            self.dock.starter_box.set_style("min-width:0px;")
            GLib.timeout_add(250, self._delayed_clear_style_2(self.dock.starter_box))
        else:
            self.dock.starter_box.set_style("min-width:20px;")
            self.dock.ender_box.set_style("min-width:20px;")
            self.dock.starter_box.add_style_class("start")
            self.dock.ender_box.add_style_class("end")

        self.dock.hole.set_style(
            f"min-height:40px; min-width:{overlay.width}px;"
            "transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1),"
            "min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
        )

        if self.dock.hole_state:
            overlay._hole.set_style(
                "min-width:0px; transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1); "
            )
            GLib.timeout_add(250, self._delayed_clear_style(overlay))
            self.dock.main_hole.set_style(
                f"min-height:0px; min-width:{main_hole_width}px; margin-top:0px;"
                "transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1),"
                "min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1), margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
            )
        else:
            overlay._hole.set_style("min-width:0px; background-color:transparent;")
            self.dock.main_hole.set_style(
                f"min-height:0px; min-width:{main_hole_width}px; margin-top:0px;"
            )

        toggle_class(self.dock.starter_box, "contractor", "expander")
        toggle_class(self.dock.ender_box, "contractor", "expander")

    def _delayed_clear_style(self, widget):
        hover_time = widget.last_hover_time
        # the lambda is delayed, not this func
        return lambda hover_time = hover_time: (
            (widget._hole.set_style("min-width:0px; background-color:transparent;") or False)
            if widget.last_hover_time == hover_time
            else False
        )
    
    def _delayed_clear_style_2(self, widget):
        hover_time = widget.last_hover_time
        return lambda: (
            (widget.set_style("min-width:0px; background-color:transparent") or False)
            if widget.last_hover_time == hover_time
            else False
        )

    def _update_spacers(self, source_id, hovered_id):
        for i, module in enumerate(self.dock.placeholder_row.children):
            if i % 2 == 1:
                if hovered_id < 0:
                    module.set_style(f"background-color:blue; min-width:{SPACING}px")
                elif i / 2 > source_id and i < len(self.dock.placeholder_row.children) - 1:
                    module.set_style("background-color:transparent; min-width:0px;")
