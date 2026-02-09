from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox

from widgets.wrap_box import WrapBox
from widgets.material_label import MaterialIconLabel, MaterialFontLabel

import icons
from utils.cursor import add_hover_cursor
from ..state import state
from ..base import BaseWidget, SectionBuilderMixin, LayoutBuilder

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk

ALL_MODULES_MAPPING = {
    "vertical_toggle_btn": "Vertical Toggle Btn",
    "workspaces": "Workspaces",
    "vol_brightness_box": "Controls Box",
    "weather_mini": "Weather",
    "metrics": "Metrics",
    "date_time": "Date-Time",
    "battery": "Battery",
    "systray": "System Tray",
}


class PillDockTab(BaseWidget, SectionBuilderMixin):
    def __init__(self, **kwargs):
        self.binding_groups = {}
        BaseWidget.__init__(self, **kwargs)

    def _build_ui(self):
        self.container = Box(orientation="v", spacing=25)

        pill_positions = [
            {"selected": False, "icon": icons.north_west.symbol(), "text": "top-left"},
            {"selected": False, "icon": icons.north.symbol(), "text": "top-center"},
            {"selected": False, "icon": icons.north_east.symbol(), "text": "top-right"},
            {"selected": False, "icon": icons.west.symbol(), "text": "left"},
            {"selected": False, "icon": icons.center.symbol(), "text": "center"},
            {"selected": False, "icon": icons.east.symbol(), "text": "right"},
            {
                "selected": False,
                "icon": icons.south_west.symbol(),
                "text": "bottom-left",
            },
            {"selected": False, "icon": icons.south.symbol(), "text": "bottom-center"},
            {
                "selected": False,
                "icon": icons.south_east.symbol(),
                "text": "bottom-right",
            },
        ]

        dock_positions = [
            {"selected": False, "icon": icons.west.symbol(), "text": "left"},
            {"selected": False, "icon": icons.north.symbol(), "text": "top"},
            {"selected": False, "icon": icons.south.symbol(), "text": "bottom"},
            {"selected": False, "icon": icons.east.symbol(), "text": "right"},
        ]

        pill_pos = state.get(["pill", "POSITION"])
        pill_key = f"{pill_pos['y']}-{pill_pos['x']}"

        for item in pill_positions:
            item["selected"] = item["text"] == pill_key

        bar_pos = state.get(["bar", "POSITION"])

        for item in dock_positions:
            item["selected"] = item["text"] == bar_pos

        dock_modules = state.get(["bar", "modules"])

        self.container.add(
            LayoutBuilder.section(
                "Pill", self._create_position_selector("Pill", pill_positions)
            )
        )

        palette = ModulePalette(list(ALL_MODULES_MAPPING.keys()))
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
        dock_modules_section.pack_start(palette, False, False, 0)

        dock_row = Box(spacing=10)

        left_box = None
        right_box = None

        def refresh_docks():
            left_box.refresh()
            right_box.refresh()
            return False

        left_box = ModuleDropBox("left", dock_modules, refresh_docks)
        left_dropbox = Box(
            orientation="v",
            spacing=4,
            children=[
                Label(label="Left"),
                left_box,
            ],
        )
        right_box = ModuleDropBox("right", dock_modules, refresh_docks)
        right_dropbox = Box(
            orientation="v",
            spacing=4,
            children=[
                Label(label="Right"),
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
                [
                    self._create_position_selector("Dock", dock_positions),
                    dock_modules_section,
                ],
            )
        )

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
        btn._value = position["text"]

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
    def __init__(self, name):
        super().__init__()
        self.internal_key = name
        self.name = ALL_MODULES_MAPPING[name]

        self.targets = [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)]

        self.label = Label(style_classes=["module-pill"], label=self.name)
        self.add(self.label)

        self.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, self.targets, Gdk.DragAction.MOVE
        )

        self.connect("drag-data-get", self.on_drag_data_get)
        self.connect("drag-begin", self.on_drag_begin)
        self.connect("drag-end", self.on_drag_end)
        self.connect("button-press-event", self.on_button_press)

    def on_button_press(self, widget, event):
        # Returning True here prevents the Window's DragHandler
        # from ever seeing this specific click.
        return True

    def on_drag_begin(self, widget, drag_context) -> None:
        self.set_opacity(0.5)

        # set the module pill as drag icon
        surface = self.create_cairo_surface()
        Gtk.drag_set_icon_surface(drag_context, surface)

    def on_drag_end(self, widget, drag_context) -> None:
        self.set_opacity(1.0)

    def create_cairo_surface(self):
        """Create a cairo surface for the drag icon."""
        import cairo

        allocation = self.get_allocation()
        surface = cairo.ImageSurface(
            cairo.FORMAT_ARGB32, allocation.width, allocation.height
        )
        context = cairo.Context(surface)

        self.draw(context)

        return surface

    def on_drag_data_get(self, widget, drag_context, data, info, time):
        # Explicitly set the selection data as text
        data.set_text(self.internal_key, -1)


