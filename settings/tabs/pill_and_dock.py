import math
import cairo

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox

from widgets.clipping_box import ClippingBox
from widgets.wrap_box import WrapBox
from widgets.material_label import MaterialIconLabel

import icons
from utils.cursor import add_hover_cursor
from ..state import state
from modules.core.bottom.dock.placement import (
    COMPACT_MODULE_SIDE_PADDING,
    COMPACT_PADDING,
    MODULE_RADIUS,
    MODULE_SIZE,
    edge_band,
)
from modules.core.bottom.dock.surface import (
    BORDER_WIDTH,
    Hole,
    trace_inner_edge,
    trace_silhouette,
)
from ..base import BaseWidget, SectionBuilderMixin, LayoutBuilder

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk  # type: ignore

ANIMATION_MS = 180  # module rows opening, closing and fading

ALL_MODULES_MAPPING = {
    "actions": "Actions",
    "workspaces": "Workspaces",
    "vol_brightness_box": "Controls Box",
    "weather_mini": "Weather",
    "metrics": "Metrics",
    "date_time": "Date-Time",
    "battery": "Battery",
    "systray": "System Tray",
    "power_profiles": "Power Profiles",
}


class DockPreview(Gtk.DrawingArea):
    MODULE_WIDTH = 79
    CORNER_RADIUS = 12

    def __init__(self, padding: int, border: bool):
        super().__init__(name="dock-preview", hexpand=True)
        self._padding = padding
        self._border = border
        self.set_size_request(-1, 72)  # the thickest dock, with a little room above

    def set_dock_padding(self, padding: int):
        self._padding = padding
        self.queue_draw()

    def set_border(self, border: bool):
        self._border = border
        self.queue_draw()

    def do_draw(self, cr: cairo.Context):
        gap = self._padding
        width, height = self.get_allocated_width(), self.get_allocated_height()
        compact = gap == COMPACT_PADDING
        depth = MODULE_SIZE + 2 * gap
        thickness = depth + edge_band(gap)
        flare = MODULE_RADIUS + gap
        side = COMPACT_MODULE_SIDE_PADDING if compact else gap
        slot = self.MODULE_WIDTH + 2 * side  # a module with its padding

        resting_start = (width - 2 * slot) / 2  # the pair, centred
        hovered_start = resting_start + slot
        holes = [Hole(hovered_start, slot, depth, flare, flare)]

        # round the bottom corners to follow the frame around the preview
        radius = self.CORNER_RADIUS
        cr.move_to(0, 0)
        cr.line_to(width, 0)
        cr.arc(width - radius, height - radius, radius, 0, math.pi / 2)
        cr.arc(radius, height - radius, radius, math.pi / 2, math.pi)
        cr.close_path()
        cr.clip()

        context = self.get_style_context()
        state_flags = context.get_state()
        cr.translate(0, height - thickness)

        cr.save()
        trace_silhouette(cr, width, thickness, holes)
        cr.clip()
        Gdk.cairo_set_source_rgba(
            cr, context.get_property("background-color", state_flags)
        )
        cr.paint()
        if self._border:
            trace_inner_edge(cr, width, holes)
            cr.set_line_width(BORDER_WIDTH * 2)
            Gdk.cairo_set_source_rgba(
                cr, context.get_property("border-top-color", state_flags)
            )
            cr.stroke()
        cr.restore()

        for start, top, color in (
            (resting_start, gap, context.get_color(state_flags)),
            (
                hovered_start,
                0 if compact else gap,
                context.get_property("background-color", state_flags),
            ),
        ):
            cr.save()
            cr.translate(start + side, top)
            ClippingBox.render_shape(cr, self.MODULE_WIDTH, MODULE_SIZE, MODULE_RADIUS)
            Gdk.cairo_set_source_rgba(cr, color)
            cr.fill()
            cr.restore()
        return False


