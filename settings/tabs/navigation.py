from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.entry import Entry
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.core.service import Service, Signal

from widgets.material_label import MaterialIconLabel
from utils.helpers import format_accel_to_keybind

import icons
from ..base import BaseWidget, SectionBuilderMixin, LayoutBuilder
from ..state import state
from config.config import config

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk


class KeyBindingsTab(BaseWidget, SectionBuilderMixin):
    """Display i3 and module keybindings"""

    def _build_ui(self):
        self.container = Box(orientation="v", spacing=25)

        self.entries = {}
        self._overrides = state.get(["bindings", "custom"]) or {}

        self.container.add(
            Label(
                markup="<span weight='bold' foreground='#3584e4'>Note:</span> "
                "<span alpha='70%'>i3 Bindings are not validated. Enter them using valid i3wm config syntax :)</span>",
                line_wrap="word",
                h_align="start",
            )
        )

        self.container.add(
            LayoutBuilder.section(
                "i3 Bindings",
                self.build_section(
                    None,
                    config.get_all_scoped_bindings("i3"),
                    self._create_entry_binding_row,
                ),
            )
        )

        self.container.add(
            LayoutBuilder.section(
                "Module Bindings",
                [
                    self.build_section(
                        "Player",
                        config.get_all_scoped_bindings("player"),
                        self._create_btn_binding_row,
                    ),
                    self.build_section(
                        "Wifi",
                        config.get_all_scoped_bindings("wifi"),
                        self._create_btn_binding_row,
                    ),
                    self.build_section(
                        "Wallpaper",
                        config.get_all_scoped_bindings("wallpaper"),
                        self._create_btn_binding_row,
                    ),
                    self.build_section(
                        "Launcher",
                        config.get_all_scoped_bindings("launcher"),
                        self._create_btn_binding_row,
                    ),
                    self.build_section(
                        "Notifications",
                        config.get_all_scoped_bindings("notifications"),
                        self._create_btn_binding_row,
                    ),
                ],
            )
        )

    def _create_entry_binding_row(self, binding):
        entry = Entry(
            name="settings-entry", style_classes=["roboto-flex"], h_expand=True
        )
        entry.set_text(self._get_binding_key(binding))
        entry.set_width_chars(0)
        entry.set_can_focus(True)
        self.entries[binding.action] = entry

        self._update_entry_width(entry)

        value_box = Box(
            name="settings-entry-container",
            style_classes="settings-value",
            children=entry,
        )
        value_box.set_can_focus(False)

        event_box = EventBox(
            child=value_box, events=["button-press", "enter-notify", "leave-notify"]
        )
        event_box.set_can_focus(False)

        entry.connect("changed", lambda w: self._on_entry_binding_changed(binding, w))
        entry.connect(
            "focus-out-event", lambda w, *_: self._on_binding_blur(binding, w)
        )
        event_box.connect(
            "button-press-event",
            lambda *_: (entry.grab_focus(), entry.set_position(-1)),
        )
        event_box.connect("enter-notify-event", self._handle_hover, value_box, True)
        event_box.connect("leave-notify-event", self._handle_hover, value_box, False)

        return Box(
            style_classes="settings-item",
            spacing=10,
            children=[
                MaterialIconLabel(
                    icon_text=binding.icon or "\ue11f", font_size=17, h_expand=False
                ),
                Label(label=binding.title, h_expand=True, h_align="start"),
                event_box,
            ],
        )

    def _create_btn_binding_row(self, binding):
        binding_btn = ShortcutButton(
            shortcut_id=binding.action,
            name="settings-entry-container",
            style_classes=["roboto-flex", "settings-value"],
            label=format_accel_to_keybind(self._get_binding_key(binding)),
        )
        binding_btn.connect(
            "binding-changed",
            lambda btn, new_binding: self._on_binding_changed(binding, new_binding),
        )

        return Box(
            style_classes="settings-item",
            spacing=10,
            children=[
                MaterialIconLabel(
                    icon_text=binding.icon or "\ue11f", font_size=17, h_expand=False
                ),
                Label(label=binding.title, h_expand=True, h_align="start"),
                binding_btn,
            ],
        )

    def _handle_hover(self, widget, event, target: Entry, is_enter):
        if event.detail != Gdk.NotifyType.INFERIOR:
            if is_enter:
                target.add_style_class("hovered-entry")
            else:
                target.remove_style_class("hovered-entry")
        return False

    def _update_entry_width(self, entry):
        layout = entry.get_layout()
        text_width, text_height = layout.get_pixel_size()
        # padding for entry cursor
        padding = 1
        new_width = text_width + padding

        entry.set_size_request(new_width, -1)

    def _get_binding_key(self, binding):
        return self._overrides.get(binding.action, binding.key)

    def _on_entry_binding_changed(self, binding, widget: Entry):
        self._on_binding_changed(binding, widget.get_text().strip())
        self._update_entry_width(widget)

    def _on_binding_changed(self, binding, value: str):
        if not value:
            return

        if value == binding.key:
            self._clear_binding_override(binding)
            return

        self._set_binding_override(binding, value)

    def _on_binding_blur(self, binding, widget):
        text = widget.get_text().strip()
        if not text:
            # reset binding
            widget.set_text(binding.key)
            self._update_entry_width(widget)
            self._clear_binding_override(binding)

    def _set_binding_override(self, binding, value: str):
        action = binding.action
        self._overrides[action] = value

        if binding.scope == "i3":
            state.update(["bindings", "i3", action], value)
        else:
            state.update(["bindings", "modules", binding.scope, action], value)

    def _clear_binding_override(self, binding):
        self._overrides.pop(binding.action, None)


