import os
import json
from loguru import logger
from typing import Callable

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.checkbutton import CheckButton
from fabric.widgets.scrolledwindow import ScrolledWindow

from widgets.material_label import MaterialIconLabel
from widgets.clipping_box import ClippingBox, AnimatedClippingBox

import icons
from config.info import DATA_DIR, CACHE_DIR

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, Pango, GdkPixbuf


DATA_FILE = os.path.join(DATA_DIR, "agenda.json")
AGENDA_CACHE_DIR = os.path.join(CACHE_DIR, "agenda")
THUMB_W, THUMB_H = 500, 100

os.makedirs(AGENDA_CACHE_DIR, exist_ok=True)


def ensure_data_file():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w") as f:
            json.dump([], f)


def _make_icon_button(icon, tooltip: str, callback: Callable) -> Button:
    return Button(
        name="agenda-btn",
        child=MaterialIconLabel(style_classes="agenda-icon", icon_text=icon.symbol()),
        on_clicked=callback,
        tooltip_text=tooltip,
    )


def _make_editor_button(label: str, callback: Callable) -> Button:
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
    return tv


def _crop_pixbuf(pixbuf: GdkPixbuf.Pixbuf, w: int, h: int) -> GdkPixbuf.Pixbuf:
    scale = max(w / pixbuf.get_width(), h / pixbuf.get_height())
    sw, sh = int(pixbuf.get_width() * scale), int(pixbuf.get_height() * scale)
    scaled = pixbuf.scale_simple(sw, sh, GdkPixbuf.InterpType.BILINEAR)
    return scaled.new_subpixbuf((sw - w) // 2, (sh - h) // 2, w, h)


class AgendaItem(Gtk.ListBoxRow):
    def __init__(
        self,
        text: str,
        on_delete: Callable,
        on_save: Callable,
        image_path: str = None,
    ):
        super().__init__(name="agenda-box")
        self.text = text
        self.image_path = image_path
        self.on_save = on_save

        self._build_display()
        self._build_editor()
        self._build_action_revealer(on_delete)
        self._build_stack()

        self.apply_background()
        self.show_all()

    def _build_display(self):
        self.label = Label(
            label=self.text, h_align="start", line_wrap="word-char", max_chars_width=30
        )
        self.clipping_wrapper = AnimatedClippingBox(max_height=22)
        self.clipping_wrapper.add(self.label)

        self.check = CheckButton(name="agenda-check", v_align="start")
        self.check.connect("toggled", self._on_toggle)

        self.display_box = Box(
            name="display-box", spacing=10, children=[self.check, self.clipping_wrapper]
        )

    def _build_editor(self):
        self.text_view = _make_text_view()
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

    def _build_action_revealer(self, on_delete: Callable):
        self.action_revealer = Revealer(
            transition_type="slide-left",
            transition_duration=200,
            child=Box(
                spacing=2,
                style="padding-right: 2px",
                children=[
                    _make_icon_button(
                        icons.edit_material, "Edit Task", self._on_edit_requested
                    ),
                    _make_icon_button(
                        icons.trash_material, "Delete Task", lambda _: on_delete(self)
                    ),
                    _make_icon_button(
                        icons.wallpaper,
                        "Set Background Image",
                        self._on_select_background,
                    ),
                ],
            ),
            h_align="end",
            v_align="start",
        )

    def _build_stack(self):
        self.event_box = EventBox(
            child=Overlay(child=self.display_box, overlays=self.action_revealer),
            events=["enter-notify", "leave-notify", "button-press-event"],
        )
        self.event_box.connect("enter-notify-event", self._on_hover, True)
        self.event_box.connect("leave-notify-event", self._on_hover, False)
        self.event_box.connect("button-press-event", self._on_click)

        self.stack = Stack(transition_type="crossfade", transition_duration=250)
        self.stack.set_interpolate_size(True)
        self.stack.set_homogeneous(False)
        self.stack.add_named(self.event_box, "display")
        self.stack.add_named(self.edit_vbox, "edit")
        self.add(self.stack)

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

    def apply_background(self):
        if self.image_path and os.path.exists(self.image_path):
            self.display_box.set_style(
                f"background-image: url('file://{self.image_path}');"
                "background-size: cover; background-position: center;"
            )
        else:
            self.display_box.set_style("")

    def _process_and_cache_image(self, original_path: str):
        try:
            cropped = _crop_pixbuf(
                GdkPixbuf.Pixbuf.new_from_file(original_path), THUMB_W, THUMB_H
            )
            cache_name = (
                f"bg_crop_{hash(self.text)}_{os.path.basename(original_path)}.png"
            )
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
        )
        dialog.get_style_context().add_class("agenda-file-chooser-dialog")
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
        self._build_input_stack()
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
        self.new_text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        self.new_text_view.set_size_request(-1, 80)

        editor_box = Box(
            name="editor-box",
            orientation="v",
            spacing=6,
            children=[
                self.new_text_view,
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
        self.input_stack.set_visible_child_name("trigger")

    def _build_list(self):
        self.listbox = Gtk.ListBox(name="agenda-list-box")
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.set_header_func(self._update_header)

    def _assemble(self):
        scrolled = ScrolledWindow(
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
            overlays=self.input_stack,
        )

    def _show_editor(self, _widget):
        self.input_stack.set_visible_child_name("editor")
        self.new_text_view.grab_focus()

    def _hide_editor(self, _widget):
        self.input_stack.set_visible_child_name("trigger")

    def _update_header(self, row, before):
        if before:
            row.set_header(Box(style="min-height: 3px"))

    def _add_item(self, _widget):
        buf = self.new_text_view.get_buffer()
        text = buf.get_text(*buf.get_bounds(), True).strip()
        if not text:
            return
        # add to the beginning
        self.listbox.prepend(AgendaItem(text, self._remove_item, self.save_to_disk))
        buf.set_text("")
        self.input_stack.set_visible_child_name("trigger")
        self.show_all()
        self.save_to_disk()

    def _remove_item(self, item: AgendaItem):
        self.listbox.remove(item)
        self.save_to_disk()

    def load_from_disk(self):
        if not os.path.exists(DATA_FILE):
            return
        try:
            with open(DATA_FILE) as f:
                for item in reversed(json.load(f)):
                    text = item if isinstance(item, str) else item.get("text")
                    img = None if isinstance(item, str) else item.get("image")
                    # add to the beginning
                    self.listbox.prepend(
                        AgendaItem(text, self._remove_item, self.save_to_disk, img)
                    )
            self.show_all()
        except Exception as e:
            logger.error(f"Error loading agenda: {e}")

    def save_to_disk(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        items = [
            {"text": row.text, "image": row.image_path}
            for row in self.listbox.get_children()
            if hasattr(row, "text")
        ]
        with open(DATA_FILE, "w") as f:
            json.dump(items, f, indent=4)