class PillDockTab(BaseWidget, SectionBuilderMixin):
    def __init__(self, **kwargs):
        self.binding_groups = {}
        BaseWidget.__init__(self, **kwargs)

    def _build_ui(self):
        self.container = Box(orientation="v", spacing=25)

        pill_positions = [
            {
                "selected": False,
                "icon": icons.north_west.symbol(),
                "text": "top-left",
                "value": "top-left",
            },
            {
                "selected": False,
                "icon": icons.north.symbol(),
                "text": "top-center",
                "value": "top-center",
            },
            {
                "selected": False,
                "icon": icons.north_east.symbol(),
                "text": "top-right",
                "value": "top-right",
            },
            {
                "selected": False,
                "icon": icons.west.symbol(),
                "text": "left",
                "value": "center-left",
            },
            {
                "selected": False,
                "icon": icons.center.symbol(),
                "text": "center",
                "value": "center-center",
            },
            {
                "selected": False,
                "icon": icons.east.symbol(),
                "text": "right",
                "value": "center-right",
            },
            {
                "selected": False,
                "icon": icons.south_west.symbol(),
                "text": "bottom-left",
                "value": "bottom-left",
            },
            {
                "selected": False,
                "icon": icons.south.symbol(),
                "text": "bottom-center",
                "value": "bottom-center",
            },
            {
                "selected": False,
                "icon": icons.south_east.symbol(),
                "text": "bottom-right",
                "value": "bottom-right",
            },
        ]

        dock_positions = [
            {
                "selected": False,
                "icon": icons.west.symbol(),
                "text": "left",
                "value": "left",
            },
            {
                "selected": False,
                "icon": icons.south.symbol(),
                "text": "bottom",
                "value": "bottom",
            },
            {
                "selected": False,
                "icon": icons.east.symbol(),
                "text": "right",
                "value": "right",
            },
        ]

        pill_pos = state.get(["pill", "POSITION"])
        pill_key = f"{pill_pos['y']}-{pill_pos['x']}"

        for item in pill_positions:
            item["selected"] = item["value"] == pill_key

        bar_pos = state.get(["bar", "POSITION"])

        for item in dock_positions:
            item["selected"] = item["text"] == bar_pos

        dock_modules = state.get(["bar", "modules"])

        self.container.add(
            LayoutBuilder.section(
                "Pill", self._create_position_selector("Pill", pill_positions)
            )
        )

        palette = ModulePalette(list(ALL_MODULES_MAPPING.keys()), dock_modules)
        dock_modules_section = Box(
            style_classes="settings-section-container", orientation="v", spacing=6
        )
        dock_modules_section.add(
            Label(
                label="Modules",
                style_classes="section-subheading",
                h_align="start",
            )
        )
        dock_modules_section.add(
            Label(
                label="Drag a module onto a side of the dock, or between sides to move it.",
                style_classes="module-hint",
                h_align="start",
            )
        )
        dock_modules_section.pack_start(palette, False, False, 0)

        dock_row = Box(spacing=10)

        left_box = None
        right_box = None

        def refresh_docks():
            left_box.refresh()
            right_box.refresh()
            palette.refresh()
            return False

        left_box = ModuleDropBox("left", dock_modules, refresh_docks)
        left_dropbox = Box(
            orientation="v",
            spacing=4,
            children=[
                Label(label="Left", h_align="start"),
                left_box,
            ],
        )
        right_box = ModuleDropBox("right", dock_modules, refresh_docks)
        right_dropbox = Box(
            orientation="v",
            spacing=4,
            children=[
                Label(label="Right", h_align="start"),
                right_box,
            ],
        )

        dock_row.pack_start(left_dropbox, True, True, 0)
        dock_row.pack_start(right_dropbox, True, True, 0)

        drop_box_size_grp = Gtk.SizeGroup.new(Gtk.SizeGroupMode.HORIZONTAL)
        drop_box_size_grp.add_widget(left_dropbox)
        drop_box_size_grp.add_widget(right_dropbox)

        dock_modules_section.pack_start(dock_row, True, True, 0)

        self.container.add(
            LayoutBuilder.section(
                "Dock",
                Box(
                    orientation="v",
                    spacing=16,
                    children=[
                        self._create_position_selector("Dock", dock_positions),
                        self._create_appearance_section(),
                        dock_modules_section,
                    ],
                ),
            )
        )

    def _create_appearance_section(self):
        self.dock_preview = DockPreview(
            padding=state.get(["bar", "PADDING"]),
            border=state.get(["bar", "BORDER"]),
        )

        border_switch = Gtk.Switch(
            name="matugen-switcher", active=state.get(["bar", "BORDER"])
        )
        border_switch.set_valign(Gtk.Align.CENTER)
        border_switch.connect("notify::active", self._on_border_toggled)

        section_box = Box(
            style_classes="settings-section-container", orientation="v", spacing=6
        )
        section_box.add(
            Label(
                label="Appearance",
                style_classes="section-subheading",
                h_align="start",
            )
        )
        controls = Box(
            orientation="v",
            spacing=16,
            v_align="center",
            children=[
                Box(
                    spacing=10,
                    children=[
                        Label(
                            label="Border",
                            width_request=80,
                            h_expand=True,
                            h_align="start",
                        ),
                        border_switch,
                    ],
                ),
                LayoutBuilder.pixel_slider(
                    "Spacing",
                    2,
                    12,
                    self._on_padding_changed,
                    state.get(["bar", "PADDING"]),
                ),
            ],
        )
        row = Box(
            spacing=16,
            children=[
                controls,
                Box(name="module-drop-box", children=self.dock_preview),
            ],
        )
        row.set_homogeneous(True)
        section_box.add(row)
        return section_box

    def _on_padding_changed(self, scale):
        val = int(scale.get_value())
        self.dock_preview.set_dock_padding(val)
        state.update(["bar", "PADDING"], val)

    def _on_border_toggled(self, switch, _pspec):
        active = switch.get_active()
        self.dock_preview.set_border(active)
        state.update(["bar", "BORDER"], active)

    def _create_position_selector(self, group_id: str, positions: list):
        section_box = Box(
            style_classes="settings-section-container", orientation="v", spacing=6
        )
        section_box.add(
            Label(
                label=f"{group_id} position",
                style_classes="section-subheading",
                h_align="start",
            )
        )

        container = WrapBox(spacing=4)

        for index, position in enumerate(positions):
            btn = self._create_position_button(group_id, position)
            if index == 0:
                btn.add_style_class("first")
            if index == len(positions) - 1:
                btn.add_style_class("last")
            container.add(btn)

        section_box.add(container)
        return section_box

    def _create_position_button(self, group_id: str, position: dict):
        btn = Button(
            name="settings-button-group-btn",
            style_classes=[] + (["active"] if position["selected"] else []),
            on_clicked=lambda b: self._on_position_clicked(group_id, b),
            child=Box(
                spacing=10,
                h_align="start",
                children=[
                    MaterialIconLabel(icon_text=position["icon"], font_size=17),
                    Label(label=position["text"]),
                ],
            ),
        )

        btn._group_id = group_id
        btn._position_data = position

        btn._value = position["value"]

        return add_hover_cursor(btn)

    def _on_position_clicked(self, group_id: str, button: Button):
        """Handle single-select within group"""
        parent = button.get_parent()
        clicked_box = button

        for btn in parent.get_children():
            if getattr(btn, "_group_id", None) == group_id:
                btn.remove_style_class("active")
                btn._position_data["selected"] = False

        clicked_box.add_style_class("active")
        button._position_data["selected"] = True

        self.on_position_changed(group_id, button)

    def on_position_changed(self, group_id: str, button: Button):
        val = button._value

        if group_id == "Pill":
            y_val, x_val = val.split("-")
            state.update(["pill", "POSITION", "x"], x_val)
            state.update(["pill", "POSITION", "y"], y_val)

        elif group_id == "Dock":
            state.update(["bar", "POSITION"], val)


