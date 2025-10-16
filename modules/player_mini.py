from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from fabric.widgets.eventbox import EventBox

from services.player_service import PlayerManager, PlayerService
from modules.wiggle_bar import WigglyWidget

import icons.icons as icons
import config.info as info

from loguru import logger

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GLib


class PlayerMini(Box):
    def __init__(self, player_service: PlayerService, **kwargs):
        super().__init__(style_classes="player-mini", **kwargs)

        self._player_service = player_service
        player = self._player_service._player

        if not info.VERTICAL:
            self.remove_style_class("vertical")

        self.player_name = Label(
            name=player.props.player_name,
            style_classes=["player-icon", "mini"],
            markup=getattr(icons, player.props.player_name, icons.disc),
        )

        self.set_style(
            f"background-image:url('{info.HOME_DIR}/.cache/walls/low_rez.png')"
        )

        self.song = Label(
            name="song",
            label="song",
            style_classes="mini",
            justification="left",
            h_align="start",
            ellipsization="end",
            max_chars_width=15,
        )
        self.artist = Label(
            name="artist",
            label="artist",
            style_classes="mini",
            justification="left",
            h_align="start",
        )
        self.music = Box(
            name="music",
            h_expand=True,
            v_expand=True,
            children=[self.song],
        )

        self.play_pause_button = Button(
            name="play-pause-button",
            child=Label(
                name="play-pause-label", style_classes="mini", markup=icons.play
            ),
            style_classes="mini",
            tooltip_text="Play/Pause",
            on_clicked=lambda b, *_: self.handle_play_pause(),
        )

        self.shuffle_button = Button(
            name="shuffle-button",
            child=Label(name="shuffle", markup=icons.shuffle),
            on_clicked=lambda b, *_: self.handle_shuffle(b),
        )

        self.wiggly = WigglyWidget()
        self.wiggly.connect("on-seek", self.on_seek)
        self.wiggly_bar = Box(
            orientation="v",
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            children=self.wiggly,
        )

        self.album_cover = Box(style_classes="album-image")
        self.album_cover.set_style(
            f"background-image:url('{info.HOME_DIR}/.cache/walls/low_rez.png')"
        )

        self.children = [
            self.album_cover,
            Box(
                name="source",
                style_classes="mini",
                v_align="end",
                children=self.player_name,
            ),
            Box(
                orientation="v",
                v_expand=True,
                h_expand=True,
                style="padding-left:10px;",
                children=[
                    CenterBox(
                        name="details",
                        center_children=self.music,
                    ),
                    Box(
                        name="controls",
                        style_classes="horizontal" if not info.VERTICAL else "vertical",
                        spacing=5,
                        h_expand=True,
                        children=[
                            CenterBox(
                                h_expand=True,
                                v_expand=True,
                                center_children=[
                                    Button(
                                        name="prev-button",
                                        child=Label(
                                            name="play-previous",
                                            style_classes="mini",
                                            markup=icons.previous_fill,
                                        ),
                                        on_clicked=lambda b, *_: self.handle_prev(),
                                    ),
                                    self.play_pause_button,
                                    Button(
                                        name="next-button",
                                        child=Label(
                                            name="play-next",
                                            style_classes="mini",
                                            markup=icons.next_fill,
                                        ),
                                        on_clicked=lambda b, *_: self.handle_next(),
                                    ),
                                ],
                            )
                        ],
                    ),
                ],
            ),
        ]

        self.duration = 0.0

        # connect to service signals
        self._player_service.connect("pause", self.on_pause)
        self._player_service.connect("play", self.on_play)
        self._player_service.connect("meta-change", self.on_metadata)
        self._player_service.connect("shuffle-toggle", self.on_shuffle)
        self._player_service.connect("track-position", self.on_update_track_position)
        self._player_service.connect("artwork-change", self._apply_artwork)

        # connect cleanup
        self.connect('destroy', self.on_destroy)

        # init metadata
        self.on_metadata(
            self._player_service, metadata=player.props.metadata, player=player
        )
        
        # init artwork
        current_artwork = self._player_service.get_artwork()
        if current_artwork:
            self._apply_artwork(self._player_service, current_artwork)

    def on_destroy(self, *_):
        """Cleanup widget on destroy"""
        logger.debug(f"PlayerMini UI destroyed for {self._player_service._player.props.player_name}")
        # service cleanup is handled by PlayerManager

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
        self._player_service._player.seek(seconds * 1000000)

    def skip_backward(self, seconds=10):
        self._player_service._player.seek(-1 * seconds * 1000000)

    def _apply_artwork(self, source, art_path):
        def _apply():
            self.album_cover.set_style(f"background-image:url('{art_path}')")
            self.set_style(f"background-image:url('{art_path}')")
        GLib.idle_add(_apply)

    def on_metadata(self, sender, metadata, player):
        keys = metadata.keys()
        if "xesam:artist" in keys and "xesam:title" in keys:
            song_title = metadata["xesam:title"]
            self.song.set_label(song_title)

            artist_list = metadata["xesam:artist"]
            artist_name = artist_list[0] if artist_list else "Unknown Artist"
            self.artist.set_label(artist_name)

        if (
            player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        ):
            self.on_play(self._player_service)

        if player.props.shuffle == True:
            self.shuffle_button.get_child().set_markup(icons.disable_shuffle)
            self.shuffle_button.get_child().set_name("disable-shuffle")
        else:
            self.shuffle_button.get_child().set_markup(icons.shuffle)
            self.shuffle_button.get_child().set_name("shuffle")

    def on_pause(self, sender):
        self.play_pause_button.get_child().set_markup(icons.play)
        self.wiggly.dragging = True
        self.wiggly.update_amplitude(True)
        self.wiggly.pause = True

    def on_play(self, sender):
        self.play_pause_button.get_child().set_markup(icons.pause)
        self.wiggly.pause = False
        self.wiggly.dragging = False
        self.wiggly.update_amplitude(False)

    def on_shuffle(self, sender, player, status):
        logger.debug(f"Shuffle callback status: {status}")
        if status == False:
            self.shuffle_button.get_child().set_markup(icons.shuffle)
            self.shuffle_button.get_child().set_name("shuffle")
        else:
            self.shuffle_button.get_child().set_markup(icons.disable_shuffle)
            self.shuffle_button.get_child().set_name("disable-shuffle")
        self.shuffle_button.get_child().set_style("color: white")

    def handle_next(self):
        self._player_service._player.next()

    def handle_prev(self):
        self._player_service._player.previous()

    def handle_play_pause(self):
        is_playing = (
            self._player_service._player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        )

        def _set_play_ui():
            self.play_pause_button.get_child().set_markup(icons.pause)

        def _set_pause_ui():
            self.play_pause_button.get_child().set_markup(icons.play)

        if is_playing:
            _set_pause_ui()
        else:
            _set_play_ui()

        try:
            self._player_service._player.play_pause()
        except Exception as e:
            # revert if signal failed
            if is_playing:
                _set_pause_ui()
            else:
                _set_play_ui()
            logger.warning(f"Failed to toggle playback: {e}")

    def handle_shuffle(self, shuffle_button):
        logger.debug(f"Shuffle: {self._player_service._player.props.shuffle}")
        if self._player_service._player.props.shuffle == False:
            self._player_service._player.set_shuffle(True)
            logger.debug(f"Setting to true: {self._player_service._player.props.player_name}")
        else:
            self._player_service._player.set_shuffle(False)
        shuffle_button.get_child().set_style("color: var(--outline)")


