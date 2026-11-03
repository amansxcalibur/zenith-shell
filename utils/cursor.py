import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gtk  # type: ignore


def add_hover_cursor(widget: Gtk.Widget, cursor_name="pointer"):
    """Wraps Widget and sets custom cursor."""

    # idempotent: widgets that get re-added (e.g. top bar controls on every view
    # switch) would otherwise pile up another pair of handlers each time
    if getattr(widget, "_hover_cursor_wired", False):
        return widget
    widget._hover_cursor_wired = True

    def on_enter(w, event):
        window = w.get_window()
        if window:
            display = Gdk.Display.get_default()
            cursor = Gdk.Cursor.new_from_name(display, cursor_name)
            window.set_cursor(cursor)

    def on_leave(w, event):
        window = w.get_window()
        if window:
            window.set_cursor(None)

    widget.connect("enter-notify-event", on_enter)
    widget.connect("leave-notify-event", on_leave)
    widget.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)

    return widget
