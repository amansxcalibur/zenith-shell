from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.revealer import Revealer
from fabric.utils.helpers import exec_shell_command_async

import icons
from config.info import SHELL_NAME
from utils.cursor import add_hover_cursor
from widgets.clipping_box import ClippingBox, TrueClippingBox
from widgets.material_label import MaterialIconLabel

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class TileSimple(ClippingBox):
    def __init__(
        self,
        markup: str = icons.blur.symbol(),
        label: str = "__",
        status_label_widget: Label = Label(
            style_classes="tile-label", label="N/A", h_align="start"
        ),
        **kwargs,
    ):
        default_classes = ["tile", "simple", "off"]
        extra_classes = kwargs.pop("style_classes", [])
        merged_classes = default_classes + extra_classes
        markup_styles = kwargs.pop("markup_style", "")
        super().__init__(style_classes=merged_classes, v_align="start", **kwargs)

        self.state = False
        self.props = status_label_widget
        self.status_label_widget_revealer = Revealer(
            transition_duration=250, transition_type="slide-down", child=self.props
        )

        self.icon = MaterialIconLabel(
            style_classes="tile-icon",
            icon_text=markup,
            style=markup_styles,
            v_align="center",
        )
        self.icon_wrapper = Box(
            style_classes="tile-icon-box",
            children=self.icon,
        )
        self.tile_label = Label(
            style_classes="tile-label", label=label, h_align="start"
        )
        self.toggle = False

        self.type_box = Box(
            style_classes="tile-type",
            h_expand=True,
            children=Box(
                orientation="v",
                v_expand=True,
                h_expand=True,
                v_align="center",
                children=[self.tile_label, self.status_label_widget_revealer],
            ),
        )

        self.content_revealer = Revealer(
            transition_duration=150,
            transition_type="slide-left",
            child=Box(h_expand=True, children=[self.type_box]),
            child_revealed=True,
            h_expand=True,
        )

        self.normal_view = TrueClippingBox(
            style_classes="tile-clipper",
            max_width=164,
            children=Box(
                children=[
                    self.icon_wrapper,
                    self.content_revealer,
                ]
            ),
        )
        box_shadow_overlay = Box(style_classes="tile-overlay")
        self.overlay = Overlay(
            h_expand=True,
            child=self.normal_view,
            overlays=box_shadow_overlay,
        )
        self.overlay.set_overlay_pass_through(box_shadow_overlay, True)
        self.children = add_hover_cursor(
            Button(
                h_expand=True,
                child=self.overlay,
                on_clicked=self.handle_state_toggle,
            )
        )

        add_hover_cursor(self.type_box)

    def set_active_style(self, is_active: bool):
        if is_active:
            self.add_style_class("on")
            self.remove_style_class("off")
        else:
            self.add_style_class("off")
            self.add_style_class("on")

    def handle_state_toggle(self, *_):
        # overriden
        self.state = not self.state

    def close(self):
        self.toggle = False
        self.maxi_view()

    def mini_view(self):
        self.content_revealer.set_reveal_child(False)
        self.icon_wrapper.set_h_expand(True)
        self.content_revealer.set_h_expand(False)
        self.add_style_class("mini")
        # self.icon.add_style_class("mini")
        # self.icon.remove_style_class("maxi")

    def maxi_view(self):
        self.content_revealer.set_reveal_child(True)
        self.icon_wrapper.set_h_expand(False)
        self.content_revealer.set_h_expand(True)
        self.remove_style_class("mini")
        # self.icon.add_style_class("maxi")
        # self.icon.remove_style_class("mini")

    def hide_status_widget(self):
        self.status_label_widget_revealer.unreveal()

    def reveal_status_widget(self):
        self.status_label_widget_revealer.reveal()


