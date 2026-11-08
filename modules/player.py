from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.overlay import Overlay
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox

import svg
import icons

from config.info import ROOT_DIR
from config.config import config

from modules.wiggle_bar import WigglyScale
from modules.audio_panel import DEVICE_ICONS
from modules.wallpaper import WallpaperService

from services.volume_service import VolumeService
from services.theme import ThemeMode, ThemeService
from services.player_service import PlayerManager, PlayerService, get_track_labels

from utils.colors import get_css_variable, hex_to_rgb01
from utils.helpers import format_accel_to_keybind

from widgets.overrides import Svg
from widgets.animated_scale import AnimatedScale
from widgets.material_label import MaterialIconLabel
from widgets.popup_window import PopSlot, FlyingOverlay

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib  # type: ignore


def format_track_time(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02}:{secs:02}"
    return f"{minutes}:{secs:02}"


def default_scrim(mode: ThemeMode) -> str:
    return "#ffffff" if mode == ThemeMode.LIGHT else "#000000"


def card_background(image_path: str | None, scrim_hex: str) -> str:
    # more solid on the text side, so the artwork still shows behind the controls
    red, green, blue = (round(c * 255) for c in hex_to_rgb01(scrim_hex))
    scrim = (
        f"linear-gradient(to right, rgba({red}, {green}, {blue}, 0.88),"
        f" rgba({red}, {green}, {blue}, 0.5))"
    )
    image = f", url('{image_path}')" if image_path else ""
    return f"background-image: {scrim}{image};"


class PlayerAudioScaleMaterial3(AnimatedScale):
    def __init__(self, service_instance, orientation="h", **kwargs):
        super().__init__(
            name="control-slider-mui",
            orientation=orientation,
            h_expand=True,
            has_origin=True,
            inverted=orientation != "h",
            style_classes="" if orientation == "h" else "vertical",
            increments=(0.01, 0.01),
            max_value=1.0,
            min_value=0.0,
            value=service_instance._player.props.volume,
            **kwargs,
        )
        self.service_instance = service_instance
        self.current = self.service_instance._player.props.volume
        self.max = 1.0
        self.percentage = self.current / self.max
        self.update_from_user = False
        self.ui_updating = False
        self.service_instance._player.connect("volume", self.update_slider)
        self.connect("change-value", self.set_audio)

    def update_slider(self, source, new_value):
        if self.ui_updating:
            return

        self.ui_updating = True
        volume = new_value / self.max_value
        if self.update_from_user:
            self.set_value(volume)
        else:
            self.animate_value(volume)
        self.update_from_user = False
        self.ui_updating = False

    def set_audio(self, source, scroll_type, value):
        self.update_from_user = True
        self.service_instance.set_volume(value)  # 0.0 to 1.0


