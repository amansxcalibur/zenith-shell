import os
import glob
import json
import uuid
import cairo
from loguru import logger

from fabric.utils.helpers import exec_shell_command_async
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.checkbutton import CheckButton
from fabric.widgets.scrolledwindow import ScrolledWindow

import icons
from config.info import DATA_DIR, CACHE_DIR, IS_WAYLAND
from services.animator import CubicBezierCurves

from utils.colors import bind_theme
from utils.text_view import add_undo, keep_cursor_visible

from widgets.material_label import MaterialIconLabel
from widgets.clipping_box import ClippingBox, AnimatedClippingBox

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GdkPixbuf, GLib  # type: ignore

DND_TARGET = "agenda-row"
ANIMATION_MS = 180  # rows and drop gaps opening and closing


DATA_FILE = os.path.join(DATA_DIR, "agenda.json")
AGENDA_CACHE_DIR = os.path.join(CACHE_DIR, "agenda")
BACKGROUND_PREFIX = "bg_crop_"
THUMB_W, THUMB_H = 500, 100

os.makedirs(AGENDA_CACHE_DIR, exist_ok=True)


def ensure_data_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump([], f)


def _make_icon_button(icon, tooltip: str, callback: callable) -> Button:
    return Button(
        name="agenda-btn",
        child=MaterialIconLabel(style_classes="agenda-icon", icon_text=icon.symbol()),
        on_clicked=callback,
        tooltip_text=tooltip,
    )


def _make_editor_button(label: str, callback: callable) -> Button:
    return Button(
        name="editor-btn",
        h_expand=True,
        label=label,
        style_classes="agenda-icon",
        on_clicked=callback,
    )


def _make_text_view(name="text-editor") -> Gtk.TextView:
    tv = Gtk.TextView(name=name)
    tv.set_wrap_mode(Gtk.WrapMode.WORD)
    tv.set_pixels_above_lines(2)
    add_undo(tv)  # ctrl+z / ctrl+shift+z
    return tv


