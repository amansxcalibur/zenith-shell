from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox

from widgets.wrap_box import WrapBox
from widgets.material_label import MaterialIconLabel, MaterialFontLabel

import icons
from config.info import config
from utils.cursor import add_hover_cursor
from ..base import BaseWidget, SectionBuilderMixin, LayoutBuilder

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk


class PillDockTab(BaseWidget, SectionBuilderMixin):

    def __init__(self):
        self.binding_groups = {}
        BaseWidget.__init__(self)

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

        pill_pos = config.pill.POSITION
        pill_key = f"{pill_pos['y']}-{pill_pos['x']}"

        for item in pill_positions:
            item["selected"] = (item["text"] == pill_key)

        bar_pos = config.bar.POSITION

        for item in dock_positions:
            item["selected"] = (item["text"] == bar_pos)


        dock_modules = {
            "left": [
                "Vertical Toggle Btn",
                "Workspaces",
                "Controls Box",
                "Weather",
                "Metrics",
            ],
            "right": ["System Tray", "Battery", "Time"],
        }
        all_modules = [
            "Vertical Toggle Btn",
            "Workspaces",
            "Controls Box",
            "Weather",
            "Metrics",
            "System Tray",
            "Battery",
            "Time",
        ]

        self.container.add(
            LayoutBuilder.section(
                "Pill", self._create_position_selector("Pill", pill_positions)
            )
        )

        palette = ModulePalette(all_modules)
        dock_modules_section = Box(
            style_classes="settings-section-container", orientation="v", spacing=6
        )
        dock_modules_section.add(
            Label(
                label=f"Modules",
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

        self.on_position_changed(group_id, button._position_data)

    def on_position_changed(self, group_id: str, position: dict):
        # override
        pass


class ModulePill(EventBox):
    def __init__(self, name):
        super().__init__()
        self.name = name

        self.targets = [Gtk.TargetEntry.new("text/plain", Gtk.TargetFlags.SAME_APP, 0)]

        self.label = Label(style_classes=["module-pill"], label=name)
        self.add(self.label)

        self.drag_source_set(
            Gdk.ModifierType.BUTTON1_MASK, self.targets, Gdk.DragAction.MOVE
        )

        self.connect("drag-data-get", self.on_drag_data_get)
        self.connect("button-press-event", self.on_button_press)

    def on_button_press(self, widget, event):
        # Returning True here prevents the Window's DragHandler
        # from ever seeing this specific click.
        return True

    def on_drag_data_get(self, widget, drag_context, data, info, time):
        # Explicitly set the selection data as text
        data.set_text(self.name, -1)


class ModuleDropBox(Gtk.ListBox):
    def __init__(self, side, model, refresh_all):
        super().__init__(name="module-drop-box")
        self.side = side
        self.model = model
        self.refresh_all = refresh_all
        self.placeholder = None
        self.set_selection_mode(Gtk.SelectionMode.NONE)
        self.set_vexpand(True)

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
            new_index = len(self.get_children())

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
            self.placeholder = None

    def on_drop(self, widget, drag_context, x, y, data, info, time):
        name = data.get_text()

        drop_index = (
            self.placeholder.get_index()
            if self.placeholder
            else len(self.model[self.side])
        )

        # cleanup placeholder
        if self.placeholder:
            self.remove(self.placeholder)
            self.placeholder = None

        if not name:
            drag_context.finish(False, False, time)
            return

        # update model
        for side in ("left", "right"):
            if name in self.model[side]:
                self.model[side].remove(name)
        self.model[self.side].insert(drop_index, name)

        # Gtk.drag_finish(drag_context, True, False, time)
        drag_context.finish(True, False, time)

        GLib.idle_add(self.refresh_all)

        return True

    def refresh(self):
        for row in self.get_children():
            self.remove(row)
        for index, name in enumerate(self.model[self.side]):
            row = Gtk.ListBoxRow()
            mod_pill = ModulePill(name)
            mod_pill.label.add_style_class("active")
            elem = Box(
                h_align="center",
                spacing=4,
                children=[
                    MaterialFontLabel(
                        style_classes=["module-pill", "active", "ranking"],
                        text="#" + str(index + 1),
                        wght=100,
                        font_size=15,
                    ),
                    mod_pill,
                ],
            )
            row.add(elem)
            self.add(row)
        self.show_all()


class ModulePalette(WrapBox):
    def __init__(self, all_modules):
        super().__init__(spacing=4)
        self.handles_own_drag = True

        for name in all_modules:
            self.add(ModulePill(name))