class PlayerSource(Button):
    def __init__(self, service: PlayerService, volume_service: VolumeService, **kwargs):
        super().__init__(name="source", on_clicked=self.handle_click, **kwargs)
        self._service = service
        self._volume_service = volume_service
        self._player = service._player  # Playerctl.Player

        self.toggle = False
        self.quick_settings_slot = None  # stamped in by PopSlot

        MAX_AUDIO_DEVICE_NAME_CHARS = 14

        self.player_icon = Svg(
            name=self._player.props.player_name,
            size=24,
            style_classes="player-icon",
            svg_string=getattr(svg, self._player.props.player_name, svg.disc),
        )
        self.audio_device_icon = MaterialIconLabel(
            icon_text=icons.headphones.symbol(),
            wght=600,
        )
        self.audio_device_label = Label(
            style="font-size: 13px;",
            max_chars_width=MAX_AUDIO_DEVICE_NAME_CHARS,
            ellipsization="end",
        )
        self.audio_source = Box(
            name="source-name",
            spacing=5,
            children=[self.audio_device_icon, self.audio_device_label],
        )

        self.full_device_label = Label(
            h_align="start",
            style_classes="full-device-name",
        )
        self.on_audio_device_changed()
        self.volume_scale = PlayerAudioScaleMaterial3(service_instance=service)
        self.image_container = Box(
            style="background-position: center; background-size: cover; border-radius: 20px",
            v_align="start",
            size=90,
        )
        self.menu_spacer = Box(
            h_expand=True,
            style="min-height: 2px; border-radius: 10px; background-color: grey;",
        )
        # A wrapping label's natural width is its whole text on one line, which the
        # overlay would grow to fit. Capping it leaves the column's width in charge.
        self.song = Label(
            name="song",
            label="song",
            justification="left",
            line_wrap="word-char",
            max_chars_width=20,
            h_align="fill",
        )
        self.song.set_xalign(0)

        self.artist = Label(
            name="artist",
            label="artist",
            justification="left",
            line_wrap="word-char",
            max_chars_width=20,
            h_align="fill",
        )
        self.artist.set_xalign(0)

        self.music = Box(
            name="music",
            orientation="v",
            h_expand=True,
            v_expand=True,
            v_align="end",
            children=[self.song, self.artist],
        )
        self.player_menu = Box(
            name="audio-source-menu",
            orientation="v",
            spacing=20,
            children=[
                Box(
                    spacing=20,
                    children=[
                        self.image_container,
                        Box(
                            orientation="v",
                            v_expand=True,
                            size=(196, -1),
                            children=[
                                Box(
                                    name="source-icon-container",
                                    h_align="start",
                                    spacing=6,
                                    children=[
                                        self.player_icon,
                                        Label(label=self._player.props.player_name),
                                    ],
                                ),
                                self.music,
                            ],
                        ),
                    ],
                ),
                self.menu_spacer,
                self.full_device_label,
                self.volume_scale,
            ],
        )

        self.audio_source_stack = Stack(
            transition_duration=200,
            transition_type="crossfade",
            children=[self.audio_source, self.player_menu],
            interpolate_size=True,
        )
        self.audio_source_stack.set_homogeneous(False)
        self.add(self.audio_source_stack)

        self._device_signal_id = self._volume_service.connect(
            "speaker-device-changed", self.on_audio_device_changed
        )

    def disconnect_services(self):
        self._volume_service.disconnect(self._device_signal_id)

    def get_audio_source_widget(self) -> Box:
        return self.audio_source

    def get_audio_source_menu(self) -> Box:
        return self.player_menu

    def handle_click(self, *_):
        if self.toggle:
            self.toggle = False
            self.audio_source_stack.set_visible_child(self.audio_source)
            self.quick_settings_slot.dismiss()
            return
        self.toggle = True
        self.audio_source_stack.set_visible_child(self.player_menu)
        self.quick_settings_slot.pop_out()

    def on_audio_device_changed(self, *_args):
        # what the controls popup calls it: the jack in use, e.g. "Headphones"
        device = self._volume_service.get_current_device()
        if device is None:  # not read yet
            return
        self.audio_device_icon.set_icon(DEVICE_ICONS[device.icon].symbol())
        self.audio_device_label.set_label(device.label)
        self.audio_device_label.set_tooltip_text(device.full_name)
        self.full_device_label.set_label(device.full_name)

    def on_restored(self):
        self.toggle = False
        self.audio_source_stack.set_visible_child(self.audio_source)

    def update_theme(self, theme_json, mode: ThemeMode):
        if theme_json:
            primary_color = theme_json["colors"]["primary"][mode.value]["color"]
            surface_container_high_color = theme_json["colors"][
                "surface_container_high"
            ][mode.value]["color"]
            surface_bright_color = (
                theme_json["colors"]["surface_bright"]["dark"]["color"]
                if mode == ThemeMode.DARK
                else theme_json["colors"]["outline_variant"]["light"]["color"]
            )
            surface_color = theme_json["colors"]["surface"][mode.value]["color"]
            foreground_color = theme_json["colors"]["on_background"][mode.value][
                "color"
            ]
            chip_color = theme_json["colors"]["secondary_container"][mode.value][
                "color"
            ]
            on_chip_color = theme_json["colors"]["on_secondary_container"][mode.value][
                "color"
            ]
        else:
            colors_path = f"{ROOT_DIR}/styles/colors.css"
            primary_color = get_css_variable(colors_path, "--primary")
            chip_color = primary_color
            on_chip_color = get_css_variable(colors_path, "--on-primary")
            surface_container_high_color = get_css_variable(
                colors_path, "--surface-semi-bright"
            )
            surface_bright_color = get_css_variable(colors_path, "--surface-bright")
            surface_color = get_css_variable(colors_path, "--surface")
            foreground_color = get_css_variable(colors_path, "--foreground")

        self.audio_source.set_style(
            f"background-color: {chip_color}; color: {on_chip_color}"
        )
        self.player_menu.set_style(
            f"background-color: {surface_container_high_color}; color: {foreground_color}"
        )
        self.artist.set_style(f"color: {foreground_color}")
        self.song.set_style(f"color: {foreground_color}")
        self.menu_spacer.set_style(
            f"min-height: 2px; border-radius: 10px; background-color:{surface_bright_color};"
        )
        self.player_icon.set_style(f"color: {primary_color}")
        self.volume_scale.set_style(
            f"""
                #control-slider-mui trough {{
                    background-color: {surface_color};
                }}
                #control-slider-mui slider {{
                    background-color: {primary_color};
                    box-shadow: 0 0 0 4px {surface_container_high_color};
                }}
                #control-slider-mui:hover slider {{
                    box-shadow: 1px 0 0 4px {surface_container_high_color};
                }}
                #control-slider-mui highlight {{
                    border-radius: 8px 4px 4px 8px;
                    background-color: {primary_color};
                    box-shadow: 4px 0 0 4px {surface_container_high_color};
                }}
            """,
            compile=False,  # no macros/vars here, skip the regex passes
        )

    def update_track_info(self, song, artist):
        self.song.set_label(song)
        self.artist.set_label(artist)

    def update_artwork(self, art_path):
        self.image_container.set_style(
            f"background-position: center; background-size: cover; border-radius: 20px; background-image:url('{art_path}')"
        )


