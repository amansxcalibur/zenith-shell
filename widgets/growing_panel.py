from collections.abc import Callable

from fabric.core.service import Signal
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button

from services.animator import Animator, CubicBezierCurves

from widgets.clipping_box import ClippingBox

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore


def get_natural_size(widget: Gtk.Widget) -> tuple[int, int]:
    _, natural = widget.get_preferred_size()
    return natural.width, natural.height


def build_button(**kwargs) -> Button:
    button = Button(**kwargs)
    button.set_can_focus(False)
    button.set_focus_on_click(False)
    return button


class GrowingPanel(Box):
    COLUMNS = 1
    BACKGROUND_FADE_RATE = 4.0
    FADE_RATE = 2.5  # items are gone before the last few pixels

    @Signal
    def picked(self, key: str) -> None: ...

    @Signal
    def resting_clicked(self) -> None: ...

    @Signal
    def collapsed(self) -> None: ...

    @property
    def is_collapsing(self) -> bool:
        return not self.is_open and self._progress > 0.0

    def __init__(self, padding: int, **kwargs):
        super().__init__(v_align="end", **kwargs)
        self.is_open = False
        self.current = ""
        self.items: dict[str, Button] = {}
        self._cursor = 0
        self._landing: str | None = None
        self._landing_shift = (0, 0)
        self._padding = padding
        self._progress = 0.0

        self.resting = self._build_resting()
        self.extras: list[Gtk.Widget] = []
        self.content = self._build_content()
        self.content.set_border_width(padding)
        self.add(self.content)
        for extra in self.extras:
            extra.set_no_show_all(True)
            extra.hide()

        self._animator = Animator(
            bezier_curve=CubicBezierCurves.EMPHASIS, duration=0.3, tick_widget=self
        )
        self._animator.connect("notify::value", self._on_tick)
        self._animator.connect("finished", self._on_finished)
        # ticks stop with the widget hidden
        self.connect("unmap", lambda *_: self._settle())

    def _build_resting(self) -> Button:
        raise NotImplementedError

    def _build_content(self) -> Box:
        raise NotImplementedError

    def _arrange(self) -> None:
        raise NotImplementedError

    def _refresh_resting(self) -> None:
        raise NotImplementedError

    def select(self, key: str) -> None:
        if self._landing is None:
            is_new = key != self.current
            self.current = key
            self._refresh_resting()
            if is_new and self.is_open:
                self._arrange()
                self._set_cursor(len(self.items) - 1)
        elif key != self._landing:
            self._land()
            self.select(key)

    def get_order(self) -> list[str]:
        return [key for key in self.items if key != self.current] + [self.current]

    def get_rest_size(self) -> tuple[int, int]:
        width, height = get_natural_size(self._get_anchor())
        return width + 2 * self._padding, height + 2 * self._padding

    def open(self) -> None:
        if self.is_open:
            return
        self._land()
        self.is_open = True
        self._arrange()
        for extra in self.extras:
            extra.show()
        self.add_style_class("expanded")
        self._set_cursor(len(self.items) - 1)
        self._animate_to(1.0)

    def close(self, landing: str | None = None) -> None:
        if not self.is_open:
            return
        self.is_open = False
        self._clear_cursor()
        if landing is not None and landing != self.current:
            self._landing = landing
            self._landing_shift = self._get_distance_to_rest(self.items[landing])
        self._animate_to(0.0)

    def _get_anchor(self) -> Button:
        return self.resting if self._landing is None else self.items[self._landing]

    def _get_distance_to_rest(self, item: Button) -> tuple[int, int]:
        if not self.get_mapped():
            return 0, 0
        x, y = item.translate_coordinates(
            self.resting, item.get_allocated_width(), item.get_allocated_height()
        )
        return (
            self.resting.get_allocated_width() - x,
            self.resting.get_allocated_height() - y,
        )

    def _land(self) -> None:
        if self._landing is None:
            return
        self.current, self._landing = self._landing, None
        self._landing_shift = (0, 0)
        self._refresh_resting()

    def move_cursor(self, dx: int, dy: int) -> None:
        if self.COLUMNS == 1 and dx:
            return
        target = self._cursor + dx + dy * self.COLUMNS
        if 0 <= target < len(self.items):
            self._set_cursor(target)

    def activate_cursor(self) -> None:
        self._pick(self.get_order()[self._cursor])

    def _pick(self, key: str) -> None:
        if self.is_open and self._get_button(key).get_sensitive():
            self.picked(key)

    def _get_button(self, key: str) -> Button:
        return self.resting if key == self.current else self.items[key]

    def _clear_cursor(self) -> None:
        for button in (self.resting, *self.items.values()):
            button.remove_style_class("cursor")

    def _set_cursor(self, index: int) -> None:
        self._clear_cursor()
        self._cursor = index
        self._get_button(self.get_order()[index]).add_style_class("cursor")

    def _animate_to(self, target: float) -> None:
        self._animator.pause()
        self._animator.min_value = self._progress
        self._animator.max_value = target
        if self.get_mapped():
            self._animator.play()
        else:
            self._settle()

    def _settle(self) -> None:
        self._animator.pause()
        self._progress = 1.0 if self.is_open else 0.0
        self._on_finished()

    def _on_tick(self, *_) -> None:
        self._progress = self._animator.value
        self._fade_items()
        self.queue_resize()

    def _on_finished(self, *_) -> None:
        if not self.is_open:
            self._land()
            self.remove_style_class("expanded")
            for extra in self.extras:
                extra.hide()
        self._fade_items()
        self.queue_resize()
        if not self.is_open:
            self.collapsed()

    def _get_opacity(self, rate: float) -> float:
        return min(1.0, max(0.0, self._progress) * rate)

    def _fade_items(self) -> None:
        anchor = self._get_anchor()
        opacity = self._get_opacity(self.FADE_RATE)
        for item in (self.resting, *self.items.values()):
            item.set_opacity(1.0 if item is anchor else opacity)

    def _get_grown_size(self) -> tuple[int, int]:
        rest, full = self.get_rest_size(), get_natural_size(self.content)
        width, height = (
            round(a + (max(a, b) - a) * self._progress)
            for a, b in zip(rest, full, strict=True)
        )
        return width, height

    def do_get_preferred_width(self):
        width, _ = self._get_grown_size()
        return width, width

    def do_get_preferred_height(self):
        _, height = self._get_grown_size()
        return height, height

    def do_get_preferred_width_for_height(self, _height):
        return self.do_get_preferred_width()

    def do_get_preferred_height_for_width(self, _width):
        return self.do_get_preferred_height()

    def do_size_allocate(self, alloc):
        self.set_allocation(alloc)
        natural_width, natural_height = get_natural_size(self.content)
        rect = alloc.copy()
        rect.width = max(natural_width, alloc.width)
        rect.height = max(natural_height, alloc.height)
        # pinned to the bottom right, the rest is clipped away
        shift_x, shift_y = self._landing_shift
        left = 1.0 - self._progress
        rect.x = alloc.x + alloc.width - rect.width + round(shift_x * left)
        rect.y = alloc.y + alloc.height - rect.height + round(shift_y * left)
        self.content.size_allocate(rect)

    def do_draw(self, cr):
        context = self.get_style_context()
        width, height = self.get_allocated_width(), self.get_allocated_height()
        radius = context.get_property("border-radius", self.get_state_flags())
        cr.save()
        ClippingBox.render_shape(cr, width, height, radius)
        cr.clip()
        # a css transition would lag behind theme changes
        cr.push_group()
        Gtk.render_background(context, cr, 0, 0, width, height)
        cr.pop_group_to_source()
        cr.paint_with_alpha(self._get_opacity(self.BACKGROUND_FADE_RATE))
        self.propagate_draw(self.content, cr)
        cr.restore()
        return False


