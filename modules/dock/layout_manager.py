import time
from enum import Enum
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.widgets.overlay import Overlay
from utils.helpers import toggle_class

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib

SPACING = 0
DEFAULT_MARGIN = 0
FOCUS_MARGIN = 3


class ModuleRelation(Enum):
    MAIN = 0
    ADJACENT_NEIGHBOUR_EXPAND = 1
    NEIGHBOUR_EXPAND = 2
    COLLAPSE = 3


class LayoutManager:
    def __init__(self, dock, side, **kwargs):
        self.dock = dock
        self.side = side
        self.curr_hovered_index = -1

    def init_layout(self):
        self.main_hole = Box(name="hori")
        self.starter_box = Box(name="start", h_expand=True)
        self.ender_box = Box(name="end", h_expand=True)
        self.starter_box.last_hover_time = time.monotonic()
        self.ender_box.last_hover_time = time.monotonic()
        self._last_event_update_time = time.monotonic()
        self.main_hole_container = Box(
            name="dock-place",
            children=[
                self.starter_box,
                Box(
                    h_expand=True,
                    orientation="v",
                    children=[
                        self.main_hole,
                        Box(v_expand=True, style="background-color:black"),
                    ],
                ),
                self.ender_box,
            ],
            style="min-height:40px;",
        )
        self.placeholders = (
            self.dock.placeholders_left
            if self.side == "left"
            else self.dock.placeholders_right
        )
        self.hover_overlay_row = (
            self.dock.hover_overlay_row_left
            if self.side == "left"
            else self.dock.hover_overlay_row_right
        )
        self.hole_state = (
            self.dock.hole_state_left
            if self.side == "left"
            else self.dock.hole_state_right
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
                    self.placeholder_row.add(self.main_hole_container)
                    self.placeholder_row.add(
                        Box(h_expand=True, style="background-color:black")
                    )
        else:
            self.placeholder_row.add(Box(h_expand=True, style="background-color:black"))
            self.placeholder_row.add(self.main_hole_container)
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
        self._last_event_update_time = time.monotonic()
        GLib.timeout_add(
            500,
            lambda hover_time=self._last_event_update_time: self._trigger_default_hover(
                hover_time
            ),
        )

    def set_hole_state(self, source, event, state: bool):
        """Handles main hole collapse on module unhover."""
        if not state:
            print("event:", event, "\n")
            self.starter_box.add_style_class("start")
            self.ender_box.add_style_class("end")

            if self.curr_hovered_index == 0 and self.side == "left":
                self.starter_box.last_hover_time = time.monotonic()
                self.starter_box.set_style("min-width:0px; background-color:black")
            elif self.curr_hovered_index == len(self.placeholders)-1 and self.side == "right":
                self.ender_box.last_hover_time = time.monotonic()
                self.ender_box.set_style("min-width:0px; background-color:black")

            toggle_class(self.starter_box, "expander", "contractor")
            toggle_class(self.ender_box, "expander", "contractor")
            self.main_hole.set_style(
                "min-height:0px; min-width:0px; margin-top:0px;"
                "transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1),"
                "min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1), margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1)"
            )
            self.hole_state = False
            self._last_event_update_time = time.monotonic()
            # trigger default state
            GLib.timeout_add(
                500,
                lambda hover_time=self._last_event_update_time: self._trigger_default_hover(
                    hover_time
                ),
            )
            self.curr_hovered_index = -1

    def handle_hover(self, source, id: int):
        """Hover handler for dock modules"""
        self.curr_hovered_index = id
        self._last_event_update_time = time.monotonic()
        self.starter_box.last_hover_time = time.monotonic()
        self.ender_box.last_hover_time = time.monotonic()

        overlays = self._get_active_overlays()

        # update all overlays with new hover state
        for i, overlay in enumerate(overlays):
            overlay.last_hover_time = time.monotonic()
            self._apply_hover_effects(i, overlay, id)

        self._update_spacers(source._id, id)
        self.hole_state = True

    def _get_active_overlays(self):
        """Get the list of overlays to process based on side."""
        if self.side == "left":
            return self.hover_overlay_row.children[:-1]
        else:
            return self.hover_overlay_row.children[1:]

    def _apply_hover_effects(self, overlay_index, overlay, hovered_id):
        if hovered_id < 0:
            return

        animated = self.hole_state
        relation = self._get_overlay_relation(overlay_index, hovered_id)

        if relation == ModuleRelation.MAIN:
            overlay.expand_as_main(animated=animated)
            self._handle_main_hole(overlay_index, overlay)

        elif relation == ModuleRelation.ADJACENT_NEIGHBOUR_EXPAND:
            overlay.expand_as_neighbor(is_adjacent=True, animated=animated)

        elif relation == ModuleRelation.NEIGHBOUR_EXPAND:
            overlay.expand_as_neighbor(is_adjacent=False, animated=animated)

        elif relation == ModuleRelation.COLLAPSE:
            overlay.collapse(animated=animated)

    def _get_overlay_relation(self, overlay_index, hovered_id):
        """Determine the relationship between an overlay and the hovered item."""
        if overlay_index == hovered_id:
            return ModuleRelation.MAIN

        if self.side == "left":
            if overlay_index < hovered_id:
                return (
                    ModuleRelation.ADJACENT_NEIGHBOUR_EXPAND
                    if overlay_index == hovered_id - 1
                    else ModuleRelation.NEIGHBOUR_EXPAND
                )
            else:
                return ModuleRelation.COLLAPSE
        else:
            if overlay_index > hovered_id:
                return (
                    ModuleRelation.ADJACENT_NEIGHBOUR_EXPAND
                    if overlay_index == hovered_id + 1
                    else ModuleRelation.NEIGHBOUR_EXPAND
                )
            else:
                return ModuleRelation.COLLAPSE

    def _handle_main_hole(self, i, overlay):
        num_modules = (
            len(self.dock.visual_modules_left)
            if self.side == "left"
            else len(self.dock.visual_modules_right)
        )
        if self.side == "left":
            is_edge = i == 0
            main_hole_width = overlay.width + (0 if is_edge else 40)
        else:
            is_edge = i == num_modules - 1
            main_hole_width = overlay.width + (0 if is_edge else 40)

        if is_edge:
            self._setup_edge_hole(overlay, i)
        else:
            self._setup_regular_hole(overlay)

        # animate the main_hole
        self.main_hole.set_style(
            f"min-height:40px; min-width:{overlay.width}px;"
            "transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1),"
            "min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
        )

        # animate main_hole_container
        # keeps the main_hole_container size constant to make its child (self.main_hole) appear to collapse towards the box center, not the start.
        if self.hole_state:
            self.main_hole_container.set_style(
                f"min-height:0px; min-width:{main_hole_width}px; margin-top:0px;"
                "transition: min-height 0.25s cubic-bezier(0.5, 0.25, 0, 1),"
                "min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1), margin-top 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
            )
        else:
            self.main_hole_container.set_style(
                f"min-height:0px; min-width:{main_hole_width}px; margin-top:0px;"
            )

        toggle_class(self.starter_box, "contractor", "expander")
        toggle_class(self.ender_box, "contractor", "expander")

    def _setup_edge_hole(self, overlay, index):
        """Setup hole styling for edge modules."""
        self.starter_box.remove_style_class("start")
        self.ender_box.remove_style_class("end")
        self.main_hole_container.set_style(
            f"min-height:0px; min-width:{overlay.width}px; margin-top:0px;"
        )

        if self.side == "left":
            self.starter_box.set_style("min-width:0px;")
            GLib.timeout_add(250, self._delayed_clear_style_edges(self.starter_box))
        else:
            self.ender_box.set_style("min-width:0px;")
            GLib.timeout_add(250, self._delayed_clear_style_edges(self.ender_box))

    def _setup_regular_hole(self, overlay):
        """Setup hole styling for regular (non-edge) modules."""
        self.starter_box.set_style("min-width:20px;")
        self.ender_box.set_style("min-width:20px;")
        self.starter_box.add_style_class("start")
        self.ender_box.add_style_class("end")

    def _delayed_clear_style_edges(self, widget):
        hover_time = widget.last_hover_time
        # the lambda is delayed, not this func
        return lambda hover_time=hover_time: (
            (widget.set_style("min-width:0px; background-color:transparent;") or False)
            if widget.last_hover_time == hover_time
            else False
        )

    def _update_spacers(self, source_id, hovered_id):
        # spacers exists between each placeholders to mimic the spacing between overlay modules
        for i, module in enumerate(self.placeholder_row.children):
            if (self.side == "left" and i % 2 == 1) or (
                self.side == "right" and i > 1 and i % 2 == 0
            ):
                if hovered_id < 0:
                    module.set_style(f"background-color:black; min-width:{SPACING}px")
                elif i / 2 > source_id and i < len(self.placeholder_row.children) - 1:
                    module.set_style("background-color:transparent; min-width:0px;")

    def _trigger_default_hover(self, hover_time):
        # simulate hover on the first HoverOverlay
        if hover_time != self._last_event_update_time:
            return False
        if self.hover_overlay_row and self.hover_overlay_row.children:
            overlay = self.hover_overlay_row.children[0 if self.side == "left" else -1]
            overlay.on_hover(overlay, None)
        return False
