from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer

from modules.bluetooth import Bluetooth
from modules.network import Network
from modules.tile import Tile, TileSpecial
from modules.wavy_clock import WavyCircle
from modules.player_mini import PlayerContainerMini

import icons.icons as icons
import config.info as info


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
        self.mini_player_tile = TileSpecial(
            props=self.mini_player, mini_props=self.mini_player.get_mini_view()
        )

        self.controls = controls
        self.brightness_revealer_mui = self.controls.get_brightness_slider_mui()

        self.wavy = self.gtk_wrapper = CenterBox(
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            center_children=WavyCircle(),
        )

        self.low_bat_msg = Label(label="Low Battery fam (<15%)")

        self.content_box = Box(
            orientation="v",
            children=[
                Label(name="notification-source", label="ZENITH", h_align=True),
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
            style_classes="vertical" if info.VERTICAL else "horizontal",
            children=[
                Label(name="notification-icon", h_align=True, markup=icons.blur),
                Box(h_expand=True, children=self.content_box),
                Box(children=close_btn),
            ],
        )

        self.tiles = Box(
            spacing=3,
            orientation='v',
            children=[
                Box(
                    spacing=3,
                    children=[
                        self.wifi,
                        self.bluetooth,
                        self.mini_player_tile,
                    ],
                ),
                # Box(
                #     spacing=3,
                #     children=[
                        # Box(style='background-color:white; min-height:60px; min-width:70px; border-radius:20px;'),
                        # Box(style='background-color:white; min-height:60px; min-width:140px; border-radius:20px;'),
                        # Box(style='background-color:white; min-height:60px; min-width:140px; border-radius:20px;'),
                        # Box(style='background-color:white; min-height:60px; min-width:70px; border-radius:20px;'),
                #     ],
                # )
            ],
        )
        self.low_bat_msg_2 = Label(label="Notification ctl test")

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
            style_classes="vertical" if info.VERTICAL else "horizontal",
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
                children=[
                    Box(
                        name="notification-container",
                        orientation="v",
                        v_expand=True,
                        spacing=3,
                        children=[self.notification_box, self.notification_box_2],
                    ),
                    Box(
                        v_expand=True,
                        h_expand=True,
                        children=self.wavy,
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

    def handle_tile_menu_expand(self, tile: str, toggle: bool):
        if toggle:
            self.notification_container.set_reveal_child(False)
        else:
            self.notification_container.set_reveal_child(True)
        
        for rows in self.tiles:
            for elem in rows:
                if elem.get_name() == tile:
                    print("found")
                else:
                    if toggle:
                        elem.mini_view()
                        elem.icon.add_style_class("mini")
                        elem.icon.remove_style_class("maxi")
                    else:
                        elem.maxi_view()
                        elem.icon.add_style_class("maxi")
                        elem.icon.remove_style_class("mini")
        print("search complete")
