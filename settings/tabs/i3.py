from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox

from widgets.wrap_box import WrapBox
from widgets.material_label import MaterialIconLabel
from widgets.animated_scale import AnimatedScale

import icons
from config.info import IS_WAYLAND
from config.i3.utils import is_swayfx
from utils.cursor import add_hover_cursor
from utils.helpers import bind_group_toggle
from utils.lock import get_available_external_locker
from ..state import state
from ..base import BaseWidget, SectionBuilderMixin, LayoutBuilder

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore

WM = ("SwayFX" if is_swayfx else "Sway") if IS_WAYLAND else "I3"


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
        ]
        if locker := get_available_external_locker():
            lockscreen_options.append(
                {
                    "selected": False,
                    "icon": icons.editors_choice.symbol(),
                    "text": locker,
                    "value": locker,
                }
            )

        lockscreen_selected = state.get(["system", "LOCKSCREEN"])

        for item in lockscreen_options:
            item["selected"] = item["value"] == lockscreen_selected

        self.container.add(
            LayoutBuilder.section(
                "Lockscreen",
                self._create_position_selector("Lockscreen", lockscreen_options),
            )
        )

        # corners settings
        self.corner_demo = Box(
            name="i3-settings-demo-window",
            style_classes="corner-demo",
        )
        corners_enabled_switch = self._create_switch(
            state_path=[
                "screen_corners",
                "enabled",
            ]
        )
        corner_radius_control = self._create_i3_controls(
            "Corner Radius",
            0,
            50,
            self._on_corner_radius_changed,
            state.get(["screen_corners", "props", "radius"]),
        )
        bind_group_toggle(corners_enabled_switch, [corner_radius_control])
        self.container.add(
            Box(
                h_expand=True,
                spacing=30,
                children=[
                    LayoutBuilder.section(
                        "Screen Corner",
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
                                                        label="Enable",
                                                        style_classes="section-subheading",
                                                        h_align="start",
                                                        h_expand=True,
                                                    ),
                                                    corners_enabled_switch,
                                                ],
                                            ),
                                            corner_radius_control,
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    )
                    .build()
                    .set_hexpand(True)
                    .unwrap(),
                    self.corner_demo,
                ],
            )
        )

        self.demo_container = Box(name="module-drop-box", size=(-1, 400), spacing=10)

        self.demo_window_left = self._create_demo_window(is_active=True)
        self.demo_window_right_top = self._create_demo_window(is_active=False)
        self.demo_window_right_bottom = self._create_demo_window(is_active=False)

        self.demo_inner_stack = Box(
            spacing=10, h_expand=True, v_expand=True, orientation="v"
        )
        self.demo_inner_stack.children = [
            self.demo_window_right_top,
            self.demo_window_right_bottom,
        ]

        self.demo_container.children = [self.demo_window_left, self.demo_inner_stack]

        self.all_windows_list = [
            self.demo_window_left,
            self.demo_window_right_top,
            self.demo_window_right_bottom,
        ]

        # border settings
        borders_enabled_switch = self._create_switch(
            state_path=["i3", "borders", "enabled"]
        )
        border_theme_row = Box(
            children=[
                Label(
                    label="Theme sync",
                    h_expand=True,
                    h_align="start",
                ),
                self._create_switch(state_path=["i3", "borders", "matugen"]),
            ]
        )
        border_smart_row = Box(
            children=[
                Label(
                    label="Smart Borders",
                    h_expand=True,
                    h_align="start",
                ),
                self._create_switch(
                    state_path=["i3", "borders", "props", "smart_borders"]
                ),
            ]
        )
        border_width_control = self._create_i3_controls(
            "Border Width",
            0,
            10,
            self._on_border_width_changed,
            state.get(["i3", "borders", "props", "border_width"]),
        )
        border_radius_control = (
            self._create_i3_controls(
                "Corner Radius",
                0,
                50,
                None,
                state.get(["i3", "borders", "props", "corner_radius"]),
            )
            if is_swayfx()
            else None
        )

        bind_group_toggle(
            borders_enabled_switch,
            [
                w
                for w in [
                    border_width_control,
                    border_theme_row,
                    border_smart_row,
                    border_radius_control,
                ]
                if w is not None
            ],
        )

        # gaps settings
        gaps_enabled_switch = self._create_switch(state_path=["i3", "gaps", "enabled"])
        inner_gap_control = self._create_i3_controls(
            "Inner",
            0,
            50,
            self._on_inner_gap_changed,
            state.get(["i3", "gaps", "props", "inner"]),
        )
        outer_gap_control = self._create_i3_controls(
            "Outer",
            0,
            50,
            self._on_outer_gap_changed,
            state.get(["i3", "gaps", "props", "outer"]),
        )

        bind_group_toggle(gaps_enabled_switch, [inner_gap_control, outer_gap_control])

        self.container.add(
            LayoutBuilder.section(
                WM,
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
                                        orientation="v",
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
                                                    borders_enabled_switch,
                                                ],
                                            ),
                                            border_width_control,
                                            *(
                                                [border_radius_control]
                                                if border_radius_control
                                                else []
                                            ),
                                        ],
                                    ),
                                    border_theme_row,
                                    border_smart_row,
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
                                            gaps_enabled_switch,
                                        ]
                                    ),
                                    inner_gap_control,
                                    outer_gap_control,
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
        self,
        label: str,
        min_val: float,
        max_val: float,
        callback: callable = None,  # noqa: RUF013
        initial_val=30,
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
            if callback is not None and scale.get_mapped():
                callback(s)

        scale.connect("value-changed", on_value_changed)
        if callback is not None:
            scale.connect("map", lambda: callback(scale))

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

    def _on_inner_gap_changed(self, scale):
        val = int(scale.get_value())
        self.demo_container.set_spacing(val)
        self.demo_inner_stack.set_spacing(val)
        state.update(["i3", "gaps", "props", "inner"], val)

    def _on_outer_gap_changed(self, scale):
        val = int(scale.get_value())
        self.demo_container.set_style(f"padding: {val}px;")
        state.update(["i3", "gaps", "props", "outer"], val)

    def _on_border_width_changed(self, scale):
        val = int(scale.get_value())

        for window in self.all_windows_list:
            color = (
                "var(--primary)"
                if "active" in window.get_style_context().list_classes()
                else "var(--surface-bright)"
            )
            window.get_children()[0].set_style(f"border: {val}px solid {color};")

        state.update(["i3", "borders", "props", "border_width"], val)

    def _on_corner_radius_changed(self, scale):
        val = int(scale.get_value())
        self.corner_demo.set_style(f"border-radius: {val}px")
        state.update(["screen_corners", "props", "radius"], val)

    def _create_demo_window(self, is_active=False):
        window = Box(
            name="i3-settings-demo-window",
            style_classes=["active"] if is_active else [],
            h_expand=True,
            v_expand=True,
        )

        event_box = EventBox(
            child=window,
            h_expand=True,
            v_expand=True,
        )

        event_box.connect(
            "enter-notify-event", lambda *_: self._set_window_active(window)
        )
        event_box.connect(
            "leave-notify-event", lambda *_: self._set_window_active(window, False)
        )

        return event_box

    def _set_window_active(self, target_window, active: bool = True):
        border_width = state.get(["i3", "borders", "props", "border_width"])

        if active:
            target_window.add_style_class("active")
            target_window.set_style(f"border: {border_width}px solid var(--primary);")
        else:
            target_window.remove_style_class("active")
            target_window.set_style(
                f"border: {border_width}px solid var(--surface-bright);"
            )

    def _on_toggle(self, switch, pspec, path):
        state.update(path, switch.get_active())

    def _create_switch(self, state_path):
        switch = Gtk.Switch(active=state.get(state_path), name="matugen-switcher")
        switch.connect("notify::active", self._on_toggle, state_path)
        return switch
