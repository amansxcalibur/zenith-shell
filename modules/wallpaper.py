import os
import shutil
import subprocess
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from PIL import Image
from loguru import logger
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

        self.thumbnails_map = {}
        self._visible_children = []
        self._scan_generation = 0
        self.file_monitor = None
        bindings = config.get("bindings.modules.wallpaper")
        self._cached_binds = {
            name: Gtk.accelerator_parse(bindings[f"wallpaper.{name}"])
            for name in (
                "scheme_prev",
                "scheme_next",
                "scheme_open",
                "move_up",
                "move_down",
                "move_left",
                "move_right",
                "activate",
            )
        }
        self.executor = ThreadPoolExecutor(max_workers=5)

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
            placeholder="Search Wallpapers",
            h_expand=True,
            style_classes="" if not config.VERTICAL else "vertical",
            notify_text=lambda entry, *_: self.arrange_viewport(entry.get_text()),
            on_key_press_event=self.on_search_entry_key_press,
        )
        # override gtk entry 150px internal min width
        self.search_entry.set_width_chars(1)
        self.search_entry.set_size_request(20, -1)
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

        self.wall_dir_path_label = Label(
            style="color: var(--foreground); font-size: 14px",
            ellipsization="middle",
            max_chars_width=35,
            h_align="start",
        )
        self.launch_options_list = Box(
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
        )
        self.launcher_options_revealer = Revealer(
            child=self.launch_options_list,
            transition_type="slide-left",
            transition_duration=150,
        )
        self.launch_mode = Box(
            name="launch-mode-box",
            children=[
                Button(
                    style_classes="launch-mode-btn",
                    child=MaterialIconLabel(
                        icon_text=icons.folder_open.symbol(),
                        FILL=1,
                        style="font-size: 20px; color: var(--primary)",
                    ),
                    on_clicked=lambda *_: self.prompt_for_path(),
                    tooltip_text="Open directory",
                ),
                self.launcher_options_revealer,
            ],
        )

        self.launch_mode_event_box = EventBox(
            name="launch-mode-event-container", child=self.launch_mode, events="all"
        )
        self.launch_mode_event_box.connect("enter-notify-event", self._on_hover_enter)
        self.launch_mode_event_box.connect("leave-notify-event", self._on_hover_leave)
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
                        self.launch_mode_event_box,
                        Box(name="search-container-item-seperator"),
                        self.search_entry,
                    ],
                ),
                self.scheme_dropdown,
                Button(
                    name="close-button",
                    child=MaterialIconLabel(
                        name="close-label", icon_text=icons.close.symbol()
                    ),
                    tooltip_text="Exit",
                    on_clicked=lambda *_: self._pill.stack.set_visible_child(
                        self._pill.launcher
                    ),
                ),
            ],
        )

        self.dir_chooser_btn = Button(
            style="margin: 18px; padding: 52px;",
            child=MaterialIconLabel(
                icon_text=icons.add_material.symbol(),
                FILL=0,
                style="font-size: 120px; color: var(--surface)",
            ),
            on_clicked=lambda *_: self.prompt_for_path(),
        )
        self.interactive_shape = InteractiveMorphShape(
            clip=True, shape_start=pill, shape_end=sunny, child=self.dir_chooser_btn
        )
        self.dir_chooser = Box(
            # name="wallpaper-choose-dir-dialog",
            h_expand=True,
            h_align="center",
            v_align="center",
            v_expand=True,
            orientation="v",
            style="color: var(--primary);",
            children=[
                self.interactive_shape,
                MaterialFontLabel(
                    text="Choose Wallpaper Directory",
                    font_family="Google Sans Flex",
                    style="color: var(--foreground); font-size: 20px",
                ),
            ],
        )
        self.dir_chooser_btn.connect(
            "enter-notify-event", self.interactive_shape.play_forward
        )
        self.dir_chooser_btn.connect(
            "leave-notify-event", self.interactive_shape.play_backward
        )

        self.stack = Stack(
            v_expand=True,
            children=[self.dir_chooser, self.scrolled_window],
            interpolate_size=True,
        )
        self.stack.set_homogeneous(False)
        if os.path.isdir(config.WALLPAPERS_DIR):
            self.stack.set_visible_child(self.scrolled_window)
            self._set_wall_dir_label(str(config.WALLPAPERS_DIR))
            self.executor.submit(self._perform_scan_and_clean)
        else:
            self.stack.set_visible_child(self.dir_chooser)
            self._set_wall_dir_label(None)
            self.set_header_controls_state(False)

        box_shadow_overlay = Box(name="wallpaper-overlay")
        self.overlay = Overlay(
            v_expand=True,
            child=Box(
                name="wallpaper-selector",
                spacing=10,
                orientation="v",
                children=[self.stack, self.header_box],
            ),
            overlays=box_shadow_overlay,
        )
        self.overlay.set_overlay_pass_through(box_shadow_overlay, True)

        self.temp_label = Label(label="Choosing Wallpaper", style="padding: 20px 30px;")
        self.view_stack = Stack(
            transition_type="crossfade",
            transition_duration=150,
            children=[self.overlay, self.temp_label],
            interpolate_size=True,
        )
        self.view_stack.set_homogeneous(False)

        self.add(self.view_stack)

        self.setup_file_monitor()
        self.show_all()

        def grab_initial_focus(widget):
            widget.set_text("")
            if widget.get_sensitive():
                widget.grab_focus()
            return False

        self.search_entry.connect("map", grab_initial_focus)

    def _on_hover_enter(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.launcher_options_revealer.set_reveal_child(True)
        return False

    def _on_hover_leave(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.launcher_options_revealer.set_reveal_child(False)
        # self._refocus_search_entry()
        return False

    def set_header_controls_state(self, active: bool):
        self.search_entry.set_sensitive(active)
        self.scheme_dropdown.set_sensitive(active)
        opacity = 1.0 if active else 0.5
        if not active:
            self._set_wall_dir_label(None)
        self.search_entry.set_opacity(opacity)
        self.scheme_dropdown.set_opacity(opacity)

    def _set_wall_dir_label(self, path: str | None):
        if path is None:
            self.wall_dir_path_label.set_label("None")
            self.wall_dir_path_label.set_tooltip_text(None)
            return

        self.wall_dir_path_label.set_label(str(path))
        if len(self.wall_dir_path_label.get_text()) > 35:
            self.wall_dir_path_label.set_tooltip_text(str(path))
        else:
            self.wall_dir_path_label.set_tooltip_text(None)

    def prompt_for_path(self):
        win = self.get_toplevel()
        
        if isinstance(win, Gtk.Window):
            self.view_stack.set_visible_child(self.temp_label)
            dialog = Gtk.FileChooserNative.new(
                "Select a Directory",
                win,
                Gtk.FileChooserAction.SELECT_FOLDER,
                "Choose",
                "Cancel",
            )

            # blocking
            response = dialog.run()

            if response == Gtk.ResponseType.ACCEPT:
                selected_path = str(dialog.get_filename())
                config.WALLPAPERS_DIR = selected_path
                self.set_header_controls_state(True)
                self._set_wall_dir_label(str(config.WALLPAPERS_DIR))
                self.setup_file_monitor()
                self.stack.set_visible_child(self.scrolled_window)
                self.executor.submit(self._perform_scan_and_clean)
                logger.info(f"New wallpaper directory selected: {selected_path}")
            elif response == Gtk.ResponseType.CANCEL:
                logger.info("Wallpaper directory selection canceled.")

            dialog.destroy()
            self.view_stack.set_visible_child(self.overlay)
        else:
            logger.error("WallpaperSelector not attached to a Gtk.Window.")

    def _clear_wallpapers(self):
        def _clear():
            for child in self.viewport.get_children():
                self.viewport.remove(child)
            self.thumbnails_map.clear()
            self._visible_children = []
            self.viewport.unselect_all()
            return False

        GLib.idle_add(_clear)

    def _perform_scan_and_clean(self):
        ensure_wallpaper_dirs()

        self._scan_generation += 1
        generation = self._scan_generation
        self._clear_wallpapers()

        try:
            all_files = sorted(
                f for f in os.listdir(config.WALLPAPERS_DIR) if self._is_image(f)
            )
        except OSError as e:
            logger.error(f"Failed to list wallpapers dir: {e}")
            return

        for file_name in all_files:
            if generation != self._scan_generation:
                return
            self.executor.submit(self._process_thumbnail_task, file_name, generation)

    def _process_thumbnail_task(self, file_name: str, generation: int | None = None):
        generation = self._scan_generation if generation is None else generation
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

            GLib.idle_add(self._add_thumbnail_to_ui, file_name, image_bytes, generation)

        except Exception as e:
            logger.error(f"Thumbnail task failed for {file_name}: {e}")

    def _add_thumbnail_to_ui(self, file_name, image_bytes, generation):
        if generation != self._scan_generation:
            return

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

                self.update_badge_visibility()

            GLib.idle_add(self.arrange_viewport, self.search_entry.get_text())

        except Exception as e:
            logger.error(f"Error creating pixbuf for {file_name}: {e}")

    def setup_file_monitor(self):
        if not os.path.isdir(config.WALLPAPERS_DIR):
            return

        if self.file_monitor is not None and not self.file_monitor.is_cancelled():
            self.file_monitor.cancel()

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

        badge = Box(
            name="badge-container",
            visible=False,
            all_visible=False,
            orientation="v",
            children=[
                Box(name="bade-hole", h_expand=True, v_expand=True),
                Box(
                    name="bade-label-container",
                    h_expand=True,
                    children=MaterialFontLabel(
                        name="bade-label",
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
        badge.hide()

        box = ClippingBox(
            name="wallpaper-thumbnail-clipper",
            orientation=Gtk.Orientation.VERTICAL,
            children=Overlay(child=image, overlays=badge),
            spacing=4,
        )

        child = Gtk.FlowBoxChild()
        child.set_name("wallpaper-thumbnail-container")
        child.add(box)
        child.file_name = file_name
        child.set_can_focus(True)
        child.badge = badge

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
        else:
            self.viewport.unselect_all()

    def on_wallpaper_selected(self, flowbox, child):
        file_name = child.file_name
        full_path = os.path.join(config.WALLPAPERS_DIR, file_name)

        selected_scheme = self.scheme_dropdown.get_active_id()

        self.wallpaper_service.apply_wallpaper(full_path)

        # generate
        self.executor.submit(save_wallpaper_history, full_path)
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

        self.update_badge_visibility(target_file_name=file_name)

    def update_badge_visibility(self, target_file_name: str | None = None):
        if target_file_name is None:
            current_path = self.wallpaper_service.get_wallpaper_path()
            target_file_name = os.path.basename(current_path) if current_path else ""

        def _ui_sync():
            for child in self.viewport.get_children():
                if hasattr(child, "badge"):
                    if child.file_name == target_file_name:
                        child.badge.show()
                    else:
                        child.badge.hide()
            return False

        GLib.idle_add(_ui_sync)

    def on_scheme_changed(self, combo):
        selected_scheme = combo.get_active_id()
        logger.info(f"Color scheme selected: {selected_scheme}")

    def _cycle_scheme(self, delta: int) -> None:
        schemes_list = list(self.schemes.keys())
        current_id = self.scheme_dropdown.get_active_id()
        current_index = (
            schemes_list.index(current_id) if current_id in schemes_list else 0
        )
        new_index = (current_index + delta) % len(schemes_list)
        self.scheme_dropdown.set_active(new_index)

    def on_search_entry_key_press(self, widget, event):
        # ignores CapsLock, NumLock, etc.
        core_modifiers = event.state & (
            Gdk.ModifierType.SHIFT_MASK
            | Gdk.ModifierType.CONTROL_MASK
            | Gdk.ModifierType.MOD1_MASK
        )
        key_s_prev, mask_s_prev = self._cached_binds["scheme_prev"]
        key_s_next, mask_s_next = self._cached_binds["scheme_next"]
        key_s_open, mask_s_open = self._cached_binds["scheme_open"]
        key_up, mask_up = self._cached_binds["move_up"]
        key_down, mask_down = self._cached_binds["move_down"]
        key_left, mask_left = self._cached_binds["move_left"]
        key_right, mask_right = self._cached_binds["move_right"]
        key_activate, mask_activate = self._cached_binds["activate"]

        # scheme dropdown navigation with Shift
        if event.keyval == key_s_prev and core_modifiers == mask_s_prev:
            self._cycle_scheme(-1)
            return True

        elif event.keyval == key_s_next and core_modifiers == mask_s_next:
            self._cycle_scheme(1)
            return True

        elif event.keyval == key_s_open and core_modifiers == mask_s_open:
            self.scheme_dropdown.popup()
            return True

        # Arrow key navigation in FlowBox
        if (
            (event.keyval == key_up and core_modifiers == mask_up)
            or (event.keyval == key_down and core_modifiers == mask_down)
            or (event.keyval == key_left and core_modifiers == mask_left)
            or (event.keyval == key_right and core_modifiers == mask_right)
        ):
            self.move_selection_2d(event.keyval)
            return True

        # Enter key to activate selection
        elif event.keyval == key_activate and core_modifiers == mask_activate:
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

        # clamp to valid range
        new_index = max(0, min(new_index, len(self._visible_children) - 1))

        if new_index != current_visible_index:
            new_child = self._visible_children[new_index]
            self.viewport.select_child(new_child)
            # scrolls to view
            new_child.grab_focus()

    @staticmethod
    def _is_image(file_name: str) -> bool:
        return file_name.lower().endswith(IMAGE_EXTENSIONS)

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
        command = f"{matugen_bin} image '{image_path}' -t {scheme} -c '{config_path}' --source-color-index 0"

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

    def destroy(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
        if self.file_monitor:
            self.file_monitor.cancel()
        super().destroy()
