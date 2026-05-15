from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.circularprogressbar import CircularProgressBar

from .metrics_popup import Metrics

from widgets.animated_scale import AnimatedScale
from widgets.popup_window import SharedPopupWindow
from widgets.material_label import MaterialIconLabel
from services.metrics import MetricsProvider

import icons as icons
from config.config import config

from gi.repository import GLib


class MetricItem(Box):
    def __init__(self, icon_symbol, style_class, vertical, bar_size):
        super().__init__(name=f"metric-{style_class}-item", orientation="h")
        
        self.icon = MaterialIconLabel(
            name=f"{style_class}-icon", FILL=0, wght=600, icon_text=icon_symbol
        )
        self.circle = CircularProgressBar(
            name="metrics-circle",
            value=0,
            size=bar_size,
            line_width=2,
            start_angle=-90,
            end_angle=270,
            style_classes=style_class,
            child=self.icon,
        )
        self.level = Label(name="metrics-level", style_classes=style_class, label="0%")
        self.revealer = Revealer(
            transition_duration=250,
            transition_type="slide-left" if not vertical else "slide-down",
            child=self.level,
        )
        
        self.add(self.circle)
        self.add(self.revealer)

    def update(self, value, vertical):
        self.circle.set_value(value / 100.0)
        rounded = round(value)
        self.level.set_label(f"{rounded}" if vertical else f"{rounded}%")


class MetricsSmall(Button):
    BAR_SIZE = 34

    def __init__(self, **kwargs):
        super().__init__(name="metrics-small", **kwargs)
        self.service = MetricsProvider()
        
        self.cpu = MetricItem(icons.cpu.symbol(), "cpu", config.VERTICAL, self.BAR_SIZE)
        self.ram = MetricItem(icons.memory.symbol(), "ram", config.VERTICAL, self.BAR_SIZE)
        self.disk = MetricItem(icons.disk.symbol(), "disk", config.VERTICAL, self.BAR_SIZE)

        self.metrics_list = [self.disk, self.ram, self.cpu]

        self.main_box = Box(
            orientation="v" if config.VERTICAL else "h",
            children=self.metrics_list,
        )
        self.children = self.main_box

        self.connect("enter-notify-event", self.on_mouse_enter)
        self.connect("leave-notify-event", self.on_mouse_leave)
        self.service.connect("metrics-changed", self.update_metrics)

        self.popup_win = SharedPopupWindow()
        self.popup_win.add_child(pointing_widget=self, child=Metrics())

        self.hide_timer = None
        self.hover_counter = 0

        if config.VERTICAL:
            self.add_style_class("vertical")

    # Revealing is disabled in favour of interruption free popup placement
    def on_mouse_enter(self, widget, event):
        ...
        # self.hover_counter += 1
        # if self.hide_timer:
        #     GLib.source_remove(self.hide_timer)
        #     self.hide_timer = None
        # for m in self.metrics_list:
        #     m.revealer.set_reveal_child(True)

    def on_mouse_leave(self, widget, event):
        ...
        # self.hover_counter = max(0, self.hover_counter - 1)
        # if self.hover_counter == 0:
        #     if self.hide_timer:
        #         GLib.source_remove(self.hide_timer)
        #     self.hide_timer = GLib.timeout_add(100, self.hide_revealer)

    def hide_revealer(self):
        # for m in self.metrics_list:
        #     m.revealer.set_reveal_child(False)
        # self.hide_timer = None
        return False

    def update_metrics(self, source, cpu, mem, disk):
        self.cpu.update(cpu, config.VERTICAL)
        self.ram.update(mem, config.VERTICAL)
        self.disk.update(disk, config.VERTICAL)


class MetricsSliderMaterial3(AnimatedScale):
    def __init__(self, orientation="h", **kwargs):
        super().__init__(
            name="control-slider-mui",
            orientation=orientation,
            h_expand=True,
            has_origin=True,
            inverted=False if orientation == "h" else True,
            style_classes="" if orientation == "h" else "vertical",
            increments=(0.01, 0.1),
            **kwargs,
        )


