import os
import shutil
from PIL import Image
from pathlib import Path
from loguru import logger
from concurrent.futures import ThreadPoolExecutor

from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.core.service import Service, Signal
from fabric.utils.helpers import exec_shell_command_async

from widgets.clipping_box import ClippingBox
from widgets.material_label import MaterialIconLabel

import icons
from config.config import config
from config.info import CONFIG_DIR, CACHE_DIR
from utils.helpers import hash_file
from utils.lock import generate_lockscreen_image

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GdkPixbuf, Gtk, GLib, Gio, Gdk


# paths
WP_CACHE = Path(CACHE_DIR) / "wallpapers"
WP_THUMBS = WP_CACHE / "thumbs"
WP_PREVIEW_DIR = WP_CACHE / "previews"
WP_HISTORY = Path(CACHE_DIR) / "current_wallpaper.txt"
WP_PREVIEW_FILE = WP_PREVIEW_DIR / "low_rez.png"
WP_PREVIEW_TEMP = WP_PREVIEW_DIR / "low_rez.tmp.png"


def ensure_wallpaper_dirs():
    WP_THUMBS.mkdir(parents=True, exist_ok=True)
    WP_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)


def get_thumbnail_cache_path(file_path: str) -> Path:
    file_hash = hash_file(Path(file_path))
    return WP_THUMBS / f"{file_hash}.png"


def generate_wallpaper_preview(image_path: str | Path) -> Path | None:
    """Generate low-res preview for wallpaper. Less memory when loading onto widgets"""
    try:
        WP_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)

        with Image.open(image_path) as img:
            img.thumbnail((400, 200))
            # stomic save - write to temp first to prevent half-baked images
            img.save(WP_PREVIEW_TEMP, "PNG")

        # replace temp
        WP_PREVIEW_TEMP.replace(WP_PREVIEW_FILE)
        return WP_PREVIEW_FILE
    except Exception as e:
        logger.error(f"Preview generation failed for {image_path}: {e}")
        return None


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

            self._apply_wallpaper(full_path)

            # update path refs
            self._wallpaper_path = full_path
            self._preview_path = str(preview_path) if preview_path else None

            if preview_path:
                # emit
                self.wallpaper_changed(full_path, str(preview_path))

            logger.info(f"Restored wallpaper: {full_path}")

        except Exception as e:
            logger.error(f"Failed to initialize wallpaper: {e}")

    def _apply_wallpaper(self, full_path: str):
        feh_bin = shutil.which("feh")
        if not feh_bin:
            logger.error("'feh' binary not found")
            return

        exec_shell_command_async(f"{feh_bin} --zoom fill --bg-fill '{full_path}'")

    def set_wallpaper_path(self, full_path: str, preview_path: str | None):
        self._wallpaper_path = full_path
        if preview_path:
            self._preview_path = preview_path
        self.wallpaper_changed(full_path, preview_path)

    def get_wallpaper_path(self) -> str | None:
        return self._wallpaper_path

    def get_preview_path(self) -> str | None:
        return self._preview_path


