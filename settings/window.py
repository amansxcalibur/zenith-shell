from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.x11 import X11Window as Window
from fabric.widgets.scrolledwindow import ScrolledWindow

from modules.wiggle_bar import WigglyArrow
from widgets.shapes import Pill, Circle, WavyCircle, Ellipse, Pentagon
from widgets.material_label import MaterialIconLabel, MaterialFontLabel

import icons
from config.info import CONFIG_FILE
from utils.cursor import add_hover_cursor
from config.i3_config import i3_keybinds_setter

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

from .base import TabConfig
from .tabs import IconVariationsTab, FontVariationsTab, KeyBindingsTab, LauncherTab, PillDockTab


class DragHandler:
    def __init__(self, window):
        self.window = window
        self.dragging = False
        self.offset_x = 0
        self.offset_y = 0

    def on_button_press(self, source, event):
        if event.button == 1:
            self.window.begin_move_drag(
                event.button, int(event.x_root), int(event.y_root), event.time
            )
            # We return False so the event still reaches the ModulePill
            # to start the DnD operation.
            return False

    def on_motion(self, source, event):
        if self.dragging:
            new_x = int(event.x_root - self.offset_x)
            new_y = int(event.y_root - self.offset_y)
            self.window.get_window().move(new_x, new_y)

    def on_button_release(self, source, event):
        if event.button == 1:
            self.dragging = False


