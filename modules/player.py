from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack

from services.player_service import PlayerManager, PlayerService
from modules.wiggle_bar import WigglyWidget

import icons.icons as icons
import config.info as info

from loguru import logger
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib


class Player(Box):
    def __init__(self, player, **kwargs):
        super().__init__(style_classes="player", orientation="v", **kwargs)

        if not info.VERTICAL:
            self.remove_style_class(
                "vertical"
            )  # vertical class binding from unknown source

        self._player_service = PlayerService(player=player)

        self.duration = 0.0
        self._theme_cache = {}
        self._current_artwork_hash = ""
        MAX_CHARS = 30

        self._player_service.connect("pause", self.on_pause)
        self._player_service.connect("play", self.on_play)
        self._player_service.connect("meta-change", self.on_metadata)
        self._player_service.connect("shuffle-toggle", self.on_shuffle)
        self._player_service.connect("track-position", self.on_update_track_position)
        self._player_service.connect("theme-change", self._apply_theme)
        self._player_service.connect("artwork-change", self._apply_artwork)

        GLib.idle_add(
            lambda: (
                self.set_style(
                    f"background-image:url('{info.HOME_DIR}/.cache/walls/low_rez.png')"
                )
            )
        )

        self.player_icon = Label(
            name=player.props.player_name,
            style_classes="player-icon",
            markup=getattr(icons, player.props.player_name, icons.disc),
        )
        self.player_name = Label(label="stereo zenith", style="color: black; font-size: 13px;")
        self.player_name.set_max_width_chars(MAX_CHARS)
        self.player_source = Box(
            spacing=13,
            name="source-name",
            children=[
                Label(markup=icons.headphones, style="color: black;"),
                self.player_name,
            ],
        )

        self.song = Label(
            name="song",
            label="song",
            justification="left",
            h_align="start",
            ellipsization="end",
        )
        self.song.set_max_width_chars(MAX_CHARS)

        self.artist = Label(
            name="artist", label="artist", justification="left", h_align="start"
        )
        self.artist.set_max_width_chars(MAX_CHARS)

        self.music = Box(
            name="music",
            orientation="v",
            h_expand=True,
            v_expand=True,
            children=[self.song, self.artist],
        )

        self.play_pause_button = Button(
            name="pause-button",
            child=Label(name="pause-label", markup=icons.play),
            style_classes="pause-track",
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

        self.children = [
            Box(
                name="source",
                children=[
                    Box(h_expand=True, v_expand=True, children=self.player_icon),
                    self.player_source,
                ],
            ),
            Box(
                name="details",
                children=[self.music, self.play_pause_button],
            ),
            Box(
                name="controls",
                style_classes="horizontal" if not info.VERTICAL else "vertical",
                spacing=5,
                children=(
                    [
                        Button(
                            name="prev-button",
                            child=Label(name="play-previous", markup=icons.previous),
                            on_clicked=lambda b, *_: self.handle_prev(),
                        ),
                        CenterBox(
                            name="progress-container",
                            h_expand=True,
                            v_expand=True,
                            orientation="v",
                            center_children=[self.wiggly_bar],
                        ),
                        Button(
                            name="next-button",
                            child=Label(name="play-next", markup=icons.next),
                            on_clicked=lambda b, *_: self.handle_next(),
                        ),
                        self.shuffle_button,
                    ]
                    if not info.VERTICAL
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
                                                markup=icons.previous,
                                            ),
                                            on_clicked=lambda b, *_: self.handle_prev(),
                                        ),
                                        Button(
                                            name="next-button",
                                            child=Label(
                                                name="play-next", markup=icons.next
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

        self.on_metadata(
            self._player_service, metadata=player.props.metadata, player=player
        )

    def on_update_track_position(self, sender, pos, dur):
        if dur == 0:
            return
        self.duration = dur
        self.wiggly.update_value_from_signal(pos / dur)

    def on_seek(self, sender, ratio):
        pos = ratio * self.duration  # duration in seconds
        print(f"Seeking to {pos:.2f}s")
        self._player_service.set_position(int(pos))

    def skip_forward(self, seconds=10):
        self._player_service._player.seek(seconds * 1000000)

    def skip_backward(self, seconds=10):
        self._player_service._player.seek(-1 * seconds * 1000000)

    def _update_track_info(self, metadata, keys):
        if "xesam:artist" in keys and "xesam:title" in keys:
            song_title = metadata["xesam:title"]
            self.song.set_label(song_title)

            artist_list = metadata["xesam:artist"]
            artist_name = artist_list[0] if artist_list else "Unknown Artist"
            self.artist.set_label(artist_name)

    def _apply_artwork(self, source, art_path):
        GLib.idle_add(lambda: self.set_style(f"background-image:url('{art_path}')"))

    def _apply_theme(self, source, theme_json):
        primary_color = theme_json["colors"]["dark"]["primary"]
        def _apply():
            self.play_pause_button.set_style(f"background-color: {primary_color}")
            self.player_icon.set_style(f"color: {primary_color}")
            self.player_source.set_style(f"background-color: {primary_color}")
        GLib.idle_add(lambda:_apply())

    def _update_playback_status(self):
        if (
            self._player_service._player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        ):
            self.on_play(self._player_service)

    def _update_shuffle_status(self):
        child = self.shuffle_button.get_child()
        if self._player_service._player.props.shuffle:
            child.set_markup(icons.disable_shuffle)
            child.set_name("disable-shuffle")
        else:
            child.set_markup(icons.shuffle)
            child.set_name("shuffle")

    def on_metadata(self, sender, metadata, player):
        keys = metadata.keys()
        self._update_track_info(metadata, keys)
        # self._handle_artwork(metadata, keys)
        self._update_playback_status()
        self._update_shuffle_status()

    def on_pause(self, sender):
        child = self.play_pause_button.get_child()
        child.set_markup(icons.play)
        child.set_name("pause-label")
        self.wiggly.dragging = True
        self.wiggly.update_amplitude(True)
        self.wiggly.pause = True
        self.play_pause_button.add_style_class("pause-track")

    def on_play(self, sender):
        child = self.play_pause_button.get_child()
        child.set_markup(icons.pause)
        child.set_name("play-label")
        self.wiggly.pause = False
        self.wiggly.dragging = False
        self.wiggly.update_amplitude(False)
        self.play_pause_button.remove_style_class("pause-track")

    def on_shuffle(self, sender, player, status):
        print("callback status", status)
        child = self.shuffle_button.get_child()
        if status:
            child.set_markup(icons.disable_shuffle)
            child.set_name("disable-shuffle")
        else:
            child.set_markup(icons.shuffle)
            child.set_name("shuffle")

        child.set_style("color: white")

    def handle_next(self):
        self._player_service._player.next()

    def handle_prev(self):
        self._player_service._player.previous()

    def handle_play_pause(self):
        is_playing = (
            self._player_service._player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        )

        def _set_pause_ui():
            self.play_pause_button.get_child().set_markup(icons.pause)
            self.play_pause_button.remove_style_class("pause-track")
            self.play_pause_button.get_child().set_name("pause-label")

        def _set_play_ui():
            self.play_pause_button.get_child().set_markup(icons.play)
            self.play_pause_button.add_style_class("pause-track")
            self.play_pause_button.get_child().set_name("play-label")

        if is_playing:
            _set_play_ui()
        else:
            _set_pause_ui()

        try:
            self._player_service._player.play_pause()
        except Exception as e:
            # revert if signal failed
            if is_playing:
                _set_play_ui()
            else:
                _set_pause_ui()
            logger.warning("Failed to toggle playback:", e)

    def handle_shuffle(self, shuffle_button):
        print("shuffle", self._player_service._player.props.shuffle)
        if self._player_service._player.props.shuffle == False:
            self._player_service._player.set_shuffle(True)
            print("setting to true", self._player_service._player.props.player_name)
        else:
            self._player_service._player.set_shuffle(False)
        shuffle_button.get_child().set_style("color: var(--outline)")


class Placeholder(Box):
    def __init__(self, **kwargs):
        super().__init__(style_classes="player", **kwargs)

        self.set_style(
            f"background-image:url('{info.HOME_DIR}/.cache/walls/low_rez.png')"
        )

        self.children = [
            Label(label="Nothing Playing", h_expand=True),
            Label(
                markup=icons.disc,
                v_align="end",
                style="font-size:40px; margin-left:-30px; margin-bottom:-18px",
            ),
        ]


class PlayerContainer(Box):
    def __init__(self, window, **kwargs):
        super().__init__(name="player-container", orientation="v", **kwargs)

        self.window = window
        self.manager = PlayerManager()
        self.manager.connect("new-player", self.new_player)
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
                "horizontal-player" if not info.VERTICAL else "vertical-player"
            ),
            center_children=[],
        )
        self.children = [self.stack, self.player_switch_container]
        self.players = []
        self.manager.init_all_players()

    def new_player(self, manager, player):
        print(player.props.player_name, "new player")
        new_player = Player(player=player)
        new_player.wiggly_bar.queue_draw()
        new_player.set_name(player.props.player_name)
        self.players.append(new_player)
        self.stack.add_named(new_player, player.props.player_name)
        if len(self.players) == 1:
            self.stack.remove(self.placeholder_player)

        self.player_switch_container.add_center(
            Button(
                name=player.props.player_name,
                style_classes="player-button",
                on_clicked=lambda b: self.switch_player(player.props.player_name, b),
            )
        )
        self.update_player_list()

    def switch_player(self, player_name, button):
        self.stack.set_visible_child_name(player_name)

        for btn in self.player_switch_container.center_children:
            btn.remove_style_class("active")
        button.add_style_class("active")

    def on_player_vanish(self, manager, player):
        for player_instance in self.players:
            if player_instance.get_name() == player.props.player_name:
                self.stack.remove(player_instance)
                self.players.remove(player_instance)
                for btn in self.player_switch_container.center_children:
                    if btn.get_name() == player_instance.get_name():
                        self.player_switch_container.remove_center(btn)
                self.update_player_list()
                break
        if len(self.players) == 0:
            self.stack.add_named(self.placeholder_player, "placeholder")

    def update_player_list(self):
        curr = self.stack.get_visible_child()
        for btn in self.player_switch_container.center_children:
            print(btn.get_name())
            if btn.get_name() == curr.get_name():
                btn.add_style_class("active")
            else:
                btn.remove_style_class("active")

    def register_keybindings(self):
        keybindings = {
            "p": self.handle_play_pause,
            "j": self.handle_prev,
            "k": self.handle_skip_backward,
            "l": self.handle_skip_forward,
            "semicolon": self.handle_next,
            "Tab": lambda: self.switch_relative_player(True),
            "Shift ISO_Left_Tab": lambda: self.switch_relative_player(False),
        }

        for key, handler in keybindings.items():
            self.window.add_keybinding(key, lambda *_, h=handler: h())

    def unregister_keybindings(self):
        keys = ["p", "j", "k", "l", "semicolon", "Tab", "Shift ISO_Left_Tab"]
        for key in keys:
            self.window.remove_keybinding(key)

    def handle_play_pause(self):
        if current := self.stack.get_visible_child():
            current.handle_play_pause()

    def handle_prev(self):
        if current := self.stack.get_visible_child():
            current.handle_prev()

    def handle_next(self):
        if current := self.stack.get_visible_child():
            current.handle_next()

    def handle_skip_forward(self):
        if current := self.stack.get_visible_child():
            current.skip_forward(seconds=10)

    def handle_skip_backward(self):
        if current := self.stack.get_visible_child():
            current.skip_backward(seconds=10)

    def switch_relative_player(self, forward=True):
        if not self.players:
            return

        current_player = self.stack.get_visible_child()
        current_index = self.players.index(current_player)

        next_index = (current_index + (1 if forward else -1)) % len(self.players)
        next_player = self.players[next_index]

        for btn in self.player_switch_container.center_children:
            if btn.get_name() == next_player.get_name():
                self.switch_player(next_player.get_name(), btn)
                break