class WallpaperSelector(Box):
    COLUMNS: int = 7
    IMG_THUMB_SIZE: int = 96

    def __init__(self, pill, **kwargs):
        self._pill = pill

        super().__init__(
            name="wallpapers",
            spacing=10,
            orientation="v",
            h_expand=False,
            v_expand=False,
            **kwargs,
        )
        self.wallpaper_service = WallpaperService()

        self.files = []
        self.thumbnails_map = {}
        self._visible_children = []
        self.executor = ThreadPoolExecutor(max_workers=5)

        self.executor.submit(self._perform_scan_and_clean)

        self.viewport = Gtk.FlowBox()
        self.viewport.set_name("wallpaper-flowbox")
        self.viewport.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.viewport.set_activate_on_single_click(True)
        self.viewport.set_column_spacing(5)
        self.viewport.set_row_spacing(5)
        self.viewport.set_homogeneous(True)
        self.viewport.set_max_children_per_line(self.COLUMNS)
        self.viewport.set_min_children_per_line(self.COLUMNS)
        self.viewport.set_vexpand(False)
        self.viewport.set_valign(Gtk.Align.START)

        self.viewport.connect("child-activated", self.on_wallpaper_selected)

        self.scrolled_window = ScrolledWindow(
            name="scrolled-window",
            spacing=10,
            h_expand=True,
            v_expand=True,
            style_classes="launcher",
            min_content_size=(5, 5),
            max_content_size=(5, 5),
            child=self.viewport,
            h_scrollbar_policy="never",
        )

        self.search_entry = Entry(
            name="search-entry-walls",
            placeholder="Search Wallpapers...",
            h_expand=True,
            style_classes="" if not config.VERTICAL else "vertical",
            notify_text=lambda entry, *_: self.arrange_viewport(entry.get_text()),
            on_key_press_event=self.on_search_entry_key_press,
        )
        self.search_entry.props.xalign = 0.5
        self.search_entry.connect("focus-out-event", self.on_search_entry_focus_out)

        self.schemes = {
            "scheme-tonal-spot": "Tonal Spot",
            "scheme-content": "Content",
            "scheme-expressive": "Expressive",
            "scheme-fidelity": "Fidelity",
            "scheme-fruit-salad": "Fruit Salad",
            "scheme-monochrome": "Monochrome",
            "scheme-neutral": "Neutral",
            "scheme-rainbow": "Rainbow",
        }

        self.scheme_dropdown = Gtk.ComboBoxText()
        self.scheme_dropdown.set_name("scheme-dropdown")
        self.scheme_dropdown.set_tooltip_text("Select color scheme")
        for key, display_name in self.schemes.items():
            self.scheme_dropdown.append(key, display_name)
        self.scheme_dropdown.set_active_id("scheme-fidelity")
        self.scheme_dropdown.connect("changed", self.on_scheme_changed)

        self.mat_icon = Label(name="mat-label", markup=icons.palette.markup())

        self.header_box = Box(
            name="header-box",
            orientation="h",
            h_expand=True,
            children=[
                self.search_entry,
                self.scheme_dropdown,
                Button(
                    name="close-button",
                    child=MaterialIconLabel(name="close-label", icon_text=icons.close.symbol()),
                    tooltip_text="Exit",
                    on_clicked=lambda *_: self._pill.close(),
                ),
            ],
        )

        self.add(self.scrolled_window)
        self.add(self.header_box)

        self.setup_file_monitor()
        self.show_all()

        def grab_initial_focus(widget):
            widget.grab_focus()
            return False

        self.search_entry.connect("map", grab_initial_focus)

    def _perform_scan_and_clean(self):
        ensure_wallpaper_dirs()
        Path(config.WALLPAPERS_DIR).mkdir(parents=True, exist_ok=True)

        # process and rename old wallpapers
        with os.scandir(config.WALLPAPERS_DIR) as entries:
            for entry in entries:
                if entry.is_file() and self._is_image(entry.name):
                    if entry.name != entry.name.lower() or " " in entry.name:
                        new_name = entry.name.lower().replace(" ", "-")
                        full_path = os.path.join(config.WALLPAPERS_DIR, entry.name)
                        new_full_path = os.path.join(config.WALLPAPERS_DIR, new_name)
                        try:
                            os.rename(full_path, new_full_path)
                        except Exception as e:
                            logger.error(f"Error renaming {entry.name}: {e}")

        # refresh the file list after potential renaming
        all_files = sorted(
            [f for f in os.listdir(config.WALLPAPERS_DIR) if self._is_image(f)]
        )

        self.files = all_files

        # start thumbnail generation jobs
        for file_name in self.files:
            self.executor.submit(self._process_thumbnail_task, file_name)

    def _process_thumbnail_task(self, file_name):
        try:
            full_path = os.path.join(config.WALLPAPERS_DIR, file_name)
            cache_path = get_thumbnail_cache_path(full_path)

            # generate thumbs if missing
            if not cache_path.exists():
                with Image.open(full_path) as img:
                    width, height = img.size
                    side = min(width, height)
                    left = (width - side) // 2
                    top = (height - side) // 2
                    img_cropped = img.crop((left, top, left + side, top + side))
                    img_cropped.thumbnail(
                        (self.IMG_THUMB_SIZE, self.IMG_THUMB_SIZE),
                        Image.Resampling.LANCZOS,
                    )
                    img_cropped.save(cache_path, "PNG")

            # READ BYTES here, so UI thread doesn't have to touch disk
            with open(cache_path, "rb") as f:
                image_bytes = f.read()

            GLib.idle_add(self._add_thumbnail_to_ui, file_name, image_bytes)

        except Exception as e:
            logger.error(f"Thumbnail task failed for {file_name}: {e}")

    def _add_thumbnail_to_ui(self, file_name, image_bytes):
        try:
            # create stream from bytes (Memory operation, very fast)
            stream = Gio.MemoryInputStream.new_from_bytes(GLib.Bytes.new(image_bytes))
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)

            self.thumbnails_map[file_name] = pixbuf

            # pass through current filter and adding
            current_filter = self.search_entry.get_text().lower()
            if current_filter in file_name.lower():
                child = self._create_flowbox_child(pixbuf, file_name)
                self.viewport.add(child)
                child.show_all()
                GLib.idle_add(self.arrange_viewport, self.search_entry.get_text())

        except Exception as e:
            logger.error(f"Error creating pixbuf for {file_name}: {e}")

    def setup_file_monitor(self):
        gfile = Gio.File.new_for_path(config.WALLPAPERS_DIR)
        self.file_monitor = gfile.monitor_directory(Gio.FileMonitorFlags.NONE, None)
        self.file_monitor.connect("changed", self.on_directory_changed)

    def on_directory_changed(self, monitor, file, other_file, event_type):
        self.executor.submit(self._handle_file_change, file, event_type)

    def _handle_file_change(self, file, event_type):
        file_name = file.get_basename()
        if not file_name or not self._is_image(file_name):
            return

        if event_type == Gio.FileMonitorEvent.DELETED:
            if file_name in self.thumbnails_map:
                del self.thumbnails_map[file_name]
                GLib.idle_add(self._remove_child_by_name, file_name)

        # handles creation and change
        elif event_type == Gio.FileMonitorEvent.CHANGES_DONE_HINT:
            self._process_thumbnail_task(file_name)

    def _remove_child_by_name(self, file_name):
        for child in self.viewport.get_children():
            if child.file_name == file_name:
                self.viewport.remove(child)
                break

    def _create_flowbox_child(self, pixbuf, file_name):
        image = Gtk.Image.new_from_pixbuf(pixbuf)
        image.set_name("wallpaper-thumbnail")

        box = ClippingBox(
            name="wallpaper-thumbnail-clipper",
            orientation=Gtk.Orientation.VERTICAL,
            spacing=4,
        )
        box.pack_start(image, False, False, 0)

        child = Gtk.FlowBoxChild()
        child.set_name("wallpaper-thumbnail-container")
        child.add(box)
        child.file_name = file_name  # store metadata
        child.set_can_focus(True)

        return child

    def arrange_viewport(self, query: str):
        query = query.lower()
        first_visible = None
        self._visible_children = []

        # hiding > destroying/recreating widgets
        for child in self.viewport.get_children():
            visible = query in child.file_name.lower()
            child.set_visible(visible)

            if visible:
                self._visible_children.append(child)
                if first_visible is None:
                    first_visible = child

        # select first item
        if first_visible:
            self.viewport.select_child(first_visible)
            # first_visible.grab_focus()

    def on_wallpaper_selected(self, flowbox, child):
        file_name = child.file_name
        full_path = os.path.join(config.WALLPAPERS_DIR, file_name)

        selected_scheme = self.scheme_dropdown.get_active_id()
        feh_bin = shutil.which("feh")

        if not feh_bin:
            logger.error("'feh' binary not found.")
            exec_shell_command_async(
                "notify-send 'Zenith Error' '\"feh\" not found. Wallpaper not applied.'"
            )
            return

        # apply wallpaper
        exec_shell_command_async(f"{feh_bin} --zoom fill --bg-fill '{full_path}'")

        def save_history():
            WP_HISTORY.parent.mkdir(parents=True, exist_ok=True)
            WP_HISTORY.write_text(full_path)

        # generate
        self.executor.submit(save_history)
        future = self.executor.submit(generate_wallpaper_preview, full_path)
        self.executor.submit(self._generate_theme, full_path, selected_scheme)
        self.executor.submit(generate_lockscreen_image, full_path)

        # callback
        def _on_preview_ready(fut):
            preview_path = fut.result()
            if not preview_path:
                return

            self.wallpaper_service.set_wallpaper_path(
                full_path,
                str(preview_path),
            )

        future.add_done_callback(_on_preview_ready)

    def on_scheme_changed(self, combo):
        selected_scheme = combo.get_active_id()
        print(f"Color scheme selected: {selected_scheme}")

    def on_search_entry_key_press(self, widget, event):
        # scheme dropdown navigation with Shift
        if event.state & Gdk.ModifierType.SHIFT_MASK:
            if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
                schemes_list = list(self.schemes.keys())
                current_id = self.scheme_dropdown.get_active_id()
                current_index = (
                    schemes_list.index(current_id) if current_id in schemes_list else 0
                )
                new_index = (
                    (current_index - 1) % len(schemes_list)
                    if event.keyval == Gdk.KEY_Up
                    else (current_index + 1) % len(schemes_list)
                )
                self.scheme_dropdown.set_active(new_index)
                return True
            elif event.keyval == Gdk.KEY_Right:
                self.scheme_dropdown.popup()
                return True

        # Arrow key navigation in FlowBox
        if event.keyval in (Gdk.KEY_Up, Gdk.KEY_Down, Gdk.KEY_Left, Gdk.KEY_Right):
            self.move_selection_2d(event.keyval)
            return True
        # Enter key to activate selection
        elif event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            selected = self.viewport.get_selected_children()
            if selected:
                self.on_wallpaper_selected(self.viewport, selected[0])
            return True
        return False

    def move_selection_2d(self, keyval):
        if not self._visible_children:
            return

        selected = self.viewport.get_selected_children()
        if not selected or selected[0] not in self._visible_children:
            # no selection, select first or last
            new_child = (
                self._visible_children[0]
                if keyval in (Gdk.KEY_Down, Gdk.KEY_Right)
                else self._visible_children[-1]
            )
            self.viewport.select_child(new_child)
            # new_child.grab_focus()
            return

        current_child = selected[0]
        current_visible_index = self._visible_children.index(current_child)

        if keyval == Gdk.KEY_Right:
            new_index = current_visible_index + 1
        elif keyval == Gdk.KEY_Left:
            new_index = current_visible_index - 1
        elif keyval == Gdk.KEY_Down:
            new_index = current_visible_index + self.COLUMNS
        elif keyval == Gdk.KEY_Up:
            new_index = current_visible_index - self.COLUMNS
        else:
            return

        # clamp to valid range
        new_index = max(0, min(new_index, len(self._visible_children) - 1))

        if new_index != current_visible_index:
            new_child = self._visible_children[new_index]
            self.viewport.select_child(new_child)
            # scrolls to view
            new_child.grab_focus()

    @staticmethod
    def _is_image(file_name: str) -> bool:
        return file_name.lower().endswith(
            (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
        )

    def on_search_entry_focus_out(self, widget, event):
        if self.get_mapped():
            widget.grab_focus()
        return False

    def _generate_theme(self, image_path, scheme):
        matugen_bin = shutil.which("matugen")
        if not matugen_bin:
            logger.error("'matugen' not found.")
            exec_shell_command_async(
                "notify-send 'Zenith Shell' '\"matugen\" not found. Theme not updated.'"
            )
            return

        config_path = f"{CONFIG_DIR}/matugen/config.toml"
        command = f"{matugen_bin} image '{image_path}' -t {scheme} -c '{config_path}'"

        try:
            process, _ = exec_shell_command_async(command)
            process.wait_check_async(
                None,
                lambda p, r: logger.info("Theme updated")
                if p.wait_check_finish(r)
                else logger.error("Theme failed"),
            )
        except Exception as e:
            logger.exception(f"Matugen error: {e}")