def _crop_pixbuf(pixbuf: GdkPixbuf.Pixbuf, w: int, h: int) -> GdkPixbuf.Pixbuf:
    scale = max(w / pixbuf.get_width(), h / pixbuf.get_height())
    sw, sh = int(pixbuf.get_width() * scale), int(pixbuf.get_height() * scale)
    scaled = pixbuf.scale_simple(sw, sh, GdkPixbuf.InterpType.BILINEAR)
    return scaled.new_subpixbuf((sw - w) // 2, (sh - h) // 2, w, h)


def _by_order(row_a, row_b, *_):
    return (row_a._order > row_b._order) - (row_a._order < row_b._order)


def _animated(child, revealed=False) -> Revealer:
    revealer = Revealer(
        child=child,
        child_revealed=revealed,
        transition_type="slide-down",
        transition_duration=ANIMATION_MS,
    )
    if not revealed:
        revealer.connect("map", lambda r: r.set_reveal_child(True))
    return revealer


class AgendaItem(Gtk.ListBoxRow):
    def __init__(
        self,
        text: str,
        on_delete: callable,
        on_save: callable,
        image_path: str | None = None,
        order: float = 0,
    ):
        # the row itself stays unstyled so a lifted one can close to nothing
        super().__init__(name="agenda-row", activatable=False, selectable=False)
        self.text = text
        self.image_path = image_path
        self.on_save = on_save
        self._order = order  # place in the list, see `_by_order`
        self._leaving = False
        self.lifted = False  # picked up by a drag, its space closed

        self._build_display()
        self._build_editor()
        self._build_action_revealer()
        self._build_stack(on_delete)

        self.apply_background()
        self.show_all()

    def _build_display(self):
        self.label = Label(
            label=self.text, h_align="start", line_wrap="word-char", max_chars_width=30
        )
        self.clipping_wrapper = AnimatedClippingBox(
            max_height=22,
            contracting_bezier_curve=CubicBezierCurves.EMPHASIS,
            expanding_bezier_curve=CubicBezierCurves.EMPHASIS,
        )
        self.clipping_wrapper.add(self.label)

        self.check = CheckButton(name="agenda-check", v_align="start")
        self.check.connect("toggled", self._on_toggle)

        self.display_box = Box(
            name="display-box", spacing=10, children=[self.check, self.clipping_wrapper]
        )

    def _build_editor(self):
        self.text_view = _make_text_view()
        # nested in the agenda list's ScrolledWindow, so GTK won't follow the cursor
        keep_cursor_visible(self.text_view)

        def force_focus(widget, event):
            widget.grab_focus()
            return True  # stops event from bubbling up to the EventBox/Pill

        # connect_after, not connect: the TextView places the cursor / starts a
        # selection in its class handler (its click gesture). A plain connect
        # handler runs first and returning True would cancel that entirely.
        self.text_view.connect_after("button-press-event", force_focus)
        self.text_view.connect_after("button-release-event", force_focus)

        editor_actions = Box(
            spacing=5,
            children=[
                _make_editor_button("Save", self._on_save_changes),
                _make_editor_button("Cancel", self._on_cancel_edit),
            ],
        )
        self.edit_vbox = Box(
            orientation="v",
            spacing=5,
            children=[self.text_view, editor_actions],
        )

    def _build_action_revealer(self):
        self.remove_background_button = _make_icon_button(
            icons.hide_image, "Remove Background Image", self._on_remove_background
        )
        self.remove_background_button.set_no_show_all(True)
        self.background_button = _make_icon_button(
            icons.wallpaper, "Set Background Image", self._on_select_background
        )

        self.action_revealer = Revealer(
            transition_type="slide-left",
            transition_duration=200,
            child=Box(
                spacing=4,
                style="padding-right: 2px",
                children=[
                    Box(
                        name="agenda-btn-group",
                        children=[
                            _make_icon_button(
                                icons.edit_material,
                                "Edit Task",
                                self._on_edit_requested,
                            ),
                            self.background_button,
                        ],
                    ),
                    Box(
                        name="agenda-btn-group",
                        children=[
                            self.remove_background_button,
                            _make_icon_button(
                                icons.trash_material,
                                "Delete Task",
                                lambda: self.stack.set_visible_child_name("delete"),
                            )
                            .build()
                            .add_style_class("delete-btn")
                            .unwrap(),
                        ],
                    ),
                ],
            ),
            h_align="end",
            v_align="start",
        )

    def _build_stack(self, on_delete: callable):
        self.event_box = EventBox(
            child=Overlay(child=self.display_box, overlays=self.action_revealer),
            events=["enter-notify", "leave-notify", "button-press-event"],
        )
        self.event_box.connect("enter-notify-event", self._on_hover, True)
        self.event_box.connect("leave-notify-event", self._on_hover, False)
        self.event_box.connect("button-press-event", self._on_click)

        del_actions = Box(
            spacing=5,
            children=[
                _make_editor_button("Delete", lambda _: on_delete(self))
                .build()
                .add_style_class("delete-btn")
                .unwrap(),
                _make_editor_button("Cancel", self._on_cancel_edit),
            ],
        )
        self.del_box = Box(
            orientation="v",
            spacing=5,
            children=[
                Label(
                    name="text-editor",
                    label="Are you sure you wanna delete this?",
                )
                .build()
                .set_xalign(0.0)
                .unwrap(),
                del_actions,
            ],
        )

        self.stack = Stack(
            transition_type="crossfade", transition_duration=250, h_expand=True
        )
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)
        self.stack.add_named(self.event_box, "display")
        self.stack.add_named(self.edit_vbox, "edit")
        self.stack.add_named(self.del_box, "delete")
        self.stack.add_named(self._build_drag_page(), "drag")
        self.card = Box(name="agenda-box", children=self.stack)
        self.grip = EventBox(child=self.card)
        self.revealer = _animated(self.grip, revealed=True)
        self.add(self.revealer)

    def _build_drag_page(self) -> Box:
        self.drag_label = Label(
            label=self._mini_text(),
            h_align="start",
            h_expand=True,
            ellipsization="end",
            max_chars_width=30,
        )
        # ellipsizing alone still renders every "\n" line; force one line
        self.drag_label.set_single_line_mode(True)
        return Box(
            name="display-box",
            spacing=10,
            children=[
                MaterialIconLabel(
                    style_classes="agenda-icon",
                    icon_text=icons.drag_indicator.symbol(),
                ),
                self.drag_label,
            ],
        )

    def _mini_text(self) -> str:
        return next((ln for ln in self.text.splitlines() if ln.strip()), self.text)

    def set_reorder_mode(self, on: bool):
        self.drag_label.set_label(self._mini_text())  # text may have been edited
        self.stack.set_visible_child_name("drag" if on else "display")
        if on:
            self.action_revealer.set_reveal_child(False)
            self.grip.drag_source_set(
                Gdk.ModifierType.BUTTON1_MASK,
                [Gtk.TargetEntry.new(DND_TARGET, Gtk.TargetFlags.SAME_APP, 0)],
                Gdk.DragAction.MOVE,
            )
        else:
            self.grip.drag_source_unset()  # the display page's clicks are its own

    def setup_dnd(self, on_begin: callable, on_end: callable):
        self.grip.connect("drag-begin", self._on_drag_begin, on_begin)
        self.grip.connect("drag-data-get", self._on_drag_data_get)
        self.grip.connect("drag-failed", self._on_drag_failed)
        self.grip.connect("drag-end", self._on_drag_end, on_end)
        for sig in ("button-press-event", "button-release-event"):
            self.grip.connect_after(sig, self._on_grip_button)

    def _on_grip_button(self, _widget, event) -> bool:
        return event.button == 1 and self.stack.get_visible_child_name() == "drag"

    @staticmethod
    def _on_drag_data_get(_widget, _ctx, data: Gtk.SelectionData, _info, _time):
        # payload is irrelevant (the app tracks the dragged row), but it must be
        # non-empty or GTK treats the drop as failed and skips the reorder
        data.set(data.get_target(), 8, b"row")

    def _on_drag_begin(self, _widget, ctx, on_begin):
        on_begin(self)
        # the card as drag icon, held by its middle
        alloc = self.card.get_allocation()
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, alloc.width, alloc.height)
        self.card.draw(cairo.Context(surface))
        surface.set_device_offset(-alloc.width / 2, -alloc.height / 2)
        Gtk.drag_set_icon_surface(ctx, surface)
        # once the drag has its icon, close the space the row leaves
        GLib.idle_add(self.set_lifted, True)

    def _on_drag_failed(self, _widget, _ctx, _result) -> bool:
        # dropped nowhere or cancelled: put it back. A drop places it instead.
        self.set_lifted(False)
        return False

    def _on_drag_end(self, _widget, _ctx, on_end):
        if self.lifted:  # neither dropped nor failed; don't leave it hidden
            self.set_lifted(False)
        on_end()

    def set_lifted(self, lifted: bool, animate: bool = True) -> bool:
        self.lifted = lifted
        self.set_opacity(0 if lifted else 1)
        if not animate:  # a drop fills its gap as is
            self.revealer.set_transition_duration(0)
        self.revealer.set_reveal_child(not lifted)
        self.revealer.set_transition_duration(ANIMATION_MS)
        return False

    def _on_click(self, _source, event):
        if event.button == 1:
            self.clipping_wrapper.toggle(22)
            self.queue_resize()
            return True
        return False

    def _on_hover(self, _source, event, reveal: bool):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.action_revealer.set_reveal_child(reveal)

    def _on_toggle(self, widget):
        active = widget.get_active()
        attrs = Pango.AttrList()
        if active:
            attrs.insert(Pango.attr_strikethrough_new(True))
        self.label.set_attributes(attrs)
        self.label.set_opacity(0.5 if active else 1.0)

    def _on_edit_requested(self, _widget):
        self.text_view.get_buffer().set_text(self.label.get_text())
        self.text_view.undo.reset()  # loading the note isn't an undoable edit
        self.action_revealer.set_reveal_child(False)
        self.stack.set_visible_child_name("edit")
        self.text_view.grab_focus()

    def _on_save_changes(self, _widget):
        buf = self.text_view.get_buffer()
        new_text = buf.get_text(*buf.get_bounds(), True).strip()
        if new_text:
            self.text = new_text
            self.label.set_text(new_text)
        self.stack.set_visible_child_name("display")
        self.on_save()

    def _on_cancel_edit(self, _widget):
        self.stack.set_visible_child_name("display")

    def _on_select_background(self, _widget):
        dialog = self._make_file_dialog()
        if dialog.run() == Gtk.ResponseType.OK:
            self._process_and_cache_image(dialog.get_filename())
        dialog.destroy()

    def _on_remove_background(self, _widget):
        self.image_path = None
        self.apply_background()
        self.on_save()

    def apply_background(self):
        has_image = bool(self.image_path and os.path.exists(self.image_path))
        if has_image:
            self.display_box.set_style(
                f"background-image: url('file://{self.image_path}');"
                "background-size: cover; background-position: center;"
            )
        else:
            self.display_box.set_style("")

        self.remove_background_button.set_visible(has_image)
        self.background_button.set_tooltip_text(
            "Change Background Image" if has_image else "Set Background Image"
        )

    def _process_and_cache_image(self, original_path: str):
        try:
            cropped = _crop_pixbuf(
                GdkPixbuf.Pixbuf.new_from_file(original_path), THUMB_W, THUMB_H
            )
            cache_name = f"{BACKGROUND_PREFIX}{uuid.uuid4().hex}.png"
            target_path = os.path.join(AGENDA_CACHE_DIR, cache_name)
            cropped.savev(target_path, "png", [], [])
            self.image_path = target_path
            self.apply_background()
            self.on_save()
        except Exception as e:
            logger.error(f"Failed to crop image: {e}")

    def _make_file_dialog(self) -> Gtk.FileChooserDialog:
        dialog = Gtk.FileChooserDialog(
            title="Select Background Image",
            parent=None,
            action=Gtk.FileChooserAction.OPEN,
            use_header_bar=False,
        )
        bind_theme(dialog)
        dialog.get_style_context().add_class("file-chooser-dialog")
        if IS_WAYLAND:
            dialog.get_style_context().add_class("wayland")
        dialog.set_visual(dialog.get_screen().get_rgba_visual())

        for stock, response, extra_class in [
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, None),
            (Gtk.STOCK_OPEN, Gtk.ResponseType.OK, "bright"),
        ]:
            btn = dialog.add_button(stock, response)
            btn.get_style_context().add_class("settings-btn")
            if extra_class:
                btn.get_style_context().add_class(extra_class)

        img_filter = Gtk.FileFilter()
        img_filter.set_name("Images")
        img_filter.add_mime_type("image/png")
        img_filter.add_mime_type("image/jpeg")
        dialog.add_filter(img_filter)
        return dialog


