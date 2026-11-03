from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.eventbox import EventBox
from fabric.widgets.centerbox import CenterBox

from widgets.shapes import Pill, Circle, WavyCircle, Ellipse, Pentagon
from modules.weather import WeatherPill
from modules.wavy_clock import WavyClock
from utils.lock import LOCKSCREEN_BLURRED_IMG_FILE, LOCKSCREEN_IMG_FILE

from gi.repository import GLib  # type: ignore

FLASH_MS = 150
WHITE = (1, 1, 1)
RED = (1, 0, 0)
BLUE = (0, 0, 1)


def _background_style() -> str:
    # read the cached images directly: WallpaperService would (re)start swaybg
    for image in (LOCKSCREEN_BLURRED_IMG_FILE, LOCKSCREEN_IMG_FILE):
        if image.exists():
            return (
                f"background-image: url('{image}');"
                "background-position: center;"
                "background-size: cover;"
            )
    return "background-color: var(--background);"


class ShapeIndicator(Stack):
    def __init__(self, **kwargs):
        super().__init__(
            h_align="center",
            children=[
                Pill(dark=True),
                Circle(dark=True),
                WavyCircle(dark=True),
                Ellipse(dark=True),
                Pentagon(dark=True),
            ],
            **kwargs,
        )

    def step(self, forward: bool = True):
        shapes = self.get_children()
        if not shapes:
            return
        index = shapes.index(self.get_visible_child())
        self.set_visible_child(shapes[(index + (1 if forward else -1)) % len(shapes)])

    def reset(self):
        self.set_visible_child(self.get_children()[0])

    def flash(self, rgb, ms: int = FLASH_MS):
        shape = self.get_visible_child()
        shape.set_color(rgb=rgb, redraw=True)

        def restore():
            shape.set_color(rgb=None, redraw=True)
            return False

        GLib.timeout_add(ms, restore)

    def hold(self, rgb):
        self.get_visible_child().set_color(rgb=rgb, redraw=True)

    def release(self):
        self.get_visible_child().set_color(rgb=None, redraw=True)


class LockContent(CenterBox):
    def __init__(self, **kwargs):
        self.indicator = ShapeIndicator()

        self.status = Label(
            label="",
            style="color: white; font-size: 14px;",
            size_request=(250, -1),
        )

        super().__init__(
            spacing=10,
            style=_background_style(),
            center_children=[
                Box(
                    spacing=10,
                    v_align="center",
                    children=[
                        WavyClock(size=(400, 400)),
                        WeatherPill(size=(400, 400)),
                    ],
                ),
            ],
            end_children=Box(
                orientation="v",
                v_align="end",
                spacing=10,
                style="margin:20px;",
                children=[EventBox(child=self.indicator)],
            ),
            **kwargs,
        )
