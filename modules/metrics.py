import psutil

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.core.fabricator import Fabricator
from fabric.core.service import Service, Signal
from fabric.widgets.circularprogressbar import CircularProgressBar

from widgets.animated_scale import AnimatedScale
from widgets.popup_window import SharedPopupWindow
from widgets.material_label import MaterialIconLabel
from widgets.animated_circular_progress_bar import AnimatedCircularProgressBar

import icons as icons
from config.info import config

from gi.repository import GLib


class MetricsProvider(Service):
    """
    Class responsible for obtaining centralized CPU, memory, disk usage, and battery metrics.
    It updates periodically so that all widgets querying it display the same values.
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        super().__init__()
        self._initialized = True

        self.cpu = 0.0
        self.mem = 0.0
        self.disk = 0.0

        self.bat_percent = 0.0
        self.bat_charging = None

        # Updates every 1 second
        GLib.timeout_add_seconds(1, self._update)

    @Signal
    def battery_changed(self, percent: float, charging: bool) -> None: ...

    def _update(self):
        # Get non-blocking usage percentages (interval=0)
        # The first call may return 0, but subsequent calls will provide consistent values.
        self.cpu = psutil.cpu_percent(interval=0)
        self.mem = psutil.virtual_memory().percent
        self.disk = psutil.disk_usage("/").percent

        battery = psutil.sensors_battery()
        if battery is None:
            self.bat_percent = 0.0
            self.bat_charging = None
        else:
            self.bat_percent = battery.percent
            self.bat_charging = battery.power_plugged
        if self.bat_charging is not None:
            self.battery_changed(self.bat_percent, self.bat_charging)

        return True

    def get_metrics(self):
        return (self.cpu, self.mem, self.disk)

    def get_battery(self):
        return (self.bat_percent, self.bat_charging)


# Global instance to share data between both widgets.
shared_provider = MetricsProvider()


class Metrics(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="metrics",
            spacing=8,
            h_align="center",
            v_align="fill",
            visible=True,
            all_visible=True,
        )

        self.cpu_usage = Scale(
            name="cpu-usage",
            value=0.25,
            orientation="v",
            inverted=True,
            v_align="fill",
            v_expand=True,
        )

        self.cpu_label = Label(
            name="cpu-label",
            markup=icons.cpu.markup(),
        )

        self.cpu = Box(
            name="cpu-box",
            orientation="v",
            spacing=8,
            children=[
                self.cpu_usage,
                self.cpu_label,
            ],
        )

        # self.cpu_slider = MetricsSliderMaterial3()

        self.ram_usage = Scale(
            name="ram-usage",
            value=0.5,
            orientation="v",
            inverted=True,
            v_align="fill",
            v_expand=True,
        )

        self.ram_label = Label(
            name="ram-label",
            markup=icons.memory.markup(),
        )

        self.ram = Box(
            name="ram-box",
            orientation="v",
            spacing=8,
            children=[
                self.ram_usage,
                self.ram_label,
            ],
        )
        # self.ram_slider = MetricsSliderMaterial3()

        self.disk_usage = Scale(
            name="disk-usage",
            value=0.75,
            orientation="v",
            inverted=True,
            v_align="fill",
            v_expand=True,
        )

        self.disk_label = Label(
            name="disk-label",
            markup=icons.disk.markup(),
        )

        self.disk = Box(
            name="disk-box",
            orientation="v",
            spacing=8,
            children=[
                self.disk_usage,
                self.disk_label,
            ],
        )
        # self.disk_slider = MetricsSliderMaterial3()

        self.scales = [
            self.disk,
            self.ram,
            self.cpu,
        ]

        # self.popup_win = PopupWindow(
        #     widget=self,
        #     child=Box(
        #         name="control-slider-mui-container",
        #         children=[self.cpu_slider, self.cpu_slider, self.disk_slider],
        #     ),
        # )

        self.cpu_usage.set_sensitive(False)
        self.ram_usage.set_sensitive(False)
        self.disk_usage.set_sensitive(False)

        for x in self.scales:
            self.add(x)

        # Update the widget every second
        GLib.timeout_add_seconds(1, self.update_status)

    def update_status(self):
        # Retrieve centralized data
        cpu, mem, disk = shared_provider.get_metrics()

        # Normalize to 0.0 - 1.0
        self.cpu_usage.value = cpu / 100.0
        # self.cpu_slider.value = cpu / 100.0
        self.ram_usage.value = mem / 100.0
        # self.ram_slider.value = mem / 100.0
        self.disk_usage.value = disk / 100.0
        # self.disk_slider.value = disk / 100.0

        return True  # Continue calling this function.


class MetricsSmall(Button):
    def __init__(self, **kwargs):
        super().__init__(name="metrics-small", **kwargs)

        if config.VERTICAL:
            self.add_style_class("vertical")

        # ------------------ CPU ------------------
        self.cpu_icon = MaterialIconLabel(name="cpu-icon", FILL=0, wght=600, icon_text=icons.cpu.symbol())
        self.cpu_circle = CircularProgressBar(
            name="metrics-circle",
            value=0,
            size=28,
            line_width=2,
            # start_angle=150,
            # end_angle=390,
            start_angle=-90,
            end_angle=270,
            style_classes="cpu",
            child=self.cpu_icon,
        )
        self.cpu_level = Label(name="metrics-level", style_classes="cpu", label="0%")
        self.cpu_revealer = Revealer(
            name="metrics-cpu-revealer",
            transition_duration=250,
            transition_type="slide-left" if not config.VERTICAL else "slide-down",
            child=self.cpu_level,
            child_revealed=False,
        )
        self.cpu_box = EventBox(
            name="metrics-cpu-box",
            orientation="h",
            spacing=0,
            h_expand=True,
            v_expand=True,
            child=self.cpu_circle,
        )

        # ------------------ RAM ------------------
        self.ram_icon = MaterialIconLabel(
            name="ram-icon", FILL=0, wght=600, icon_text=icons.memory.symbol()
        )
        self.ram_circle = CircularProgressBar(
            name="metrics-circle",
            value=0,
            size=28,
            line_width=2,
            start_angle=-90,
            end_angle=270,
            style_classes="ram",
            child=self.ram_icon,
        )
        self.ram_level = Label(name="metrics-level", style_classes="ram", label="0%")
        self.ram_revealer = Revealer(
            name="metrics-ram-revealer",
            transition_duration=250,
            transition_type="slide-left" if not config.VERTICAL else "slide-down",
            child=self.ram_level,
            child_revealed=False,
        )
        self.ram_box = EventBox(
            name="metrics-ram-box",
            orientation="h",
            spacing=0,
            h_expand=True,
            v_expand=True,
            child=self.ram_circle,
        )

        # ------------------ Disk ------------------
        self.disk_icon = MaterialIconLabel(
            name="disk-icon", FILL=0, wght=600, icon_text=icons.disk.symbol()
        )
        self.disk_circle = CircularProgressBar(
            name="metrics-circle",
            value=0,
            size=28,
            line_width=2,
            start_angle=-90,
            end_angle=270,
            style_classes="disk",
            child=self.disk_icon,
        )
        self.disk_level = Label(name="metrics-level", style_classes="disk", label="0%")
        self.disk_revealer = Revealer(
            name="metrics-disk-revealer",
            transition_duration=250,
            transition_type="slide-left" if not config.VERTICAL else "slide-down",
            child=self.disk_level,
            child_revealed=False,
        )
        self.disk_box = EventBox(
            name="metrics-disk-box",
            orientation="h",
            h_expand=True,
            v_expand=True,
            child=self.disk_circle,
        )

        self.main_box = Box(
            spacing=0,
            orientation="v" if config.VERTICAL else "h",
            visible=True,
            all_visible=True,
            h_expand=True,
            v_expand=True,
            children=[
                self.disk_box,
                self.disk_revealer,
                self.ram_box,
                self.ram_revealer,
                self.cpu_box,
                self.cpu_revealer,
            ],
        )
        self.children = self.main_box

        # Connect events directly to the button
        self.connect("enter-notify-event", self.on_mouse_enter)
        self.connect("leave-notify-event", self.on_mouse_leave)

        # sliders for popup window
        self.cpu_slider = MetricsSliderMaterial3(orientation="v")
        self.ram_slider = MetricsSliderMaterial3(orientation="v")
        self.disk_slider = MetricsSliderMaterial3(orientation="v")

        self.popup_win = SharedPopupWindow()
        self.popup_win.add_child(
            pointing_widget=self,
            child=Box(
                name="control-slider-mui-container",
                spacing=7,
                children=[self.disk_slider, self.ram_slider, self.cpu_slider],
            ),
        )

        # Metrics update every second
        GLib.timeout_add_seconds(1, self.update_metrics)

        # Initial state of the revealers and variables for hover management
        self.hide_timer = None
        self.hover_counter = 0

    def _format_percentage(self, value: int) -> str:
        if config.VERTICAL:
            return f"{value}"
        else:
            return f"{value}%"

    def on_mouse_enter(self, widget, event):
        self.hover_counter += 1
        if self.hide_timer is not None:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = None
        # Reveal levels on hover for all metrics
        self.cpu_revealer.set_reveal_child(True)
        self.ram_revealer.set_reveal_child(True)
        self.disk_revealer.set_reveal_child(True)
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
        self.cpu_revealer.set_reveal_child(False)
        self.ram_revealer.set_reveal_child(False)
        self.disk_revealer.set_reveal_child(False)
        self.hide_timer = None
        return False

    def update_metrics(self):
        # Recover centralized data
        cpu, mem, disk = shared_provider.get_metrics()
        self.cpu_circle.set_value(cpu / 100.0)
        self.ram_circle.set_value(mem / 100.0)
        self.disk_circle.set_value(disk / 100.0)

        self.cpu_slider.animate_value(cpu / 100.0)
        self.ram_slider.animate_value(mem / 100.0)
        self.disk_slider.animate_value(disk / 100.0)
        # Update labels with formatted percentage
        self.cpu_level.set_label(self._format_percentage(int(cpu)))
        self.ram_level.set_label(self._format_percentage(int(mem)))
        self.disk_level.set_label(self._format_percentage(int(disk)))
        # self.set_tooltip_markup(
        #     f"{icons.disk.markup()} DISK - {icons.memory.markup()} RAM - {icons.cpu.markup()} CPU"
        # )
        return True


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
    def __init__(self, **kwargs):
        super().__init__(name="bat-small", **kwargs)

        if config.VERTICAL:
            self.add_style_class("vertical")

        # ------------------ Battery ------------------
        self.bat_icon = MaterialIconLabel(
            angle=90,
            name="bat-icon",
            style_classes="metrics-icon",
            icon_text=icons.battery.symbol(),
        )
        self.bat_circle = CircularProgressBar(
            name="metrics-circle",
            value=0,
            size=28,
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

        # Connect events directly to the button
        self.connect("enter-notify-event", self.on_mouse_enter)
        self.connect("leave-notify-event", self.on_mouse_leave)

        # Battery update every second
        self.batt_fabricator = Fabricator(
            poll_from=lambda v: shared_provider.get_battery(),
            on_changed=lambda f, v: self.update_battery,
            interval=1000,
            stream=False,
            default_value=0,
        )
        self.batt_fabricator.changed.connect(self.update_battery)

        # Initial state of the revealers and variables for hover management
        self.hide_timer = None
        self.hover_counter = 0

    def _format_percentage(self, value: int) -> str:
        if config.VERTICAL:
            return f"{value}"
        else:
            return f"{value}%"

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

    def update_battery(self, sender, battery_data):
        value, charging = battery_data
        if value == 0:
            self.set_visible(False)
        else:
            self.set_visible(True)
            self.bat_circle.set_value(value / 100)
        percentage = int(value)
        self.bat_level.set_label(self._format_percentage(percentage))

        if percentage <= 15 and not charging:
            self.bat_icon.add_style_class("alert")
            self.bat_circle.add_style_class("alert")
            self.bat_circle.add_style_class("low-bat")
            self.add_style_class("low-bat")
        else:
            self.bat_circle.remove_style_class("low-bat")
            self.remove_style_class("low-bat")
            self.bat_icon.remove_style_class("alert")
            self.bat_circle.remove_style_class("alert")

        # Choose the icon based on charging state first, then battery level
        if percentage == 100:
            self.bat_icon.set_icon(icons.battery.symbol())
            self.bat_circle.add_style_class("full-bat")
            charging_status = f"{icons.bat_full.symbol()} Fully Charged"
        elif charging:
            self.bat_icon.set_icon(icons.battery_charging.symbol())
            charging_status = f"{icons.bat_charging.symbol()} Charging"
        elif percentage <= 15 and not charging:
            # self.bat_icon.set_markup(icons.alert.markup())
            charging_status = f"{icons.bat_low.symbol()} Low Battery"
        elif not charging:
            # self.bat_icon.set_markup(icons.discharging.markup())
            charging_status = f"{icons.discharging.symbol()} Discharging"
        else:
            self.bat_icon.set_icon(icons.battery.symbol())
            charging_status = "Battery"

        # tooltip with battery percentage
        self.set_tooltip_markup(f"{charging_status}")
