from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.revealer import Revealer
from fabric.widgets.eventbox import EventBox
from fabric.widgets.scrolledwindow import ScrolledWindow

from widgets.clipping_box import ClippingBox
from widgets.material_label import MaterialIconLabel
from services.clipboard_service import ClipboardService, ClipEntry

import icons
from config.config import config

import gi

gi.require_version("Gtk", "3.0")
import os

from gi.repository import Gdk, GdkPixbuf, GLib, Gtk  # type: ignore


class ClipboardHistory(Box):
    PAGE_SIZE = (600, 380)
    PREVIEW_CHARS = 200
    PREVIEW_IMAGE_SIZE = (440, 150)
    # copied files: how many image files a row previews side by side
    MAX_FILE_PREVIEWS = 4
    # ignores CapsLock, NumLock, etc.
    _CORE_MODS = (
        Gdk.ModifierType.SHIFT_MASK
        | Gdk.ModifierType.CONTROL_MASK
        | Gdk.ModifierType.MOD1_MASK
    )

    def __init__(self, window, **kwargs):
        super().__init__(name="clipboard", **kwargs)
        self._pill = window
        self._service = ClipboardService.get_default()
        # rows and their entries, newest first (index 0 = bottom row)
        self._row_entries: list[ClipEntry] = []
        self._row_widgets: list[Gtk.Widget] = []
        self.selected_index = -1
        self._expanded: ClipEntry | None = None
        self._rebuild_source_id: int | None = None
        self._thumbs: dict[tuple, GdkPixbuf.Pixbuf | None] = {}
        # copied files -> their image files as (path, width, height)
        self._file_images: dict[str, list[tuple[str, int, int]]] = {}
        # row that got the button press; a click copies on release over it
        self._pressed_row: Gtk.Widget | None = None

        self._build_keymap()
        self._build_ui()
        self.show_all()
        # visibility of these follows the history; the pill's show_all() on
        # close must not override it
        self.empty_box.set_no_show_all(True)
        self.viewport.set_no_show_all(True)

        self._service.connect("changed", lambda *_: self._queue_rebuild())
        self._rebuild()

    def _build_keymap(self):
        binds = config.get("bindings.modules.clipboard")

        def key(name):
            keyval, mods = Gtk.accelerator_parse(binds[f"clipboard.{name}"])
            return keyval, int(mods)

        self._keymap = {
            key("move_up"): lambda: self._move(1),
            key("move_down"): lambda: self._move(-1),
            key("activate"): self._activate,
            key("expand"): self._toggle_expanded,
            key("delete"): self._delete_current,
        }

    @staticmethod
    def _icon_button(icon, tooltip, on_clicked, name="clipboard-icon-btn", **kw):
        btn = Button(
            name=name,
            child=MaterialIconLabel(icon_text=icon.symbol()),
            tooltip_text=tooltip,
            on_clicked=on_clicked,
            **kw,
        )
        btn.set_can_focus(False)
        btn.set_focus_on_click(False)
        return btn

    def _build_ui(self):
        # list page
        self.viewport = Box(name="viewport", spacing=3, v_align="end", orientation="v")
        # empty state, centred in the page: icon, title, hint
        self.empty_label = Label(name="clipboard-empty", label="Nothing copied yet")
        self.empty_box = Box(
            name="clipboard-empty-box",
            orientation="v",
            spacing=6,
            h_align="center",
            v_align="center",
            v_expand=True,
            children=[
                MaterialIconLabel(
                    name="clipboard-empty-icon",
                    style="margin-top: 20px",  # cuz of the page spacing between the entry and list box
                    icon_text=icons.content_copy.symbol(),
                    h_align="center",
                ),
                self.empty_label,
            ],
        )
        self.list_scroll = ScrolledWindow(
            name="app-scrolled-window",
            style_classes="" if not config.VERTICAL else "vertical",
            child=Box(orientation="v", children=[self.empty_box, self.viewport]),
            h_scrollbar_policy="never",
            propagate_width=False,
            propagate_height=False,
        )

        # expanded page
        self.detail_info = Label(name="clipboard-detail-info", h_align="start")
        self.detail_text = Label(
            name="clipboard-detail-text",
            h_align="fill",
            v_align="start",
            line_wrap="word-char",
            selectable=True,
        )
        self.detail_text.set_xalign(0)
        self.detail_text.set_max_width_chars(1)  # wrap to the page, not the text
        self.detail_image = Image(name="clipboard-detail-image", v_align="center")
        self.detail_body = Stack(
            transition_type="none", children=[self.detail_text, self.detail_image]
        )
        self.detail_body.set_homogeneous(False)
        self.detail_scroll = ScrolledWindow(
            name="clipboard-detail-scroll",
            child=self.detail_body,
            h_scrollbar_policy="never",
            propagate_width=False,
            propagate_height=False,
            v_expand=True,
        )
        detail_toolbar = Box(
            name="clipboard-detail-toolbar",
            spacing=4,
            children=[
                self._icon_button(
                    icons.arrow_back, "Back to list", lambda *_: self._collapse()
                ),
                self.detail_info,
                Box(h_expand=True),
                self._icon_button(
                    icons.content_copy,
                    "Copy to clipboard",
                    lambda *_: self._copy(self._expanded),
                ),
                self._icon_button(
                    icons.trash_material,
                    "Delete from history",
                    lambda *_: self._delete_current(),
                    style_classes="danger",
                ),
            ],
        )
        self.detail_page = Box(
            name="clipboard-detail",
            orientation="v",
            spacing=6,
            children=[detail_toolbar, self.detail_scroll],
        )

        self.pages = Stack(
            transition_type="crossfade",
            transition_duration=150,
            children=[self.list_scroll, self.detail_page],
        )
        self.pages.set_homogeneous(True)
        self.pages.set_size_request(*self.PAGE_SIZE)

        # header
        self.search_entry = Entry(
            name="search-entry",
            placeholder="Search Clipboard",
            h_expand=True,
            on_key_press_event=self._on_key_press,
        )
        self.search_entry.props.xalign = 0.5
        self.search_entry.connect("notify::text", lambda *_: self._on_search())

        mode_icon = MaterialIconLabel(
            name="clipboard-mode-icon", icon_text=icons.content_copy.symbol()
        )
        mode_icon.set_tooltip_text("Clipboard history")

        clear_label = Revealer(
            child=Label(name="clipboard-clear-text", label="Clear all"),
            transition_type="slide-right",
            transition_duration=150,
        )
        self.clear_btn = clear_btn = Button(
            name="clipboard-clear-btn",
            child=Box(
                children=[
                    MaterialIconLabel(
                        name="clipboard-clear-icon",
                        icon_text=icons.delete_sweep.symbol(),
                    ),
                    clear_label,
                ],
            ),
            tooltip_text="Delete the whole clipboard history",
            on_clicked=lambda *_: self._service.clear(),
        )
        clear_btn.connect(
            "enter-notify-event", lambda *_: clear_label.set_reveal_child(True)
        )
        clear_btn.connect(
            "leave-notify-event", lambda *_: clear_label.set_reveal_child(False)
        )
        close_btn = Button(
            name="close-button",
            child=MaterialIconLabel(name="close-label", icon_text=icons.close.symbol()),
            tooltip_text="Close",
            on_clicked=lambda *_: self._pill.close(),
        )
        for btn in (clear_btn, close_btn):
            btn.set_can_focus(False)
            btn.set_focus_on_click(False)

        header_box = Box(
            name="header-box",
            spacing=8,
            children=[
                Box(
                    name="search-container",
                    h_expand=True,
                    spacing=4,
                    children=[
                        mode_icon,
                        Box(name="search-container-item-seperator"),
                        self.search_entry,
                    ],
                ),
                clear_btn,
                close_btn,
            ],
        )

        content = Box(
            name="launcher-box",
            spacing=10,
            h_expand=True,
            orientation="v",
            children=[self.pages, header_box],
        )
        shadow = Box(name="clipboard-overlay")
        overlay = Overlay(h_expand=True, child=content, overlays=shadow)
        overlay.set_overlay_pass_through(shadow, True)
        self.add(overlay)

    # called by the pill when this view is shown
    def open(self):
        self._show_list()
        if self.search_entry.get_text():
            self.search_entry.set_text("")  # rebuilds through notify::text
        else:
            self._rebuild()
        self.focus_search()

    def focus_search(self):
        if self.get_mapped():
            self.search_entry.grab_focus_without_selecting()

    def _on_search(self):
        # typing always goes back to the (filtered) list
        self._show_list()
        self._rebuild()

    # list
    def _queue_rebuild(self):
        # coalesce bursts of history changes into one rebuild
        if self._rebuild_source_id is None:
            self._rebuild_source_id = GLib.idle_add(self._on_idle_rebuild)

    def _on_idle_rebuild(self):
        self._rebuild_source_id = None
        self._rebuild()
        return False

    def _rebuild(self, keep_index: int | None = None):
        # a direct rebuild supersedes a queued one (which would reset selection)
        if self._rebuild_source_id is not None:
            GLib.source_remove(self._rebuild_source_id)
            self._rebuild_source_id = None

        query = self.search_entry.get_text().casefold()
        entries = self._service.entries
        if query:
            # images have no text to match
            entries = [
                e for e in entries if not e.is_image and query in e.text.casefold()
            ]

        live = {e.key for e in self._service.entries}
        self._thumbs = {k: v for k, v in self._thumbs.items() if k[0] in live}
        self._file_images = {k: v for k, v in self._file_images.items() if k in live}

        self.viewport.children = []
        self._row_entries = entries
        self._row_widgets = [self._create_row(e) for e in entries]
        # newest at the bottom
        for row in self._row_widgets:
            self.viewport.pack_end(row, False, False, 0)
        if self._row_widgets:
            self._row_widgets[0].get_style_context().add_class("last")
            self._row_widgets[-1].get_style_context().add_class("first")
        for row in self._row_widgets:
            row.show_all()

        if self._service.entries:
            self.empty_label.set_label("No matches")
        else:
            self.empty_label.set_label("Nothing copied yet")
        self.empty_box.set_visible(not entries)
        # an empty viewport still takes its padding and would push the empty
        # state off centre
        self.viewport.set_visible(bool(entries))
        self.clear_btn.set_sensitive(bool(self._service.entries))

        # the expanded entry is gone (deleted, cleared)
        if self._expanded is not None and self._expanded.key not in live:
            self._show_list()

        self.selected_index = -1
        if entries:
            index = 0 if keep_index is None else keep_index
            self._select(min(index, len(entries) - 1))

    def _images_of(self, entry: ClipEntry) -> list[tuple[str, int, int]]:
        """(path, width, height) of the pictures an entry shows."""
        if entry.is_image:
            return [(entry.image_path, entry.width, entry.height)]
        if not entry.is_files:
            return []
        if entry.key not in self._file_images:
            found = []
            for path in entry.paths:
                if len(found) == self.MAX_FILE_PREVIEWS:
                    break
                # reads the header only; (None, -1, -1) for non-images
                fmt, w, h = GdkPixbuf.Pixbuf.get_file_info(path)
                if fmt is not None and w > 0 and h > 0:
                    found.append((path, w, h))
            self._file_images[entry.key] = found
        return self._file_images[entry.key]

    def _thumbnail(self, entry, path, w, h, max_w, max_h):
        key = (entry.key, path, max_w, max_h)
        if key not in self._thumbs:
            self._thumbs[key] = self._load_scaled(path, w, h, max_w, max_h)
        return self._thumbs[key]

    @staticmethod
    def _load_scaled(path: str, w: int, h: int, max_w: int, max_h: int):
        # fit inside max_w x max_h, never upscale
        scale = min(max_w / max(w, 1), max_h / max(h, 1), 1.0)
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_scale(
                path, max(1, int(w * scale)), max(1, int(h * scale)), True
            )
        except GLib.Error:
            return None

    def _image_strip(self, entry: ClipEntry, images) -> Gtk.Widget:
        max_w, max_h = self.PREVIEW_IMAGE_SIZE
        if len(images) > 1:
            max_w, max_h = max_w // len(images) - 6, 110
        return Box(
            spacing=6,
            h_align="start",
            children=[
                ClippingBox(
                    name="clipboard-image-preview",
                    v_align="center",
                    children=Image(
                        pixbuf=self._thumbnail(entry, path, w, h, max_w, max_h)
                    ),
                )
                for path, w, h in images
            ],
        )

    @staticmethod
    def _short_dir(path: str) -> str:
        home = os.path.expanduser("~")
        parent = os.path.dirname(path)
        return "~" + parent[len(home) :] if parent.startswith(home) else parent

    def _files_desc(self, entry: ClipEntry, images) -> str:
        paths = entry.paths
        where = self._short_dir(paths[0])
        if not any(os.path.exists(p) for p in paths):
            return f"{'File' if len(paths) == 1 else f'{len(paths)} files'} · missing"
        if len(paths) == 1:
            if images:
                return f"Image file · {images[0][1]} × {images[0][2]} · {where}"
            kind = "Folder" if os.path.isdir(paths[0]) else "File"
            return f"{kind} · {where}"
        return f"{len(paths)} files · {where}"

    def _create_row(self, entry: ClipEntry) -> Gtk.Widget:
        if entry.is_image:
            desc = f"Image · {entry.width} × {entry.height}"
            preview = self._image_strip(entry, self._images_of(entry))
        elif entry.is_files:
            images = self._images_of(entry)
            paths = entry.paths
            names = Label(
                name="app-label",
                label=", ".join(os.path.basename(p.rstrip("/")) or p for p in paths),
                ellipsization="end",
                h_align="fill",
                h_expand=True,
                max_chars_width=1,
            )
            names.set_xalign(0)
            icon = (
                icons.folder_material
                if len(paths) == 1 and os.path.isdir(paths[0])
                else icons.description
            )
            title_row = Box(
                spacing=6,
                children=[
                    MaterialIconLabel(
                        name="clipboard-file-icon", icon_text=icon.symbol()
                    ),
                    names,
                ],
            )
            desc = self._files_desc(entry, images)
            preview = (
                Box(
                    orientation="v",
                    spacing=6,
                    children=[self._image_strip(entry, images), title_row],
                )
                if images
                else title_row
            )
        else:
            title = " ".join(entry.text[: self.PREVIEW_CHARS].split())
            lines = entry.text.count("\n") + 1
            desc = f"{len(entry.text)} chars" + (
                f" · {lines} lines" if lines > 1 else ""
            )
            preview = Label(
                name="app-label",
                label=title,
                ellipsization="end",
                h_align="fill",
                max_chars_width=1,  # fill the row, don't widen it
            )
            preview.set_xalign(0)

        # ellipsized so long paths can't widen the fixed-size page
        desc_label = Label(
            name="app-desc",
            label=desc,
            ellipsization="middle",
            h_align="fill",
            max_chars_width=1,
        )
        desc_label.set_xalign(0)

        actions = Box(
            name="clipboard-row-actions",
            spacing=4,
            v_align="start",
            children=[
                self._icon_button(
                    icons.open_in_full,
                    "Expand",
                    lambda *_: self._expand(entry),
                ),
                self._icon_button(
                    icons.trash_material,
                    "Delete from history",
                    lambda *_: self._delete(entry),
                    style_classes="danger",
                ),
            ],
        )
        row_box = Box(
            name="clipboard-row-box",
            spacing=12,
            children=[
                Box(
                    orientation="v",
                    spacing=4,
                    h_expand=True,
                    v_align="start",
                    children=[
                        preview,
                        desc_label,
                    ],
                ),
                actions,
            ],
        )
        row = EventBox(name="clipboard-row", child=row_box, events="all")
        row.set_tooltip_text("Click to copy back to the clipboard")
        row.connect("enter-notify-event", self._on_row_crossing, True)
        row.connect("leave-notify-event", self._on_row_crossing, False)
        row.connect("button-press-event", self._on_row_press, actions)
        row.connect("button-release-event", self._on_row_release, entry)
        return row

    @staticmethod
    def _on_row_crossing(row, event, inside):
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        ctx = row.get_style_context()
        ctx.add_class("hover") if inside else ctx.remove_class("hover")
        return False

    def _on_row_press(self, row, event, actions):
        if event.button != 1:
            return False
        # presses on the row's own buttons are theirs
        widget = Gtk.get_event_widget(event)
        if widget is not None and (widget is actions or widget.is_ancestor(actions)):
            return False
        if event.type == Gdk.EventType.BUTTON_PRESS:  # not double/triple clicks
            self._pressed_row = row
            row.get_style_context().add_class("pressed")
        # handled: unhandled presses reach the pill window, which starts a
        # window drag that never ends (its release would never arrive)
        return True

    def _on_row_release(self, row, event, entry):
        if event.button != 1:
            return False
        pressed, self._pressed_row = self._pressed_row, None
        row.get_style_context().remove_class("pressed")
        if pressed is not row:
            return False
        # a click is press + release on the same row; dragging off cancels it
        alloc = row.get_allocation()
        if 0 <= event.x < alloc.width and 0 <= event.y < alloc.height:
            self._copy(entry)
        return True

    def _select(self, new_index: int):
        rows = self._row_widgets
        if 0 <= self.selected_index < len(rows):
            rows[self.selected_index].get_style_context().remove_class("selected")
        if 0 <= new_index < len(rows):
            row = rows[new_index]
            row.get_style_context().add_class("selected")
            self.selected_index = new_index
            self._scroll_to(row)
        else:
            self.selected_index = -1

    def _scroll_to(self, row: Gtk.Widget):
        def clamp(alloc):
            self.list_scroll.get_vadjustment().clamp_page(
                alloc.y - 12, alloc.y + alloc.height
            )

        alloc = row.get_allocation()
        if alloc.height > 1 and alloc.y >= 0:
            clamp(alloc)
            return

        def on_allocate(widget, a):
            widget.disconnect(handler_id)
            clamp(a)

        handler_id = row.connect("size-allocate", on_allocate)

    def _selected_entry(self) -> ClipEntry | None:
        if 0 <= self.selected_index < len(self._row_entries):
            return self._row_entries[self.selected_index]
        return None

    # expanded view
    def _expand(self, entry: ClipEntry | None):
        if entry is None:
            return
        if entry in self._row_entries:
            self._select(self._row_entries.index(entry))
        self._expanded = entry
        images = self._images_of(entry)
        if images and (entry.is_image or len(entry.uris) == 1):
            path, w, h = images[0]
            self.detail_info.set_label(
                f"Image · {w} × {h}"
                if entry.is_image
                else f"{os.path.basename(path)} · {w} × {h}"
            )
            self.detail_image.set_from_pixbuf(
                self._load_scaled(
                    path, w, h, self.PAGE_SIZE[0] - 12, self.PAGE_SIZE[1] - 68
                )
            )
            self.detail_body.set_visible_child(self.detail_image)
        elif entry.is_files:
            n = len(entry.uris)
            self.detail_info.set_label(f"{n} file{'s' if n > 1 else ''}")
            self.detail_text.set_text(entry.text)
            self.detail_body.set_visible_child(self.detail_text)
        else:
            lines = entry.text.count("\n") + 1
            self.detail_info.set_label(
                f"{len(entry.text)} chars · {lines} line{'s' if lines > 1 else ''}"
            )
            self.detail_text.set_text(entry.text)
            self.detail_body.set_visible_child(self.detail_text)
        self.detail_scroll.get_vadjustment().set_value(0)
        self.pages.set_visible_child(self.detail_page)

    def _collapse(self):
        self._show_list()
        self.focus_search()

    def _show_list(self):
        self._expanded = None
        self.pages.set_visible_child(self.list_scroll)
        # drop the full-size text/image
        self.detail_text.set_text("")
        self.detail_image.clear()

    def _toggle_expanded(self):
        if self._expanded is not None:
            self._collapse()
        else:
            self._expand(self._selected_entry())

    # actions
    def _copy(self, entry: ClipEntry | None):
        if entry is None:
            return
        self._service.copy(entry)
        self._pill.close()

    def _activate(self):
        self._copy(self._expanded or self._selected_entry())

    def _delete(self, entry: ClipEntry):
        index = (
            self._row_entries.index(entry)
            if entry in self._row_entries
            else self.selected_index
        )
        self._service.remove(entry)
        # rebuild now (not on idle) so the selection can stay in place
        self._rebuild(keep_index=index)
        self.focus_search()

    def _delete_current(self):
        entry = self._expanded or self._selected_entry()
        if entry is not None:
            self._delete(entry)

    def _move(self, delta: int):
        if self._expanded is not None:
            # scroll the expanded entry instead
            adj = self.detail_scroll.get_vadjustment()
            adj.set_value(adj.get_value() - delta * adj.get_step_increment() * 3)
            return
        if not self._row_entries:
            return
        self._select(
            max(0, min(self.selected_index + delta, len(self._row_entries) - 1))
        )

    def _on_key_press(self, _widget, event):
        action = self._keymap.get((event.keyval, int(event.state & self._CORE_MODS)))
        if action is None:
            return False
        action()
        return True
