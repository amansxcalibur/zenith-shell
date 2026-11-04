import math
import cairo

from fabric.core.service import Service, Signal, Property

from config.info import ROOT_DIR
from utils.colors import get_css_variable, hex_to_rgb01

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib  # type: ignore


class WigglyScale(Gtk.DrawingArea, Service):
    MAX_AMPLITUDE = 3
    AMPLITUDE_SPEED = 12.0  # per second
    WAVE_SPEED = 4.0  # radians per second
    WAVELENGTH = 32
    STROKE_WIDTH = 4
    TRACK_GAP = 4  # between the handle and either track
    INACTIVE_ALPHA = 0.3
    HANDLE_WIDTH = 4
    HANDLE_PRESSED_WIDTH = 2
    HANDLE_SPEED = 16.0  # px per second
    HEIGHT = 32
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
        self._handle_width = self.HANDLE_WIDTH
        self._color = (1.0, 1.0, 1.0)
        self._dragging = False
        self._press = None  # (x, value before the press) while button 1 is held
        self._hold_source_id = None
        self._last_frame_time = None
        self.pause = False

        self.set_size_request(-1, self.HEIGHT)
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

    def set_color(self, rgb: tuple[float, float, float]):
        self._color = rgb
        self.queue_draw()

    def update_value_from_x(self, x):
        # the inverse of on_draw, which keeps the handle centered on the pointer
        travel = self.get_allocated_width() - self.HANDLE_WIDTH
        self.value = max(0.0, min(1.0, (x - self.HANDLE_WIDTH / 2) / travel))
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

        pressed = self._press is not None
        flat = self.pause or pressed
        target = 0 if flat else self.MAX_AMPLITUDE
        handle_target = self.HANDLE_PRESSED_WIDTH if pressed else self.HANDLE_WIDTH

        if self.amplitude == target and self._handle_width == handle_target and flat:
            return True  # nothing is moving, skip the redraw

        self.amplitude = self._step_towards(
            self.amplitude, target, self.AMPLITUDE_SPEED * elapsed
        )
        self._handle_width = self._step_towards(
            self._handle_width, handle_target, self.HANDLE_SPEED * elapsed
        )

        if not flat:
            self.phase += self.WAVE_SPEED * elapsed
        self.queue_draw()
        return True

    @staticmethod
    def _step_towards(current, target, max_step):
        return current + max(-max_step, min(max_step, target - current))

    def on_draw(self, widget, cr):
        width = self.get_allocated_width()
        height = self.get_allocated_height()
        center_y = height / 2
        cap = self.STROKE_WIDTH / 2

        # the handle stays fully inside the widget at either end
        travel = max(0, width - self.HANDLE_WIDTH)
        handle_x = round(self.HANDLE_WIDTH / 2 + self.value * travel)
        clearance = self._handle_width / 2 + self.TRACK_GAP + cap

        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_line_width(self.STROKE_WIDTH)

        cr.set_source_rgb(*self._color)
        self._draw_active_track(cr, cap, handle_x - clearance, center_y)

        inactive_start = handle_x + clearance
        inactive_end = width - cap
        self._draw_handle(cr, handle_x, height)

        if inactive_start < inactive_end:
            # the stop indicator marks the end of the track
            if inactive_end - inactive_start >= self.STROKE_WIDTH:
                cr.arc(inactive_end, center_y, cap, 0, 2 * math.pi)
                cr.fill()

            cr.set_source_rgba(*self._color, self.INACTIVE_ALPHA)
            cr.move_to(inactive_start, center_y)
            cr.line_to(inactive_end, center_y)
            cr.stroke()

    def _draw_active_track(self, cr, start, end, center_y):
        if end < start:
            return

        frequency = 2 * math.pi / self.WAVELENGTH
        # the wave settles onto the center line before it reaches the handle
        taper = self.WAVELENGTH / 2

        def wave_y(x):
            envelope = min(1.0, (end - x) / taper)
            offset = math.sin(x * frequency + self.phase)
            return center_y + self.amplitude * envelope * offset

        cr.move_to(start, wave_y(start))
        for x in range(math.ceil(start), math.ceil(end)):
            cr.line_to(x, wave_y(x))
        cr.line_to(end, center_y)
        cr.stroke()

    def _draw_handle(self, cr, center_x, height):
        radius = self._handle_width / 2
        cr.new_sub_path()
        cr.arc(center_x, radius, radius, -math.pi, 0)
        cr.arc(center_x, height - radius, radius, 0, math.pi)
        cr.close_path()
        cr.fill()