class Player(Box):
    def __init__(self, player_service: PlayerService, **kwargs):
        super().__init__(style_classes="player", orientation="v", spacing=12, **kwargs)

        # vertical class binding from unknown source
        if not config.VERTICAL:
            self.remove_style_class("vertical")

        self._theme_service = ThemeService()
        self._volume_service = VolumeService()
        self._wallpaper_service = WallpaperService()

        self._flying_overlay = FlyingOverlay.get_shared()

        MAX_SONG_CHARS = 23
        MAX_ARTIST_CHARS = 27
        self.duration = 0.0
        self._palette = None  # the current artwork's colors in the current mode
        self._background_image = None
        self._shuffle_on = False
        self._player_service = player_service
        player = self._player_service._player
        self._service_handlers = []  # (service, handler id), released on destroy

        def _set_initial_bg(
            service: WallpaperService, full_path: str, preview_path: str
        ):
            self._set_background_image(preview_path)
            return False

        self._wallpaper_signal_id = self._wallpaper_service.connect(
            "wallpaper-changed", _set_initial_bg
        )

        GLib.idle_add(
            _set_initial_bg,
            self._wallpaper_service,
            self._wallpaper_service.get_wallpaper_path(),
            self._wallpaper_service.get_preview_path(),
        )

        self.player_icon = Svg(
            name=player.props.player_name,
            size=24,
            h_expand=True,
            v_expand=True,
            h_align="center",
            v_align="center",
            style_classes="player-icon",
            svg_string=getattr(svg, player.props.player_name, svg.disc),
        )
        self.audio_source = PlayerSource(
            service=player_service, volume_service=self._volume_service
        )

        self.song = Label(
            name="song",
            label="song",
            justification="left",
            h_align="start",
            ellipsization="end",
            max_chars_width=MAX_SONG_CHARS,
        )

        self.artist = Label(
            name="artist",
            label="artist",
            justification="left",
            h_align="start",
            ellipsization="end",
            max_chars_width=MAX_ARTIST_CHARS,
        )

        self.music = Box(
            name="music",
            orientation="v",
            h_expand=True,
            v_align="center",
            children=[self.song, self.artist],
        )

        # controls
        self.play_pause_button = Button(
            name="pause-button",
            child=MaterialIconLabel(
                name="pause-label", icon_text=icons.play_material.symbol()
            ),
            style_classes="pause-track",
            v_align="center",
            tooltip_text="Play/Pause",
            on_clicked=lambda b, *_: self.handle_play_pause(),
        )

        shuffle_dot = Box(name="shuffle-dot", h_align="center", v_align="end")
        shuffle_content = Overlay(
            child=Svg(
                name="shuffle",
                style_classes=["material-icon"],
                size=20,
                h_expand=True,
                v_expand=True,
                h_align="center",
                v_align="center",
                svg_string=svg.shuffle,
            ),
            overlays=shuffle_dot,
        )
        shuffle_content.set_overlay_pass_through(shuffle_dot, True)

        self.shuffle_button = Button(
            name="shuffle-button",
            child=shuffle_content,
            on_clicked=lambda b, *_: self.handle_shuffle(b),
        )

        self.prev_button = Button(
            name="prev-button",
            child=MaterialIconLabel(
                name="play-previous",
                style_classes=["material-icon"],
                icon_text=icons.skip_prev.symbol(),
            ),
            on_clicked=lambda b, *_: self.handle_prev(),
        )
        self.next_button = Button(
            name="next-button",
            child=MaterialIconLabel(
                name="play-next",
                style_classes=["material-icon"],
                icon_text=icons.skip_next.symbol(),
            ),
            on_clicked=lambda b, *_: self.handle_next(),
        )

        self.position_label = Label(label="0:00", style_classes="player-time")
        self.length_label = Label(label="0:00", style_classes="player-time")
        # hug the seek bar, the slots hang past the card's padding
        self.position_label.set_xalign(1)
        self.length_label.set_xalign(0)
        self.prev_slot = self._create_time_slot(self.prev_button, self.position_label)
        self.next_slot = self._create_time_slot(self.next_button, self.length_label)

        self.wiggly = WigglyScale()
        self.wiggly.connect("on-seek", self.on_seek)
        self.wiggly.connect("on-scrub", self.on_scrub)
        self.wiggly.connect("notify::dragging", self.on_dragging_changed)

        self.wiggly_bar = Box(
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            children=self.wiggly,
        )

        self.children = [
            Box(
                name="source",
                children=[
                    Box(
                        name="source-icon-container",
                        v_align="center",
                        children=self.player_icon,
                    ),
                    Box(h_expand=True),
                    PopSlot(
                        self.audio_source,
                        overlay=self._flying_overlay,
                        target_size=(346, 360),
                    ),
                ],
            ),
            Box(
                name="details",
                spacing=12,
                children=[self.music, self.play_pause_button],
            ),
            Box(
                name="controls",
                style_classes="horizontal" if not config.VERTICAL else "vertical",
                spacing=8,
                children=(
                    [
                        self.prev_slot,
                        CenterBox(
                            name="progress-container",
                            h_expand=True,
                            v_expand=True,
                            orientation="v",
                            center_children=[self.wiggly_bar],
                        ),
                        self.next_slot,
                        self.shuffle_button,
                    ]
                    if not config.VERTICAL
                    else [
                        CenterBox(
                            orientation="v",
                            h_expand=True,
                            start_children=[
                                CenterBox(
                                    h_expand=True,
                                    v_expand=True,
                                    v_align="end",
                                    start_children=Box(
                                        spacing=8,
                                        children=[
                                            self.prev_slot,
                                            self.next_slot,
                                            self.shuffle_button,
                                        ],
                                    ),
                                )
                            ],
                            end_children=CenterBox(
                                name="progress-container",
                                h_expand=True,
                                v_expand=True,
                                orientation="v",
                                center_children=[self.wiggly_bar],
                            ),
                        )
                    ]
                ),
            ),
        ]

        # connect to service signals
        for service, signal, callback in (
            (self._player_service, "pause", self.on_pause),
            (self._player_service, "play", self.on_play),
            (self._player_service, "meta-change", self.on_metadata),
            (self._player_service, "shuffle-toggle", self.on_shuffle),
            (self._player_service, "track-position", self.on_update_track_position),
            (self._player_service, "theme-change", self._apply_theme),
            (self._player_service, "artwork-change", self._apply_artwork),
            (self._player_service, "notify::can-shuffle", self._update_shuffle_button),
            (self._theme_service, "theme-changed", self._switch_theme_mode),
        ):
            self._service_handlers.append((service, service.connect(signal, callback)))

        self.connect("destroy", self.on_destroy)

        # init metadata
        self.on_metadata(
            self._player_service, metadata=player.props.metadata, player=player
        )

        # init artwork & theme
        current_artwork = self._player_service.get_artwork()
        if current_artwork:
            self._apply_artwork(self._player_service, current_artwork)
        current_theme = self._player_service.get_theme()
        if current_theme:
            self._apply_theme(
                self._player_service, current_theme, self._theme_service.theme
            )
        else:
            self._apply_fallback_theme(self._theme_service.theme)

    def _create_time_slot(self, button: Button, time_label: Label) -> Stack:
        slot = Stack(
            transition_type="crossfade",
            transition_duration=200,
            children=[button, time_label],
        )
        # same size either way, so the scale doesn't move under the pointer
        slot.set_homogeneous(True)
        slot.set_no_show_all(True)
        return slot

    def _sync_time_slots(self):
        dragging = self.wiggly.dragging
        for slot, button, time_label, available in (
            (
                self.prev_slot,
                self.prev_button,
                self.position_label,
                self._player_service.can_go_previous,
            ),
            (
                self.next_slot,
                self.next_button,
                self.length_label,
                self._player_service.can_go_next,
            ),
        ):
            button.set_visible(available)
            button.set_sensitive(available)
            # a player that can't skip still gets its times while dragging
            slot.set_visible(available or dragging)
            if dragging:
                slot.set_visible_child(time_label)
            elif available:
                slot.set_visible_child(button)

    def _set_duration(self, duration: float):
        if duration == self.duration:
            return
        self.duration = duration
        text = format_track_time(duration)
        self.length_label.set_label(text)
        # the position can't get wider than the length, reserve that up front
        self.position_label.set_width_chars(len(text))
        self.length_label.set_width_chars(len(text))

    def _sync_track_times(self):
        self._set_duration(self._player_service.get_duration())
        self._player_service.fabricating()

    def on_update_track_position(self, sender, pos, dur):
        self._set_duration(dur)
        # past the end means it's still the previous track's position
        if 0 < dur and pos <= dur:
            self.wiggly.update_value_from_signal(pos / dur)

    def on_seek(self, sender, ratio):
        pos = ratio * self.duration  # duration in seconds
        logger.debug(f"Seeking to {pos:.2f}s")
        self._player_service.set_position(pos)

    def on_scrub(self, sender, ratio):
        self.position_label.set_label(format_track_time(ratio * self.duration))

    def on_dragging_changed(self, *_):
        if self.wiggly.dragging:
            self.on_scrub(self.wiggly, self.wiggly.value)
        self._sync_time_slots()

    def skip_forward(self, seconds=10):
        if self._player_service.can_seek:
            self._player_service._player.seek(seconds * 1000000)

    def skip_backward(self, seconds=10):
        if self._player_service.can_seek:
            self._player_service._player.seek(-1 * seconds * 1000000)

    def _update_track_info(self, metadata, keys):
        # empty between tracks, keep what's showing
        if not keys:
            return

        song_title, artist_name = get_track_labels(metadata)

        def _update_metadata_label():
            self.song.set_label(song_title)
            self.artist.set_label(artist_name)
            self.audio_source.update_track_info(song_title, artist_name)
            return False

        GLib.idle_add(_update_metadata_label)

    def _apply_artwork(self, source, art_path, _blurred_art_path=None):
        # remove wallpaper connection
        if self._wallpaper_signal_id:
            self._wallpaper_service.disconnect(self._wallpaper_signal_id)
            self._wallpaper_signal_id = None

        def apply(art_path):
            self._set_background_image(art_path)
            self.audio_source.update_artwork(art_path)

        GLib.idle_add(lambda art_path: apply(art_path), art_path)

    def _apply_theme(self, source, theme_json, mode: ThemeMode | None = None):
        if mode is None:
            mode = self._theme_service.theme

        def color(role):
            return theme_json["colors"][role][mode.value]["color"]

        def _apply():
            self._palette = palette = {
                "primary": color("primary"),
                "on_primary": color("on_primary"),
                "on_surface": color("on_surface"),
                "on_surface_variant": color("on_surface_variant"),
                "scrim": color("surface_container_lowest"),
            }

            self._paint_background()
            self.play_pause_button.set_style(
                f"background-color: {palette['primary']}; color: {palette['on_primary']}"
            )
            self.prev_button.set_style(f"color: {palette['on_surface']}")
            self.next_button.set_style(f"color: {palette['on_surface']}")
            self._paint_shuffle_button()
            self.player_icon.set_style(f"color: {palette['primary']}")
            self.song.set_style(f"color: {palette['on_surface']}")
            self.artist.set_style(f"color: {palette['on_surface_variant']}")
            self.position_label.set_style(f"color: {palette['on_surface']}")
            self.length_label.set_style(f"color: {palette['on_surface']}")
            self.wiggly.set_color(hex_to_rgb01(palette["primary"]))
            self.audio_source.update_theme(theme_json, mode)

        GLib.idle_add(_apply)

    def _apply_fallback_theme(self, mode: ThemeMode):
        # no artwork colors yet, the stylesheet colors the rest of the card
        self._paint_background()
        self.wiggly.set_color((0, 0, 0) if mode == ThemeMode.LIGHT else (1, 1, 1))
        self.audio_source.update_theme({}, mode)

    def _set_background_image(self, image_path: str | None):
        self._background_image = image_path
        self._paint_background()

    def _paint_background(self):
        scrim = (
            self._palette["scrim"]
            if self._palette
            else default_scrim(self._theme_service.theme)
        )
        self.set_style(card_background(self._background_image, scrim))

    def _paint_shuffle_button(self):
        palette = self._palette
        if not palette:
            return  # the stylesheet's colors apply until a theme arrives
        color = palette["primary"] if self._shuffle_on else palette["on_surface"]
        self.shuffle_button.set_style(f"color: {color}")

    def _switch_theme_mode(self, service: ThemeService, mode: ThemeMode):
        theme_json = self._player_service.get_theme()
        if theme_json:
            self._apply_theme(self._player_service, theme_json, mode)
        else:
            self._apply_fallback_theme(mode)

    def _update_playback_status(self):
        if (
            self._player_service._player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        ):
            self.on_play(self._player_service)
        else:
            self.on_pause(self._player_service)

    def _update_shuffle_status(self, status):
        def _update():
            self._shuffle_on = status
            if status:
                self.shuffle_button.add_style_class("active")
            else:
                self.shuffle_button.remove_style_class("active")
            self._paint_shuffle_button()
            return False

        GLib.idle_add(_update)

    def on_metadata(self, sender, metadata, player):
        keys = metadata.keys()
        self._update_track_info(metadata, keys)
        self._update_playback_status()
        self._update_shuffle_status(player.props.shuffle)
        self._sync_track_times()
        self._update_controls()

    def _update_controls(self):
        self.wiggly.set_sensitive(self._player_service.can_seek and self.duration > 0)
        self._sync_time_slots()
        self.play_pause_button.set_visible(
            self._player_service.can_play or self._player_service.can_pause
        )
        self.play_pause_button.set_sensitive(
            self._player_service.can_play or self._player_service.can_pause
        )
        self.play_pause_button.set_no_show_all(True)
        self._update_shuffle_button()

    def _update_shuffle_button(self, *_):
        self.shuffle_button.set_visible(self._player_service.can_shuffle)
        self.shuffle_button.set_sensitive(self._player_service.can_shuffle)
        self.shuffle_button.set_no_show_all(True)

    def _set_pause_ui(self):
        child = self.play_pause_button.get_child()
        child.set_icon(icons.play_material.symbol())
        child.set_name("pause-label")
        self.play_pause_button.add_style_class("pause-track")
        return False

    def on_pause(self, sender):
        GLib.idle_add(self._set_pause_ui)

        self.wiggly.pause = True

    def _set_play_ui(self):
        child = self.play_pause_button.get_child()
        child.set_icon(icons.pause_material.symbol())
        child.set_name("play-label")
        self.play_pause_button.remove_style_class("pause-track")
        return False

    def on_play(self, sender):
        GLib.idle_add(self._set_play_ui)

        self.wiggly.pause = False

    def on_shuffle(self, sender, player, status):
        logger.debug(f"Shuffle callback status: {status}")
        self._update_shuffle_status(status)

    def handle_next(self):
        if self._player_service.can_go_next:
            self._player_service._player.next()

    def handle_prev(self):
        if self._player_service.can_go_previous:
            self._player_service._player.previous()

    def handle_play_pause(self):
        if not (self._player_service.can_play or self._player_service.can_pause):
            return

        is_playing = (
            self._player_service._player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        )

        if is_playing:
            GLib.idle_add(self._set_pause_ui)
        else:
            GLib.idle_add(self._set_play_ui)

        try:
            self._player_service._player.play_pause()
        except Exception as e:
            # revert if signal failed
            if is_playing:
                GLib.idle_add(self._set_pause_ui)
            else:
                GLib.idle_add(self._set_play_ui)
            logger.warning(f"Failed to toggle playback: {e}")

    def handle_shuffle(self, shuffle_button):
        if not self._player_service.can_shuffle:
            return

        if not self._player_service._player.props.shuffle:
            self._player_service._player.set_shuffle(True)
            logger.debug(
                f"Setting to true: {self._player_service._player.props.player_name}"
            )
        else:
            self._player_service._player.set_shuffle(False)

    def on_destroy(self, *_):
        logger.debug(
            f"Player UI destroyed for {self._player_service._player.props.player_name}"
        )
        # service cleanup is handled by PlayerManager
        for service, handler_id in self._service_handlers:
            service.disconnect(handler_id)
        self._service_handlers.clear()

        if self._wallpaper_signal_id:
            self._wallpaper_service.disconnect(self._wallpaper_signal_id)
            self._wallpaper_signal_id = None

        self.audio_source.disconnect_services()