class ModuleDropBox(Gtk.ListBox):
    def __init__(self, side, model, refresh_all):
        super().__init__(name="module-drop-box")
        self.side = side
        self.model = model
        self.refresh_all = refresh_all
        self.placeholder = None
        self.set_selection_mode(Gtk.SelectionMode.NONE)
        self.set_vexpand(True)
        self._pending_drop_index = None

        targets = [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)]
        self.drag_dest_set(Gtk.DestDefaults.ALL, targets, Gdk.DragAction.MOVE)

        self.connect("drag-motion", self.on_drag_motion)
        self.connect("drag-leave", self.on_drag_leave)
        self.connect("drag-data-received", self.on_drop)

        GLib.idle_add(self.refresh_all)

    def create_placeholder(self):
        row = Gtk.ListBoxRow()
        box = Box()
        box.set_size_request(200, 60)
        box.add_style_class("placeholder-row")

        row.add(Box(children=box, h_align="center"))

        return row

    def on_drag_motion(self, widget, context, x, y, time):
        target_row = self.get_row_at_y(y)

        if target_row:
            new_index = target_row.get_index()
        else:
            # If mouse is in the empty space at the bottom
            new_index = len(self.model[self.side])

        self._pending_drop_index = new_index

        # placeholder positioning
        if not self.placeholder:
            # create
            self.placeholder = self.create_placeholder()
            self.insert(self.placeholder, new_index)
            self.show_all()
        else:
            # move it only if the index has changed
            current_index = self.placeholder.get_index()
            if current_index != new_index:
                self.remove(self.placeholder)
                self.insert(self.placeholder, new_index)
                self.placeholder.show_all()

        Gdk.drag_status(context, Gdk.DragAction.MOVE, time)
        return True

    def on_drag_leave(self, widget, context, time):
        # Remove placeholder when mouse exits the box
        if self.placeholder:
            self.remove(self.placeholder)
            self.placeholder.destroy()
            self.placeholder = None

    def on_drop(self, widget, drag_context, x, y, data, info, time):
        name = data.get_text()

        drop_index = (
            self._pending_drop_index
            if self._pending_drop_index is not None
            else len(self.model[self.side])
        )

        # cleanup placeholder
        if self.placeholder:
            self.remove(self.placeholder)
            self.placeholder = None

        if not name:
            drag_context.finish(False, False, time)
            return

        source_side = None
        old_index = None

        # update model
        for side in ("left", "right"):
            if name in self.model[side]:
                source_side = side
                old_index = self.model[side].index(name)
                self.model[side].remove(name)
                break

        if source_side == self.side and old_index is not None:
            if drop_index > old_index:
                drop_index -= 1

        self.model[self.side].insert(drop_index, name)

        drag_context.finish(True, False, time)
        GLib.idle_add(self.refresh_all)
        return True

    def refresh(self):
        for row in self.get_children():
            self.remove(row)

        module_list = []

        for index, name in enumerate(self.model[self.side]):
            row = self._create_module_row(index, name)
            self.add(row)
            row.show()
            module_list.append(name)

        state.update(["bar", "modules", self.side], module_list)

    def _create_module_row(self, index, name):
        row = Gtk.ListBoxRow()

        mod_pill = ModulePill(name)
        mod_pill.label.add_style_class("active")

        close_button = Button(
            name="module-pill-close-button",
            child=MaterialIconLabel(name="close-label", icon_text=icons.close.symbol()),
            on_clicked=self.on_close,
            visible=False,
        )

        elem = EventBox(
            events="all",
            child=Box(
                h_align="center",
                spacing=4,
                style="margin-top:4px;",
                children=[
                    MaterialFontLabel(
                        style_classes=["module-pill", "active", "ranking"],
                        text=f"#{index + 1}",
                        wght=100,
                        font_size=15,
                    ),
                    mod_pill,
                    Box(v_align="start", children=close_button),
                ],
            ),
        )

        elem.close_button = close_button

        def on_enter(widget, _event):
            widget.close_button.show()

        def on_leave(widget, event):
            if event.detail == Gdk.NotifyType.INFERIOR:
                return
            widget.close_button.hide()

        elem.connect("enter-notify-event", on_enter)
        elem.connect("leave-notify-event", on_leave)

        row.add(elem)
        return row

    def on_close(self, button):
        widget = button
        while widget and not isinstance(widget, Gtk.ListBoxRow):
            widget = widget.get_parent()

        if not widget:
            return

        index = widget.get_index()

        # remove module
        if 0 <= index < len(self.model[self.side]):
            self.model[self.side].pop(index)

        GLib.idle_add(self.refresh_all)


class ModulePalette(WrapBox):
    def __init__(self, all_modules):
        super().__init__(spacing=4)
        self.handles_own_drag = True

        for name in all_modules:
            self.add(ModulePill(name))
