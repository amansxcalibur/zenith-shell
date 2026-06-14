import gi
import math
import cairo
from cffi import FFI
from typing import Any, Self, Iterable, Literal, cast
from collections.abc import Callable
from fabric.core.service import Property
from fabric.widgets.container import Container

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk

# import faulthandler
# faulthandler.enable()

ffi = FFI()

libgdk = ffi.dlopen("libgdk-3.so.0")
libgobject = ffi.dlopen("libgobject-2.0.so.0")

ffi.cdef("""
typedef struct _GdkWindow GdkWindow;
typedef void* gpointer;

// signal defs from docs
typedef void (*to_embedder_cb)(
    GdkWindow* self,
    double offscreen_x,
    double offscreen_y,
    double* embedder_x,
    double* embedder_y,
    gpointer user_data
);

typedef void (*from_embedder_cb)(
    GdkWindow* self,
    double embedder_x,
    double embedder_y,
    double* offscreen_x,
    double* offscreen_y,
    gpointer user_data
);

// stripped down
unsigned long g_signal_connect_data(
    void* instance,
    const char* detailed_signal,
    void* c_handler,
    void* data,
    void* destroy_data,
    int connect_flags
);
""")


class RotateBox(Container):
    """A container that can rotate its child without messing the input hitbox for the child."""

    # PyGObject can't handle "out" parameters looks like it
    @ffi.callback("void(GdkWindow*, double, double, double*, double*, void*)")
    def to_embedder_callback(
        window,
        off_x: float,
        off_y: float,
        embedder_x_ptr: FFI.CData,
        embedder_y_ptr: FFI.CData,
        user_data: FFI.CData,
    ):
        self: Self = ffi.from_handle(user_data)
        embedder_x_ptr[0], embedder_y_ptr[0] = self.do_transform_offscreen_to_parent(
            off_x, off_y
        )
        return

    @ffi.callback("void(GdkWindow*, double, double, double*, double*, void*)")
    def from_embedder_callback(
        window,
        emb_x: float,
        emb_y: float,
        off_x_ptr: FFI.CData,
        off_y_ptr: FFI.CData,
        user_data: FFI.CData,
    ):
        self: Self = ffi.from_handle(user_data)
        off_x_ptr[0], off_y_ptr[0] = self.do_transform_offscreen_from_parent(
            emb_x, emb_y
        )
        return

    @staticmethod
    def do_connect_ffi(
        obj_pointer: int, name: str, callback: Callable, user_data: int | FFI.CData
    ):
        return libgobject.g_signal_connect_data(
            ffi.cast("void*", obj_pointer),
            name.encode("utf-8"),
            callback,
            user_data,
            ffi.NULL,
            0,
        )

    @Property(float, "read-write", default_value=0.0)
    def angle(self) -> float:
        return self._angle

    @angle.setter
    def angle(self, value: float):
        self._angle = math.radians(value)
        self.queue_resize()
        if self._offscreen_window:
            self._offscreen_window.geometry_changed()
        return

    @Property(bool, "read-write", default_value=False)
    def clip(self) -> bool:
        return self._clip

    @clip.setter
    def clip(self, value: bool):
        self._clip = value
        self.queue_resize()
        if self._offscreen_window:
            self._offscreen_window.geometry_changed()
        return

    def __init__(
        self,
        clip: bool = False,  # should we fix the bounding box when rotating or let the child clip outside the box
        angle: float = 0.0,  # rotation angle in degrees
        child: Gtk.Widget | None = None,
        name: str | None = None,
        visible: bool = True,
        all_visible: bool = False,
        style: str | None = None,
        style_classes: Iterable[str] | str | None = None,
        tooltip_text: str | None = None,
        tooltip_markup: str | None = None,
        h_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        v_align: Literal["fill", "start", "end", "center", "baseline"]
        | Gtk.Align
        | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        size: Iterable[int] | int | None = None,
        **kwargs,
    ):
        self._clip = clip
        self._angle = 0.0
        self._child: Gtk.Widget | None = None
        self._offscreen_window: Gdk.Window | None = None
        self._c_handle = ffi.new_handle(self)
        
        Container.__init__(
            self,
            child,
            name,
            visible,
            all_visible,
            style,
            style_classes,
            tooltip_text,
            tooltip_markup,
            h_align,
            v_align,
            h_expand,
            v_expand,
            size,
            **kwargs,
        )

        

        self.clip = clip
        self.angle = angle

        self.set_has_window(True)

    def do_realize(self):
        self.set_realized(True)
        alloc: cairo.Rectangle = self.get_allocation()  # type: ignore
        border_width: int = self.get_border_width()

        attrs = Gdk.WindowAttr()
        attrs.x = alloc.x + border_width
        attrs.y = alloc.y + border_width
        attrs.width = alloc.width - 2 * border_width
        attrs.height = alloc.height - 2 * border_width
        attrs.window_type = Gdk.WindowType.CHILD
        attrs.event_mask = Gdk.EventMask.ALL_EVENTS_MASK

        attrs.visual = self.get_visual()
        attrs.wclass = Gdk.WindowWindowClass.INPUT_OUTPUT
        attrs_mask = (
            Gdk.WindowAttributesType.X
            | Gdk.WindowAttributesType.Y
            | Gdk.WindowAttributesType.VISUAL
        )

        window: Gdk.Window = Gdk.Window.new(self.get_parent_window(), attrs, attrs_mask)

        self.set_window(window)
        window.set_user_data(self)

        window.connect("pick-embedded-child", self.do_handle_offscreen_pick_child)

        # the offscreen window
        attrs.window_type = Gdk.WindowType.OFFSCREEN
        if self._child and self._child.get_visible():
            child_alloc = self._child.get_allocation()
            attrs.width = child_alloc.width
            attrs.height = child_alloc.height
        else:
            attrs.width = 0
            attrs.height = 0

        self._offscreen_window = cast(
            Gdk.Window,
            Gdk.Window.new(
                self.get_screen().get_root_window(),
                attrs,
                Gdk.WindowAttributesType.VISUAL,
            ),
        )
        self._offscreen_window.set_user_data(self)

        if self._child:
            self._child.set_parent_window(self._offscreen_window)

        Gdk.offscreen_window_set_embedder(self._offscreen_window, window)

        # BUG: for some reason, if the callback was never called and the application quits the thing crashes
        # not a big deal since we're exiting anyways, this might caused from a dangling pointer somewhere
        self.do_connect_ffi(
            hash(self._offscreen_window),
            "to-embedder",
            self.to_embedder_callback,
            self._c_handle,
        )

        self.do_connect_ffi(
            hash(self._offscreen_window),
            "from-embedder",
            self.from_embedder_callback,
            self._c_handle,
        )

        self._offscreen_window.show()

    def do_unrealize(self):
        if self._offscreen_window:
            self._offscreen_window.set_user_data(None)
            self._offscreen_window.destroy()
            self._offscreen_window = None
        return Container.do_unrealize(self)

    def do_bake_transformation(self):
        if not self._child:
            return cairo.Matrix()

        width = self.get_allocated_width()
        height = self.get_allocated_height()
        child_width = self._child.get_allocated_width()
        child_height = self._child.get_allocated_height()

        matrix = cairo.Matrix()

        # move to parent container's center
        matrix.translate(width / 2.0, height / 2.0)
        # rotate in center
        matrix.rotate(self._angle)
        # alignment
        matrix.translate(-child_width / 2.0, -child_height / 2.0)

        return matrix

    def do_transform_offscreen_to_parent(
        self, off_x: float, off_y: float, *_
    ) -> tuple[float, float]:
        if not self._child:
            return off_x, off_y
        return self.do_bake_transformation().transform_point(off_x, off_y)

    def do_transform_offscreen_from_parent(
        self, emb_x: float, emb_y: float, *_
    ) -> tuple[float, float]:
        if not self._child:
            return emb_x, emb_y
        matrix = self.do_bake_transformation()
        try:
            matrix.invert()
        except cairo.Error:
            return emb_x, emb_y  # non-invertible angle. weird
        return matrix.transform_point(emb_x, emb_y)

    def do_handle_offscreen_pick_child(
        self, offscreen_window: Gdk.Window, widget_x: float, widget_y: float
    ):
        if not self._child or not self._child.get_visible():
            return None

        x, y = self.do_transform_offscreen_from_parent(widget_x, widget_y)
        child_alloc: cairo.Rectangle = self._child.get_allocation()  # type: ignore
        if 0 <= x < child_alloc.width and 0 <= y < child_alloc.height:
            return self._offscreen_window
        return None

    def do_get_child_boundries(self) -> tuple[float, float]:
        border_width: int = self.get_border_width()
        if self._child and self._child.get_visible():
            child_requisition, _ = self._child.get_preferred_size()  # type: ignore
        else:
            child_requisition: cairo.Rectangle = Gtk.Requisition()  # type: ignore

        angle_sin = abs(math.sin(self._angle))
        angle_cos = abs(math.cos(self._angle))
        width = (
            angle_cos * child_requisition.width + angle_sin * child_requisition.height
        )
        height = (
            angle_sin * child_requisition.width + angle_cos * child_requisition.height
        )

        return border_width * 2 + width, border_width * 2 + height

    def do_get_preferred_width(self) -> tuple[float, float]:
        if self._clip and self._child:
            return self._child.get_preferred_width()  # type: ignore
        return (self.do_get_child_boundries()[0],) * 2  # type: ignore

    def do_get_preferred_height(self) -> tuple[float, float]:
        if self._clip and self._child:
            return self._child.get_preferred_height()  # type: ignore
        return (self.do_get_child_boundries()[1],) * 2  # type: ignore

    def do_size_allocate(self, allocation: cairo.RectangleInt):
        self.set_allocation(allocation)
        border_width = self.get_border_width()
        width: int = allocation.width - border_width * 2
        height: int = allocation.height - border_width * 2

        if self.get_realized():
            self.get_window().move_resize(
                allocation.x + border_width, allocation.y + border_width, width, height
            )

        if not self._child or not self._child.get_visible():
            return

        child_requisition, _ = self._child.get_preferred_size()
        child_allocation: cairo.RectangleInt = Gdk.Rectangle()  # type: ignore
        child_allocation.x = 0
        child_allocation.y = 0
        child_allocation.width = child_requisition.width
        child_allocation.height = child_requisition.height

        if self._offscreen_window and self.get_realized():
            self._offscreen_window.move_resize(
                0, 0, child_requisition.width, child_requisition.height
            )

        return self._child.size_allocate(child_allocation)

    def do_damage_event(self, event: Gdk.EventExpose):
        return self.get_window().invalidate_rect(None, False)

    def do_draw(self, cr: cairo.Context) -> bool:
        if not (
            (window := self.get_window())
            and self._offscreen_window
            and self._child
            and self._child.get_visible()
        ):
            return False

        if (
            Gtk.cairo_should_draw_window(cr, window)
            and self._child
            and self._child.get_visible()
        ):
            surface = Gdk.offscreen_window_get_surface(self._offscreen_window)

            cr.transform(self.do_bake_transformation())
            cr.rectangle(
                0,
                0,
                self._offscreen_window.get_width(),
                self._offscreen_window.get_height(),
            )
            cr.clip()
            cr.set_source_surface(surface, 0, 0)
            cr.paint()

        if not Gtk.cairo_should_draw_window(cr, self._offscreen_window):
            return False

        Gtk.render_background(
            self.get_style_context(),
            cr,
            0,
            0,
            self._offscreen_window.get_width(),
            self._offscreen_window.get_height(),
        )

        if self._child:
            self.propagate_draw(self._child, cr)

        return False

    def do_add(self, widget: Gtk.Widget):
        print(f"ScaleBox.do_add called with {widget}, current child: {self._child}")
        if self._child:
            raise ValueError

        self._child = widget
        widget.set_parent(self)
        self._child.connect("destroy", print)
        return (
            widget.set_parent_window(self._offscreen_window)
            if self._offscreen_window
            else None
        )

    def do_remove(self, widget: Gtk.Widget):
        if not self._child or self._child is not widget:
            return

        # BUG: when this line is commented it stops the segfault
        self._child.unparent()
        self._child = None

        return self.queue_resize()

    def do_forall(
        self,
        include_internals: bool,
        callback: Callable[[Gtk.Widget, Any], Any],
        *user_data,
    ):
        return callback(self._child, *user_data) if self._child else None

