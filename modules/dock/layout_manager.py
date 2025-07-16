import time
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.overlay import Overlay
from fabric.widgets.label import Label
from gi.repository import GLib, Gtk
from utils.helpers import toggle_class

SPACING = 0


class LayoutManager:
    def __init__(self, dock, side, **kwargs):
        self.dock = dock
        self.side = side

    def init_layout(self):
        self.hole = Box(name="hori")
        self.starter_box = Box(name="start", h_expand=True)
        self.ender_box = Box(name="end", h_expand=True)
        self.starter_box.last_hover_time = time.monotonic()
        self.ender_box.last_hover_time = time.monotonic()
        self.main_hole = Box(
            name="dock-place",
            children=[
                self.starter_box,
                Box(
                    h_expand=True,
                    orientation="v",
                    children=[
                        self.hole,
                        Box(v_expand=True, style="background-color:black"),
                    ],
                ),
                self.ender_box,
            ],
            style="min-height:40px;",
        )
        self.placeholders = (
            self.dock.placeholders_left if self.side == "left" else self.dock.placeholders_right
        )
        self.hover_overlay_row = (
            self.dock.hover_overlay_row_left if self.side == "left" else self.dock.hover_overlay_row_right
        )
        self.hole_state = (
            self.dock.hole_state_left if self.side == "left" else self.dock.hole_state_right
        )

        self.placeholder_row = Box(style="min-height:40px;", h_expand=True)

        if self.side == "left":
            for i, module in enumerate(self.placeholders):
                if i < len(self.placeholders) - 1:
                    self.placeholder_row.add(module)
                    self.placeholder_row.add(
                        Box(name="spacer", style=f"min-width:{SPACING}px;")
                    )
                else:
                    self.placeholder_row.add(self.main_hole)
                    self.placeholder_row.add(
                        Box(h_expand=True, style="background-color:black")
                    )
        else:
            self.placeholder_row.add(
                Box(h_expand=True, style="background-color:black")
            )
            self.placeholder_row.add(self.main_hole)
            for i, module in enumerate(self.placeholders):
                if i > 0:
                    self.placeholder_row.add(
                        Box(name="spacer", style=f"min-width:{SPACING}px;")
                    )
                    self.placeholder_row.add(module)

        self._dock_overlay = Overlay(
            child=self.placeholder_row,
            overlays=self.hover_overlay_row,
            h_expand=True,
        )

        self.event_wrapper = EventBox(
            child=self._dock_overlay,
            events=["enter-notify", "leave-notify"],
            h_expand=True,
        )
        self.event_wrapper.connect(
            "enter-notify-event", lambda w, e: self.set_hole_state(w, e, True)
        )
        self.event_wrapper.connect(
            "leave-notify-event", lambda w, e: self.set_hole_state(w, e, False)
        )

    def set_hole_state(self, source, event, state: bool):
        if not state:
            self.starter_box.add_style_class("start")
            self.ender_box.add_style_class("end")
            if self.side=="left":
                self.starter_box.set_style("min-width:0px; background-color:black")
            else:
                self.ender_box.set_style("min-width:0px; background-color:black")
            toggle_class(self.starter_box, "expander", "contractor")
            toggle_class(self.ender_box, "expander", "contractor")
            self.hole.set_style(
                "min-height:0px; min-width:0px; margin-top:0px;"
                "transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1),"
                "min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1), margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1)"
            )
            self.hole_state = False

    def handle_hover(self, source, id: int):
        print("got signal")
        self.starter_box.last_hover_time = time.monotonic()
        self.ender_box.last_hover_time = time.monotonic()
        if self.side == "left":
            enumerate_thru = self.hover_overlay_row.children[:-1]
        else:
            enumerate_thru = self.hover_overlay_row.children[1:]
        for i, overlay in enumerate(enumerate_thru):

            overlay.last_hover_time = time.monotonic()
            self._apply_hover_effects(i, overlay, id)
        if self.side=="left":
            self._update_spacers(source._id, id)
        self.hole_state = True

    def _apply_hover_effects(self, i, overlay, id):
        if id < 0:
            return
        
        if self.side == "left":

            if i < id:
                if overlay.width == 0:
                    overlay.width = overlay.get_allocation().width
                width = overlay.width if i != id - 1 else overlay.width - 20
                style = f"min-width:{width}px;"
                if self.hole_state:
                    style += " transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
                overlay._hole.set_style(style)

            elif i > id:
                style = "min-width:0px; background-color:transparent;"
                if self.hole_state:
                    style += " transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
                overlay._hole.set_style(style)

            elif i == id:
                self._handle_main_hole(i, overlay)
        else:
            if i < id:
                style = "min-width:0px; background-color:transparent;"
                if self.hole_state:
                    style += " transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
                overlay._hole.set_style(style)

            elif i > id:
                
                if overlay.width == 0:
                    overlay.width = overlay.get_allocation().width
                width = overlay.width if i != id + 1 else overlay.width - 20
                style = f"min-width:{width}px;"
                if self.hole_state:
                    style += " transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
                overlay._hole.set_style(style)

            elif i == id:
                self._handle_main_hole(i, overlay)

    def _handle_main_hole(self, i, overlay):
        if self.side=="left":
            main_hole_width = overlay.width + (40 if i != 0 else 0)
        else:
            main_hole_width = overlay.width + (40 if i != len(self.dock.visual_modules_right)-1 else 0)
        num_modules = len(self.dock.visual_modules_left) if self.side == "left" else len(self.dock.visual_modules_right)
        

        if self.side == "left":
            # left edge
            if i == 0:
                self.starter_box.remove_style_class("start")
                self.ender_box.remove_style_class("end")
                self.main_hole.set_style(
                    f"min-height:0px; min-width:{overlay.width}px; margin-top:0px;"
                )
                self.starter_box.set_style("min-width:0px; background-color:transparent;")
                GLib.timeout_add(250, self._delayed_clear_style_edges(self.starter_box))
            else:
                self.starter_box.set_style("min-width:20px;")
                self.ender_box.set_style("min-width:20px;")
                self.starter_box.add_style_class("start")
                self.ender_box.add_style_class("end")
        else:
            # right edge
            if i == num_modules - 1:
                self.starter_box.remove_style_class("start")
                self.ender_box.remove_style_class("end")
                self.main_hole.set_style(
                    f"min-height:0px; min-width:{overlay.width}px; margin-top:0px;"
                )
                self.ender_box.set_style("min-width:0px;")
                GLib.timeout_add(250, self._delayed_clear_style_edges(self.ender_box))
            else:
                self.starter_box.set_style("min-width:20px;")
                self.ender_box.set_style("min-width:20px;")
                self.starter_box.add_style_class("start")
                self.ender_box.add_style_class("end")
    
        self.hole.set_style(
            f"min-height:40px; min-width:{overlay.width}px;"
            "transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1),"
            "min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
        )

        if self.hole_state:
            overlay._hole.set_style(
                "min-width:0px; transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1); "
            )
            GLib.timeout_add(250, self._delayed_clear_style(overlay))
            self.main_hole.set_style(
                f"min-height:0px; min-width:{main_hole_width}px; margin-top:0px;"
                "transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1),"
                "min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1), margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
            )
        else:
            overlay._hole.set_style("min-width:0px; background-color:transparent;")
            self.main_hole.set_style(
                f"min-height:0px; min-width:{main_hole_width}px; margin-top:0px;"
            )

        toggle_class(self.starter_box, "contractor", "expander")
        toggle_class(self.ender_box, "contractor", "expander")

    def _delayed_clear_style(self, widget):
        hover_time = widget.last_hover_time
        # the lambda is delayed, not this func
        return lambda hover_time = hover_time: (
            (widget._hole.set_style("min-width:0px; background-color:transparent;") or False)
            if widget.last_hover_time == hover_time
            else False
        )
    
    def _delayed_clear_style_edges(self, widget):
        hover_time = widget.last_hover_time
        return lambda hover_time = hover_time: (
            (widget.set_style("min-width:0px; background-color:transparent;") or False)
            if widget.last_hover_time == hover_time
            else False
        )

    def _update_spacers(self, source_id, hovered_id):
        for i, module in enumerate(self.placeholder_row.children):
            if (self.side=="left" and i % 2 == 1) or (self.side=="right" and i>1 and i%2==0):
                if hovered_id < 0:
                    module.set_style(f"background-color:black; min-width:{SPACING}px")
                elif i / 2 > source_id and i < len(self.placeholder_row.children) - 1:
                    module.set_style("background-color:transparent; min-width:0px;")