class TileSimpleWithMenu(ClippingBox):
    def __init__(
        self,
        markup: str = icons.blur.symbol(),
        label: str = "__",
        title: str = "",
        status_label_widget: Label = Label(
            style_classes="tile-label", label="N/A", h_align="start"
        ),
        menu_children: Gtk.Widget = None,
        **kwargs,
    ):
        default_classes = ["tile", "simple", "off"]
        extra_classes = kwargs.pop("style_classes", [])
        merged_classes = default_classes + extra_classes
        markup_styles = kwargs.pop("markup_style", "")
        super().__init__(style_classes=merged_classes, v_align="start", **kwargs)

        self.state = False
        self.props = status_label_widget
        self.status_label_widget_revealer = Revealer(
            transition_duration=250, transition_type="slide-up", child=self.props
        )
        self.toggle = False

        self.icon = MaterialIconLabel(
            style_classes="tile-icon",
            icon_text=markup,
            style=markup_styles,
            v_align="center",
        )
        self.icon_wrapper = Box(
            style_classes="tile-icon-box",
            children=self.icon,
        )

        self.tile_label = Label(
            style_classes="tile-label", label=label, h_align="start"
        )

        self.type_box = Box(
            style_classes="tile-type",
            h_expand=True,
            children=Box(
                orientation="v",
                v_expand=True,
                h_expand=True,
                v_align="center",
                children=[self.tile_label, self.status_label_widget_revealer],
            ),
        )

        self.content_revealer = Revealer(
            transition_duration=150,
            transition_type="slide-left",
            child=Box(h_expand=True, children=[self.type_box]),
            child_revealed=True,
            h_expand=True,
        )

        self.normal_view = TrueClippingBox(
            style_classes="tile-clipper",
            max_width=164,
            children=Button(
                h_expand=True,
                on_clicked=self.handle_menu_click,
                child=Box(
                    children=[
                        self.icon_wrapper,
                        self.content_revealer,
                    ]
                ),
            ),
        )
        box_shadow_overlay = Box(style_classes="tile-overlay")
        self.overlay = Overlay(
            h_expand=True,
            child=self.normal_view,
            overlays=box_shadow_overlay,
        )
        self.overlay.set_overlay_pass_through(box_shadow_overlay, True)

        self.menu_close_btn = Button(
            name="menu-close-button",
            child=MaterialIconLabel(
                name="close-label",
                style_classes="settings",
                icon_text=icons.close.symbol(),
            ),
            tooltip_text="Exit",
            on_clicked=self.handle_menu_click,
        )

        self.menu = Box(
            style_classes="tile-menu",
            orientation="v",
            children=(
                [
                    Box(
                        name="menu-header",
                        children=[
                            Label(
                                name="menu-title",
                                label=title if title != "" else label,
                                h_expand=True,
                            ),
                            self.menu_close_btn,
                        ],
                    ),
                ]
                + (
                    [menu_children]
                    if menu_children
                    else [Label(label="No options available")]
                )
            ),
        )

        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            h_expand=True,
            children=[self.overlay, self.menu],
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.children = self.stack

        # cursors
        add_hover_cursor(self.stack)
        add_hover_cursor(self.type_box)
        add_hover_cursor(self.menu_close_btn)

    def handle_menu_click(self, *_):
        if self.toggle:
            self.toggle = False
            self.menu.add_style_class("contract")
            self.menu.remove_style_class("expand")
            self.stack.set_visible_child(self.overlay)
        else:
            self.toggle = True
            self.stack.set_visible_child(self.menu)
            self.menu.add_style_class("expand")
            self.menu.remove_style_class("contract")

        name = self.get_name()
        if name:
            exec_shell_command_async(
                f"fabric-cli exec {SHELL_NAME} \"pill.dashboard.handle_tile_menu_expand('{name}', {self.toggle})\""
            )

    def set_active_style(self, is_active: bool):
        if is_active:
            self.add_style_class("on")
            self.remove_style_class("off")
        else:
            self.add_style_class("off")
            self.remove_style_class("on")

    def close(self):
        self.toggle = False
        self.menu.add_style_class("contract")
        self.menu.remove_style_class("expand")
        self.stack.set_visible_child(self.overlay)
        self.maxi_view()

    def mini_view(self):
        self.content_revealer.set_reveal_child(False)
        self.icon_wrapper.set_h_expand(True)
        self.content_revealer.set_h_expand(False)
        self.add_style_class("mini")

    def maxi_view(self):
        self.content_revealer.set_reveal_child(True)
        self.icon_wrapper.set_h_expand(False)
        self.content_revealer.set_h_expand(True)
        self.remove_style_class("mini")

    def hide_status_widget(self):
        self.status_label_widget_revealer.unreveal()

    def reveal_status_widget(self):
        self.status_label_widget_revealer.reveal()


