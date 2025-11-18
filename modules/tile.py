from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer

import icons
import config.info as info
from utils.cursor import add_hover_cursor
from widgets.clipping_box import ClippingBox

from fabric.utils.helpers import exec_shell_command_async


class Tile(ClippingBox):
    def __init__(
        self,
        title: str = "",
        menu: bool = False,
        markup: str = icons.blur,
        label: str = "__",
        menu_children=None,
        props: Label = Label(style_classes="tile-label", label="N/A", h_align="start"),
        **kwargs,
    ):
        default_classes = ["tile", "off"]
        extra_classes = kwargs.pop("style_classes", [])
        merged_classes = default_classes + extra_classes
        markup_styles = kwargs.pop("markup_style", "")
        super().__init__(style_classes=merged_classes, v_align="start", **kwargs)

        self.state = False
        self.props = props

        self.icon = Label(style_classes="tile-icon", markup=markup, style=markup_styles)
        self.icon_wrapper = Button(
            style="all:unset;",
            on_clicked=self.handle_state_toggle,
            child=self.icon,
        )
        self.tile_label = Label(
            style_classes="tile-label", label=label, h_align="start"
        )
        self.toggle = False

        self.type_box = Button(
            style="all:unset;",
            on_clicked=self.handle_state_toggle,
            style_classes="tile-type",
            h_expand=True,
            child=Box(
                orientation="v",
                v_expand=True,
                h_expand=True,
                v_align="center",
                children=[self.tile_label, self.props],
            ),
        )

        self.menu_button = Button(
            style_classes="tile-button",
            child=Label(
                name="menu-btn", style_classes="tile-icon", markup=icons.arrow_forward
            ),
            on_clicked=self.handle_menu_click,
        )

        self.content_button = None

        if menu:
            self.content_button = Revealer(
                transition_duration=150,
                transition_type="slide-left",
                child=Box(h_expand=True, children=[self.type_box, self.menu_button]),
                child_revealed=True,
                h_expand=True,
            )
        else:
            self.content_button = Revealer(
                transition_duration=150,
                transition_type="slide-left",
                child=Box(h_expand=True, children=[self.type_box]),
                child_revealed=True,
                h_expand=True,
            )

        self.normal_view = Box(
            children=[
                self.icon_wrapper,
                self.content_button,
            ],
        )

        self.menu_close_btn = Button(
            name="menu-close-button",
            child=Label(name="close-label", markup=icons.cancel),
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
                                label=title if title is not "" else label,
                                h_expand=True,
                            ),
                            self.menu_close_btn,
                        ],
                    ),
                ]
                + ([menu_children] if menu_children else [Label(label="hi!")])
            ),
        )

        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            h_expand=True,
            children=[self.normal_view, self.menu],
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)

        self.children = self.stack

        add_hover_cursor(self.menu)
        add_hover_cursor(self.type_box)
        add_hover_cursor(self.menu_button)
        add_hover_cursor(self.icon_wrapper)

    def handle_state_toggle(self, *_):
        self.state = not self.state

    def handle_menu_click(self, source):
        if self.toggle:
            self.toggle = False
            self.menu.add_style_class("contract")
            self.menu.remove_style_class("expand")
            self.stack.set_visible_child(self.normal_view)
        else:
            self.toggle = True
            self.stack.set_visible_child(self.menu)
            self.menu.add_style_class("expand")
            self.menu.remove_style_class("contract")
        print(self.toggle, self.get_name())
        name = self.get_name()
        exec_shell_command_async(
            f"fabric-cli exec {info.SHELL_NAME} \"pill.dashboard.handle_tile_menu_expand('{name}', {self.toggle})\""
        )

    def mini_view(self):
        self.content_button.set_reveal_child(False)
        self.icon_wrapper.set_h_expand(True)
        self.content_button.set_h_expand(False)
        self.add_style_class("mini")
        self.icon.add_style_class("mini")
        self.icon.remove_style_class("maxi")

    def maxi_view(self):
        self.content_button.set_reveal_child(True)
        self.icon_wrapper.set_h_expand(False)
        self.content_button.set_h_expand(True)
        self.remove_style_class("mini")
        self.icon.add_style_class("maxi")
        self.icon.remove_style_class("mini")


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