class WigglyArrow(Gtk.DrawingArea, Service):
    # keeping this a static wiggly arrow for now

    @Signal
    def on_seek(self, ratio: float) -> None: ...

    @Property(bool, default_value=False, flags="read-write")
    def dragging(self) -> bool:
        return self._dragging

    @dragging.setter
    def dragging(self, dragging: bool) -> None:
        self._dragging = dragging

    def __init__(
        self,
        dark: bool = False,
        override_color: tuple[float, float, float] | None = None,
    ):
        super().__init__()
        self.phase = 0
        self.value = 1.0
        self.amplitude = 2
        self._dragging = False
        self.pause = False
        self.speed = 0.05

        self.dark = dark
        self._override_color: tuple[float, float, float] | None = override_color

        self.set_size_request(-1, 20)
        self.connect("draw", self.on_draw)

        # mouse events
        # self.add_events(
        #     Gdk.EventMask.BUTTON_PRESS_MASK
        #     | Gdk.EventMask.BUTTON_RELEASE_MASK
        #     | Gdk.EventMask.POINTER_MOTION_MASK
        # )

        # self.connect("button-press-event", self.on_button_press)
        # self.connect("motion-notify-event", self.on_motion)
        # self.connect("button-release-event", self.on_button_release)

        self.add_tick_callback(self.update)  # matches screen refresh rate

        self.show_all()

    def animate_amplitude_to(self, *_):
        if abs(self.amplitude - self.amplitude_target) < 0.01:
            self.amplitude = self.amplitude_target
            self.queue_draw()
            return False
        else:
            self.amplitude += self.amplitude_step
            self.queue_draw()
            return True

    def update_amplitude(self, decrease):
        if decrease:
            self.amplitude_target = 0
            self.amplitude_step = (0 - self.amplitude) / 10.0
        else:
            self.amplitude_target = 2
            self.amplitude_step = (2 - self.amplitude) / 10.0

        self.add_tick_callback(
            self.animate_amplitude_to
        )  # animation stops when False is returned btw

    def update_value_from_x(self, x):
        width = self.get_allocated_width()
        self.value = max(0.0, min(1.0, x / width))
        self.on_seek(self.value)
        self.queue_draw()

    def on_button_press(self, widget, event):
        self.dragging = True
        self.update_amplitude(True)
        self.update_value_from_x(event.x)
        return True

    def update_value_from_signal(self, new_value):
        self.value = min(1.0, new_value)

    def on_motion(self, widget, event):
        if self.dragging and not self.pause:
            self.update_value_from_x(event.x)

        cursor = Gdk.Cursor.new(Gdk.CursorType.HAND1)
        widget.get_window().set_cursor(cursor)

        return True

    def on_button_release(self, widget, event):
        if self.pause == False:
            self.dragging = False
            self.update_amplitude(False)
        return True

    def update(self, *_):
        if self.dragging == False:
            self.phase += self.speed
            self.queue_draw()
        return True

    def on_draw(self, widget, cr):
        alloc_width = self.get_allocated_width()
        height = self.get_allocated_height()
        center_y = height / 2

        frequency = 0.3
        slider_diameter = 6
        stroke_width = 2
        arc_radius = slider_diameter / 2

        width = int(alloc_width * self.value) - slider_diameter + 1
        width = max(width, stroke_width + 1)

        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgb(*self._get_color())
        cr.set_line_width(stroke_width)

        init_x = stroke_width
        init_y = center_y + self.amplitude * math.sin((init_x * frequency) + self.phase)
        cr.move_to(init_x, init_y)

        last_x = init_x
        last_y = init_y

        settle_len = int(height / 2)
        settle_start_x = max(init_x, width - settle_len)

        # ---- pure sine section ----
        for x in range(init_x, settle_start_x):
            y = center_y + self.amplitude * math.sin((x * frequency) + self.phase)
            cr.line_to(x, y)
            last_x, last_y = x, y

        # ---- settling arc (no crossing x-axis, flat ending) ----
        settle_steps = width - settle_start_x - int(arc_radius)
        if settle_steps > 0:
            for i in range(settle_steps + 1):
                t = i / settle_steps  # 0 -> 1

                # smoothstep for velocity kill
                # smooth = 1 - (3 * t * t - 2 * t * t * t)

                # cosine easing ensures horizontal tangent at end
                y = center_y + (last_y - center_y) * 1 * math.cos(t * math.pi / 2)

                x = settle_start_x + i
                cr.line_to(x, y)

                last_x, last_y = x, y

        cr.stroke()

        # ---- arrow head ----
        rect_width = 6
        self.draw_arrow_head(cr, last_x, height, rect_width, rect_width, arc_radius)
        cr.stroke()

        # ---- trailing flat line ----
        # cr.set_source_rgba(1, 1, 1, 0.5)
        # cr.set_line_width(stroke_width)

        # cr.move_to(last_x + 2 * arc_radius, center_y)
        # cr.line_to(alloc_width, center_y)
        # cr.stroke()

    def draw_arrow_head(self, cr, x, y, width, height, radius):
        x = x - y / 4

        cr.new_path()
        cr.move_to(x + 3 * y / 4 - radius, y / 2)
        cr.line_to(x + radius, radius)
        cr.move_to(x + 3 * y / 4 - radius, y / 2)
        cr.line_to(x + radius, y - radius)

    def _get_color(self) -> tuple[float, float, float]:
        if self._override_color is not None:
            return self._override_color

        hex_color = get_css_variable(
            f"{ROOT_DIR}/styles/colors.css",
            "--on-primary" if self.dark else "--primary",
        )
        return hex_to_rgb01(hex_color)

    def set_color(self, rgb: tuple[float, float, float] | None, redraw: bool = True):
        self._override_color = rgb
        if redraw:
            self.queue_draw()
