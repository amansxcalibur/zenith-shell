import math
import cairo

from fabric.core.service import Service, Signal, Property

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # type: ignore


class WigglyScale(Gtk.DrawingArea, Service):
    MAX_AMPLITUDE = 2
    AMPLITUDE_SPEED = 24.0  # per second
    WAVE_SPEED = 3.0  # radians per second
    SLIDER_DIAMETER = 6
    DRAG_THRESHOLD_PX = 1
    HOLD_TO_DRAG_MS = 200

    @Signal
    def on_seek(self, ratio: float) -> None: ...

    @Signal
    def on_scrub(self, ratio: float) -> None: ...

    @Property(bool, default_value=False, flags="read-write")
    def dragging(self) -> bool:
        return self._dragging

    @dragging.setter
    def dragging(self, dragging: bool) -> None:
        self._dragging = dragging

    def __init__(self):
        super().__init__()
        self.phase = 0
        self.value = 0.0
        self.amplitude = self.MAX_AMPLITUDE
        self._dragging = False
        self._press = None  # (x, value before the press) while button 1 is held
        self._hold_source_id = None
        self._last_frame_time = None
        self.pause = False

        self.set_size_request(-1, 20)
        self.connect("draw", self.on_draw)

        # mouse events
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )

        self.connect("button-press-event", self.on_button_press)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("button-release-event", self.on_button_release)

        # none of these deliver a button release
        self.connect("grab-broken-event", self._cancel_press)
        self.connect("unmap", self._cancel_press)
        self.connect("notify::sensitive", self._cancel_press)

        self.add_tick_callback(self.update)  # matches screen refresh rate

        self.show_all()

    def update_value_from_x(self, x):
        # the inverse of on_draw, which keeps the slider centered on the pointer
        travel = self.get_allocated_width() - self.SLIDER_DIAMETER
        self.value = max(0.0, min(1.0, (x - self.SLIDER_DIAMETER / 2) / travel))
        self.queue_draw()

    def on_button_press(self, widget, event):
        if event.button != 1:
            return False
        # a double click also sends 2BUTTON_PRESS, with no release of its own
        if event.type == Gdk.EventType.BUTTON_PRESS:
            self._press = (event.x, self.value)
            self._hold_source_id = GLib.timeout_add(self.HOLD_TO_DRAG_MS, self._on_hold)
            self.update_value_from_x(event.x)
        return True

    def _on_hold(self):
        self._hold_source_id = None
        self.dragging = True
        return False

    def _end_hold_timer(self):
        if self._hold_source_id is not None:
            GLib.source_remove(self._hold_source_id)
            self._hold_source_id = None

    def update_value_from_signal(self, new_value):
        # the pointer owns the value until it lets go
        if self._press is None:
            self.value = min(1.0, new_value)
            self.queue_draw()

    def on_motion(self, widget, event):
        if self._press is not None:
            press_x, _value = self._press
            if not self.dragging and abs(event.x - press_x) >= self.DRAG_THRESHOLD_PX:
                self._end_hold_timer()
                self.dragging = True

            self.update_value_from_x(event.x)
            if self.dragging:
                self.on_scrub(self.value)

        cursor = Gdk.Cursor.new(Gdk.CursorType.HAND1)
        widget.get_window().set_cursor(cursor)

        return True

    def on_button_release(self, widget, event):
        if event.button != 1 or self._press is None:
            return False
        self._press = None
        self._end_hold_timer()
        self.on_seek(self.value)
        self.dragging = False
        return True

    def _cancel_press(self, *_):
        if self._press is None:
            return False
        self.value = self._press[1]
        self._press = None
        self._end_hold_timer()
        self.dragging = False
        self.queue_draw()
        return False

    def update(self, widget, frame_clock):
        # by elapsed time, so the wave runs the same on any refresh rate
        now = frame_clock.get_frame_time() / 1_000_000
        elapsed = now - (self._last_frame_time or now)
        self._last_frame_time = now

        flat = self.pause or self._press is not None
        target = 0 if flat else self.MAX_AMPLITUDE

        if self.amplitude != target:
            max_step = self.AMPLITUDE_SPEED * elapsed
            delta = target - self.amplitude
            self.amplitude += max(-max_step, min(max_step, delta))
        elif flat:
            return True  # nothing is moving, skip the redraw

        if not flat:
            self.phase += self.WAVE_SPEED * elapsed
        self.queue_draw()
        return True

    def on_draw(self, widget, cr):
        alloc_width = self.get_allocated_width()
        height = self.get_allocated_height()
        center_y = height / 2
        frequency = 0.3
        slider_diameter = self.SLIDER_DIAMETER
        stroke_width = 2

        # left edge of the slider, which stays fully inside the widget
        slider_x = round(self.value * max(0, alloc_width - slider_diameter))

        cr.set_line_cap(cairo.LINE_CAP_ROUND)  # rounded line ends
        cr.set_source_rgb(1, 1, 1)  # color here btw
        cr.set_line_width(stroke_width)

        # init_x = stroke_width
        init_y = center_y + self.amplitude * math.sin(
            (stroke_width * frequency) + self.phase
        )
        cr.move_to(stroke_width, init_y)
        for x in range(stroke_width, slider_x):
            y = center_y + self.amplitude * math.sin((x * frequency) + self.phase)
            cr.line_to(x, y)

        cr.stroke()

        # hex_color = get_css_variable(f'{info.ROOT_DIR}/styles/colors_player.css', '--foreground-player')
        # r, g, b = hex_to_rgb01(hex_color)
        # cr.set_source_rgb(r, g, b)

        rect_width = 6
        arc_radius = slider_diameter / 2
        self.draw_rounded_rect(cr, slider_x, height, rect_width, rect_width, arc_radius)
        cr.fill()

        cr.stroke()

        cr.set_source_rgba(1, 1, 1, 0.5)
        cr.set_line_width(stroke_width)

        # This is for anti aliasing. When line width becomes 1px and the position is not an integer, two lines of opacity 50% is drawn on two pixel rows.
        # This moves the line to make it pixel perfect hence not needing anti aliasing
        # cr.translate(0, 0.5)

        cr.move_to(slider_x + 2 * arc_radius, height / 2)
        cr.line_to(alloc_width, height / 2)

        cr.stroke()

    def draw_rounded_rect(self, cr, x, y, width, height, radius):
        cr.new_sub_path()
        cr.arc(x + width - radius, radius, radius, -math.pi, 0)
        cr.arc(x + width - radius, y - radius, radius, 0, -math.pi)
        cr.close_path()