class Placeholder(Box):
    def __init__(self, **kwargs):
        super().__init__(style_classes="player", **kwargs)

        self._wallpaper_service = WallpaperService()
        self._theme_service = ThemeService()
        self._background_image = None

        def _set_initial_bg(
            service: WallpaperService, full_path: str, preview_path: str | None
        ):
            self._background_image = preview_path
            self._paint_background(self._theme_service.theme)
            return False

        self._wallpaper_signal_id = self._wallpaper_service.connect(
            "wallpaper-changed", _set_initial_bg
        )
        self._theme_service.connect(
            "theme-changed", lambda _, mode: self._paint_background(mode)
        )

        GLib.idle_add(
            _set_initial_bg,
            self._wallpaper_service,
            self._wallpaper_service.get_wallpaper_path(),
            self._wallpaper_service.get_preview_path(),
        )

        self.children = [
            Label(label="Nothing Playing", h_expand=True),
            Box(
                v_align="end",
                children=MaterialIconLabel(
                    name="placeholder-icon",
                    icon_text=icons.disc.symbol(),
                    h_align="end",
                    v_align="end",
                    fill=1,
                ),
            ),
        ]

    def _paint_background(self, mode: ThemeMode):
        self.set_style(card_background(self._background_image, default_scrim(mode)))