class ModulePill(EventBox):
    """A draggable module; with a rank and a remove callback it is a placed one."""

    def __init__(self, name, rank=None, on_remove=None):
        super().__init__()
        self.internal_key = name
        self.name = ALL_MODULES_MAPPING[name]
        self.lifted = False  # picked up by a drag, its space closed

        self.targets = [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)]

        placed = rank is not None
        self.rank_label = Label(style_classes="module-rank", label=str(rank))
        children = [
            MaterialIconLabel(
                style_classes="module-drag-icon",
                icon_text=icons.drag_indicator.symbol(),
                font_size=18,
            )
        ]
        if placed:
            children.append(self.rank_label)
        children.append(
            Label(label=self.name, h_expand=placed, h_align="start"),
        )
        if on_remove is not None:
            children.append(
                add_hover_cursor(
                    Button(
                        name="module-pill-close-button",
                        tooltip_text=f"Remove {self.name}",
                        child=MaterialIconLabel(
                            name="close-label",
                            style_classes="settings",
                            icon_text=icons.close.symbol(),
                        ),
                        on_clicked=lambda *_: on_remove(name),
                    )
                )
            )

        self.add(
            Box(
                style_classes=["module-pill"] + (["placed"] if placed else []),
                spacing=8,
                children=children,
            )
        )
        add_hover_cursor(self, "grab")

        self.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, self.targets, Gdk.DragAction.MOVE
        )

        self.connect("drag-data-get", self.on_drag_data_get)
        self.connect("drag-begin", self.on_drag_begin)
        self.connect("drag-failed", self.on_drag_failed)
        self.connect("button-press-event", self.on_button_press)

    def on_button_press(self, widget, event):
        # returning True here prevents the Window's DragHandler
        # from ever seeing this specific click.
        return True

    def on_drag_begin(self, widget, drag_context) -> None:
        # set the module pill as drag icon, held by its middle
        surface = self.create_cairo_surface()
        allocation = self.get_allocation()
        surface.set_device_offset(-allocation.width / 2, -allocation.height / 2)
        Gtk.drag_set_icon_surface(drag_context, surface)

        # once the drag has its icon, close the space the module leaves
        GLib.idle_add(self.set_lifted, True)

    def on_drag_failed(self, widget, drag_context, result) -> bool:
        # dropped nowhere or cancelled: put it back. A drop rebuilds it instead.
        self.set_lifted(False)
        return False

    def set_lifted(self, lifted: bool) -> bool:
        self.lifted = lifted
        parent = self.get_parent()
        if isinstance(parent, Gtk.Revealer) and isinstance(
            parent.get_parent(), Gtk.ListBoxRow
        ):
            # a placed row vanishes at once, and its empty space slides shut
            self.set_opacity(0 if lifted else 1)
            parent.set_reveal_child(not lifted)
        elif parent is not None:
            # a palette chip, maybe inside its fade-in revealer, leaves the wrap
            (parent if isinstance(parent, Gtk.Revealer) else self).set_visible(
                not lifted
            )
        return False

    def create_cairo_surface(self):
        allocation = self.get_allocation()
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, allocation.width, allocation.height
        )
        context = cairo.Context(surface)

        self.draw(context)

        return surface

    def on_drag_data_get(self, widget, drag_context, data, info, time):
        # explicitly set the selection data as text
        data.set_text(self.internal_key, -1)


