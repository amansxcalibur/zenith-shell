from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.utils.helpers import exec_shell_command_async

from config.info import IS_WAYLAND
from config.i3.utils import generate_i3_keybinds_config, is_swayfx
from config.info import CONFIG_FILE, SHELL_NAME
from config.bindings import (
    KeyBinding,
    KeybindingValidationError,
    find_keybinding_conflicts,
)

import icons

from modules.wiggle_bar import WigglyArrow

from utils.colors import bind_theme
from utils.cursor import add_hover_cursor
from utils.helpers import format_accel_to_keybind

from widgets.material_label import MaterialIconLabel, MaterialFontLabel
from widgets.shapes.expressive.morphing_shapes import AnimateShapeMorph

from .state import state
from .base import TabConfig
from .tabs import (
    IconVariationsTab,
    FontVariationsTab,
    KeyBindingsTab,
    LauncherTab,
    PillDockTab,
    ShapesTab,
    I3Tab,
)
from .tabs.navigation import ShortcutButton

if IS_WAYLAND:
    from fabric.widgets.window import Window
else:
    from fabric.widgets.x11 import X11Window as Window

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib  # type: ignore


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
        if IS_WAYLAND:
            super().__init__(
                title=f"{SHELL_NAME}-settings",
                type="popup",
                visible=True,
                all_visible=True,
            )
        else:
            super().__init__(
                layer="top",
                geometry="center",
                type_hint="normal",
                visible=True,
                sticky=False,
                all_visible=True,
            )

        bind_theme(self)

        self.buttons = {}
        self.stack = None
        self.shapes_box = None
        self.drag_handler = DragHandler(self)
        self.key_bindings_tab = KeyBindingsTab()
        self.tabs = self._register_tabs()

        self._build_ui()
        self._setup_events()

    def set_light_theme(self, enabled: bool) -> None:
        if enabled:
            self.add_style_class("light")
        else:
            self.remove_style_class("light")

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
                TabConfig(
                    "i3wm",
                    ("SwayFX" if is_swayfx() else "Sway") if IS_WAYLAND else "I3",
                    icons.bento.symbol(),
                    lambda: I3Tab().get_widget(),
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
                    lambda: self.key_bindings_tab.get_widget(),
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
        # capture phase: buttons and scales would otherwise keep the click to themselves
        self._outside_click = Gtk.GestureMultiPress.new(self)
        self._outside_click.set_button(0)
        self._outside_click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        self._outside_click.connect("pressed", self._on_window_pressed)

        self.connect("button-press-event", self.drag_handler.on_button_press)
        # self.connect("motion-notify-event", self.drag_handler.on_motion)
        # self.connect("button-release-event", self.drag_handler.on_button_release)
        self.connect("delete-event", self.on_close)

    def _on_window_pressed(self, _gesture, _n_press, x, y):
        """A click outside the focused entry or recording shortcut drops its focus."""
        focus = self.get_focus()
        if isinstance(focus, Gtk.Entry):
            area = focus.get_parent()  # its padding focuses the entry too
        elif isinstance(focus, ShortcutButton) and focus.is_recording:
            area = focus
        else:
            return

        coords = self.translate_coordinates(area, x, y)
        allocation = area.get_allocation()
        inside = (
            coords is not None
            and 0 <= coords[0] < allocation.width
            and 0 <= coords[1] < allocation.height
        )
        if not inside:
            self.set_focus(None)

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
            child=MaterialIconLabel(
                name="close-label",
                style_classes="settings",
                icon_text=icons.close.symbol(),
            ),
            on_clicked=lambda b: self.on_close(None),
        )

        settings_header = MaterialFontLabel(text="Settings", font_size=16)
        header.pack_end(close_button, False, False, 0)
        header.pack_end(settings_header, True, False, 0)

        return header

    def _create_sidebar(self) -> Box:
        switch_box = self._create_tab_switcher()

        shapes_id = "shapes"
        aspect = Gtk.AspectFrame(ratio=1.0, obey_child=False, xalign=0.5, yalign=1.0)
        self.shapes_box = Box(
            h_expand=True,
            v_expand=True,
            children=[AnimateShapeMorph(name="settings-shapes-morph")],
        )
        aspect.add(
            Button(
                name="shapes-box",
                h_expand=True,
                v_expand=True,
                child=self.shapes_box,
                on_clicked=lambda: self.stack.set_visible_child_name(shapes_id),
            )
        )

        self.stack.add_titled(ShapesTab().get_widget(), shapes_id, "expressive-shapes")

        return Box(orientation="v", children=[switch_box, aspect])

    def _create_tab_switcher(self) -> Box:
        switch_box = Box(name="stack-switcher", orientation="v", spacing=2)
        self.stack = Stack(name="settings-stack")
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        for section_name, tabs in self.tabs.items():
            switch_box.pack_start(
                Label(
                    label=section_name,
                    h_align="start",
                    style_classes="section-subheading",
                ),
                False,
                False,
                0,
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

        button = Button(
            style_classes=["settings-option-btn"],
            child=box,
            on_clicked=lambda b: self._on_tab_clicked(tab_config.id),
        )

        self.buttons[tab_config.id] = button

        return button

    def _create_footer(self) -> Box:
        save_btn = add_hover_cursor(
            Button(
                label="Save",
                style_classes=["settings-btn", "bright"],
                on_clicked=self.on_save,
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

    def on_close(self, widget):
        if self.application:
            self.application.quit()
        else:
            self.destroy()

    def _scroll_to_widget(self, widget):
        # centers widget in the page
        def scroll(frame_clock):
            frame_clock.disconnect(handler_id)
            coords = widget.translate_coordinates(self.stack, 0, 0)
            if coords is None:
                return
            adjustment = self.scrollable_window.get_vadjustment()
            margin = (adjustment.get_page_size() - widget.get_allocated_height()) / 2
            adjustment.set_value(coords[1] - margin)

        handler_id = self.get_frame_clock().connect("after-paint", scroll)
        widget.queue_draw()

    def _validate_state_bindings(self):
        conflicts = find_keybinding_conflicts(state.get(["bindings"]) or {})
        if conflicts:
            raise KeybindingValidationError(
                "\n".join(self._describe_conflict(group) for group in conflicts)
            )

    def _describe_conflict(self, group: list[KeyBinding]) -> str:
        scope = group[0].scope
        if scope == "i3":
            scope_label = "Sway" if IS_WAYLAND else "i3"
        else:
            scope_label = scope.capitalize()
        key = format_accel_to_keybind(group[0].key).strip()
        titles = [binding.title for binding in group]
        actions = ", ".join(titles[:-1]) + f" and {titles[-1]}"
        return f"{scope_label}: {key} is used by {actions}"

    def _show_first_conflict(self):
        self.stack.set_visible_child_name("key_bindings")
        row = self.key_bindings_tab.get_first_conflict_row()
        if row:
            self._scroll_to_widget(row)

    def on_save(self, btn):
        try:
            self._validate_state_bindings()
            state.print_all()
            state.save_to_disk()
            state.reset()
            generate_i3_keybinds_config()
            if self.key_bindings_tab.check_wm_conflicts():
                self._show_first_conflict()
                exec_shell_command_async(
                    [
                        "notify-send",
                        "-u",
                        "critical",
                        "Keybinding conflict",
                        (
                            "Settings were saved, but a key is also used by your window "
                            "manager config. Rebind it or remove it from that config."
                        ),
                    ]
                )
                return
            exec_shell_command_async(
                "notify-send 'Zenith Settings' 'Restart zenith-shell to apply changes.'"
            )
            self.on_close(None)

        except KeybindingValidationError as e:
            logger.warning(f"Failed to save: {e}")
            self._show_first_conflict()
            # Passed as argv, and escaped because notification bodies are markup.
            body = GLib.markup_escape_text(f"{e}\nSettings were not saved.")
            exec_shell_command_async(
                ["notify-send", "-u", "critical", "Duplicate keybindings", body]
            )

        except Exception as e:
            logger.error(f"Failed to save: {e}")
            exec_shell_command_async(f"notify-send 'Zenith Settings' '{e}'")
