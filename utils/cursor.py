import gi
gi.require_version('Gtk', '3.0')
from gi.repository import GLib, Gdk, Gtk

def add_hover_cursor(widget: Gtk.Widget, cursor_name="pointer"):
    """Wraps Widget and sets custom cursor."""
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