class AgendaApp(Box):
    def __init__(self, **kwargs):
        super().__init__(name="agenda-app", **kwargs)
        self.reorder_mode = False
        self._dragged: AgendaItem | None = None
        self._load_failed = False

        self._build_input_stack()
        self._build_actions_pill()
        self._build_list()
        self._assemble()
        self.show_all()
        ensure_data_file()
        self.load_from_disk()

    def _build_input_stack(self):
        self.trigger_box = Button(
            name="add-new-agenda-btn",
            h_align="end",
            child=MaterialIconLabel(icon_text=icons.add_material.symbol()),
            on_clicked=self._show_editor,
        )

        self.new_text_view = Gtk.TextView(name="text-editor")
        add_undo(self.new_text_view)
        self.new_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.scrolled_window = ScrolledWindow(
            h_scrollbar_policy="never",
            v_scrollbar_policy="automatic",
            min_content_size=(-1, 80),
            max_content_size=(-1, 150),
            child=self.new_text_view,
        )

        editor_box = Box(
            name="editor-box",
            orientation="v",
            spacing=6,
            children=[
                self.scrolled_window,
                Box(
                    spacing=6,
                    children=[
                        _make_editor_button("Add", self._add_item),
                        _make_editor_button("Cancel", self._hide_editor),
                    ],
                ),
            ],
        )

        self.input_stack = Stack(
            h_align="end",
            v_align="end",
            transition_duration=250,
            transition_type="crossfade",
        )
        self.input_stack.set_interpolate_size(True)
        self.input_stack.set_homogeneous(False)
        self.input_stack.add_named(self.trigger_box, "trigger")
        self.input_stack.add_named(editor_box, "editor")
        self.input_stack.add_named(Box(), "hidden")
        self.input_stack.set_visible_child_name("trigger")

    def _build_actions_pill(self):
        self.copy_icon = MaterialIconLabel(icon_text=icons.content_copy.symbol())
        self.edit_icon = MaterialIconLabel(icon_text=icons.edit_material.symbol())
        self.copy_btn = Button(
            name="agenda-pill-btn",
            child=self.copy_icon,
            tooltip_text="Copy agenda data",
            on_clicked=self._copy_data,
        )
        self.edit_btn = Button(
            name="agenda-pill-btn",
            child=self.edit_icon,
            tooltip_text="Re-arrange items",
            on_clicked=self._toggle_reorder,
        )
        self.actions_pill = Box(
            name="agenda-actions-pill",
            spacing=2,
            children=[self.copy_btn, self.edit_btn],
        )
        # same show_all() reasoning as input_stack: hide via an empty child
        self.actions_stack = Stack(
            h_align="start",
            v_align="end",
            transition_duration=250,
            transition_type="crossfade",
        )
        self.actions_stack.set_interpolate_size(True)
        self.actions_stack.set_homogeneous(False)
        self.actions_stack.add_named(self.actions_pill, "pill")
        self.actions_stack.add_named(Box(), "hidden")
        self.actions_stack.set_visible_child_name("pill")

    def _copy_data(self, _widget):
        self.save_to_disk()  # make sure the file reflects what's on screen
        try:
            with open(DATA_FILE) as f:
                data = f.read()
        except OSError as e:
            logger.error(f"Failed to read agenda file for copying: {e}")
            return
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        clipboard.set_text(data, -1)
        clipboard.store()  # keep it after we lose focus (needs a clipboard manager)
        self.copy_icon.set_text(icons.check_material.symbol())
        GLib.timeout_add(
            750, lambda: self.copy_icon.set_text(icons.content_copy.symbol()) and False
        )

    def _toggle_reorder(self, _widget):
        self.reorder_mode = not self.reorder_mode
        self._hide_drop_gap()
        for row in self._rows():
            row.set_reorder_mode(self.reorder_mode)
        self.edit_btn.set_tooltip_text(
            "Done" if self.reorder_mode else "Re-arrange items"
        )
        if self.reorder_mode:
            self.edit_btn.add_style_class("active")
        else:
            self.edit_btn.remove_style_class("active")
        self._sync_overlays()

    def _rows(self) -> list[AgendaItem]:
        """Agenda items in list order, a lifted one included."""
        return [r for r in self.listbox.get_children() if isinstance(r, AgendaItem)]

    def _staying_rows(self) -> list[AgendaItem]:
        """Items that keep their place during a drag: not the lifted one."""
        return [r for r in self._rows() if not r.lifted]

    def _renumber(self):
        for index, row in enumerate(self._rows()):
            row._order = index
        self.listbox.invalidate_sort()

    def _make_item(
        self, text: str, image: str | None = None, order: float = 0
    ) -> AgendaItem:
        item = AgendaItem(text, self._remove_item, self.save_to_disk, image, order)
        item.setup_dnd(self._on_drag_begin, self._on_drag_end)
        item.stack.connect(
            "notify::visible-child-name", lambda *_: self._sync_overlays()
        )
        item.set_reorder_mode(self.reorder_mode)
        return item

    def _setup_drop_target(self):
        self._drop_gap: Gtk.ListBoxRow | None = None
        self._gap_height = -1  # the dragged card's, so the list doesn't jump on drop
        self._pending_drop_index: int | None = None  # among the staying rows
        self._hovering = False
        self._dropping = False
        # no defaults: GTK's would emit drag-leave on drop and close the gap
        # before the row could fill it, so drops are taken by hand
        self.listbox.drag_dest_set(
            0,
            [Gtk.TargetEntry.new(DND_TARGET, Gtk.TargetFlags.SAME_APP, 0)],
            Gdk.DragAction.MOVE,
        )
        self.listbox.connect("drag-motion", self._on_drag_motion)
        self.listbox.connect("drag-leave", self._on_drag_leave)
        self.listbox.connect("drag-drop", self._on_drag_drop)
        self.listbox.connect("drag-data-received", self._on_drop)

    def _new_gap(self, order: float) -> Gtk.ListBoxRow:
        box = Box(name="agenda-drop-placeholder")
        box.set_size_request(-1, self._gap_height)
        row = Gtk.ListBoxRow(name="agenda-drop-slot", activatable=False)
        row.set_selectable(False)
        row._order = order
        row._leaving = False
        row.add(_animated(box))
        self.listbox.add(row)
        row.show_all()
        return row

    def _collapse(self, row: Gtk.ListBoxRow):
        """Close the row, then drop it."""
        row._leaving = True
        row._order -= 0.5  # sit just above the row that now holds its index
        revealer = row.get_child()
        if not revealer.get_reveal_child() and not revealer.get_child_revealed():
            self.listbox.remove(row)  # already shut
            return

        def on_revealed(revealer, _pspec):
            if not revealer.get_child_revealed() and row.get_parent() is self.listbox:
                self.listbox.remove(row)

        revealer.connect("notify::child-revealed", on_revealed)
        revealer.set_reveal_child(False)

    def _drop_index_at(self, y: int) -> int:
        """Staying rows above y, by their middles; the gap doesn't count."""
        index = 0
        for row in self._staying_rows():
            _, row_y = row.translate_coordinates(self.listbox, 0, 0)
            if row_y + row.get_allocated_height() / 2 < y:
                index += 1
        return index

    def _show_drop_gap(self, index: int):
        rows = self._staying_rows()
        # just above the row the drop would push down
        if index < len(rows):
            order = rows[index]._order - 0.25
        else:
            order = (rows[-1]._order if rows else 0) + 0.75

        if self._drop_gap is None:
            self._drop_gap = self._new_gap(order)
        elif self._drop_gap._order != order:
            self._drop_gap._order = order
            self._drop_gap.changed()

    def _hide_drop_gap(self):
        if self._drop_gap is not None:
            self._collapse(self._drop_gap)
            self._drop_gap = None
        self._pending_drop_index = None

    def _on_drag_begin(self, item: AgendaItem):
        self._dragged = item
        self._gap_height = item.card.get_allocated_height()

    def _on_drag_end(self):
        self._dropping = False
        self._hide_drop_gap()
        self._dragged = None

    def _on_drag_motion(self, widget, ctx, _x, y, time) -> bool:
        if self._dragged is None:  # not one of our rows
            Gdk.drag_status(ctx, 0, time)
            return False
        self._hovering = True
        self._autoscroll(widget, y)
        self._pending_drop_index = self._drop_index_at(y)
        self._show_drop_gap(self._pending_drop_index)
        Gdk.drag_status(ctx, Gdk.DragAction.MOVE, time)
        return True

    def _on_drag_leave(self, _widget, _ctx, _time):
        # GTK also leaves just before a drop, so wait to see if one follows
        self._hovering = False
        GLib.idle_add(self._close_gap_if_left)

    def _close_gap_if_left(self) -> bool:
        if not self._hovering and not self._dropping:
            self._hide_drop_gap()
        return False

    def _on_drag_drop(self, widget, ctx, _x, _y, time) -> bool:
        if self._dragged is None:
            return False
        self._dropping = True
        widget.drag_get_data(ctx, widget.drag_dest_find_target(ctx, None), time)
        return True

    def _on_drop(self, _widget, ctx, _x, _y, _data, _info, time):
        self._dropping = False
        src, gap, index = self._dragged, self._drop_gap, self._pending_drop_index
        if src is None or gap is None or index is None:
            self._hide_drop_gap()
            ctx.finish(False, False, time)
            return

        # the index counts the rows staying here, the dragged one aside
        rows = self._staying_rows()
        rows.insert(index, src)
        for order, row in enumerate(rows):
            row._order = order
        # the row fills its gap as is
        self._drop_gap = self._pending_drop_index = None
        self.listbox.remove(gap)
        src.set_lifted(False, animate=False)
        self.listbox.invalidate_sort()

        ctx.finish(True, False, time)
        self.save_to_disk()

    def _autoscroll(self, row: Gtk.Widget, y: int):
        # auto-scroll when hovering near the top/bottom edge of the viewport
        adj = self.scrolled.get_vadjustment()
        coords = row.translate_coordinates(self.scrolled, 0, y)
        if coords is None:  # not realized/mapped yet
            return
        _, vy = coords
        edge, step = 30, 12
        if vy < edge:
            adj.set_value(max(adj.get_lower(), adj.get_value() - step))
        elif vy > self.scrolled.get_allocated_height() - edge:
            adj.set_value(
                min(adj.get_upper() - adj.get_page_size(), adj.get_value() + step)
            )

    def _build_list(self):
        self.listbox = Gtk.ListBox(name="agenda-list-box")
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        # rows sit by `_order`, so a closing gap stays put while the rest settle
        self.listbox.set_sort_func(_by_order)
        self._setup_drop_target()

    def _assemble(self):
        self.scrolled = scrolled = ScrolledWindow(
            min_content_size=(300, 220),
            max_content_size=(300, 220),
            h_expand=True,
            child=self.listbox,
        )
        self.children = Overlay(
            h_expand=True,
            v_expand=True,
            child=ClippingBox(
                name="agenda-scrolled-clipper",
                h_expand=True,
                v_expand=True,
                children=scrolled,
            ),
            overlays=[self.actions_stack, self.input_stack],
        )
        # Their box-shadows paint outside the overlay child's window, which is
        # all GTK repaints on a theme change. Repaint from here to clear them.
        for widget in (self.trigger_box, self.actions_pill):
            widget.connect("style-updated", lambda *_: self.queue_draw())

    def _show_editor(self, _widget):
        self.input_stack.set_visible_child_name("editor")
        self.actions_stack.set_visible_child_name("hidden")
        self.new_text_view.grab_focus()

    def _hide_editor(self, _widget):
        self.input_stack.set_visible_child_name("trigger")
        self._sync_overlays()

    def _sync_overlays(self):
        # the new-note editor already hid the pill, and hiding it would lose its view
        if self.input_stack.get_visible_child_name() == "editor":
            return
        # the overlays would sit on top of a row's editor or delete confirmation
        row_busy = any(
            row.stack.get_visible_child_name() in ("edit", "delete")
            for row in self._rows()
        )
        # adding notes while re-arranging makes no sense
        self.input_stack.set_visible_child_name(
            "hidden" if row_busy or self.reorder_mode else "trigger"
        )
        self.actions_stack.set_visible_child_name("hidden" if row_busy else "pill")

    def _add_item(self, _widget):
        buf = self.new_text_view.get_buffer()
        text = buf.get_text(*buf.get_bounds(), True).strip()
        if not text:
            return
        # add to the beginning
        self.listbox.add(self._make_item(text, order=-1))
        self._renumber()
        buf.set_text("")
        self.new_text_view.undo.reset()
        self.input_stack.set_visible_child_name("trigger")
        self._sync_overlays()
        self.show_all()
        self.save_to_disk()

    def _remove_item(self, item: AgendaItem):
        self.listbox.remove(item)
        self._sync_overlays()
        self.save_to_disk()

    def load_from_disk(self):
        if not os.path.exists(DATA_FILE):
            return

        try:
            with open(DATA_FILE) as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise TypeError("expected a list of items")
        except Exception as e:
            self._on_load_failed(f"Failed to read or parse agenda file: {e}")
            return

        for order, item in enumerate(data):
            try:
                text = item if isinstance(item, str) else item.get("text")
                img = None if isinstance(item, str) else item.get("image")
                self.listbox.add(self._make_item(text, img, order))
            except Exception as e:
                self._on_load_failed(f"Error loading agenda item ({item}): {e}")

        self.show_all()

    def _on_load_failed(self, reason: str):
        # What's on disk is more than what we hold, so saving would lose the rest.
        logger.error(reason)
        if self._load_failed:
            return
        self._load_failed = True
        body = GLib.markup_escape_text(
            f"Could not read {DATA_FILE}. Changes won't be saved until "
            "it's fixed and the shell is restarted."
        )
        exec_shell_command_async(
            ["notify-send", "-u", "critical", "Agenda not loaded", body]
        )

    def save_to_disk(self):
        if self._load_failed:
            logger.warning("Not saving the agenda, as it failed to load")
            return

        os.makedirs(DATA_DIR, exist_ok=True)
        rows = self._rows()
        items = [{"text": row.text, "image": row.image_path} for row in rows]

        # atomic, so a crash mid-write can't leave a file that fails to load
        temp_path = f"{DATA_FILE}.tmp"
        with open(temp_path, "w") as f:
            json.dump(items, f, indent=4)
        os.replace(temp_path, DATA_FILE)

        self._delete_unused_backgrounds(rows)

    def _delete_unused_backgrounds(self, rows: list[AgendaItem]):
        used = {row.image_path for row in rows}
        pattern = os.path.join(glob.escape(AGENDA_CACHE_DIR), f"{BACKGROUND_PREFIX}*")
        for path in glob.glob(pattern):
            if path not in used:
                try:
                    os.remove(path)
                except OSError as e:
                    logger.warning(f"Failed to delete unused background: {e}")
