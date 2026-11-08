import math
from collections.abc import Callable, Iterable

import cairo
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, Gtk, Pango, PangoCairo  # type: ignore

from icons.icon import Icon

ICON_FAMILY = "Material Symbols Rounded"
ICON_SIZE = 26  # px
ICON_PADDING = 8  # px between the icon and the track's top, or the handle
VALUE_SIZE = 12  # px
STOP_SIZE = 4  # px
BUBBLE_HEIGHT = 22  # px
BUBBLE_GAP = 12  # px between the bubble and the handle, so its gap shows


def _font(family: str | None, px: int, bold: bool = False, filled: bool = False):
    desc = Pango.FontDescription()
    if family:
        desc.set_family(family)
    desc.set_absolute_size(px * Pango.SCALE)
    if bold:
        desc.set_weight(Pango.Weight.BOLD)
    if filled:
        desc.set_variations("FILL=1")
    return desc


class TrackDecor:
    def __init__(
        self,
        scale: Gtk.Scale,
        icon: Callable[[], Icon],
        value_text: Callable[[], str] | None = None,
        stops: Iterable[float] = (),
    ):
        self.scale = scale
        self.icon = icon
        self.value_text = value_text or (lambda: str(round(scale.get_value() * 100)))
        self.stops = tuple(stops)
        self.dragging = False
        self.hovered = False

        scale.connect_after("draw", self._draw)
        scale.connect("button-press-event", self._on_press, True)
        scale.connect("button-release-event", self._on_press, False)
        scale.connect("enter-notify-event", self._on_hover, True)
        scale.connect("leave-notify-event", self._on_hover, False)

    def refresh(self) -> None:
        self.scale.queue_draw()

    def _on_press(self, _widget, event, pressed: bool) -> bool:
        if event.button == 1:
            self.dragging = pressed
            self.scale.queue_draw()
        return False

    def _on_hover(self, _widget, event, hovered: bool) -> bool:
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.hovered = hovered
            self.scale.queue_draw()
        return False

    def _at(self, value: float) -> float:
        """Where the handle's middle sits at value."""
        track = self.scale.get_range_rect()
        start, end = self.scale.get_slider_range()
        handle = end - start
        adjustment = self.scale.get_adjustment()
        low, high = adjustment.get_lower(), adjustment.get_upper()
        fraction = (value - low) / (high - low) if high > low else 0
        if self.scale.get_inverted():
            fraction = 1 - fraction
        return track.y + (track.height - handle) * fraction + handle / 2

    def _covered(self, y: float) -> bool:
        # the fill runs from the handle to the bottom of an inverted track
        start, end = self.scale.get_slider_range()
        edge = (start + end) / 2
        return y > edge if self.scale.get_inverted() else y < edge

    def _color(self, *classes: str, prop: str = "color") -> Gdk.RGBA:
        context = self.scale.get_style_context()
        context.save()
        for name in classes:
            context.add_class(name)
        state = context.get_state()
        color = (
            context.get_color(state)
            if prop == "color"
            else context.get_property(prop, state)
        )
        context.restore()
        return color

    def _ink(self, y: float) -> Gdk.RGBA:
        return self._color("on-fill") if self._covered(y) else self._color()

    def _value_font(self):
        # the theme's family, at the value's own size
        context = self.scale.get_style_context()
        family = context.get_property("font", context.get_state()).get_family()
        return _font(family, VALUE_SIZE, bold=True)

    @staticmethod
    def _layout(cr, text: str, desc, glyph: bool = False):
        layout = PangoCairo.create_layout(cr)
        layout.set_font_description(desc)
        layout.set_text(text, -1)
        ink, logical = layout.get_pixel_extents()
        return layout, ink if glyph else logical

    def _draw(self, _widget, cr: cairo.Context) -> bool:
        if self.scale.get_orientation() != Gtk.Orientation.VERTICAL:
            return False
        track = self.scale.get_range_rect()
        if track.width <= 0 or track.height <= 0:
            return False
        centre = track.x + track.width / 2
        handle_start, handle_end = self.scale.get_slider_range()

        def clear_of_handle(top: float, bottom: float) -> bool:
            return bottom < handle_start - 2 or top > handle_end + 2

        for stop in self.stops:
            y = self._at(stop)
            if clear_of_handle(y - STOP_SIZE, y + STOP_SIZE):
                Gdk.cairo_set_source_rgba(cr, self._ink(y))
                cr.arc(centre, y, STOP_SIZE / 2, 0, 2 * math.pi)
                cr.fill()

        # the icon tops the track; with the handle up there, it sits just past it
        layout, ink = self._layout(
            cr,
            self.icon().symbol(),
            _font(ICON_FAMILY, ICON_SIZE, filled=True),
            glyph=True,
        )
        top = track.y + ICON_PADDING
        below = handle_end  # where the space past the handle starts
        if not clear_of_handle(top, top + ink.height):
            # from where the fill starts: the handle's range runs past what's
            # drawn of it, into its bottom margin
            top = (handle_start + handle_end) / 2 + ICON_PADDING
            below = top + ink.height
        Gdk.cairo_set_source_rgba(cr, self._ink(top + ink.height / 2))
        cr.move_to(centre - ink.width / 2 - ink.x, top - ink.y)
        PangoCairo.show_layout(cr, layout)

        if self.dragging or self.hovered:
            self._draw_bubble(cr, track, centre, handle_start, below)
        return False

    def _draw_bubble(self, cr, track, centre, handle_start, below):
        layout, ink = self._layout(cr, self.value_text(), self._value_font())
        width = max(ink.width + 12, BUBBLE_HEIGHT)
        # above the handle, or below it when there's no room
        top = handle_start - BUBBLE_GAP - BUBBLE_HEIGHT
        if top < track.y:
            top = below + BUBBLE_GAP
        left = centre - width / 2

        radius = BUBBLE_HEIGHT / 2
        cr.new_sub_path()
        cr.arc(left + width - radius, top + radius, radius, -math.pi / 2, math.pi / 2)
        cr.arc(left + radius, top + radius, radius, math.pi / 2, 3 * math.pi / 2)
        cr.close_path()
        Gdk.cairo_set_source_rgba(cr, self._color("bubble", prop="background-color"))
        cr.fill()

        Gdk.cairo_set_source_rgba(cr, self._color("bubble"))
        cr.move_to(
            centre - ink.width / 2 - ink.x,
            top + (BUBBLE_HEIGHT - ink.height) / 2 - ink.y,
        )
        PangoCairo.show_layout(cr, layout)
