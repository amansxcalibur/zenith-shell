import cairo

from fabric.widgets.box import Box
from fabric.widgets.shapes import Corner
from fabric.widgets.shapes.corner import CornerOrientation

from config.info import IS_WAYLAND
from utils.helpers import keep_window

if IS_WAYLAND:
    from fabric.widgets.wayland import WaylandWindow as Window
    from gi.repository import GtkLayerShell  # type: ignore
else:
    from widgets.overrides import PatchedX11Window as Window

from gi.repository import Gdk  # type: ignore

from widgets.window_shape import shape_window


def build_corners_region(width: int, height: int, radius: int) -> cairo.Region:
    # the same shape Corner draws, rendered 1 bit so the window can be cut to it
    region = cairo.Region()
    if radius <= 0:
        return region
    for orientation, x, y in (
        (CornerOrientation.TOP_LEFT, 0, 0),
        (CornerOrientation.TOP_RIGHT, width - radius, 0),
        (CornerOrientation.BOTTOM_LEFT, 0, height - radius),
        (CornerOrientation.BOTTOM_RIGHT, width - radius, height - radius),
    ):
        surface = cairo.ImageSurface(cairo.FORMAT_A1, radius, radius)
        cr = cairo.Context(surface)
        Corner.render_shape(cr, radius, radius, orientation)
        cr.fill()
        corner = Gdk.cairo_region_create_from_surface(surface)
        corner.translate(x, y)
        region.union(corner)
    return region


class MyCorner(Box):
    def __init__(self, corner, radius: int):
        super().__init__(
            name="corner-container",
            children=Corner(
                name="corner",
                orientation=corner,
                size=radius,
            ),
        )


class Corners(Window):
    def __init__(self, radius: int):
        self._radius = radius
        self._shaped_size: tuple[int, int] | None = None
        if IS_WAYLAND:
            super().__init__(
                layer="top",
                keyboard_mode="none",
                anchor="top bottom left right",
                exclusivity="none",
                margin=(0, 0, 0, 0),
                pass_through=True,
                visible=True,
                all_visible=True,
            )
            GtkLayerShell.set_exclusive_zone(self, -1)
        else:
            super().__init__(
                layer="top",
                geometry="top",
                type_hint="normal",
                focusable=False,
                visible=True,
                pass_through=True,
                all_visible=True,
            )

        display = Gdk.Display.get_default()
        monitor = display.get_monitor_at_window(self.get_window())
        geo = monitor.get_geometry()

        self.set_size_request(geo.width, geo.height)

        self.all_corners = Box(
            orientation="v",
            pass_through=True,
            focusable=False,
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            children=[
                Box(
                    name="top-corners",
                    orientation="h",
                    h_align="fill",
                    children=[
                        MyCorner("top-left", radius),
                        Box(h_expand=True),
                        MyCorner("top-right", radius),
                    ],
                ),
                Box(v_expand=True),
                Box(
                    name="bottom-corners",
                    orientation="h",
                    h_align="fill",
                    children=[
                        MyCorner("bottom-left", radius),
                        Box(h_expand=True),
                        MyCorner("bottom-right", radius),
                    ],
                ),
            ],
        )

        self.add(self.all_corners)

        self.connect("delete-event", self.on_delete_event)
        # without alpha the full screen window would paint black, so it keeps only the corners
        self.connect("size-allocate", lambda *_: self._update_shape())
        self.connect_after("map-event", lambda *_: self.reapply_shape())
        Gdk.Screen.get_default().connect(
            "composited-changed", lambda *_: self.reapply_shape()
        )
        self.show_all()

    def _update_shape(self):
        size = (self.get_allocated_width(), self.get_allocated_height())
        if size == self._shaped_size and self.get_mapped():
            return
        self._shaped_size = size
        shape_window(self, build_corners_region(*size, self._radius))

    def reapply_shape(self):
        self._shaped_size = None
        self._update_shape()

    def on_delete_event(self, *_):
        # don't close me :(
        return keep_window(self)