class Battery(Button):
    BAR_SIZE = 34

    def __init__(self, **kwargs):
        super().__init__(name="bat-small", **kwargs)
        self.service = MetricsProvider()

        # hover track states
        self.hide_timer = None
        self.hover_counter = 0

        if config.VERTICAL:
            self.add_style_class("vertical")

        self.bat_icon = MaterialIconLabel(
            angle=90,
            name="bat-icon",
            style_classes="metrics-icon",
            icon_text=icons.battery.symbol(),
        )
        self.bat_circle = CircularProgressBar(
            name="metrics-circle",
            value=0,
            size=self.BAR_SIZE,
            line_width=2,
            start_angle=-90,
            end_angle=270,
            child=self.bat_icon,
        )
        self.bat_level = Label(name="metrics-level", style_classes="bat", label="100%")
        self.bat_revealer = Revealer(
            name="metrics-bat-revealer",
            transition_duration=250,
            transition_type="slide-left" if not config.VERTICAL else "slide-down",
            child=self.bat_level,
            child_revealed=False,
        )
        self.bat_box = EventBox(
            name="metrics-bat-box",
            orientation="h",
            spacing=0,
            h_expand=True,
            v_expand=True,
            child=self.bat_circle,
        )

        self.main_box = Box(
            spacing=0,
            orientation="h" if not config.VERTICAL else "v",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            children=[self.bat_box, self.bat_revealer],
        )

        self.children = self.main_box

        self.connect("enter-notify-event", self.on_mouse_enter)
        self.connect("leave-notify-event", self.on_mouse_leave)
        self.service.connect("battery-changed", self.update_battery)

    def _format_percentage(self, value: int) -> str:
        return f"{value}" if config.VERTICAL else f"{value}%"

    def on_mouse_enter(self, widget, event):
        self.hover_counter += 1
        if self.hide_timer is not None:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = None
        # Reveal levels on hover for all metrics
        self.bat_revealer.set_reveal_child(True)
        return False

    def on_mouse_leave(self, widget, event):
        if self.hover_counter > 0:
            self.hover_counter -= 1
        if self.hover_counter == 0:
            if self.hide_timer is not None:
                GLib.source_remove(self.hide_timer)
            self.hide_timer = GLib.timeout_add(100, self.hide_revealer)
        return False

    def hide_revealer(self):
        self.bat_revealer.set_reveal_child(False)
        self.hide_timer = None
        return False

    def update_battery(self, sender, percent, is_charging):
        if percent == -1:
            return

        self.bat_circle.set_value(percent / 100)
        rounded_pct = round(percent)
        self.bat_level.set_label(self._format_percentage(rounded_pct))

        is_low = rounded_pct <= 15 and not is_charging
        is_full = rounded_pct == 100

        if is_full:
            icon = icons.battery.symbol()
            status_text = "Fully Charged"
        elif is_charging:
            icon = icons.battery_charging.symbol()
            status_text = f"{icons.bat_charging.symbol()} Charging"
        else:
            icon = icons.battery.symbol()
            status_text = (
                f"{icons.discharging.symbol()} Discharging"
                if not is_low
                else "Low Battery"
            )

        self.bat_icon.set_icon(icon)
        self.set_tooltip_markup(status_text)

        if is_low:
            self.bat_icon.add_style_class("alert")
            self.bat_circle.add_style_class("alert")
            self.add_style_class("low-bat")
            self.bat_circle.add_style_class("low-bat")
        else:
            self.remove_style_class("low-bat")
            self.bat_circle.remove_style_class("low-bat")
            self.bat_icon.remove_style_class("alert")
            self.bat_circle.remove_style_class("alert")

        # if is_full:
        #     self.bat_circle.add_style_class("full-bat")
        # else:
        #     self.bat_circle.remove_style_class("full-bat")
