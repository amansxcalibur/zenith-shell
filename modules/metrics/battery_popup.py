import os

from fabric.widgets.box import Box
from fabric.widgets.overlay import Overlay

import icons

from services.metrics import MetricsProvider
from services.animator import Animator, CubicBezierCurves
from services.power_profiles import power_profiles_service

from widgets.clipping_box import ClippingBox
from widgets.variable_font_label import Font, VariableFontLabel, VariableIconLabel

from gi.repository import GLib  # type: ignore


def _read(path: str) -> str | None:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


POWER_SUPPLY = "/sys/class/power_supply"


def _system_batteries() -> list[str]:
    # pickup your batteries big dawg, like psutil :)
    try:
        names = sorted(os.listdir(POWER_SUPPLY))
    except OSError:
        return []
    batteries = []
    for name in names:
        path = os.path.join(POWER_SUPPLY, name)
        if _read(os.path.join(path, "scope")) == "Device":
            continue  # wireless mouse, headset, ...
        if (
            name.startswith("BAT")
            or "battery" in name.lower()
            or _read(os.path.join(path, "type")) == "Battery"
        ):
            batteries.append(path)
    return batteries


def battery_times() -> tuple[str | None, float | None, float | None]:
    """(status, hours to full, hours to empty) from sysfs; None where unknown.

    Uses energy_* + power_now (µWh, µW) or charge_* + current_now (µAh, µA),
    whichever the battery exposes.
    """
    for path in _system_batteries():
        status = _read(os.path.join(path, "status"))
        for now_key, full_key, rate_key in (
            ("energy_now", "energy_full", "power_now"),
            ("charge_now", "charge_full", "current_now"),
        ):
            values = [
                _read(os.path.join(path, k)) for k in (now_key, full_key, rate_key)
            ]
            if None in values:
                continue
            try:
                now, full, rate = (abs(int(v)) for v in values)
            except ValueError:
                continue
            if rate <= 0:
                return status, None, None
            return status, max(0, full - now) / rate, now / rate
        return status, None, None
    return None, None, None


def _format_hours(hours: float) -> str:
    minutes = round(hours * 60)
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h {minutes % 60:02d}m"


