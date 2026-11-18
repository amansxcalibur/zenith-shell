import calendar
import datetime

from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.eventbox import EventBox
from fabric.utils.helpers import invoke_repeater

import icons
from modules.wavy_clock import WavyClock
from utils.cursor import add_hover_cursor
from widgets.material_label import MaterialFontLabel, MaterialIconLabel

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # type: ignore

FONT = "Google Sans Flex"
ROWS = 6
CLOCK_SIZE = 200
TILE_GAP = 8


class CalendarPopup(Box):
    def __init__(self, first_weekday: int = calendar.SUNDAY, **kwargs):
        super().__init__(
            name="calendar-popup", orientation="h", spacing=TILE_GAP, **kwargs
        )
        self._calendar = calendar.Calendar(first_weekday)
        self._today = datetime.date.today()
        self._shown = (self._today.year, self._today.month)
        self._scroll_acc = 0.0

        # header: today
        self.weekday_label = MaterialFontLabel(
            name="calendar-weekday",
            text="",
            font_family=FONT,
            wght=500,
            h_align="start",
        )
        self.date_label = MaterialFontLabel(
            name="calendar-date", text="", font_family=FONT, wght=700, h_align="start"
        )
        self.week_label = MaterialFontLabel(
            name="calendar-week", text="", font_family=FONT, wght=600
        )
        date_tile = Box(
            style_classes="calendar-tile",
            children=[
                Box(
                    orientation="v",
                    h_expand=True,
                    v_align="center",
                    children=[self.weekday_label, self.date_label],
                ),
                Box(v_align="start", children=self.week_label),
            ],
        )

        # month navigation
        self.month_label = MaterialFontLabel(
            name="calendar-month", text="", font_family=FONT, wght=650
        )
        month_btn = add_hover_cursor(
            Button(
                name="calendar-month-btn",
                child=self.month_label,
                tooltip_text="Back to today",
                on_clicked=lambda *_: self.show_today(),
            )
        )
        nav = Box(
            name="calendar-nav",
            children=[
                month_btn,
                Box(h_expand=True),
                self._nav_button(icons.material.chevron_left.symbol(), -1),
                self._nav_button(icons.material.chevron_right.symbol(), 1),
            ],
        )

        # day grid
        self.grid = Gtk.Grid(
            name="calendar-grid",
            column_homogeneous=True,
            row_homogeneous=True,
            visible=True,
        )
        for col, day in enumerate(self._calendar.iterweekdays()):
            self.grid.attach(
                MaterialFontLabel(
                    text=calendar.day_abbr[day][:2],
                    font_family=FONT,
                    wght=600,
                    style_classes="calendar-weekday-name",
                ),
                col,
                0,
                1,
                1,
            )
        self.day_labels: list[MaterialFontLabel] = []
        for i in range(ROWS * 7):
            label = MaterialFontLabel(
                text="", font_family=FONT, wght=500, style_classes="calendar-day"
            )
            self.day_labels.append(label)
            self.grid.attach(label, i % 7, 1 + i // 7, 1, 1)

        grid_box = EventBox(child=self.grid)
        grid_box.add_events(
            Gdk.EventMask.SCROLL_MASK | Gdk.EventMask.SMOOTH_SCROLL_MASK
        )
        grid_box.connect("scroll-event", self._on_scroll)

        self.clock = WavyClock(size=(CLOCK_SIZE, CLOCK_SIZE))
        clock_tile = Box(
            name="calendar-clock",
            style_classes="calendar-tile",
            v_expand=True,
            children=self.clock,
        )
        self.clock.set_valign(Gtk.Align.CENTER)
        self.clock.set_vexpand(True)

        month_tile = Box(
            name="calendar-month-tile",
            style_classes="calendar-tile",
            orientation="v",
            spacing=6,
            children=[nav, grid_box],
        )

        self.children = [
            Box(orientation="v", spacing=TILE_GAP, children=[date_tile, clock_tile]),
            month_tile,
        ]

        self._refresh()
        # catch the date rolling over at midnight
        invoke_repeater(30_000, self._check_date)

    def _nav_button(self, icon: str, step: int) -> Button:
        return add_hover_cursor(
            Button(
                style_classes="calendar-nav-btn",
                child=MaterialIconLabel(icon_text=icon, FILL=0),
                on_clicked=lambda *_: self.shift_month(step),
            )
        )

    def _on_scroll(self, _, event):
        match event.direction:
            case Gdk.ScrollDirection.UP:
                self.shift_month(-1)
            case Gdk.ScrollDirection.DOWN:
                self.shift_month(1)
            case Gdk.ScrollDirection.SMOOTH:
                # touchpads send many small deltas; step once per full notch
                self._scroll_acc += event.get_scroll_deltas()[2]
                while abs(self._scroll_acc) >= 1:
                    step = 1 if self._scroll_acc > 0 else -1
                    self._scroll_acc -= step
                    self.shift_month(step)
        return True

    def _check_date(self) -> bool:
        today = datetime.date.today()
        if today != self._today:
            self._today = today
            self.show_today()
        return True

    def shift_month(self, step: int):
        year, month = self._shown
        index = year * 12 + (month - 1) + step
        self._shown = (index // 12, index % 12 + 1)
        self._refresh()

    def show_today(self):
        self._shown = (self._today.year, self._today.month)
        self._refresh()

    def _refresh(self):
        today = self._today
        self.weekday_label.set_text(today.strftime("%A"))
        self.date_label.set_text(f"{today:%B} {today.day}")
        self.week_label.set_text(f"W{today.isocalendar().week}")

        year, month = self._shown
        self.month_label.set_text(f"{calendar.month_name[month]} {year}")
        if (year, month) == (today.year, today.month):
            self.month_label.add_style_class("current")
        else:
            self.month_label.remove_style_class("current")

        days = list(self._calendar.itermonthdates(year, month))
        # pad to a fixed 6 weeks
        while len(days) < ROWS * 7:
            days.append(days[-1] + datetime.timedelta(days=1))

        for label, day in zip(self.day_labels, days):
            label.set_text(str(day.day))
            for cls, on in (
                ("today", day == today),
                ("other-month", day.month != month),
            ):
                if on:
                    label.add_style_class(cls)
                else:
                    label.remove_style_class(cls)
