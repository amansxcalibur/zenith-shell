from collections.abc import Callable

from fabric.widgets.box import Box
from fabric.widgets.label import Label

from services.animator import Animator

from gi.repository import GLib, Gtk  # type: ignore

# Rescans and refreshes can finish within a frame or two, keep the feedback on
# screen long enough for the user to register that something actually happened.
MIN_BUSY_MS = 900

_FADE_CURVE = (0.4, 0.0, 0.2, 1.0)


def menu_placeholder(text: str) -> Label:
    return Label(
        label=text,
        style_classes=["tile-menu-placeholder"],
        h_expand=True,
    )


class TileMenuLoader(Box):
    """The bar under a tile menu's title, doubling as an indeterminate loader.

    Several operations can overlap (a scan while connecting), so each one holds
    the loader through its own key and it keeps running until all have let go.
    """

    CYCLE_SECONDS = 1.4
    FADE_SECONDS = 0.2
    # share of the cycle by which the tail starts moving and the head stops,
    # the segment stretches in the middle and shrinks into the end of the bar
    STAGGER = 0.25

    def __init__(self, **kwargs):
        super().__init__(name="tile-menu-separator", h_align="center", **kwargs)
        self._keys: set[str] = set()
        self._running = False
        self._phase = 0.0
        self._alpha = 0.0
        self._started_at = 0
        self._tick_id: int | None = None
        self._last_frame_time = 0
        self._stop_id: int | None = None

        self.connect("destroy", lambda *_: self._clear_stop_timer())

    def set_busy(self, key: str, busy: bool) -> None:
        if busy:
            self._keys.add(key)
        else:
            self._keys.discard(key)

        if self._keys:
            self._clear_stop_timer()
            self._start()
        elif self._running and self._stop_id is None:
            elapsed_ms = (GLib.get_monotonic_time() - self._started_at) // 1000
            self._stop_id = GLib.timeout_add(
                max(0, MIN_BUSY_MS - elapsed_ms), self._on_stop_timeout
            )

    def _clear_stop_timer(self) -> None:
        if self._stop_id is not None:
            GLib.source_remove(self._stop_id)
            self._stop_id = None

    def _on_stop_timeout(self) -> bool:
        self._stop_id = None
        self._running = False
        return False

    def _start(self) -> None:
        if self._running:
            return

        self._running = True
        self._started_at = GLib.get_monotonic_time()
        if self._tick_id is None:
            self._phase = 0.0
            self._last_frame_time = 0
            self._tick_id = self.add_tick_callback(self._on_tick)

    def _on_tick(self, _widget, frame_clock) -> bool:
        now = frame_clock.get_frame_time()
        # don't jump after the menu has been closed for a while
        dt = min((now - self._last_frame_time) / 1_000_000, 0.1)
        if self._last_frame_time == 0:
            dt = 0.0
        self._last_frame_time = now

        self._phase = (self._phase + dt / self.CYCLE_SECONDS) % 1.0

        step = dt / self.FADE_SECONDS
        if self._running:
            self._alpha = min(1.0, self._alpha + step)
        else:
            self._alpha = max(0.0, self._alpha - step)

        self.queue_draw()

        if not self._running and self._alpha == 0.0:
            self._tick_id = None
            return False
        return True

    @staticmethod
    def _ease(t: float) -> float:
        return t * t * (3 - 2 * t)

    def do_draw(self, cr) -> bool:
        Box.do_draw(self, cr)

        if self._alpha <= 0.0:
            return False

        span = 1.0 - self.STAGGER
        head = self._ease(min(self._phase / span, 1.0))
        tail = self._ease(max((self._phase - self.STAGGER) / span, 0.0))

        width = self.get_allocated_width()
        height = self.get_allocated_height()
        x = tail * width
        length = (head - tail) * width
        if length < 0.5:
            return False

        context = self.get_style_context()
        color = context.get_color(self.get_state_flags())
        cr.set_source_rgba(
            color.red, color.green, color.blue, color.alpha * self._alpha
        )

        radius = min(height, length) / 2
        cr.new_sub_path()
        cr.arc(x + length - radius, radius, radius, -1.5708, 0)
        cr.arc(x + length - radius, height - radius, radius, 0, 1.5708)
        cr.arc(x + radius, height - radius, radius, 1.5708, 3.1416)
        cr.arc(x + radius, radius, radius, 3.1416, 4.7124)
        cr.close_path()
        cr.fill()
        return False


class ContentFader:
    """Fades widgets out, lets the caller rebuild them, then fades them back in."""

    DIM_OPACITY = 0.4
    DIM_SECONDS = 0.18
    OUT_SECONDS = 0.12
    IN_SECONDS = 0.22

    def __init__(self, *widgets: Gtk.Widget):
        self.widgets = widgets
        self._opacity = 1.0
        self._animator: Animator | None = None
        self._populate: Callable[[], None] | None = None

    def dim(self) -> None:
        """Keep the old content readable while the new content is being fetched."""
        if self._populate is None and self._is_mapped():
            self._fade_to(self.DIM_OPACITY, self.DIM_SECONDS)

    def swap(self, populate: Callable[[], None]) -> None:
        if not self._is_mapped():
            # no one's watching and ticks may not fire, there's nothing to fade
            self._stop()
            self._populate = None
            populate()
            self._set_opacity(1.0)
            return

        fading_out = self._populate is not None
        self._populate = populate  # the latest content wins
        if not fading_out:
            self._fade_to(0.0, self.OUT_SECONDS, self._on_faded_out)

    def fade_in(self) -> None:
        self._set_opacity(0.0)
        self._fade_to(1.0, self.IN_SECONDS)

    def _on_faded_out(self) -> None:
        populate, self._populate = self._populate, None
        try:
            populate()
        finally:
            self._fade_to(1.0, self.IN_SECONDS)

    def _is_mapped(self) -> bool:
        return any(widget.get_mapped() for widget in self.widgets)

    def _set_opacity(self, opacity: float) -> None:
        self._opacity = opacity
        for widget in self.widgets:
            widget.set_opacity(opacity)

    def _stop(self) -> None:
        if self._animator is not None:
            self._animator.stop()
            self._animator = None

    def _fade_to(
        self, target: float, duration: float, on_done: Callable[[], None] | None = None
    ) -> None:
        self._stop()

        def on_finished(*_):
            self._animator = None
            if on_done:
                on_done()

        # no tick widget: a fade has to finish even if the menu gets closed midway
        self._animator = Animator(
            bezier_curve=_FADE_CURVE,
            duration=duration,
            min_value=self._opacity,
            max_value=target,
            notify_value=lambda animator, *_: self._set_opacity(animator.value),
            on_finished=on_finished,
        )
        self._animator.play()
