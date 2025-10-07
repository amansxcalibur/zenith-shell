import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gdk, Gtk

from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.core.service import Service, Signal

DEFAULT_MARGIN = 2
FOCUS_MARGIN = 3


class HoverOverlay(EventBox, Service):
    @Signal
    def hole_index(self, id: int) -> None: ...

    def __init__(
        self,
        target_box: Gtk.Widget,
        hole_box: Gtk.Widget,
        layout_manager,
        id: int,
        edge_flag=False,
        **kwargs,
    ):
        super().__init__(
            name="hover-overlay",
            events=["enter-notify", "leave-notify"],
            visible_window=False,
        )

        self._id = id
        self._target = target_box
        self._hole = hole_box
        self._edge_flag = edge_flag
        self._layout_manager = layout_manager
        self.width = 0
        self.is_currently_hovered = False
        self.is_currently_expanded = False

        import time

        self.last_hover_time = time.monotonic()

        self.add(self._target)

        self.connect("enter-notify-event", self.on_hover)
        self.connect("leave-notify-event", self.on_unhover)

        self._target.connect("size-allocate", self.on_target_resize)
        self._resize_timeout = None

        # init styles
        self.on_unhover(self, None)

    def on_hover(self, widget, event):
        self.is_currently_hovered = True
        self.is_currently_expanded = True
        self._target.set_style(
            f""
            f"padding-bottom:{FOCUS_MARGIN}px; padding-left:{FOCUS_MARGIN}px; padding-right:{FOCUS_MARGIN}px; "
            "transition: padding-bottom 0.1s cubic-bezier(0.5, 0.25, 0, 1), padding-top 0.1s cubic-bezier(0.5, 0.25, 0, 1)"
        )
        self.hole_index(self._id)

    def on_unhover(self, widget, event):
        # hovering to a child widget, don't unhover
        if event and event.detail == Gdk.NotifyType.INFERIOR:
            return
        self.is_currently_hovered = False
        self.is_currently_expanded = False
        self._target.set_style(
            ""
            f"padding-left:{FOCUS_MARGIN}px; padding-right:{FOCUS_MARGIN}px; padding-bottom: {DEFAULT_MARGIN}px; padding-top: {DEFAULT_MARGIN}px;"
            "transition: padding-bottom 0.1s cubic-bezier(0.5, 0.25, 0, 1), padding-top 0.1s cubic-bezier(0.5, 0.25, 0, 1)"
        )
        self._hole.set_style("min-width:0px;")
        self.hole_index(-1)

    def on_target_resize(self, widget, allocation):
        new_width = allocation.width
        if self._edge_flag:
            new_width -= 20

        if self.width != new_width:
            self.width = new_width

        if self.is_currently_expanded:
            self._sync_hole_to_target()

    def _sync_hole_to_target(self):
        """Synchronize placeholder hole width with target width."""
        curr_hovered_index = self._layout_manager.curr_hovered_index
        # main-hole if hovered, placeholder hole if not
        current_hole_width = (
            self._hole.get_allocation().width
            if curr_hovered_index != self._id
            else self._layout_manager.main_hole.get_allocation().width
        )
        target_width = self._target.get_allocation().width

        # print(f"  Syncing hole: {current_hole_width}px -> {expected_width}px  :  ", self._target.get_children()[0].get_name(), "id:", self._id)

        if self._id == curr_hovered_index:
            expected_width = target_width
            if current_hole_width != expected_width:
                self._layout_manager._handle_main_hole(self._id, self)
            return

        diff = -1 if self._layout_manager.side == "left" else +1

        if self._id == curr_hovered_index + diff:
            # adjacent neighbor
            expected_width = target_width - 20
        else:
            # regular neighbor
            expected_width = target_width

        if current_hole_width != expected_width:
            self._hole.set_style(
                f"min-width:{expected_width}px;"
                "transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"
            )

    # ---- handle hover states ----
    def expand_as_main(self, animated=True):
        self.is_currently_expanded = True
        target_width = (
            self.width if self.width > 0 else self._target.get_allocation().width
        )

        style = "min-width:0px;"
        if not self._layout_manager.hole_state:
            style += "background-color:transparent;"
        if animated:
            style += "transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"

        self._hole.set_style(style)
        GLib.timeout_add(250 if animated else 0, self._delayed_clear_style())

    def expand_as_neighbor(self, is_adjacent=False, animated=True):
        self.is_currently_expanded = True
        target_width = (
            self.width if self.width > 0 else self._target.get_allocation().width
        )

        # making room for the main hole - (40/2)px
        width = target_width - 20 if is_adjacent else target_width
        if width < 0:
            width = 0

        style = f"min-width:{width}px;"
        if animated:
            style += " transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"

        self._hole.set_style(style)

    def collapse(self, animated=True):
        self.is_currently_expanded = False

        style = "min-width:0px; background-color:transparent;"
        if animated:
            style += " transition: min-width 0.25s cubic-bezier(0.5, 0.25, 0, 1);"

        self._hole.set_style(style)

    #  fixes the small annoying black boxes at edges
    def _delayed_clear_style(self):
        """Clears residual styles from collapsed overlay."""
        hover_time = self.last_hover_time
        # the lambda is delayed, not this func
        return lambda hover_time=hover_time: (
            (
                self._hole.set_style("min-width:0px; background-color:transparent;")
                or False
            )
            if self.last_hover_time == hover_time
            else False
        )


class HolePlaceholder(Box):
    def __init__(self, target, edge_flag, **kwargs):
        super().__init__(name="hole-placeholder-box")
        self._edge_flag = edge_flag
        self._target = target
        # width handling done in HoverOverlay funnily enough
        self.width = self.get_allocation().width