class ListPanel(GrowingPanel):
    MAX_CHARS = 18

    def _build_row(self, on_clicked) -> Button:
        return build_button(
            name="panel-row",
            child=Label(
                h_align="end",
                h_expand=True,
                ellipsization="end",
                max_chars_width=self.MAX_CHARS,
            ),
            on_clicked=on_clicked,
        )

    def _build_resting(self) -> Button:
        return self._build_row(lambda *_: self.resting_clicked())

    def _build_content(self) -> Box:
        self._rows = Box(orientation="v")
        self.extras = [self._rows]
        return Box(orientation="v", children=[self._rows, self.resting])

    def set_options(self, options: dict[str, str], current: str) -> None:
        self._options = options
        if list(options) != list(self.items):
            for row in self._rows.get_children():
                self._rows.remove(row)
            self.items = {}
            for key, text in options.items():
                row = self._build_row(lambda _, key=key: self._pick(key))
                row.get_child().set_label(text)
                row.show_all()
                self._rows.add(row)
                self.items[key] = row
        self.select(current)

    def disable_option(self, key: str, reason: str) -> None:
        self.items[key].set_sensitive(False)
        self.items[key].set_tooltip_text(reason)

    def _refresh_resting(self) -> None:
        self.resting.get_child().set_label(self._options[self.current])

    def _arrange(self) -> None:
        for key, row in self.items.items():
            row.set_visible(key != self.current)


class Backdrop(Box):
    def __init__(self, get_painted_height: Callable[[], int], **kwargs):
        super().__init__(**kwargs)
        self._get_painted_height = get_painted_height

    def do_draw(self, cr):
        context = self.get_style_context()
        width, full_height = self.get_allocated_width(), self.get_allocated_height()
        height = min(self._get_painted_height(), full_height)
        for render in (Gtk.render_background, Gtk.render_frame):
            render(context, cr, 0, full_height - height, width, height)
        for child in self.get_children():
            self.propagate_draw(child, cr)
        return False