class BatteryPopup(Box):
    LOW_THRESHOLD = 15  # percent, same rule as the dock's battery icon
    FILL_DURATION = 0.5  # seconds
    REFRESH_SECONDS = 5  # time estimates, while the popup is open

    def __init__(self, **kwargs):
        super().__init__(name="bat-popup", **kwargs)
        self.service = MetricsProvider()
        self._percent = 0.0  # what the fill currently shows (animated)
        self._target = 0.0
        self._charging = False
        self._refresh_id = None

        self._fill = Box(name="bat-tank-fill", v_align="end", h_expand=True)
        self._fill.set_size_request(-1, 0)

        self._status = VariableFontLabel(
            text="", font_family=Font.GOOGLE_SANS_FLEX, name="bat-tank-status", h_align="end"
        )
        self._bolt = VariableIconLabel(
            name="bat-tank-bolt",
            icon_text=icons.material.bolt.symbol(),
            v_align="center",
        )
        self._bolt.set_no_show_all(True)
        self._percent_label = VariableFontLabel(
            text="0%", font_family=Font.GOOGLE_SANS_FLEX, name="bat-tank-percent"
        )
        self._corner = Box(
            name="bat-tank-corner",
            orientation="v",
            h_align="end",
            v_align="end",
            children=[
                self._status,
                Box(h_align="end", children=[self._bolt, self._percent_label]),
            ],
        )

        self._space = Box(name="bat-tank-space")  # sets the tank's size
        self._space.connect("size-allocate", lambda *_: self._apply_fill())
        self._corner.connect("size-allocate", lambda *_: self._sync_text_colors())

        self.children = ClippingBox(
            name="bat-tank",
            children=Overlay(child=self._space, overlays=[self._fill, self._corner]),
        )

        self._animator = Animator(
            bezier_curve=CubicBezierCurves.EMPHASIS,
            duration=self.FILL_DURATION,
            tick_widget=self,
        )
        self._animator.connect("notify::value", self._on_tick)

        self.connect("map", self._on_map)
        self.connect("unmap", self._on_unmap)

        self.service.connect("battery-changed", self._on_battery_changed)
        charging = getattr(self.service, "bat_charging", None)
        if charging is not None:
            self._on_battery_changed(
                None, self.service.bat_percent, charging, animate=False
            )

    def _on_battery_changed(self, _sender, percent, is_charging, animate=True):
        if percent is None or percent < 0:
            return
        self._target = max(0.0, min(100.0, float(percent)))
        self._charging = bool(is_charging)
        self._percent_label.set_label(f"{round(self._target)}%")
        self._update_status()

        self._animator.pause()
        if not animate or not self.get_mapped():
            self._percent = self._target
            self._apply_fill()
            return
        self._animator.duration = self.FILL_DURATION * (
            0.5 if power_profiles_service.active_profile == "power-saver" else 1.0
        )
        self._animator.min_value = self._percent
        self._animator.max_value = self._target
        self._animator.value = self._percent
        self._animator.play()

    def _is_low(self) -> bool:
        return round(self._target) <= self.LOW_THRESHOLD and not self._charging

    def _update_status(self) -> bool:
        # psutil only knows "plugged in"; sysfs also knows plugged-in-but-
        # holding ("Not charging", e.g. a charge limit), so it wins when present
        status, to_full, to_empty = battery_times()
        charging = False
        if status == "Full" or (self._charging and round(self._target) >= 100):
            text = "Fully charged"
        elif status == "Not charging":
            text = "Plugged in · Not charging"
        elif self._charging:
            charging = True
            text = "Charging"
            if to_full:
                text += f" · {_format_hours(to_full)} to full"
        else:
            text = "Low battery" if self._is_low() else "On battery"
            if to_empty:
                text += f" · {_format_hours(to_empty)} left"
        self._status.set_label(text)

        self._bolt.set_visible(charging)
        for cls, on in (("charging", charging), ("low", self._is_low())):
            for widget in (self._fill, self._corner):
                (widget.add_style_class if on else widget.remove_style_class)(cls)
        return True  # keep the refresh timer going

    def _on_map(self, *_):
        self._update_status()
        if self._refresh_id is None:
            self._refresh_id = GLib.timeout_add_seconds(
                self.REFRESH_SECONDS, self._update_status
            )

    def _on_unmap(self, *_):
        if self._refresh_id is not None:
            GLib.source_remove(self._refresh_id)
            self._refresh_id = None

    def _on_tick(self, animator, _pspec):
        self._percent = max(0.0, min(100.0, animator.value))
        self._apply_fill()

    def _apply_fill(self):
        height = self._space.get_allocated_height()
        if height <= 1:
            return
        fill = round(height * self._percent / 100)
        if fill != self._fill.get_size_request()[1]:
            self._fill.set_size_request(-1, fill)

        # the number gets heavier, wider and rounder as the charge goes up
        p = self._percent / 100
        self._percent_label.set_variations(
            wght=round(400 + 500 * p), wdth=round(75 + 35 * p), ROND=round(100 * p)
        )
        self._sync_text_colors()

    def _sync_text_colors(self):
        # text goes dark once the fill covers its middle.
        corner_height = self._corner.get_allocated_height()
        if corner_height <= 1:
            return
        fill = self._fill.get_size_request()[1]
        for widget in (self._status, self._percent_label, self._bolt):
            alloc = widget.get_allocation()
            mid_from_bottom = corner_height - (alloc.y + alloc.height / 2)
            if fill >= mid_from_bottom:
                widget.add_style_class("on-fill")
            else:
                widget.remove_style_class("on-fill")
