import gi
import time
from loguru import logger
from typing import Literal
from collections.abc import Iterable

from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.core.service import Property
from fabric.utils.helpers import invoke_repeater, exec_shell_command_async

import icons
from config.info import SHELL_NAME
from widgets.popup_window.shared_popup_window import SharedPopupWindow
from widgets.material_label import MaterialFontLabel, MaterialIconLabel
from utils.helpers import restart_shell

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk


# too much overriding
class DateTime(Button):
    @Property(tuple[str, ...], "read-write")
    def formatters(self):
        return self._formatters

    @formatters.setter
    def formatters(self, value: str | Iterable[str]):
        if isinstance(value, (tuple, list)):
            self._formatters = tuple(value)
        elif isinstance(value, str):
            self._formatters = (value,)
        if len(self._formatters) < 1:
            logger.warning(
                "[DateTime] passed in invalid list of formatters, using default formatters list"
            )
            self._formatters = ("%I:%M %p", "%A", "%m-%d-%Y")
        return

    @Property(int, "read-write")
    def interval(self):
        return self._interval

    @interval.setter
    def interval(self, value: int):
        self._interval = value
        if self._repeater_id:
            GLib.source_remove(self._repeater_id)
        self._repeater_id = invoke_repeater(self._interval, self.do_update_label)
        self.do_update_label()
        return

    def __init__(
        self,
        formatters: str | Iterable[str] = ("%I:%M %p", "%A", "%m-%d-%Y"),
        interval: int = 1000,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        size: Iterable[int] | int | None = None,
        **kwargs,
    ):
        self.label = MaterialFontLabel(
            text="__", font_family="Google Sans Flex", wght=600, ROND=100
        )
        super().__init__(
            None,
            None,
            self.label,
            name,
            visible,
            all_visible,
            style,
            style_classes,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            size,
            **kwargs,
        )
        self.add_events(Gdk.EventMask.SCROLL_MASK)
        self._formatters: tuple[str, ...] = tuple()
        self._current_index: int = 0
        self._interval: int = interval
        self._repeater_id: int | None = None

        self.formatters = formatters
        self.interval = interval

        self.connect(
            "button-press-event",
            lambda *args: self.do_handle_press(*args),  # to allow overriding
        )
        self.connect("scroll-event", lambda *args: self.do_handle_scroll(*args))

    def do_format(self) -> str:
        return time.strftime(self._formatters[self._current_index])

    def do_update_label(self):
        self.label.set_text(self.do_format())
        return True

    def do_check_invalid_index(self, index: int) -> bool:
        return (index < 0) or (index > (len(self.formatters) - 1))

    def do_cycle_next(self):
        self._current_index = self._current_index + 1
        if self.do_check_invalid_index(self._current_index):
            self._current_index = 0  # reset tags

        return self.do_update_label()

    def do_cycle_prev(self):
        self._current_index = self._current_index - 1
        if self.do_check_invalid_index(self._current_index):
            self._current_index = len(self.formatters) - 1

        return self.do_update_label()

    def do_handle_press(self, _, event, *args):
        match event.button:
            case 1:  # left click
                self.do_cycle_next()
            case 3:  # right click
                self.do_cycle_prev()
        return

    def do_handle_scroll(self, _, event, *args):
        match event.direction:
            case Gdk.ScrollDirection.UP:  # scrolling up
                self.do_cycle_next()
            case Gdk.ScrollDirection.DOWN:  # scrolling down
                self.do_cycle_prev()
        return


class ActionButton(EventBox):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.restart_btn = Button(
            name="orientation-btn",
            child=MaterialIconLabel(
                name="orientation-label",
                FILL=0,
                icon_text=(icons.planet.symbol()),
            ),
            on_clicked=lambda b, *_: restart_shell(),
        )
        self.toggle_vrt_btn = Button(
            name="orientation-btn",
            child=MaterialIconLabel(
                name="orientation-label",
                FILL=0,
                icon_text=(icons.toggle_orientation.symbol()),
            ),
            on_clicked=lambda b, *_: self.toggle_vertical(),
        )
        self.start_launcher_btn = Button(
            name="orientation-btn",
            child=MaterialIconLabel(
                name="orientation-label",
                FILL=0,
                icon_text=(icons.rocket_launch.symbol()),
            ),
            on_clicked=lambda b, *_: self.start_launcher(),
        )

        self.children = self.restart_btn

        self.action_options = Box(
            spacing=4,
            orientation="v",
            children=[
                Button(
                    child=Box(
                        spacing=2,
                        children=[
                            MaterialIconLabel(
                                name="orientation-label",
                                style="background-color: var(--surface); padding: 2px 5px; border-radius: 15px",
                                FILL=0,
                                icon_text=self.toggle_vrt_btn.get_children()[0].get_text(),
                            ),
                            Label(
                                label="Toggle Bar Orientation",
                                style_classes="action-menu-label",
                            ),
                        ],
                    ),
                    on_clicked=lambda *_: self.select_action("toggle"),
                ),
                Button(
                    child=Box(
                        spacing=2,
                        children=[
                            MaterialIconLabel(
                                name="orientation-label",
                                style="background-color: var(--surface); padding: 2px 5px; border-radius: 15px",
                                FILL=0,
                                icon_text=self.start_launcher_btn.get_children()[0].get_text(),
                            ),
                            Label(
                                label="Start Launcher",
                                style_classes="action-menu-label",
                            ),
                        ],
                    ),
                    on_clicked=lambda *_: self.select_action("launcher"),
                ),
                Button(
                    child=Box(
                        spacing=2,
                        children=[
                            MaterialIconLabel(
                                name="orientation-label",
                                style="background-color: var(--surface); padding: 2px 5px; border-radius: 15px",
                                FILL=0,
                                icon_text=self.restart_btn.get_children()[0].get_text(),
                            ),
                            Label(
                                label="Restart Bar",
                                style_classes="action-menu-label",
                            ),
                        ],
                    ),
                    on_clicked=lambda *_: self.select_action("restart"),
                ),
            ],
        )

        self.popup_win = SharedPopupWindow()
        self.popup_win.add_child(pointing_widget=self, child=self.action_options)

    def select_action(self, action: str):
        if action == "toggle":
            self.children = self.toggle_vrt_btn
        elif action == "restart":
            self.children = self.restart_btn
        elif action == "launcher":
            self.children = self.start_launcher_btn
        # self.popup_win.hide()

    def toggle_vertical(self):
        exec_shell_command_async(
            "notify-send 'Zenith Shell' 'Toggling is coming soon.'"
        )

    def start_launcher(self):
        exec_shell_command_async(f"fabric-cli exec {SHELL_NAME} 'pill.open()'")