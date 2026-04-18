import gi
import time
from loguru import logger
from typing import Literal
from collections.abc import Iterable

from fabric.widgets.button import Button
from fabric.widgets.box import Box
from fabric.widgets.eventbox import EventBox
from fabric.core.service import Property
from fabric.utils.helpers import invoke_repeater, exec_shell_command_async

import icons
from config.info import SHELL_NAME
from widgets.popup_window.shared_popup_window import SharedPopupWindow
from widgets.material_label import MaterialFontLabel, MaterialIconLabel
from services.animator import Animator
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
        self.start_power_btn = Button(
            name="orientation-btn",
            child=MaterialIconLabel(
                name="orientation-label",
                FILL=0,
                icon_text=(icons.shutdown.symbol()),
            ),
            on_clicked=lambda b, *_: self.toggle_power_menu(),
        )

        self.children = self.restart_btn

        self.mapping = {
            self.start_power_btn: {"label": "Open Power Menu", "action": "power"},
            self.toggle_vrt_btn: {
                "label": "Toggle Bar Orientation",
                "action": "toggle",
            },
            self.start_launcher_btn: {"label": "Start Launcher", "action": "launcher"},
            self.restart_btn: {"label": "Restart Bar", "action": "restart"},
        }

        self.action_options = Box(
            spacing=4,
            orientation="v",
            children=[
                Button(
                    name="action-btn",
                    h_align="start",
                    child=Box(
                        spacing=2,
                        children=[
                            MaterialIconLabel(
                                name="orientation-label",
                                style_classes="action-icon",
                                FILL=0,
                                icon_text=btn.get_children()[0].get_text(),
                            ),
                            MaterialFontLabel(
                                text=info["label"],
                                style_classes="action-menu-label",
                                font_family="Google Sans Flex",
                                font_size=15,
                            ),
                        ],
                    ),
                    on_clicked=lambda btn, *_, i=info: self.select_action(
                        btn, i["action"]
                    ),
                )
                for btn, info in self.mapping.items()
            ],
        )

        self.popup_win = SharedPopupWindow()
        self.popup_win.add_child(pointing_widget=self, child=self.action_options)

    def select_action(self, btn_option: Button, action: str):
        action_map = {
            "toggle": self.toggle_vrt_btn,
            "restart": self.restart_btn,
            "launcher": self.start_launcher_btn,
            "power": self.start_power_btn,
        }

        target_widget = action_map.get(action)
        if target_widget:
            if self.get_child():
                self.remove(self.get_child())
            self.add(target_widget)

        def ensure_animator(label: MaterialFontLabel):
            if hasattr(label, "_animator"):
                return

            # setup a 0.0 -> 1.0 animator (linear)
            label._animator = Animator(
                bezier_curve=(0, 0, 1, 1), duration=0.15, tick_widget=label
            )

            # visual state to interrupt animations smoothly
            label._wght_start, label._wght_end = 450.0, 450.0
            label._slnt_start, label._slnt_end = 0.0, 0.0

            def on_animate_tick(*_):
                t = label._animator.value

                # lerp
                curr_wght = (
                    label._wght_start + (label._wght_end - label._wght_start) * t
                )
                curr_slnt = (
                    label._slnt_start + (label._slnt_end - label._slnt_start) * t
                )

                label.set_variations(wght=curr_wght, slnt=curr_slnt)

            label._animator.connect("notify::value", on_animate_tick)

        for btn in self.action_options.get_children():
            content_box = btn.get_children()[0]
            label = content_box.get_children()[1]

            ensure_animator(label)

            # capture current state as the new start point
            t_prev = label._animator.value
            current_visual_wght = (
                label._wght_start + (label._wght_end - label._wght_start) * t_prev
            )
            current_visual_slnt = (
                label._slnt_start + (label._slnt_end - label._slnt_start) * t_prev
            )

            # reset timeline and play
            if label._animator.playing:
                label._animator.pause()

            label._wght_start = current_visual_wght
            label._slnt_start = current_visual_slnt

            if btn == btn_option:
                btn.add_style_class("active")
                label._wght_end = 700.0
                label._slnt_end = -10.0
            else:
                btn.remove_style_class("active")
                label._wght_end = 450.0
                label._slnt_end = 0.0

            label._animator.play()

        self.show_all()

    def toggle_vertical(self):
        exec_shell_command_async(
            "notify-send 'Zenith Shell' 'Toggling is coming soon.'"
        )

    def start_launcher(self):
        exec_shell_command_async(f"fabric-cli exec {SHELL_NAME} 'pill.open()'")

    def toggle_power_menu(self):
        exec_shell_command_async(
            f"fabric-cli exec {SHELL_NAME} 'pill.toggle_power_menu()'"
        )
