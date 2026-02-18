from loguru import logger

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox

from widgets.overrides import Svg

from modules.wiggle_bar import WigglyScale
from modules.wallpaper import WallpaperService
from services.volume_service import VolumeService
from widgets.material_label import MaterialIconLabel
from services.player_service import PlayerManager, PlayerService

import svg
import icons
from config.config import config

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, GObject


class Player(Box):
    def __init__(self, player_service: PlayerService, **kwargs):
        super().__init__(style_classes="player", orientation="v", spacing=15, **kwargs)

        # vertical class binding from unknown source
        if not config.VERTICAL:
            self.remove_style_class("vertical")

        self._volume_service = VolumeService()
        self._wallpaper_service = WallpaperService()

        MAX_CHARS = 30
        MAX_AUDIO_DEVICE_NAME_CHARS = 15
        self.duration = 0.0
        self._player_service = player_service
        player = self._player_service._player
        self._device_name = self._volume_service.get_current_device_name()

        def _set_initial_bg(
            service: WallpaperService, full_path: str, preview_path: str
        ):
            self.set_style(f"background-image:url('{preview_path}')")
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
            h_expand=True,
            style_classes="player-icon",
            svg_string=getattr(svg, player.props.player_name, svg.disc),
        )
        self.audo_device_label = Label(
            label=self._device_name,
            style="color: black; font-size: 13px;",
            max_chars_width=MAX_AUDIO_DEVICE_NAME_CHARS,
            ellipsization="end",
        )
        self.audio_source = Box(
            spacing=5,
            name="source-name",
            children=[
                MaterialIconLabel(
                    icon_text=icons.headphones.symbol(), wght=600, style="color: black;"
                ),
                self.audo_device_label,
            ],
        )

        self.song = Label(
            name="song",
            label="song",
            justification="left",
            h_align="start",
            ellipsization="end",
            max_chars_width=MAX_CHARS,
        )

        self.artist = Label(
            name="artist",
            label="artist",
            justification="left",
            h_align="start",
            max_chars_width=MAX_CHARS,
        )

        self.music = Box(
            name="music",
            orientation="v",
            h_expand=True,
            v_expand=True,
            children=[self.song, self.artist],
        )

        # controls
        self.play_pause_button = Button(
            name="pause-button",
            child=MaterialIconLabel(
                name="pause-label", icon_text=icons.play_material.symbol()
            ),
            style_classes="pause-track",
            tooltip_text="Play/Pause",
            on_clicked=lambda b, *_: self.handle_play_pause(),
        )

        self.shuffle_button = Button(
            name="shuffle-button",
            child=Svg(
                name="shuffle",
                style_classes=["material-icon"],
                v_expand=True,
                svg_string=svg.shuffle,
            ),
            on_clicked=lambda b, *_: self.handle_shuffle(b),
        )

        self.prev_button = Button(
            name="prev-button",
            child=MaterialIconLabel(
                name="play-previous",
                style_classes=["material-icon"],
                FILL=0,
                icon_text=icons.skip_prev.symbol(),
            ),
            on_clicked=lambda b, *_: self.handle_prev(),
        )
        self.next_button = Button(
            name="next-button",
            child=MaterialIconLabel(
                name="play-next",
                style_classes=["material-icon"],
                FILL=0,
                icon_text=icons.skip_next.symbol(),
            ),
            on_clicked=lambda b, *_: self.handle_next(),
        )

        self.wiggly = WigglyScale()
        self.wiggly.connect("on-seek", self.on_seek)
        # self.wiggly.connect("notify::dragging", self.on_dragging_changed)

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
                        v_expand=True,
                        children=self.player_icon,
                    ),
                    Box(h_expand=True),
                    self.audio_source,
                ],
            ),
            Box(
                name="details",
                children=[self.music, self.play_pause_button],
            ),
            Box(
                name="controls",
                style_classes="horizontal" if not config.VERTICAL else "vertical",
                spacing=5,
                children=(
                    [
                        self.prev_button,
                        CenterBox(
                            name="progress-container",
                            h_expand=True,
                            v_expand=True,
                            orientation="v",
                            center_children=[self.wiggly_bar],
                        ),
                        self.next_button,
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
                                    start_children=[
                                        Button(
                                            name="prev-button",
                                            child=Label(
                                                name="play-previous",
                                                markup=icons.previous.markup(),
                                            ),
                                            on_clicked=lambda b, *_: self.handle_prev(),
                                        ),
                                        Button(
                                            name="next-button",
                                            child=Label(
                                                name="play-next",
                                                markup=icons.next.markup(),
                                            ),
                                            on_clicked=lambda b, *_: self.handle_next(),
                                        ),
                                        self.shuffle_button,
                                    ],
                                    end_children=self.play_pause_button,
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
        self._player_service.connect("pause", self.on_pause)
        self._player_service.connect("play", self.on_play)
        self._player_service.connect("meta-change", self.on_metadata)
        self._player_service.connect("shuffle-toggle", self.on_shuffle)
        self._player_service.connect("track-position", self.on_update_track_position)
        self._player_service.connect("theme-change", self._apply_theme)
        self._player_service.connect("artwork-change", self._apply_artwork)

        self._volume_service.connect("device-changed", self.on_audio_device_changed)

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
            self._apply_theme(self._player_service, current_theme)

    def on_update_track_position(self, sender, pos, dur):
        if dur == 0:
            return
        self.duration = dur
        self.wiggly.update_value_from_signal(pos / dur)

    def on_seek(self, sender, ratio):
        pos = ratio * self.duration  # duration in seconds
        logger.debug(f"Seeking to {pos:.2f}s")
        self._player_service.set_position(int(pos))

    def skip_forward(self, seconds=10):
        if self._player_service.can_seek:
            self._player_service._player.seek(seconds * 1000000)

    def skip_backward(self, seconds=10):
        if self._player_service.can_seek:
            self._player_service._player.seek(-1 * seconds * 1000000)

    def _update_track_info(self, metadata, keys):
        if "xesam:artist" in keys and "xesam:title" in keys:
            song_title = metadata["xesam:title"]
            artist_list = metadata["xesam:artist"]
            artist_name = artist_list[0] if artist_list else "Unknown Artist"

            def _update_metadata_label():
                self.song.set_label(song_title)
                self.artist.set_label(artist_name)
                return False

            GLib.idle_add(_update_metadata_label)

    def _apply_artwork(self, source, art_path):
        # remove wallpaper connection
        if self._wallpaper_signal_id:
            self._wallpaper_service.disconnect(self._wallpaper_signal_id)
            self._wallpaper_signal_id = None
        GLib.idle_add(lambda: self.set_style(f"background-image:url('{art_path}')"))

    def _apply_theme(self, source, theme_json):
        primary_color = theme_json["colors"]["primary"]["dark"]["color"]

        def _apply():
            self.play_pause_button.set_style(f"background-color: {primary_color}")
            self.player_icon.set_style(f"color: {primary_color}")
            self.audio_source.set_style(f"background-color: {primary_color}")

        GLib.idle_add(_apply)

    def _update_playback_status(self):
        if (
            self._player_service._player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        ):
            self.on_play(self._player_service)

    def _update_shuffle_status(self, status):
        def _update():
            child = self.shuffle_button.get_child()
            if status:
                child.set_from_string(svg.disable_shuffle)
                child.set_name("disable-shuffle")
            else:
                child.set_from_string(svg.shuffle)
                child.set_name("shuffle")
            return False

        GLib.idle_add(_update)

    def on_audio_device_changed(self, source: VolumeService, device_name: str):
        self.audo_device_label.set_label(device_name)

    def on_metadata(self, sender, metadata, player):
        keys = metadata.keys()
        self._update_track_info(metadata, keys)
        self._update_playback_status()
        self._update_shuffle_status(player.props.shuffle)
        self._update_controls()

    def _update_controls(self):
        self.wiggly.set_sensitive(self._player_service.can_seek)
        self.next_button.set_visible(self._player_service.can_go_next)
        self.next_button.set_sensitive(self._player_service.can_go_next)
        self.next_button.set_no_show_all(True)
        self.play_pause_button.set_visible(
            self._player_service.can_play or self._player_service.can_pause
        )
        self.play_pause_button.set_sensitive(
            self._player_service.can_play or self._player_service.can_pause
        )
        self.prev_button.set_no_show_all(True)
        self.prev_button.set_visible(self._player_service.can_go_previous)
        self.prev_button.set_sensitive(self._player_service.can_go_previous)
        self.play_pause_button.set_no_show_all(True)
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

        self.wiggly._dragging = True
        self.wiggly.update_amplitude(True)
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
        self.wiggly._dragging = False
        self.wiggly.update_amplitude(False)

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
        if not (self._player_service.can_play or self._player_service.can_play):
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


class Placeholder(Box):
    def __init__(self, **kwargs):
        super().__init__(style_classes="player", **kwargs)

        self._wallpaper_service = WallpaperService()

        def _set_initial_bg(
            service: WallpaperService, full_path: str, preview_path: str | None
        ):
            self.set_style(f"background-image:url('{preview_path}')")
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
            name="player-switch-container",
            orientation="h",
            style_classes=(
                "horizontal-player" if not config.VERTICAL else "vertical-player"
            ),
            center_children=[],
        )
        self.children = [self.stack, self.player_switch_container]

        # track UI instances: player_name -> Player widget
        self.player_widgets = {}

        self.init_players()

    def init_players(self):
        """Create UI instances of existing players"""
        self._services = self.manager.get_all_services()
        for service in self._services:
            self.on_new_player(self.manager, service, self._services[service])

    def on_new_player(self, manager, player_name: str, player_service: PlayerService):
        """Called when PlayerManager creates a new PlayerService"""
        logger.info(f"Creating UI for player: {player_name}")

        # avoid duplicate widget creation
        if player_name in self.player_widgets:
            logger.warning(f"UI for {player_name} already exists, skipping")
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
        """Switch to a specific player"""

        def _switch():
            self.stack.set_visible_child_name(player_name)

            for btn in self.player_switch_container.center_children:
                btn.remove_style_class("active")
            button.add_style_class("active")
            return False

        GLib.idle_add(_switch)

    def on_player_vanish(self, manager, player_name: str):
        """Called when a player disappears"""
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
        """Update active state of player switch buttons"""
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
        return {
            "p": self.handle_play_pause,
            "j": self.handle_prev,
            "k": self.handle_skip_backward,
            "l": self.handle_skip_forward,
            "semicolon": self.handle_next,
            "Tab": lambda: self.switch_relative_player(True),
            "Shift ISO_Left_Tab": lambda: self.switch_relative_player(False),
        }
    
    def register_keybindings(self):
        """Register keyboard shortcuts"""
        for key, handler in self._keybindings().items():
            self.window.add_keybinding(key, lambda *_, h=handler: h())

    def unregister_keybindings(self):
        """Unregister keyboard shortcuts"""
        for key in self._keybindings().keys():
            self.window.remove_keybinding(key)

    def handle_play_pause(self):
        """Handle play/pause for current player"""
        if current := self.stack.get_visible_child():
            if isinstance(current, Player):
                current.handle_play_pause()

    def handle_prev(self):
        """Handle previous track for current player"""
        if current := self.stack.get_visible_child():
            if isinstance(current, Player):
                current.handle_prev()

    def handle_next(self):
        """Handle next track for current player"""
        if current := self.stack.get_visible_child():
            if isinstance(current, Player):
                current.handle_next()

    def handle_skip_forward(self):
        """Skip forward 10 seconds in current player"""
        if current := self.stack.get_visible_child():
            if isinstance(current, Player):
                current.skip_forward(seconds=10)

    def handle_skip_backward(self):
        """Skip backward 10 seconds in current player"""
        if current := self.stack.get_visible_child():
            if isinstance(current, Player):
                current.skip_backward(seconds=10)

    def switch_relative_player(self, forward=True):
        """Switch to next/previous player"""
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
        """Cleanup all resources on application shutdown"""
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