def animated(child, transition, revealed=False):
    """Wrap child in a revealer that opens once shown, unless already revealed."""
    revealer = Gtk.Revealer(
        transition_type=transition,
        transition_duration=ANIMATION_MS,
        reveal_child=revealed,
    )
    revealer.add(child)
    if not revealed:
        revealer.connect("map", lambda r: r.set_reveal_child(True))
    return revealer


class ModuleDropBox(Gtk.ListBox):
    """
    One side of the dock. Rows are kept per module and ordered by `_order`, so a
    row on its way out can collapse in place while the others settle around it.
    A drag hovering here opens an empty gap, which the module fills when dropped.
    """

    def __init__(self, side, model, refresh_all):
        super().__init__(name="module-drop-box")
        self.side = side
        self.model = model
        self.refresh_all = refresh_all
        self.drop_gap = None
        self.set_selection_mode(Gtk.SelectionMode.NONE)
        self.set_vexpand(True)
        self.set_sort_func(self._sort)
        self._pending_drop_index = None
        self._rows = {}  # module name -> its row, while on this side
        self._dropped = None  # the module to put in the gap on the next refresh
        self._filled_gap = None  # the gap it replaces then
        self._hovering = False
        self._dropping = False
        self._built = False

        empty_hint = Label(
            style_classes=["module-hint", "empty"], label="Drop modules here"
        )
        empty_hint.show()
        self.set_placeholder(empty_hint)

        # no defaults: GTK's would emit drag-leave on drop and close the gap
        # before the module could fill it, so drops are taken by hand
        targets = [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)]
        self.drag_dest_set(0, targets, Gdk.DragAction.MOVE)

        self.connect("drag-motion", self.on_drag_motion)
        self.connect("drag-leave", self.on_drag_leave)
        self.connect("drag-drop", self.on_drag_drop)
        self.connect("drag-data-received", self.on_drop)

        GLib.idle_add(self.refresh_all)

    @staticmethod
    def _sort(row_a, row_b, *_):
        return (row_a._order > row_b._order) - (row_a._order < row_b._order)

    def _new_row(self, child, order, animate):
        row = Gtk.ListBoxRow(activatable=False, selectable=False)
        row._order = order
        row._leaving = False
        row.pill = None
        row.add(animated(child, Gtk.RevealerTransitionType.SLIDE_DOWN, not animate))
        self.add(row)
        row.show_all()
        return row

    def _collapse(self, row):
        """Close the row, then drop it."""
        row._leaving = True
        # sit just above the row that now holds its index
        row._order -= 0.5

        revealer = row.get_child()
        if not revealer.get_reveal_child() and not revealer.get_child_revealed():
            self.remove(row)  # already shut, as a lifted row is
            return

        def on_revealed(revealer, _pspec):
            if not revealer.get_child_revealed() and row.get_parent() is self:
                self.remove(row)

        revealer.connect("notify::child-revealed", on_revealed)
        revealer.set_reveal_child(False)

    def _module_rows(self):
        """Rows of modules staying here, in order: not leaving, not lifted."""
        return [
            row
            for row in self.get_children()
            if row.pill is not None and not row._leaving and not row.pill.lifted
        ]

    def drop_index_at(self, y):
        """Module rows above y, by their middles; the gap doesn't count."""
        index = 0
        for row in self._module_rows():
            _, row_y = row.translate_coordinates(self, 0, 0)
            if row_y + row.get_allocated_height() / 2 < y:
                index += 1
        return index

    def show_drop_gap(self, index):
        rows = self._module_rows()
        # just above the module the drop would push down
        if index < len(rows):
            order = rows[index]._order - 0.25
        else:
            order = (rows[-1]._order if rows else 0) + 0.75

        if not self.drop_gap:
            self.drop_gap = self._new_row(
                Box(style_classes="drop-gap"), order, animate=True
            )
        elif self.drop_gap._order != order:
            self.drop_gap._order = order
            self.drop_gap.changed()

    def hide_drop_gap(self):
        if self.drop_gap:
            self._collapse(self.drop_gap)
            self.drop_gap = None

    @staticmethod
    def _is_module_drag(widget, context):
        target = widget.drag_dest_find_target(context, None)
        return target is not None and target.name() == "text/plain"

    def on_drag_motion(self, widget, context, x, y, time):
        if not self._is_module_drag(widget, context):
            Gdk.drag_status(context, 0, time)
            return False

        self._hovering = True
        self._pending_drop_index = self.drop_index_at(y)
        self.show_drop_gap(self._pending_drop_index)
        self.get_style_context().add_class("drag-over")

        Gdk.drag_status(context, Gdk.DragAction.MOVE, time)
        return True

    def on_drag_leave(self, widget, context, time):
        # GTK also leaves just before a drop, so wait to see if one follows
        self._hovering = False
        self.get_style_context().remove_class("drag-over")
        GLib.idle_add(self._close_gap_if_left)

    def _close_gap_if_left(self):
        if not self._hovering and not self._dropping:
            self.hide_drop_gap()
        return False

    def on_drag_drop(self, widget, context, x, y, time):
        if not self._is_module_drag(widget, context):
            return False
        self._dropping = True
        widget.drag_get_data(context, widget.drag_dest_find_target(context, None), time)
        return True

    def on_drop(self, widget, drag_context, x, y, data, info, time):
        self._dropping = False
        name = data.get_text()

        drop_index = (
            self._pending_drop_index
            if self._pending_drop_index is not None
            else len(self.model[self.side])
        )

        if not name:
            self.hide_drop_gap()
            drag_context.finish(False, False, time)
            return

        # the index counts the modules staying here, the dragged one aside
        for side in ("left", "right"):
            if name in self.model[side]:
                self.model[side].remove(name)
                break

        self.model[self.side].insert(drop_index, name)
        self._dropped = name
        self._filled_gap = self.drop_gap  # stays open until the module fills it
        self.drop_gap = None

        drag_context.finish(True, False, time)
        GLib.idle_add(self.refresh_all)
        return True

    def refresh(self):
        names = self.model[self.side]

        # rows that left, and a row moved within this side, close where they were
        for name, row in list(self._rows.items()):
            if name not in names or name == self._dropped:
                del self._rows[name]
                self._collapse(row)

        for index, name in enumerate(names):
            row = self._rows.get(name)
            if row is None:
                pill = ModulePill(name, rank=index + 1, on_remove=self.on_remove)
                # a dropped module fills its gap as is; others open into place
                animate = self._built and name != self._dropped
                row = self._new_row(pill, index, animate=animate)
                row.pill = pill
                self._rows[name] = row
            row._order = index
            row.pill.rank_label.set_label(str(index + 1))

        if self._filled_gap is not None:
            if self._filled_gap.get_parent() is self:
                self.remove(self._filled_gap)
            self._filled_gap = None

        self._dropped = None
        self._built = True
        self.invalidate_sort()
        state.update(["bar", "modules", self.side], list(names))

    def on_remove(self, name):
        if name in self.model[self.side]:
            self.model[self.side].remove(name)

        GLib.idle_add(self.refresh_all)


class ModulePalette(WrapBox):
    """The modules on neither side of the dock; ones that come back fade in."""

    def __init__(self, all_modules, model):
        super().__init__(spacing=4)
        self.handles_own_drag = True
        self.all_modules = all_modules
        self.model = model
        self._available = None

    def refresh(self):
        for child in self.get_children():
            self.remove(child)

        placed = self.model["left"] + self.model["right"]
        available = [name for name in self.all_modules if name not in placed]
        returned = set(available) - set(
            available if self._available is None else self._available
        )
        self._available = available

        for name in available:
            pill = ModulePill(name)
            if name in returned:
                pill = animated(pill, Gtk.RevealerTransitionType.CROSSFADE)
            self.add(pill)
        self.show_all()
