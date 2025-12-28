from fabric.widgets.box import Box
from fabric.widgets.label import Label
from widgets.material_label import MaterialIconLabel

import icons
from ..base import BaseWidget, SectionBuilderMixin, LayoutBuilder


class KeyBindingsTab(BaseWidget, SectionBuilderMixin):
    """Display i3 and module keybindings"""

    def _build_ui(self):
        from config.i3_config import (
            I3_KEYBINDINGS,
            PLAYER_KEYBINDINGS,
            WIFI_KEYBINDINGS,
        )

        self.container = Box(orientation="v", spacing=25)

        self.container.add(
            LayoutBuilder.section(
                "i3 Bindings",
                self.build_section(None, I3_KEYBINDINGS, self._create_binding_row),
            )
        )

        self.container.add(
            LayoutBuilder.section(
                "Module Bindings",
                [
                    self.build_section(
                        "Player", PLAYER_KEYBINDINGS, self._create_binding_row
                    ),
                    self.build_section(
                        "Wifi", WIFI_KEYBINDINGS, self._create_binding_row
                    ),
                ],
            )
        )

    def _create_binding_row(self, binding):
        return Box(
            style_classes="settings-item",
            spacing=10,
            children=[
                MaterialIconLabel(
                    icon_text=binding.icon or "\ue11f", font_size=17, h_expand=False
                ),
                Label(label=binding.title, h_expand=True, h_align="start"),
                Label(label=binding.key, style_classes="settings-value"),
            ],
        )


class LauncherTab(BaseWidget, SectionBuilderMixin):
    """Display launcher integrated modules"""

    def _build_ui(self):
        self.container = Box(orientation="v", spacing=25)

        modules = [
            {"module": "Dashboard", "text": ":d", "icon": icons.dashboard.symbol()},
            {"module": "Wallpaper", "text": ":w", "icon": icons.wallpaper.symbol()},
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