class Tile(ClippingBox):
    def __init__(
        self,
        title: str = "",
        markup: str = icons.blur.symbol(),
        label: str = "__",
        menu_children=None,
        props: Label = None,
        on_toggle: callable = None,
        **kwargs,
    ):
        default_classes = ["tile", "off"]
        extra_classes = kwargs.pop("style_classes", [])
        merged_classes = default_classes + extra_classes
        markup_styles = kwargs.pop("markup_style", "")
        super().__init__(style_classes=merged_classes, v_align="start", **kwargs)

        self._on_toggle = on_toggle
        self.state = False
        self.toggle = False  # menu state
        self.props = (
            props
            if props
            else Label(style_classes="tile-label", label="N/A", h_align="start")
        )
        self.status_label_widget_revealer = Revealer(
            transition_duration=250, transition_type="slide-up", child=self.props
        )

        self.icon = MaterialIconLabel(
            style_classes="tile-icon", icon_text=markup, style=markup_styles
        )
        self.icon_wrapper = Button(
            style_classes="tile-icon-btn",
            on_clicked=self.handle_state_toggle,
            child=self.icon,
        )

        self.tile_label = Label(
            style_classes="tile-label", label=label, h_align="start"
        )

        self.type_box = Button(
            on_clicked=self.handle_menu_click,
            style_classes="tile-type",
            h_expand=True,
            child=Box(
                orientation="v",
                v_expand=True,
                h_expand=True,
                v_align="center",
                children=[self.tile_label, self.status_label_widget_revealer],
            ),
        )

        self.content_button = Revealer(
            transition_duration=150,
            transition_type="slide-left",
            child=Box(h_expand=True, children=[self.type_box]),
            child_revealed=True,
            h_expand=True,
        )

        self.normal_view = TrueClippingBox(
            style_classes="tile-clipper",
            max_width=164,
            children=[
                self.icon_wrapper,
                self.content_button,
            ],
        )
        box_shadow_overlay = Box(style_classes="tile-overlay")
        self.overlay = Overlay(
            h_expand=True,
            child=self.normal_view,
            overlays=box_shadow_overlay,
        )
        self.overlay.set_overlay_pass_through(box_shadow_overlay, True)

        self.menu_close_btn = Button(
            name="menu-close-button",
            child=MaterialIconLabel(
                name="close-label",
                style_classes="settings",
                icon_text=icons.close.symbol(),
            ),
            tooltip_text="Exit",
            on_clicked=self.handle_menu_click,
        )

        self.menu_box = Box(
            style_classes="tile-menu",
            orientation="v",
            children=(
                [
                    Box(
                        name="menu-header",
                        children=[
                            Label(
                                name="menu-title",
                                label=title if title != "" else label,
                                h_expand=True,
                            ),
                            self.menu_close_btn,
                        ],
                    ),
                ]
                + ([menu_children] if menu_children else [Label(label="Options")])
            ),
        )

        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            h_expand=True,
            children=[self.overlay, self.menu_box],
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.children = self.stack

        # cursors
        add_hover_cursor(self.icon_wrapper)
        add_hover_cursor(self.type_box)
        add_hover_cursor(self.menu_close_btn)

    def handle_state_toggle(self, *_):
        self.state = not self.state
        if self.state:
            self.add_style_class("on")
            self.remove_style_class("off")
        else:
            self.add_style_class("off")
            self.remove_style_class("on")

        self._on_toggle()

    def handle_menu_click(self, *_):
        if self.toggle:
            self.toggle = False
            self.menu_box.add_style_class("contract")
            self.menu_box.remove_style_class("expand")
            self.stack.set_visible_child(self.overlay)
        else:
            self.toggle = True
            self.stack.set_visible_child(self.menu_box)
            self.menu_box.add_style_class("expand")
            self.menu_box.remove_style_class("contract")

        name = self.get_name()
        if name:
            exec_shell_command_async(
                f"fabric-cli exec {SHELL_NAME} \"pill.dashboard.handle_tile_menu_expand('{name}', {self.toggle})\""
            )

    def close(self):
        self.toggle = False
        self.stack.set_visible_child(self.overlay)
        self.maxi_view()

    def mini_view(self):
        self.content_button.set_reveal_child(False)
        self.icon_wrapper.set_h_expand(True)
        self.content_button.set_h_expand(False)
        self.add_style_class("mini")

    def maxi_view(self):
        self.content_button.set_reveal_child(True)
        self.icon_wrapper.set_h_expand(False)
        self.content_button.set_h_expand(True)
        self.remove_style_class("mini")

    def hide_status_widget(self):
        self.status_label_widget_revealer.unreveal()

    def reveal_status_widget(self):
        self.status_label_widget_revealer.reveal()


class TileSpecial(Box):
    def __init__(self, *, mini_props, props, **kwargs):
        super().__init__(**kwargs)
        self.props = props
        self.mini_props = mini_props
        self.toggle = False

        self.content_button = None

        self.normal_view = Box(
            children=self.props,
        )
        self.collapsed_view = Box(children=self.mini_props)

        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            h_expand=True,
            v_align="start",
            children=[self.normal_view, self.collapsed_view],
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.children = self.stack

    def mini_view(self):
        self.stack.set_visible_child(self.collapsed_view)

    def maxi_view(self):
        self.stack.set_visible_child(self.normal_view)

    def close(self):
        self.maxi_view()