class LauncherTab(BaseWidget, SectionBuilderMixin):
    """Display launcher integrated modules"""

    def _build_ui(self):
        self.container = Box(orientation="v", spacing=25)

        modules = [
            {"module": "Dashboard", "text": ":d", "icon": icons.dashboard.symbol()},
            {"module": "Wallpaper", "text": ":w", "icon": icons.wallpaper.symbol()},
            {"module": "Player", "text": ":u", "icon": icons.disc.symbol()},
            {"module": "Power", "text": ":p", "icon": icons.power.symbol()},
            {
                "module": "Zenith Settings",
                "text": ":s",
                "icon": icons.settings.symbol(),
            },
        ]

        self.container.add(
            LayoutBuilder.section(
                "Launcher Integrated Modules",
                self.build_section(None, modules, self._create_binding_row),
            )
        )

    def _create_binding_row(self, binding):
        return Box(
            style_classes="settings-item",
            spacing=10,
            children=[
                MaterialIconLabel(
                    icon_text=binding["icon"] or "\ue11f", font_size=17, h_expand=False
                ),
                Label(label=binding["module"], h_expand=True, h_align="start"),
                Label(label=binding["text"], style_classes="settings-value"),
            ],
        )


class ShortcutButton(Button, Service):
    MODIFIER_KEYVALS = {
        # Standard
        Gdk.KEY_Shift_L,
        Gdk.KEY_Shift_R,
        Gdk.KEY_Control_L,
        Gdk.KEY_Control_R,
        Gdk.KEY_Alt_L,
        Gdk.KEY_Alt_R,
        Gdk.KEY_Meta_L,
        Gdk.KEY_Meta_R,
        Gdk.KEY_Super_L,
        Gdk.KEY_Super_R,
        Gdk.KEY_Hyper_L,
        Gdk.KEY_Hyper_R,
        Gdk.KEY_Caps_Lock,
        Gdk.KEY_Shift_Lock,
        Gdk.KEY_Num_Lock,
        Gdk.KEY_Scroll_Lock,
        Gdk.KEY_Mode_switch,
        # ISO / international keyboards (AltGr etc.)
        Gdk.KEY_ISO_Level3_Shift,
        Gdk.KEY_ISO_Level3_Latch,
        Gdk.KEY_ISO_Level3_Lock,
        Gdk.KEY_ISO_Level5_Shift,
        Gdk.KEY_ISO_Level5_Latch,
        Gdk.KEY_ISO_Level5_Lock,
        Gdk.KEY_ISO_Group_Shift,
        Gdk.KEY_ISO_Group_Latch,
        Gdk.KEY_ISO_Group_Lock,
        Gdk.KEY_ISO_Next_Group,
        Gdk.KEY_ISO_Prev_Group,
    }

    @Signal
    def binding_changed(self, binding: str) -> None: ...

    def __init__(self, shortcut_id, **args):
        super().__init__(**args)
        self.shortcut_id = shortcut_id
        self.is_recording = False
        self.binding_string = self.get_label()

        self.connect("clicked", self._on_clicked)

    def _on_clicked(self, btn):
        if not self.is_recording:
            self.start_recording()

    def start_recording(self):
        self.is_recording = True
        self.set_label("Press shortcut")

        self.grab_focus()

        window = self.get_toplevel()
        self.handler_id = window.connect("key-press-event", self._on_key_press)
        self.focus_out_id = self.connect("focus-out-event", self._on_focus_out)

    def _on_key_press(self, widget, event):
        keyval = event.keyval
        modifiers = event.state & Gtk.accelerator_get_default_mod_mask()

        if keyval in self.MODIFIER_KEYVALS:
            return True

        # Fallback: if modifiers is 0 and the key produced no usable
        # accelerator, it's likely an unrecognised modifier. Keep waiting
        accel_name = Gtk.accelerator_name(keyval, modifiers)
        if not accel_name and not modifiers:
            return True

        if not accel_name:
            accel_name = Gdk.keyval_name(keyval)

        display_name = format_accel_to_keybind(accel_name)

        self.set_label(display_name)
        self.stop_recording(accel_name)
        logger.info(f"Saved setting [{self.shortcut_id}]: {accel_name}")
        return True

    def stop_recording(self, binding):
        self.is_recording = False
        window = self.get_toplevel()
        window.disconnect(self.handler_id)
        self.binding_string = binding
        self.binding_changed(binding)

    def _on_focus_out(self, widget, event):
        self.is_recording = False
        window = self.get_toplevel()
        window.disconnect(self.handler_id)
        self.disconnect(self.focus_out_id)
        self.set_label(self.binding_string)
        return False