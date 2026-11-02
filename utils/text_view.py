"""Behaviour GTK 3's Gtk.TextView is missing.

- add_undo: Ctrl+Z undo, Ctrl+Shift+Z / Ctrl+Y redo
- keep_cursor_visible: follow the text cursor inside an *outer* ScrolledWindow
"""

import time

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # type: ignore


# a pause longer than this starts a new undo step
GROUP_TIMEOUT = 1.0


class TextViewUndo:
    """Snapshot-based undo/redo."""

    def __init__(self, text_view: Gtk.TextView, limit: int = 100):
        self.text_view = text_view
        self.buffer = text_view.get_buffer()
        self.limit = limit

        self._undo: list[tuple[str, int]] = []
        self._redo: list[tuple[str, int]] = []
        self._restoring = False
        self._last_time = 0.0
        self._last_kind: str | None = None
        self._pending_kind: str | None = None
        self._force_break = False
        self._state = self._snapshot()  # buffer state after the last change

        self.buffer.connect("insert-text", self._on_insert)
        self.buffer.connect("delete-range", self._on_delete)
        self.buffer.connect("changed", self._on_changed)
        self.text_view.connect("key-press-event", self._on_key)

    def reset(self):
        self._undo.clear()
        self._redo.clear()
        self._last_kind = None
        self._state = self._snapshot()

    def undo(self) -> bool:
        return self._step(self._undo, self._redo)

    def redo(self) -> bool:
        return self._step(self._redo, self._undo)

    def _snapshot(self) -> tuple[str, int]:
        text = self.buffer.get_text(*self.buffer.get_bounds(), True)
        cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert()).get_offset()
        return text, cursor

    def _on_insert(self, _buf, _iter, text: str, _length):
        self._pending_kind = "insert"
        # paste, or finishing a word/line: end the current step after this
        if len(text) > 1 or text.isspace():
            self._force_break = True

    def _on_delete(self, _buf, start, end):
        self._pending_kind = "delete"
        if abs(end.get_offset() - start.get_offset()) > 1:  # selection delete
            self._force_break = True

    def _on_changed(self, _buf):
        if self._restoring:
            return
        now = time.monotonic()
        new_group = (
            now - self._last_time > GROUP_TIMEOUT
            or self._pending_kind != self._last_kind
            or self._last_kind is None
        )
        if new_group:
            # save the state from before this group of edits
            self._undo.append(self._state)
            del self._undo[: -self.limit]
            self._redo.clear()

        self._state = self._snapshot()
        self._last_time = now
        # a break ends the group *after* this edit, so the next one starts fresh
        self._last_kind = None if self._force_break else self._pending_kind
        self._force_break = False

    def _step(self, source: list, target: list) -> bool:
        if not source:
            return False
        target.append(self._snapshot())
        text, cursor = source.pop()
        self._restoring = True
        try:
            self.buffer.set_text(text)
            self.buffer.place_cursor(self.buffer.get_iter_at_offset(cursor))
        finally:
            self._restoring = False
        self._state = (text, cursor)
        self._last_kind = None  # next edit starts a new step
        self.text_view.scroll_mark_onscreen(self.buffer.get_insert())
        return True

    def _on_key(self, _widget, event) -> bool:
        if not event.state & Gdk.ModifierType.CONTROL_MASK:
            return False
        key = Gdk.keyval_to_lower(event.keyval)
        shift = bool(event.state & Gdk.ModifierType.SHIFT_MASK)
        if key == Gdk.KEY_z and not shift:
            self.undo()
            return True
        if (key == Gdk.KEY_z and shift) or key == Gdk.KEY_y:
            self.redo()
            return True
        return False


def add_undo(text_view: Gtk.TextView, limit: int = 100) -> TextViewUndo:
    """Attach undo/redo to `text_view`; also stored as `text_view.undo`."""
    text_view.undo = TextViewUndo(text_view, limit)
    return text_view.undo


CURSOR_MARGIN = 12  # px of breathing room kept around the cursor


def keep_cursor_visible(text_view: Gtk.TextView, margin: int = CURSOR_MARGIN) -> None:
    """Scroll the nearest ScrolledWindow ancestor to keep the cursor in view.

    GTK only auto-scrolls when the TextView is the ScrolledWindow's direct
    child. When it's nested deeper (e.g. inside a ListBox row), it grows taller
    than the viewport and typing/arrowing near the bottom moves the cursor out
    of view.
    """
    buffer = text_view.get_buffer()
    pending = False

    def scroll() -> bool:
        nonlocal pending
        pending = False

        if not text_view.has_focus():
            return False
        scrolled = text_view.get_ancestor(Gtk.ScrolledWindow)
        if scrolled is None:
            return False

        rect = text_view.get_iter_location(buffer.get_iter_at_mark(buffer.get_insert()))
        x, y = text_view.buffer_to_window_coords(
            Gtk.TextWindowType.WIDGET, rect.x, rect.y
        )
        coords = text_view.translate_coordinates(scrolled, x, y)
        if coords is None:  # not realized/mapped
            return False
        top = coords[1]
        bottom = top + rect.height

        adj = scrolled.get_vadjustment()
        page = scrolled.get_allocated_height()
        delta = 0
        if top < margin:
            delta = top - margin
        elif bottom > page - margin:
            delta = bottom - (page - margin)
        if delta:
            upper = adj.get_upper() - adj.get_page_size()
            adj.set_value(min(max(adj.get_lower(), adj.get_value() + delta), upper))
        return False

    def queue(*_):
        nonlocal pending
        if pending:
            return
        pending = True
        # low priority: run after GTK has re-laid-out the text/rows for this edit
        GLib.idle_add(scroll, priority=GLib.PRIORITY_LOW)

    buffer.connect("changed", queue)
    buffer.connect(
        "mark-set",
        lambda _b, _i, mark: queue() if mark == buffer.get_insert() else None,
    )
    text_view.connect("focus-in-event", lambda *_: queue() or False)