class PlaceholderMini(Box):
    def __init__(self, **kwargs):
        super().__init__(style_classes="player-mini", **kwargs)

        self.set_style(
            f"background-image:url('{info.HOME_DIR}/.cache/walls/low_rez.png')"
        )
        self.album_cover = Box(style_classes="album-image")
        self.album_cover.set_style(
            f"background-image:url('{info.HOME_DIR}/.cache/walls/low_rez.png')"
        )
        self.player_name = Label(
            style_classes=["player-icon", "mini"], markup=icons.disc
        )

        self.children = [
            self.album_cover,
            Box(
                name="source",
                style_classes="mini",
                v_align="end",
                children=self.player_name,
            ),
            Box(
                orientation="v",
                v_expand=True,
                h_expand=True,
                style="padding-left:10px;",
                v_align="center",
                children=[
                    CenterBox(
                        name="details",
                        center_children=Label(
                            label="Nothing Playing", style="color:black;"
                        ),
                    )
                ],
            ),
        ]


class PlayerContainerMini(Box):
    def __init__(self, **kwargs):
        super().__init__(name="player-container", style_classes="mini", **kwargs)

        self.manager = PlayerManager()
        self.manager.connect("new-player", self.on_new_player)
        self.manager.connect("player-vanish", self.on_player_vanish)
        
        self.placeholder = PlaceholderMini()
        self.stack = Stack(
            transition_type="crossfade",
            transition_duration=100,
            children=[self.placeholder],
        )

        self.player_stack = Stack(
            name="player-stack",
            transition_type="crossfade",
            transition_duration=100,
            children=[],
        )

        self.player_switch_container = CenterBox(
            name="player-switch-container",
            orientation="v",
            style_classes=(
                ["horizontal-player", "mini"]
                if not info.VERTICAL
                else "vertical-player"
            ),
            center_children=[],
        )
        
        self.mini_tile_icon = Label(
            name="disc",
            style_classes=["tile-icon"],
            style="font-size:30px; margin:0px; padding:0px;",
            markup=icons.disc,
            justification="center",
        )

        self.mini_tile_view = CenterBox(
            style_classes=["tile", "mini", "on"],
            v_expand=False,
            center_children=self.mini_tile_icon,
        )
        
        self.event_box = EventBox(
            events=["scroll"],
            child=Box(children=[self.stack, self.player_switch_container]),
        )
        
        self.children = self.event_box
        
        # track UI instances: player_name -> PlayerMini widget
        self.player_widgets = {}
        
        self.init_players()
        
        self.event_box.connect("scroll-event", self.on_scroll)
        self.stack.connect("notify::visible-child", self.on_visible_child_changed)

    def init_players(self):
        """Create UI instances of existing players"""
        self._services = self.manager.get_all_services()
        for service in self._services:
            self.on_new_player(self.manager, service, self._services[service])

    def on_new_player(self, manager, player_name: str, player_service: PlayerService):
        """Called when PlayerManager creates a new PlayerService"""
        logger.info(f"Creating mini UI for player: {player_name}")
        
        # avoid duplicate UI creation
        if player_name in self.player_widgets:
            logger.warning(f"Mini UI for {player_name} already exists, skipping")
            return
        
        # create widget with the service
        player_widget = PlayerMini(player_service=player_service)
        player_widget.wiggly_bar.queue_draw()
        player_widget.set_name(player_name)
        
        # store reference
        self.player_widgets[player_name] = player_widget
        
        logger.debug(f"Stacking mini: {player_name}")
        self.stack.add_named(player_widget, player_name)
        
        # remove placeholder if this is the first player
        if len(self.player_widgets) == 1:
            self.stack.remove(self.placeholder)
            self.stack.set_visible_child_name(player_name)
        
        # add switch button
        self.player_switch_container.add_center(
            Button(
                name=player_name,
                style_classes=["player-button", "mini"],
                on_clicked=lambda b: self.switch_player(player_name, b),
            )
        )
        
        self.update_player_list()

    def switch_player(self, player_name, button):
        """Switch to a specific player"""
        self.stack.set_visible_child_name(player_name)

        for btn in self.player_switch_container.center_children:
            btn.remove_style_class("active")
        button.add_style_class("active")

    def on_player_vanish(self, manager, player_name: str):
        """Called when a player disappears"""
        logger.info(f"Removing mini UI for player: {player_name}")
        
        if player_name not in self.player_widgets:
            logger.warning(f"No mini UI found for {player_name}")
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
            self.stack.add_named(self.placeholder, "placeholder")
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
        for btn in self.player_switch_container.center_children:
            if btn.get_name() == curr_name:
                btn.add_style_class("active")
            else:
                btn.remove_style_class("active")

    def on_scroll(self, widget, event):
        """Handle scroll events to switch between players"""
        match event.direction:
            case 0:
                self.switch_relative_player(forward=False)
            case 1:
                self.switch_relative_player(forward=True)

    def switch_relative_player(self, forward=True):
        """Switch to next/previous player"""
        if not self.player_widgets:
            return

        current_player = self.stack.get_visible_child()
        if not isinstance(current_player, PlayerMini):
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

    def on_visible_child_changed(self, *args):
        """Update mini tile icon when visible player changes"""
        curr_child = self.stack.get_visible_child()
        if not curr_child or not hasattr(curr_child, 'get_name'):
            return
            
        curr_player = curr_child.get_name()
        self.mini_tile_icon.set_name(curr_player)
        self.mini_tile_icon.set_markup(getattr(icons, curr_player, icons.disc))

    def get_mini_view(self):
        """Get the mini tile view widget"""
        return self.mini_tile_view

    def cleanup(self):
        """Cleanup all resources on application shutdown"""
        logger.info("Cleaning up PlayerContainerMini")
        
        # cleanup all widgets
        for player_name, widget in list(self.player_widgets.items()):
            try:
                widget.destroy()
            except Exception as e:
                logger.error(f"Error destroying mini widget for {player_name}: {e}")
        
        self.player_widgets.clear()
        
        # cleanup the manager
        try:
            self.manager.cleanup_all()
        except Exception as e:
            logger.error(f"Error cleaning up manager: {e}")
        
        logger.info("PlayerContainerMini cleanup complete")