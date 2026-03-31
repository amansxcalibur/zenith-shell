from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.entry import Entry
from widgets.material_label import MaterialIconLabel

import icons
from ..base import BaseWidget, SectionBuilderMixin, LayoutBuilder
from ..state import state
from config.config import config


class KeyBindingsTab(BaseWidget, SectionBuilderMixin):
    """Display i3 and module keybindings"""

    def _build_ui(self):
        self.container = Box(orientation="v", spacing=25)

        self.entries = {}
        self._overrides = state.get(["bindings", "custom"]) or {}

        self.container.add(
            Label(
                markup="<span weight='bold' foreground='#3584e4'>Note:</span> "
                "<span alpha='70%'>Bindings are not validated. Enter them using valid syntax :)\n"
                "<b>i3 Bindings</b> use i3wm config syntax (e.g. $mod+Shift+m), while <b>Module Bindings</b> use GDK key names (e.g. ISO_Left_Tab).</span>",
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
                    self._create_binding_row,
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
                        self._create_binding_row,
                    ),
                    self.build_section(
                        "Wifi",
                        config.get_all_scoped_bindings("wifi"),
                        self._create_binding_row,
                    ),
                    self.build_section(
                        "Wallpaper",
                        config.get_all_scoped_bindings("wallpaper"),
                        self._create_binding_row,
                    ),
                    self.build_section(
                        "Launcher",
                        config.get_all_scoped_bindings("launcher"),
                        self._create_binding_row,
                    ),
                    self.build_section(
                        "Notifications",
                        config.get_all_scoped_bindings("notifications"),
                        self._create_binding_row,
                    ),
                ],
            )
        )

    def _create_binding_row(self, binding):
        entry = Entry(
            name="settings-entry", style_classes=["settings-value", "roboto-flex"]
        )
        entry.set_text(self._get_binding_key(binding))
        self.entries[binding.action] = entry

        entry.connect(
            "changed", lambda widget: self._on_binding_changed(binding, widget)
        )
        entry.connect(
            "focus-out-event",
            lambda widget, *_: self._on_binding_blur(binding, widget),
        )
        entry.connect("enter-notify-event", self._on_hover_enter)
        entry.connect("leave-notify-event", self._on_hover_leave)

        entry.set_width_chars(0)
        self._update_entry_width(entry)

        return Box(
            style_classes="settings-item",
            spacing=10,
            children=[
                MaterialIconLabel(
                    icon_text=binding.icon or "\ue11f", font_size=17, h_expand=False
                ),
                Label(label=binding.title, h_expand=True, h_align="start"),
                entry,
            ],
        )

    def _on_hover_enter(self, widget: Entry, event):
        widget.add_style_class("hovered-entry")
        return False

    def _on_hover_leave(self, widget: Entry, event):
        widget.remove_style_class("hovered-entry")
        return False

    def _update_entry_width(self, entry):
        layout = entry.get_layout()
        text_width, text_height = layout.get_pixel_size()
        # gotta settle with this for now
        padding = 30
        new_width = text_width + padding

        entry.set_size_request(new_width, -1)

    def _get_binding_key(self, binding):
        return self._overrides.get(binding.action, binding.key)

    def _on_binding_changed(self, binding, widget):
        value = widget.get_text().strip()

        if not value:
            return

        if value == binding.key:
            self._clear_binding_override(binding)
            return

        self._update_entry_width(widget)
        self._set_binding_override(binding, value)

    def _on_binding_blur(self, binding, widget):
        text = widget.get_text().strip()
        if not text:
            widget.set_text(binding.key)
            self._clear_binding_override(binding)

    def _set_binding_override(self, binding, value: str):
        action = binding.action
        self._overrides[action] = value
        print(action)
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
