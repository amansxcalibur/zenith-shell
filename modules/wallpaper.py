import os
import shlex
import bisect
import shutil
import subprocess
from pathlib import Path
from loguru import logger
from PIL import Image, ImageOps
from concurrent.futures import ThreadPoolExecutor
from expressive_shapes.shapes import sunny, pill

from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.widgets.revealer import Revealer
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.core.service import Service, Signal
from fabric.utils.helpers import exec_shell_command_async

from widgets.clipping_box import ClippingBox
from widgets.material_label import MaterialFontLabel, MaterialIconLabel
from widgets.shapes.expressive.morphing_shapes import InteractiveMorphShape

import icons
from config.config import config
from config.info import CONFIG_DIR, CACHE_DIR, IS_WAYLAND
from utils.helpers import hash_file
from utils.lock import (
    generate_lockscreen_image,
    LOCKSCREEN_IMG_FILE,
    LOCKSCREEN_BLURRED_IMG_FILE,
)

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gtk, GLib, Gio, Gdk  # type: ignore

# paths
WP_CACHE = Path(CACHE_DIR) / "wallpapers"
WP_THUMBS_DIR = WP_CACHE / "thumbs"
WP_PREVIEW_DIR = WP_CACHE / "previews"
WP_HISTORY = Path(CACHE_DIR) / "current_wallpaper.txt"
WP_PREVIEW_FILE = WP_PREVIEW_DIR / "low_rez.png"
WP_PREVIEW_TEMP = WP_PREVIEW_DIR / "low_rez.tmp.png"

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")


def ensure_wallpaper_dirs():
    WP_THUMBS_DIR.mkdir(parents=True, exist_ok=True)
    WP_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def get_thumbnail_cache_path(file_path: str) -> Path:
    file_hash = hash_file(Path(file_path))
    return WP_THUMBS_DIR / f"{file_hash}.png"


def generate_wallpaper_preview(image_path: str | Path) -> Path | None:
    try:
        ensure_wallpaper_dirs()

        with Image.open(image_path) as img:
            img.thumbnail((400, 200))
            # atomic save - write to temp first to prevent half-baked images
            img.save(WP_PREVIEW_TEMP, "PNG")

        # replace temp
        WP_PREVIEW_TEMP.replace(WP_PREVIEW_FILE)
        return WP_PREVIEW_FILE
    except Exception as e:
        logger.error(f"Preview generation failed for {image_path}: {e}")
        return None


def save_wallpaper_history(full_path: str) -> None:
    WP_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    WP_HISTORY.write_text(full_path)


