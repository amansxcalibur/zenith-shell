from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button

from widgets.wrap_box import WrapBox
from widgets.material_label import MaterialIconLabel
from widgets.animated_scale import AnimatedScale

import icons
from utils.cursor import add_hover_cursor
from ..state import state
from ..base import BaseWidget, SectionBuilderMixin, LayoutBuilder

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class I3Tab(BaseWidget, SectionBuilderMixin):
    def __init__(self, **kwargs):
        self.binding_groups = {}
        BaseWidget.__init__(self, **kwargs)

    def _build_ui(self):
        self.container = Box(orientation="v", spacing=25)

        lockscreen_options = [
            {
                "selected": False,
                "icon": icons.explosion.symbol(),
                "text": "zenith-lockscreen (WIP)",
                "value": "zenith",
            },
            {
                "selected": False,
                "icon": icons.editors_choice.symbol(),
                "text": "i3lock",
                "value": "i3lock",
            },
        ]

        lockscreen_selected = state.get(["system", "LOCKSCREEN"])

        for item in lockscreen_options:
            item["selected"] = item["value"] == lockscreen_selected

        self.container.add(
            LayoutBuilder.section(
                "Lockscreen",
                self._create_position_selector("Lockscreen", lockscreen_options),
            )
        )

        self.demo_container = Box(
            name="module-drop-box",
            size=(-1, 400),
            spacing=10,
        )

        self.demo_window_left = Box(
            name="i3-settings-demo-window",
            style_classes=["active"],
            h_expand=True,
            v_expand=True,
        )
        self.demo_window_right_top = Box(
            name="i3-settings-demo-window", h_expand=True, v_expand=True
        )
        self.demo_window_right_bottom = Box(
            name="i3-settings-demo-window", h_expand=True, v_expand=True
        )

        # demo layout
        right_stack = Box(spacing=10, h_expand=True, v_expand=True, orientation="v")
        right_stack.children = [
            self.demo_window_right_top,
            self.demo_window_right_bottom,
        ]
        self.demo_container.children = [self.demo_window_left, right_stack]

        self.all_demo_windows = {
            "active": [self.demo_window_left],
            "inactive": [
                self.demo_window_right_top,
                self.demo_window_right_bottom,
            ],
        }
        
        self.demo_inner_stack = right_stack

        self.container.add(
            LayoutBuilder.section(
                "I3",
                [
                    Box(
                        spacing=30,
                        children=[
                            Box(
                                orientation="v",
                                h_expand=True,
                                spacing=10,
                                children=[
                                    Box(
                                        h_expand=True,
                                        children=[
                                            Label(
                                                label="Borders",
                                                style_classes="section-subheading",
                                                h_align="start",
                                                h_expand=True,
                                            ),
                                            self._create_switch(
                                                state_path=["i3", "borders", "enabled"]
                                            ),
                                        ],
                                    ),
                                    self._create_i3_controls(
                                        "Border Width",
                                        0,
                                        10,
                                        self._on_border_width_changed,
                                        state.get(["i3", "borders", "props", "border_width"]),
                                    ),
                                    Box(
                                        children=[
                                            Label(
                                                label="Matugen",
                                                h_expand=True,
                                                h_align="start",
                                            ),
                                            self._create_switch(
                                                state_path=["i3", "borders", "matugen"]
                                            ),
                                        ]
                                    ),
                                    Box(
                                        children=[
                                            Label(
                                                label="Smart Borders",
                                                h_expand=True,
                                                h_align="start",
                                            ),
                                            self._create_switch(
                                                state_path=[
                                                    "i3",
                                                    "borders",
                                                    "props",
                                                    "smart_borders",
                                                ]
                                            ),
                                        ]
                                    ),
                                ],
                            ),
                            Box(
                                orientation="v",
                                h_expand=True,
                                children=[
                                    Box(
                                        children=[
                                            Label(
                                                label="Gaps",
                                                style_classes="section-subheading",
                                                h_align="start",
                                                h_expand=True,
                                            ),
                                            self._create_switch(
                                                state_path=["i3", "gaps", "enabled"]
                                            ),
                                        ]
                                    ),
                                    self._create_i3_controls(
                                        "Inner",
                                        0,
                                        50,
                                        self._on_inner_gap_changed,
                                        state.get(["i3", "gaps", "props", "inner"]),
                                    ),
                                    self._create_i3_controls(
                                        "Outer",
                                        0,
                                        50,
                                        self._on_outer_gap_changed,
                                        state.get(["i3", "gaps", "props", "outer"]),
                                    ),
                                ],
                            ),
                        ],
                    ),
                    Label(
                        label="Demo",
                        style_classes="section-subheading",
                        h_align="start",
                    ),
                    self.demo_container,
                ],
            )
        )

    def _create_i3_controls(
        self, label: str, min_val: float, max_val: float, callback, initial_val=0
    ):
        value_label = Label(
            label=f"{int(initial_val)}px", style_classes="slider-value-label"
        )

        scale = AnimatedScale(
            name="slider-mui",
            orientation="h",
            h_expand=True,
            increments=(1, 1),
            min_value=min_val,
            max_value=max_val,
            value=initial_val,
        )

        def on_value_changed(s):
            val = int(s.get_value())
            value_label.set_label(f"{val}px")
            callback(s)

        scale.connect("value-changed", on_value_changed)

        callback(scale)

        return Box(
            h_expand=True,
            spacing=10,
            children=[
                Label(label=label, width_request=80, h_align="start"),
                scale,
                value_label,
            ],
        )

    def _create_position_selector(self, group_id: str, positions: list):
        section_box = Box(
            style_classes="settings-section-container", orientation="v", spacing=6
        )
        # section_box.add(
        #     Label(
        #         label="Warning: zenith-lockscreen is still a WIP",
        #         style_classes="section-subheading",
        #         h_align="start",
        #     )
        # )

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

        if group_id == "Lockscreen":
            state.update(["system", "LOCKSCREEN"], val)

    def _on_border_width_changed(self, scale):
        val = int(scale.get_value())
        for window in self.all_demo_windows["active"]:
            window.set_style(f"border: {val}px solid var(--primary);")
        for window in self.all_demo_windows["inactive"]:
            window.set_style(f"border: {val}px solid var(--surface-bright);")

        state.update(["i3", "borders", "props", "border_width"], val)

    def _on_inner_gap_changed(self, scale):
        val = int(scale.get_value())
        self.demo_container.set_spacing(val)
        self.demo_inner_stack.set_spacing(val)
        state.update(["i3", "gaps", "props", "inner"], val)

    def _on_outer_gap_changed(self, scale):
        val = int(scale.get_value())
        self.demo_container.set_style(f"padding: {val}px;")
        state.update(["i3", "gaps", "props", "outer"], val)

    def _on_toggle(self, switch, pspec, path):
        state.update(path, switch.get_active())

    def _create_switch(self, state_path):
        switch = Gtk.Switch(active=state.get(state_path), name="matugen-switcher")
        switch.connect("notify::active", self._on_toggle, state_path)
        return switch