class SettingsWindow(Window):
    def __init__(self):
        super().__init__(
            layer="top",
            geometry="center",
            type_hint="normal",
            visible=True,
            sticky=False,
            all_visible=True,
        )

        self.buttons = {}
        self.stack = None
        self.shapes_box = None
        self.drag_handler = DragHandler(self)
        self.tabs = self._register_tabs()

        self._build_ui()
        self._setup_events()

    def _register_tabs(self) -> dict:
        return {
            "General": [
                TabConfig(
                    "dock_and_pill",
                    "Pill & Dock",
                    icons.monitor.symbol(),
                    lambda: PillDockTab().get_widget(),
                    "Appearance",
                ),
            ],
            "Typography": [
                TabConfig(
                    "icon_variations",
                    "Icon Variations",
                    icons.brightness_material.symbol(),
                    lambda: IconVariationsTab().get_widget(),
                    "Appearance",
                ),
                TabConfig(
                    "font_variations",
                    "Font Variations",
                    icons.font.symbol(),
                    lambda: FontVariationsTab().get_widget(),
                    "Appearance",
                ),
            ],
            "Navigation": [
                TabConfig(
                    "key_bindings",
                    "Key Bindings",
                    icons.dictionary.symbol(),
                    lambda: KeyBindingsTab().get_widget(),
                    "Appearance",
                ),
                TabConfig(
                    "launcher",
                    "Launcher",
                    icons.apps.symbol(),
                    lambda: LauncherTab().get_widget(),
                    "Appearance",
                ),
            ],
        }

    def _setup_events(self):
        self.connect("button-press-event", self.drag_handler.on_button_press)
        # self.connect("motion-notify-event", self.drag_handler.on_motion)
        # self.connect("button-release-event", self.drag_handler.on_button_release)
        self.connect("delete-event", self.on_close)

        GLib.timeout_add_seconds(1, self._cycle_shapes)

    def _build_ui(self):
        main_box = Box(name="settings", orientation="v", spacing=10)

        # header
        main_box.pack_start(self._create_header(), False, False, 0)

        # content
        content_box = Box(
            name="settings-content",
            orientation="h",
            spacing=12,
            h_expand=True,
            v_expand=True,
        )

        menu_box = self._create_sidebar()
        content_box.add(menu_box)

        self.scrollable_window = ScrolledWindow(
            child=self.stack,
            h_expand=True,
            h_align="center",
            min_content_size=(600, 650),
            max_content_size=(600, 650),
        )
        self.scrolled_window_container = Box(
            name="settings-stack-container",
            h_expand=True,
            children=self.scrollable_window,
        )
        content_box.add(self.scrolled_window_container)

        main_box.pack_start(content_box, True, True, 0)

        # footer
        main_box.pack_start(self._create_footer(), True, True, 0)

        self.children = main_box

    def _create_header(self) -> Box:
        header = Box(name="settings-header", orientation="h")

        close_button = Button(
            name="menu-close-button",
            child=Label(name="close-label", markup=icons.cancel.markup()),
            on_clicked=lambda b: self.on_close(None),
        )

        settings_header = MaterialFontLabel(text="Settings", font_size=16)
        header.pack_end(close_button, False, False, 0)
        header.pack_end(settings_header, True, False, 0)

        return header

    def _create_sidebar(self) -> Box:
        switch_box = self._create_tab_switcher()

        aspect = Gtk.AspectFrame(ratio=1.0, obey_child=False, xalign=0.5, yalign=1.0)

        self.shapes_box = Stack(
            name="shapes-box",
            h_expand=True,
            v_expand=True,
            children=[
                Pill(size=(-1, -1)),
                Circle(size=(-1, -1)),
                WavyCircle(size=(-1, -1)),
                Ellipse(size=(-1, -1)),
                Pentagon(size=(-1, -1)),
            ],
        )
        aspect.add(self.shapes_box)

        return Box(orientation="v", children=[switch_box, aspect])

    def _create_tab_switcher(self) -> Box:
        switch_box = Box(name="stack-switcher", orientation="v", spacing=2)
        self.stack = Stack(name="settings-stack")
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        for section_name, tabs in self.tabs.items():
            switch_box.pack_start(
                Label(label=section_name, h_align="start", style_classes="section-subheading"), False, False, 0
            )

            for tab_config in tabs:
                button = self._create_tab_button(tab_config)
                switch_box.pack_start(button, False, False, 0)
                self.stack.add_titled(
                    tab_config.widget, tab_config.id, tab_config.label
                )

        self.stack.connect("notify::visible-child-name", self._sync_checked_state)

        # init
        GLib.idle_add(lambda: self._sync_checked_state(self.stack, None))

        return switch_box
    
    def _sync_checked_state(self, stack, _):
        tab_id = stack.get_visible_child_name()

        for key, btn in self.buttons.items():
            btn.remove_style_class("checked")
            if tab_id == key:
                btn.add_style_class("checked")

    def _create_tab_button(self, tab_config: TabConfig) -> Button:
        box = Box(
            spacing=10,
            children=[
                MaterialIconLabel(
                    icon_text=tab_config.icon, font_size=17, h_expand=False
                ),
                Label(
                    style_classes=["settings-option-label"],
                    label=tab_config.label,
                    h_expand=True,
                    h_align="start",
                ),
            ],
        )

        button = Button(style_classes=["settings-option-btn"], child=box, on_clicked = lambda b: self._on_tab_clicked(tab_config.id))

        self.buttons[tab_config.id] = button

        return button

    def _create_footer(self) -> Box:
        save_btn = add_hover_cursor(
            Button(
                label="Save",
                style_classes=["settings-btn", "bright"],
                on_clicked=i3_keybinds_setter,
            )
        )
        cancel_btn = add_hover_cursor(
            Button(
                label="Cancel",
                style_classes=["settings-btn"],
                on_clicked=lambda b: self.on_close(None),
            )
        )

        config_path_box = Box(
            v_align="center",
            children=Box(
                name="config-path-box",
                spacing=10,
                children=[
                    Label(name="config-path-label", label=CONFIG_FILE),
                    Box(
                        size=(150, -1),
                        h_expand=True,
                        v_expand=True,
                        h_align="fill",
                        v_align="center",
                        orientation="v",
                        children=WigglyArrow(),
                    ),
                ],
            ),
        )

        return Box(
            name="settings-footer",
            spacing=5,
            children=[config_path_box, Box(h_expand=True), cancel_btn, save_btn],
        )

    def _on_tab_clicked(self, tab_id: str):
        self.stack.set_visible_child_name(tab_id)

    def _cycle_shapes(self) -> bool:
        if not self.shapes_box:
            return False

        widget_list = self.shapes_box.get_children()
        current_shape = self.shapes_box.get_visible_child()
        current_index = widget_list.index(current_shape)
        next_index = (current_index + 1) % len(widget_list)

        self.shapes_box.set_visible_child(widget_list[next_index])
        return True

    def on_close(self, widget):
        if self.application:
            self.application.quit()
        else:
            self.destroy()