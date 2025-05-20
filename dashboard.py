from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
import icons.icons as icons
import info
from network import Network
from bluetooth import Bluetooth
from tile import Tile


class Dashboard(Box):
    def __init__(self, controls, **kwargs):
        super().__init__(
            name="dashboard",
            visible=False,
            orientation="v",
            spacing=8,
            all_visible=False,
            **kwargs,
        )
        self.wifi = Network()
        self.bluetooth = Bluetooth()

        self.controls = controls
        self.brightness_revealer_mui = self.controls.get_brightness_slider_mui()

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
        self.children = [
            Box(
                name="inner",
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
            Box(
                name="inner",
                children=[
                    self.wifi,
                    self.bluetooth,
                    Box(
                        style_classes=["tile", "on"],
                        h_expand=True,
                        children=[
                            Label(
                                style_classes="tile-icon", markup=icons.notifications
                            ),
                            Box(
                                style_classes="tile-type",
                                orientation="v",
                                v_expand=True,
                                v_align="center",
                                children=[
                                    Label(
                                        style_classes="tile-label",
                                        label="Whaterver that goes here",
                                        h_align="start",
                                    ),
                                ],
                            ),
                        ],
                        style="min-width:250px;",
                    ),
                ],
            ),
            Box(
                children=[
                    Box(
                        name="notification-container",
                        orientation="v",
                        v_expand=True,
                        style="padding:3px; padding-top:0px",
                        children=[self.notification_box, self.notification_box_2],
                    ),
                    Box(
                        orientation="v",
                        v_expand=True,
                    ),
                ]
            ),
        ]