class PlayerContainer(Box):
    def __init__(self, window, **kwargs):
        super().__init__(name="player-container", orientation="v", **kwargs)

        self.window = window
        self.manager = PlayerManager()
        self.manager.connect("new-player", self.on_new_player)
        self.manager.connect("player-vanish", self.on_player_vanish)

        self.placeholder_player = Placeholder()
        self.stack = Stack(
            name="player-container",
            transition_type="crossfade",
            transition_duration=100,
            children=[self.placeholder_player],
        )

        self.player_switch_container = CenterBox(
            name="player-switcher",
            orientation="h",
            style_classes=(
                "horizontal-player" if not config.VERTICAL else "vertical-player"
            ),
            h_align="center",
            v_align="end",
            center_children=[],
        )
        self.children = Overlay(child=self.stack, overlays=self.player_switch_container)

        # track UI instances: player_name -> Player widget
        self.player_widgets = {}

        self.init_players()

    def init_players(self):
        self._services = self.manager.get_all_services()
        for service in self._services:
            self.on_new_player(self.manager, service, self._services[service])

    def on_new_player(self, manager, player_name: str, player_service: PlayerService):
        logger.info(f"Creating widget for player: {player_name}")

        # avoid duplicate widget creation
        if player_name in self.player_widgets:
            logger.warning(f"Widget for {player_name} already exists, skipping")
            return

        player_widget = Player(player_service=player_service)
        player_widget.wiggly_bar.queue_draw()
        player_widget.set_name(player_name)

        # store reference
        self.player_widgets[player_name] = player_widget

        self.stack.add_named(player_widget, player_name)

        # remove placeholder if this is the first player
        if len(self.player_widgets) == 1:
            self.stack.remove(self.placeholder_player)
            self.stack.set_visible_child_name(player_name)

        # add switch button
        self.player_switch_container.add_center(
            Button(
                name=player_name,
                style_classes="player-button",
                on_clicked=lambda b: self.switch_player(player_name, b),
            )
        )

        self.update_player_list()

    def switch_player(self, player_name, button):
        def _switch():
            self.stack.set_visible_child_name(player_name)

            for btn in self.player_switch_container.center_children:
                btn.remove_style_class("active")
            button.add_style_class("active")
            return False

        GLib.idle_add(_switch)

    def on_player_vanish(self, manager, player_name: str):
        logger.info(f"Removing UI for player: {player_name}")

        if player_name not in self.player_widgets:
            logger.warning(f"No UI found for {player_name}")
            return

        # get the widget
        player_widget = self.player_widgets[player_name]

        self.stack.remove(player_widget)

        # remove switch button
        for btn in self.player_switch_container.center_children:
            if btn.get_name() == player_name:
                self.player_switch_container.remove_center(btn)
                btn.destroy()
                break

        player_widget.destroy()

        # remove from tracking dict
        del self.player_widgets[player_name]

        # show placeholder or first available player
        if len(self.player_widgets) == 0:
            self.stack.add_named(self.placeholder_player, "placeholder")
            self.stack.set_visible_child_name("placeholder")
        else:
            first_player = next(iter(self.player_widgets.keys()))
            self.stack.set_visible_child_name(first_player)

        self.update_player_list()

    def update_player_list(self):
        curr = self.stack.get_visible_child()
        if not curr:
            return

        curr_name = curr.get_name()

        def _update_buttons():
            for btn in self.player_switch_container.center_children:
                if btn.get_name() == curr_name:
                    btn.add_style_class("active")
                else:
                    btn.remove_style_class("active")
            return False

        GLib.idle_add(_update_buttons)

    def _keybindings(self):
        player_bindings = config.get("bindings.modules.player")
        return {
            format_accel_to_keybind(
                player_bindings["player.play_pause"]
            ): self.handle_play_pause,
            format_accel_to_keybind(player_bindings["player.prev"]): self.handle_prev,
            format_accel_to_keybind(
                player_bindings["player.skip_backward"]
            ): self.handle_skip_backward,
            format_accel_to_keybind(
                player_bindings["player.skip_forward"]
            ): self.handle_skip_forward,
            format_accel_to_keybind(player_bindings["player.next"]): self.handle_next,
            format_accel_to_keybind(player_bindings["player.switch_next"]): lambda: (
                self.switch_relative_player(True)
            ),
            format_accel_to_keybind(player_bindings["player.switch_prev"]): lambda: (
                self.switch_relative_player(False)
            ),
        }

    def register_keybindings(self):
        for key, handler in self._keybindings().items():
            self.window.add_keybinding(key, lambda *_, h=handler: h())

    def unregister_keybindings(self):
        for key in self._keybindings():
            self.window.remove_keybinding(key)

    def handle_play_pause(self):
        if (current := self.stack.get_visible_child()) and isinstance(current, Player):
            current.handle_play_pause()

    def handle_prev(self):
        if (current := self.stack.get_visible_child()) and isinstance(current, Player):
            current.handle_prev()

    def handle_next(self):
        if (current := self.stack.get_visible_child()) and isinstance(current, Player):
            current.handle_next()

    def handle_skip_forward(self):
        if (current := self.stack.get_visible_child()) and isinstance(current, Player):
            current.skip_forward(seconds=10)

    def handle_skip_backward(self):
        if (current := self.stack.get_visible_child()) and isinstance(current, Player):
            current.skip_backward(seconds=10)

    def switch_relative_player(self, forward=True):
        if not self.player_widgets:
            return

        current_player = self.stack.get_visible_child()
        if not isinstance(current_player, Player):
            return

        player_names = list(self.player_widgets.keys())
        current_name = current_player.get_name()

        try:
            current_index = player_names.index(current_name)
        except ValueError:
            logger.warning(f"Current player {current_name} not in list")
            return

        next_index = (current_index + (1 if forward else -1)) % len(player_names)
        next_name = player_names[next_index]

        # find and click the corresponding button
        for btn in self.player_switch_container.center_children:
            if btn.get_name() == next_name:
                self.switch_player(next_name, btn)
                break

    def cleanup(self):
        logger.info("Cleaning up PlayerContainer")

        # unregister keybindings
        try:
            self.unregister_keybindings()
        except Exception as e:
            logger.warning(f"Error unregistering keybindings: {e}")

        # cleanup all widgets
        for player_name, widget in list(self.player_widgets.items()):
            try:
                widget.destroy()
            except Exception as e:
                logger.error(f"Error destroying widget for {player_name}: {e}")

        self.player_widgets.clear()

        # cleanup the manager
        try:
            self.manager.cleanup_all()
        except Exception as e:
            logger.error(f"Error cleaning up manager: {e}")

        logger.info("PlayerContainer cleanup complete")