class WallpaperService(Service):
    _instance = None

    @Signal
    def wallpaper_changed(self, full_path: str, preview_path: str) -> None: ...

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._wallpaper_path = None
            cls._instance._preview_path = None
            cls._instance._initialized = False
            cls._instance._executor = ThreadPoolExecutor(max_workers=1)
        return cls._instance

    def initialize(self):
        if self._initialized:
            return

        self._initialized = True
        ensure_wallpaper_dirs()

        self._executor.submit(self._restore_state)

    def _restore_state(self):
        if not WP_HISTORY.exists():
            logger.warning("No wallpaper history found")
            return

        try:
            full_path = WP_HISTORY.read_text().strip()

            if not full_path or not Path(full_path).exists():
                logger.warning(f"Wallpaper not found: {full_path}")
                return

            # generate preview if it doesn't exist
            preview_path = (
                WP_PREVIEW_FILE
                if WP_PREVIEW_FILE.exists()
                else generate_wallpaper_preview(full_path)
            )

            self.apply_wallpaper(full_path)

            self._set_state(full_path, preview_path)

            if preview_path:
                self.wallpaper_changed(full_path, str(preview_path))

            logger.info(f"Restored wallpaper: {full_path}")

        except Exception as e:
            logger.error(f"Failed to initialize wallpaper: {e}")

    def _set_state(self, full_path: str, preview_path: Path | str | None):
        self._wallpaper_path = full_path
        self._preview_path = str(preview_path) if preview_path else None

    def apply_wallpaper(self, full_path: str):
        if IS_WAYLAND:
            swaybg_bin = shutil.which("swaybg")
            if not swaybg_bin:
                logger.error("'swaybg' binary not found.")
                exec_shell_command_async(
                    "notify-send -a 'Zenith Wallpaper' 'Zenith Error' '\"swaybg\" not found. Wallpaper not applied.'"
                )
                return

            # apply wallpaper
            subprocess.run(["pkill", "-x", "swaybg"], check=False)
            subprocess.Popen(
                [swaybg_bin, "-i", full_path, "-m", "fill"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        else:
            feh_bin = shutil.which("feh")
            if not feh_bin:
                logger.error("'feh' binary not found.")
                exec_shell_command_async(
                    "notify-send -a 'Zenith Wallpaper' 'Zenith Error' '\"feh\" not found. Wallpaper not applied.'"
                )
                return

            # apply wallpaper
            exec_shell_command_async(f"{feh_bin} --zoom fill --bg-fill '{full_path}'")

    def set_wallpaper_path(self, full_path: str, preview_path: str | None):
        self._set_state(full_path, preview_path)
        self.wallpaper_changed(full_path, preview_path)

    def get_wallpaper_path(self) -> str | None:
        return self._wallpaper_path

    def get_preview_path(self) -> str | None:
        return self._preview_path

    def get_lockscreen_image_path(self, blurred: bool = True) -> str | None:
        if blurred:
            return (
                LOCKSCREEN_BLURRED_IMG_FILE
                if LOCKSCREEN_BLURRED_IMG_FILE.exists()
                else None
            )
        return LOCKSCREEN_IMG_FILE if LOCKSCREEN_IMG_FILE.exists() else None


class WallpaperSelector(Box):
    COLUMNS: int = 7
    IMG_THUMB_SIZE: int = 96
    DEFAULT_SCHEME = "scheme-fidelity"
    SCHEMES = {  # noqa: RUF012
        "scheme-tonal-spot": "Tonal Spot",
        "scheme-content": "Content",
        "scheme-expressive": "Expressive",
        "scheme-fidelity": "Fidelity",
        "scheme-fruit-salad": "Fruit Salad",
        "scheme-monochrome": "Monochrome",
        "scheme-neutral": "Neutral",
        "scheme-rainbow": "Rainbow",
    }
    # ignores CapsLock, NumLock, etc.
    _CORE_MODS = (
        Gdk.ModifierType.SHIFT_MASK
        | Gdk.ModifierType.CONTROL_MASK
        | Gdk.ModifierType.MOD1_MASK
    )

    def __init__(self, window, **kwargs):
        self._pill = window
        super().__init__(
            name="wallpapers",
            spacing=10,
            orientation="v",
            h_expand=False,
            v_expand=False,
            **kwargs,
        )
        self.wallpaper_service = WallpaperService()
        self.executor = ThreadPoolExecutor(max_workers=5)
        self.file_monitor = None
        self._scan_generation = 0

        # main thread only. _names is kept sorted and mirrors FlowBox order,
        # so get_children() order == display order.
        self._children: dict[str, Gtk.FlowBoxChild] = {}
        self._names: list[str] = []

        self._build_viewport()
        self._build_header()
        self._build_dir_chooser()
        self._build_layout()
        self._build_keymap()

        self.show_all()
        self.search_entry.connect("map", lambda *_: self.reset_search())
        self._refresh_dir_state()

    def _build_viewport(self):
        vp = self.viewport = Gtk.FlowBox()
        vp.set_name("wallpaper-flowbox")
        vp.set_selection_mode(Gtk.SelectionMode.SINGLE)
        vp.set_activate_on_single_click(True)
        vp.set_column_spacing(5)
        vp.set_row_spacing(5)
        vp.set_homogeneous(True)
        vp.set_max_children_per_line(self.COLUMNS)
        vp.set_min_children_per_line(self.COLUMNS)
        vp.set_vexpand(False)
        vp.set_valign(Gtk.Align.START)
        # focus stays in the search entry, selection is driven by code
        vp.set_can_focus(False)
        vp.set_filter_func(self._filter_func)
        vp.connect("child-activated", self.on_wallpaper_selected)

        self.scrolled_window = ScrolledWindow(
            name="scrolled-window",
            spacing=10,
            h_expand=True,
            v_expand=True,
            style_classes="launcher",
            min_content_size=(5, 5),
            max_content_size=(5, 5),
            child=vp,
            h_scrollbar_policy="never",
        )

    def _build_header(self):
        self.search_entry = Entry(
            name="search-entry-walls",
            placeholder="Search Wallpapers",
            h_expand=True,
            style_classes="vertical" if config.VERTICAL else "",
            on_key_press_event=self.on_search_entry_key_press,
        )
        # override gtk entry 150px internal min width
        self.search_entry.set_width_chars(1)
        self.search_entry.set_size_request(20, -1)
        self.search_entry.props.xalign = 0.5
        self.search_entry.connect("notify::text", self._on_search_changed)

        self.scheme_dropdown = Gtk.ComboBoxText()
        self.scheme_dropdown.set_name("scheme-dropdown")
        self.scheme_dropdown.set_tooltip_text("Select color scheme")
        self._no_focus(self.scheme_dropdown)
        for key, display_name in self.SCHEMES.items():
            self.scheme_dropdown.append(key, display_name)
        self.scheme_dropdown.set_active_id(self.DEFAULT_SCHEME)
        self.scheme_dropdown.connect("changed", self.on_scheme_changed)
        self.scheme_dropdown.connect("notify::popup-shown", self._on_popup_shown)

        self.mat_icon = Label(name="mat-label", markup=icons.palette.markup())

        self.wall_dir_path_label = Label(
            style="color: var(--foreground); font-size: 14px",
            ellipsization="middle",
            max_chars_width=35,
            h_align="start",
        )
        self.launcher_options_revealer = Revealer(
            child=Box(
                spacing=5,
                name="launch-options-box",
                style="padding: 0 8px;",
                children=Box(
                    orientation="v",
                    children=[
                        Label(
                            label="Current folder:",
                            h_align="start",
                            style="color: var(--outline); font-size: 13px; margin-bottom: -4px",
                        ),
                        self.wall_dir_path_label,
                    ],
                ),
            ),
            transition_type="slide-left",
            transition_duration=150,
        )
        open_btn = Button(
            style_classes="launch-mode-btn",
            child=MaterialIconLabel(
                icon_text=icons.folder_open.symbol(),
                FILL=1,
                style="font-size: 20px; color: var(--primary)",
            ),
            on_clicked=lambda *_: self.prompt_for_dir(),
            tooltip_text="Open directory",
        )
        launch_mode = Box(
            name="launch-mode-box",
            children=[open_btn, self.launcher_options_revealer],
        )
        launch_mode_event_box = EventBox(
            name="launch-mode-event-container", child=launch_mode, events="all"
        )
        launch_mode_event_box.connect("enter-notify-event", self._on_hover_enter)
        launch_mode_event_box.connect("leave-notify-event", self._on_hover_leave)

        close_btn = Button(
            name="close-button",
            child=MaterialIconLabel(name="close-label", icon_text=icons.close.symbol()),
            tooltip_text="Exit",
            on_clicked=lambda *_: self._pill.open(),
        )
        for btn in (open_btn, close_btn):
            self._no_focus(btn)

        self.header_box = Box(
            name="header-box",
            orientation="h",
            h_expand=True,
            spacing=8,
            children=[
                Box(
                    name="search-container",
                    h_expand=True,
                    spacing=4,
                    children=[
                        launch_mode_event_box,
                        Box(name="search-container-item-seperator"),
                        self.search_entry,
                    ],
                ),
                self.scheme_dropdown,
                close_btn,
            ],
        )

    def _build_dir_chooser(self):
        btn = Button(
            style="margin: 18px; padding: 52px;",
            child=MaterialIconLabel(
                icon_text=icons.add_material.symbol(),
                FILL=0,
                style="font-size: 120px; color: var(--surface)",
            ),
            on_clicked=lambda *_: self.prompt_for_dir(),
        )
        self._no_focus(btn)
        shape = InteractiveMorphShape(
            clip=True, shape_start=pill, shape_end=sunny, child=btn
        )
        btn.connect("enter-notify-event", shape.play_forward)
        btn.connect("leave-notify-event", shape.play_backward)

        self.dir_chooser = Box(
            h_expand=True,
            h_align="center",
            v_align="center",
            v_expand=True,
            orientation="v",
            style="color: var(--primary);",
            children=[
                shape,
                MaterialFontLabel(
                    text="Choose Wallpaper Directory",
                    font_family="Google Sans Flex",
                    style="color: var(--foreground); font-size: 20px",
                ),
            ],
        )

    def _build_layout(self):
        self.stack = Stack(
            v_expand=True,
            children=[self.dir_chooser, self.scrolled_window],
            interpolate_size=True,
        )
        self.stack.set_homogeneous(False)

        shadow = Box(name="wallpaper-overlay")
        self.overlay = Overlay(
            v_expand=True,
            child=Box(
                name="wallpaper-selector",
                spacing=10,
                orientation="v",
                children=[self.stack, self.header_box],
            ),
            overlays=shadow,
        )
        self.overlay.set_overlay_pass_through(shadow, True)

        self.dir_picker_indicator = Box(
            style="padding: 20px 30px;",
            spacing=8,
            children=[
                MaterialIconLabel(icon_text=icons.wallpaper.symbol()),
                MaterialFontLabel(
                    font_family="Google Sans Flex",
                    text="Choosing Wallpaper Folder...",
                ),
            ],
        )
        self.view_stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            children=[self.overlay, self.dir_picker_indicator],
            interpolate_size=True,
        )
        self.view_stack.set_homogeneous(False)
        self.add(self.view_stack)

    def _build_keymap(self):
        binds = config.get("bindings.modules.wallpaper")

        def key(name):
            keyval, mods = Gtk.accelerator_parse(binds[f"wallpaper.{name}"])
            return keyval, int(mods)

        C = self.COLUMNS
        self._keymap = {
            key("scheme_prev"): lambda: self._cycle_scheme(-1),
            key("scheme_next"): lambda: self._cycle_scheme(1),
            key("scheme_open"): lambda: self.scheme_dropdown.popup(),
            key("move_up"): lambda: self._move_selection(-C),
            key("move_down"): lambda: self._move_selection(C),
            key("move_left"): lambda: self._move_selection(-1),
            key("move_right"): lambda: self._move_selection(1),
            key("activate"): self._activate_selected,
        }

    # Policy: the search entry is the only focusable widget in this view.
    # Everything else is can_focus=False / focus_on_click=False, so focus
    # never leaves and no focus-out handler is needed. The two things that
    # can still steal focus (the scheme popup, the dir dialog) hand it back
    # explicitly through focus_search().

    @staticmethod
    def _no_focus(widget):
        widget.set_can_focus(False)
        if hasattr(widget, "set_focus_on_click"):
            widget.set_focus_on_click(False)

    def focus_search(self):
        entry = self.search_entry
        if entry.get_sensitive() and self.get_mapped():
            # plain grab_focus() selects all text, so the next keystroke
            # would replace the query
            entry.grab_focus_without_selecting()

    def reset_search(self):
        self.search_entry.set_text("")
        self.focus_search()

    def _on_popup_shown(self, combo, _pspec):
        if not combo.get_property("popup-shown"):
            self.focus_search()

    def _on_hover_enter(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.launcher_options_revealer.set_reveal_child(True)
        return False

    def _on_hover_leave(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.launcher_options_revealer.set_reveal_child(False)
        return False

    def set_header_controls_state(self, active: bool):
        opacity = 1.0 if active else 0.5
        for w in (self.search_entry, self.scheme_dropdown):
            w.set_sensitive(active)
            w.set_opacity(opacity)

    def _set_wall_dir_label(self, path: str | None):
        label = self.wall_dir_path_label
        label.set_label(path or "None")
        label.set_tooltip_text(path if path and len(path) > 35 else None)

    def _refresh_dir_state(self):
        """Single place that syncs UI + monitor + scan with config.WALLPAPERS_DIR."""
        has_dir = os.path.isdir(config.WALLPAPERS_DIR)
        self.stack.set_visible_child(
            self.scrolled_window if has_dir else self.dir_chooser
        )
        self.set_header_controls_state(has_dir)
        self._set_wall_dir_label(str(config.WALLPAPERS_DIR) if has_dir else None)
        if has_dir:
            self.setup_file_monitor()
            self.executor.submit(self._perform_scan_and_clean)

    def _build_dir_dialog(self, parent: Gtk.Window) -> Gtk.FileChooserDialog:
        dialog = Gtk.FileChooserDialog(
            "Select a Directory",
            parent,
            Gtk.FileChooserAction.SELECT_FOLDER,
            use_header_bar=False,
        )
        if IS_WAYLAND:
            dialog.get_style_context().add_class("wayland")
        for stock, response, extra in (
            (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, None),
            (Gtk.STOCK_OPEN, Gtk.ResponseType.OK, "bright"),
        ):
            ctx = dialog.add_button(stock, response).get_style_context()
            ctx.add_class("settings-btn")
            if extra:
                ctx.add_class(extra)
        return dialog

    def prompt_for_dir(self):
        win = self.get_toplevel()
        if not isinstance(win, Gtk.Window):
            logger.error("WallpaperSelector not attached to a Gtk.Window.")
            return

        if IS_WAYLAND:
            self.view_stack.set_visible_child(self.dir_picker_indicator)
        dialog = self._build_dir_dialog(win)
        try:
            # blocking
            response = dialog.run()
            path = dialog.get_filename() if response == Gtk.ResponseType.OK else None
        finally:
            dialog.destroy()
            if IS_WAYLAND:
                self.view_stack.set_visible_child(self.overlay)

        if path:
            config.WALLPAPERS_DIR = path
            self._refresh_dir_state()
            logger.info(f"New wallpaper directory selected: {path}")
        else:
            logger.info("Wallpaper directory selection canceled.")
        self.focus_search()

    def _clear_wallpapers(self):
        for child in self.viewport.get_children():
            self.viewport.remove(child)
        self._children.clear()
        self._names.clear()
        self.viewport.unselect_all()
        return False

    def _perform_scan_and_clean(self):
        ensure_wallpaper_dirs()

        self._scan_generation += 1
        generation = self._scan_generation
        GLib.idle_add(self._clear_wallpapers)

        try:
            files = sorted(
                f for f in os.listdir(config.WALLPAPERS_DIR) if self._is_image(f)
            )
        except OSError as e:
            logger.error(f"Failed to list wallpapers dir: {e}")
            return

        for file_name in files:
            if generation != self._scan_generation:
                return
            self.executor.submit(self._process_thumbnail_task, file_name, generation)

    def _process_thumbnail_task(self, file_name: str, generation: int | None = None):
        """Worker thread. Does all disk IO, hands bytes to the UI thread."""
        generation = self._scan_generation if generation is None else generation
        try:
            src = os.path.join(config.WALLPAPERS_DIR, file_name)
            cache = get_thumbnail_cache_path(src)
            # regenerate when missing or older than the source
            if not cache.exists() or cache.stat().st_mtime < os.path.getmtime(src):
                self._write_thumbnail(src, cache)
            image_bytes = cache.read_bytes()
        except Exception as e:
            logger.error(f"Thumbnail task failed for {file_name}: {e}")
            return
        GLib.idle_add(self._add_thumbnail_to_ui, file_name, image_bytes, generation)

    @classmethod
    def _write_thumbnail(cls, src, cache):
        size = (cls.IMG_THUMB_SIZE, cls.IMG_THUMB_SIZE)
        with Image.open(src) as img:
            # center square crop + resize in one step
            ImageOps.fit(img, size, Image.Resampling.LANCZOS).save(cache, "PNG")

    def _add_thumbnail_to_ui(self, file_name, image_bytes, generation):
        if generation != self._scan_generation:
            return False
        try:
            stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(image_bytes))
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
        except GLib.Error as e:
            logger.error(f"Error creating pixbuf for {file_name}: {e}")
            return False

        self._remove_child(file_name)  # file changed on disk: replace, don't duplicate
        child = self._create_flowbox_child(
            pixbuf, file_name, is_current=file_name == self._current_name()
        )
        # sorted insert: threads finish in arbitrary order
        pos = bisect.bisect(self._names, file_name)
        self._names.insert(pos, file_name)
        self._children[file_name] = child
        self.viewport.insert(child, pos)
        child.show_all()

        self._ensure_selection()
        return False

    def _remove_child(self, file_name: str):
        child = self._children.pop(file_name, None)
        if child is None:
            return
        self._names.remove(file_name)
        self.viewport.remove(child)

    def setup_file_monitor(self):
        if not os.path.isdir(config.WALLPAPERS_DIR):
            return
        if self.file_monitor is not None and not self.file_monitor.is_cancelled():
            self.file_monitor.cancel()

        gfile = Gio.File.new_for_path(config.WALLPAPERS_DIR)
        self.file_monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.file_monitor.connect("changed", self.on_directory_changed)

    def on_directory_changed(self, monitor, file, other_file, event_type):
        # runs on the main thread, so widget/state access here is safe
        file_name = file.get_basename()
        if not file_name or not self._is_image(file_name):
            return

        if event_type in (
            Gio.FileMonitorEvent.DELETED,
            Gio.FileMonitorEvent.MOVED_OUT,
        ):
            self._remove_child(file_name)
        elif event_type in (
            Gio.FileMonitorEvent.CHANGES_DONE_HINT,
            Gio.FileMonitorEvent.MOVED_IN,
        ):
            self.executor.submit(self._process_thumbnail_task, file_name)

    @staticmethod
    def _build_badge() -> Box:
        badge = Box(
            name="badge-container",
            visible=False,
            all_visible=False,
            orientation="v",
            children=[
                Box(name="badge-hole", h_expand=True, v_expand=True),
                Box(
                    name="badge-label-container",
                    h_expand=True,
                    children=MaterialFontLabel(
                        name="badge-label",
                        h_expand=True,
                        h_align="center",
                        v_align="end",
                        font_family="Google Sans Flex",
                        wght=600,
                        text="CURRENT",
                    ),
                ),
            ],
        )
        badge.set_no_show_all(True)
        badge.set_visible(False)
        return badge

    def _create_flowbox_child(self, pixbuf, file_name, is_current=False):
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.set_name("wallpaper-thumbnail")
        badge = self._build_badge()
        badge.set_visible(is_current)

        box = ClippingBox(
            name="wallpaper-thumbnail-clipper",
            orientation=Gtk.Orientation.VERTICAL,
            children=Overlay(child=image, overlays=badge),
            spacing=4,
        )
        child = Gtk.FlowBoxChild()
        child.set_name("wallpaper-thumbnail-container")
        child.add(box)
        child.set_can_focus(False)
        child.file_name = file_name
        child.badge = badge
        return child

    def _query(self) -> str:
        return self.search_entry.get_text().lower()

    def _filter_func(self, child) -> bool:
        return self._query() in child.file_name.lower()

    def _visible_children(self) -> list:
        q = self._query()
        return [c for c in self.viewport.get_children() if q in c.file_name.lower()]

    def _on_search_changed(self, entry, *_):
        self.arrange_viewport()

    def arrange_viewport(self, *_):
        """Re-filter and select the first match. Filtering hides, never recreates."""
        self.viewport.invalidate_filter()
        visible = self._visible_children()
        if visible:
            self._select(visible[0])
        else:
            self.viewport.unselect_all()

    def _ensure_selection(self):
        """Used while thumbnails stream in, so we don't clobber user navigation."""
        if self.viewport.get_selected_children():
            return
        visible = self._visible_children()
        if visible:
            self.viewport.select_child(visible[0])

    def _select(self, child):
        self.viewport.select_child(child)
        self._scroll_to(child)

    def _scroll_to(self, child):
        # scroll via the adjustment, no grab_focus() so focus stays in the entry
        coords = child.translate_coordinates(self.viewport, 0, 0)
        if coords is None:
            return

        TOP_MARGIN = 12
        _, y = coords
        self.scrolled_window.get_vadjustment().clamp_page(
            y - TOP_MARGIN, y + child.get_allocated_height()
        )

    def _move_selection(self, delta: int):
        visible = self._visible_children()
        if not visible:
            return
        selected = self.viewport.get_selected_children()
        if not selected or selected[0] not in visible:
            self._select(visible[0] if delta > 0 else visible[-1])
            return
        idx = visible.index(selected[0]) + delta
        self._select(visible[max(0, min(idx, len(visible) - 1))])

    def _activate_selected(self):
        selected = self.viewport.get_selected_children()
        if selected:
            self.on_wallpaper_selected(self.viewport, selected[0])

    def _current_name(self) -> str:
        path = self.wallpaper_service.get_wallpaper_path()
        return os.path.basename(path) if path else ""

    def on_wallpaper_selected(self, flowbox, child):
        file_name = child.file_name
        full_path = os.path.join(config.WALLPAPERS_DIR, file_name)
        scheme = self.scheme_dropdown.get_active_id()

        self.wallpaper_service.apply_wallpaper(full_path)

        self.executor.submit(save_wallpaper_history, full_path)
        self.executor.submit(self._generate_theme, full_path, scheme)
        self.executor.submit(generate_lockscreen_image, full_path)
        future = self.executor.submit(generate_wallpaper_preview, full_path)
        future.add_done_callback(lambda fut: self._on_preview_ready(full_path, fut))

        self.update_badge_visibility(target_file_name=file_name)
        self.focus_search()

    def _on_preview_ready(self, full_path, fut):
        try:
            preview_path = fut.result()
        except Exception as e:
            logger.error(f"Preview generation failed: {e}")
            return
        if preview_path:
            self.wallpaper_service.set_wallpaper_path(full_path, str(preview_path))

    def update_badge_visibility(self, target_file_name: str | None = None):
        if target_file_name is None:
            target_file_name = self._current_name()

        def _sync():
            for name, child in self._children.items():
                child.badge.set_visible(name == target_file_name)
            return False

        GLib.idle_add(_sync)

    def on_scheme_changed(self, combo):
        logger.info(f"Color scheme selected: {combo.get_active_id()}")

    def _cycle_scheme(self, delta: int):
        ids = list(self.SCHEMES)
        current = self.scheme_dropdown.get_active_id()
        idx = ids.index(current) if current in ids else 0
        self.scheme_dropdown.set_active((idx + delta) % len(ids))

    def _generate_theme(self, image_path, scheme):
        matugen_bin = shutil.which("matugen")
        if not matugen_bin:
            logger.error("'matugen' not found.")
            exec_shell_command_async(
                "notify-send 'Zenith Shell' '\"matugen\" not found. Theme not updated.'"
            )
            return

        # shlex.quote: filenames containing ' broke the original command
        command = " ".join(
            [
                shlex.quote(matugen_bin),
                "image",
                shlex.quote(str(image_path)),
                "-t",
                shlex.quote(scheme),
                "-c",
                shlex.quote(f"{CONFIG_DIR}/matugen/config.toml"),
                "--source-color-index",
                "0",
            ]
        )
        try:
            process, _ = exec_shell_command_async(command)
            process.wait_check_async(
                None,
                lambda p, r: (
                    logger.info("Theme updated")
                    if p.wait_check_finish(r)
                    else logger.error("Theme failed")
                ),
            )
        except Exception as e:
            logger.exception(f"Matugen error: {e}")

    def on_search_entry_key_press(self, widget, event):
        mods = int(event.state & self._CORE_MODS)
        handler = self._keymap.get((event.keyval, mods))
        if handler is None:
            return False
        handler()
        return True

    @staticmethod
    def _is_image(file_name: str) -> bool:
        return file_name.lower().endswith(IMAGE_EXTENSIONS)

    def destroy(self):
        self._scan_generation += 1  # invalidate queued idle callbacks
        self.executor.shutdown(wait=False, cancel_futures=True)
        if self.file_monitor:
            self.file_monitor.cancel()
        super().destroy()
