from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer
from fabric.widgets.centerbox import CenterBox

from modules.network import Network
from modules.tile import TileSpecial, Tile
from modules.bluetooth import Bluetooth
from modules.wavy_clock import WavyClock
from modules.notification import NotificationTile
from modules.player_mini import PlayerContainerMini
from modules.weather import WeatherPill

import icons
from config.info import config
from utils.cursor import add_hover_cursor

from loguru import logger


class Dashboard(Box):
    def __init__(self, controls, **kwargs):
        super().__init__(
            name="dashboard",
            visible=True,
            orientation="v",
            spacing=8,
            all_visible=True,
            **kwargs,
        )
        self.wifi = Network()
        self.bluetooth = Bluetooth()
        self.mini_player = PlayerContainerMini()
        self.silent = NotificationTile()
        self.mini_player_tile = TileSpecial(
            props=self.mini_player, mini_props=self.mini_player.get_mini_view()
        )

        self.controls = controls
        self.brightness_revealer_mui = self.controls.get_brightness_slider_mui()

        self.wavy_clock = CenterBox(
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            center_children=WavyClock(dark=False),
        )
        self.weather_pill = CenterBox(
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            center_children=WeatherPill(dark=False),
        )
        self.widget_stack = Stack(
            name="widget-stack",
            transition_type="crossfade",
            transition_duration=100,
            style_classes="" if not config.VERTICAL else "vertical",
            children=(
                [
                    self.wavy_clock,
                    self.weather_pill,
                ]
            ),
        )

        self.low_bat_msg = Label(label="Welcome to (=Zenith=)")

        self.content_box = Box(
            orientation="v",
            children=[
                Label(name="notification-source", label="Zenith Shell", h_align=True),
                self.low_bat_msg,
            ],
        )

        close_btn = Button(
            name="close-button",
            child=Label(name="close-label", markup=icons.cancel),
            tooltip_text="Exit",
            on_clicked=lambda *_: print("clicked close"),
        )

        self.notification_box = Box(
            name="notification-box",
            style_classes="vertical" if config.VERTICAL else "horizontal",
            children=[
                Label(name="notification-icon", h_align=True, markup=icons.blur),
                Box(h_expand=True, children=self.content_box),
                Box(children=close_btn),
            ],
        )

        self.tiles = Box(
            spacing=3,
            orientation="v",
            children=[
                Box(
                    spacing=3,
                    children=[
                        self.wifi,
                        self.bluetooth,
                        self.mini_player_tile,
                    ],
                ),
                Box(
                    spacing=3,
                    children=[
                        self.silent,
                        CenterBox(
                            style="background-color:var(--surface-bright); border-radius:20px;",
                            h_expand=True,
                            center_children=Label(
                                label="~", style="font-size:25px; color: var(--outline)"
                            ),
                        ),
                        Tile(style_classes=["off"]),
                        # Box(style='background-color:white; min-height:60px; min-width:140px; border-radius:20px;'),
                        # Box(style='background-color:white; min-height:60px; min-width:70px; border-radius:20px;'),
                    ],
                ),
            ],
        )
        self.low_bat_msg_2 = Label(label="Happy farming :)")

        self.content_box_2 = Box(
            orientation="v",
            children=[
                Label(name="notification-source", label="System", h_align=True),
                self.low_bat_msg_2,
            ],
        )

        close_btn_2 = Button(
            name="close-button",
            child=Label(name="close-label", markup=icons.cancel),
            tooltip_text="Exit",
            on_clicked=lambda *_: print("clicked close"),
        )

        self.notification_box_2 = Box(
            name="notification-box",
            style_classes="vertical" if config.VERTICAL else "horizontal",
            children=[
                Label(name="notification-icon", h_align=True, markup=icons.blur),
                Box(h_expand=True, children=self.content_box_2),
                Box(children=close_btn_2),
            ],
        )

        self.notification_container = Revealer(
            transition_duration=250,
            transition_type="slide-down",
            h_expand=True,
            child=Box(
                h_expand=True,
                v_expand=True,
                spacing=3,
                children=[
                    Box(
                        name="notification-container",
                        orientation="v",
                        v_expand=True,
                        spacing=3,
                        children=[
                            Label(
                                label="SOSS Agenda",
                                style="color:var(--foreground); margin-bottom:3px; font-family: Roboto Flex",
                            ),
                            self.notification_box,
                            self.notification_box_2,
                        ],
                    ),
                    Box(
                        orientation="v",
                        h_expand=True,
                        v_expand=True,
                        children=[
                            Box(
                                h_align="end",
                                children=[
                                    Label(
                                        markup=icons.edit,
                                        style="font-size:25px; margin-right:15px; color:var(--foreground)",
                                    ),
                                    Label(
                                        markup=icons.settings,
                                        style="font-size:25px; color:var(--foreground);",
                                    ),
                                ],
                            ),
                            add_hover_cursor(
                                widget=Button(
                                    style="all:unset",
                                    v_expand=True,
                                    h_expand=True,
                                    child=self.widget_stack,
                                    on_clicked=lambda *_: self.cycle_widgets(),
                                )
                            ),
                        ],
                    ),
                ],
            ),
            child_revealed=True,
        )
        self.children = [
            Box(
                orientation="h",
                children=[
                    CenterBox(
                        style_classes="scale-icon-container",
                        center_children=Label(
                            style_classes="scale-icon", markup=icons.brightness
                        ),
                    ),
                    self.brightness_revealer_mui,
                ],
            ),
            Box(children=self.tiles),
            Box(
                children=[
                    self.notification_container,
                ]
            ),
        ]

        self.connect("unmap", lambda *_: self.close_all())

    def close_all(self):
        self.notification_container.set_reveal_child(True)
        rows = self.tiles.get_children()
        for row in rows:
            elems = row.get_children()
            for elem in elems:
                if hasattr(elem, "close"):
                    elem.close()

    def handle_tile_menu_expand(self, tile: str, toggle: bool, close: bool = False):
        if toggle:
            self.notification_container.set_reveal_child(False)
        else:
            self.notification_container.set_reveal_child(True)

        rows = self.tiles.get_children()
        for row in rows:
            elems = row.get_children()
            for elem in elems:
                if elem.get_name() == tile:
                    print("found")
                else:
                    if toggle:
                        try:
                            elem.mini_view()
                        except:
                            logger.error(
                                f"Failed to switch {elem.get_name()} to mini view"
                            )
                    else:
                        try:
                            elem.maxi_view()
                        except:
                            logger.error(
                                f"Failed to switch {elem.get_name()} to mini view"
                            )

    def cycle_widgets(self, forward=True):
        if not self.widget_stack:
            return

        widget_list = self.widget_stack.get_children()

        current_widget = self.widget_stack.get_visible_child()
        current_index = widget_list.index(current_widget)

        next_index = (current_index + (1 if forward else -1)) % len(widget_list)
        next_widget = widget_list[next_index]
        self.widget_stack.set_visible_child(next_widget)
