from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from fabric.utils.helpers import exec_shell_command_async

from services.player_service import PlayerManager, PlayerService
from modules.wiggle_bar import WigglyWidget

import icons.icons as icons
import config.info as info

from loguru import logger
import urllib.parse, urllib.request
import os, tempfile
import hashlib, pathlib
from pathlib import Path
import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk


class Player(Box):
    def __init__(self, player, **kwargs):
        super().__init__(style_classes="player", orientation="v", **kwargs)

        if not info.VERTICAL:
            self.remove_style_class(
                "vertical"
            )  # vertical class binding from unknown source

        self._player = PlayerService(player=player)

        self.duration = 0.0

        self._player.connect("pause", self.on_pause)
        self._player.connect("play", self.on_play)
        self._player.connect("meta-change", self.on_metadata)
        self._player.connect("shuffle-toggle", self.on_shuffle)
        self._player.connect("track-position", self.on_update_track_position)

        self.player_name = Label(
            name=player.props.player_name,
            style_classes="player-icon",
            markup=getattr(icons, player.props.player_name, icons.disc),
        )

        GLib.idle_add(
            lambda: (
                self.set_style(
                    f"background-image:url('{info.HOME_DIR}/.cache/walls/low_rez.png')"
                )
            )
        )
        # self.set_style(
        #     f"background-image:url('{info.HOME_DIR}/.cache/walls/low_rez.png')"
        # )

        self.song = Label(
            name="song",
            label="song",
            justification="left",
            h_align="start",
            max_chars_width=10,
        )
        self.artist = Label(
            name="artist", label="artist", justification="left", h_align="start"
        )
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
            on_clicked=lambda b, *_: self.handle_play_pause(player),
        )

        self.shuffle_button = Button(
            name="shuffle-button",
            child=Label(name="shuffle", markup=icons.shuffle),
            on_clicked=lambda b, *_: self.handle_shuffle(b, player),
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
            Box(name="source", h_expand=True, v_expand=True, children=self.player_name),
            CenterBox(
                name="details",
                start_children=self.music,
                end_children=self.play_pause_button if not info.VERTICAL else [],
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
                            on_clicked=lambda b, *_: self.handle_prev(player),
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
                            on_clicked=lambda b, *_: self.handle_next(player),
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
                                            on_clicked=lambda b, *_: self.handle_prev(
                                                player
                                            ),
                                        ),
                                        Button(
                                            name="next-button",
                                            child=Label(
                                                name="play-next", markup=icons.next
                                            ),
                                            on_clicked=lambda b, *_: self.handle_next(
                                                player
                                            ),
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

        self.on_metadata(self._player, metadata=player.props.metadata, player=player)

    def on_update_track_position(self, sender, pos, dur):
        if dur == 0:
            return
        self.duration = dur
        self.wiggly.update_value_from_signal(pos / dur)

    def on_seek(self, sender, ratio):
        pos = ratio * self.duration  # duration in seconds
        print(f"Seeking to {pos:.2f}s")
        self._player.set_position(int(pos))

    def skip_forward(self, seconds=10):
        self._player._player.seek(seconds * 1000000)

    def skip_backward(self, seconds=10):
        self._player._player.seek(-1 * seconds * 1000000)

    def on_metadata(self, sender, metadata, player):
        keys = metadata.keys()
        if "xesam:artist" in keys and "xesam:title" in keys:
            _max_chars = 33 if not info.VERTICAL else 30
            song_title = metadata["xesam:title"]
            if len(song_title) > _max_chars:
                song_title = song_title[: _max_chars - 1] + "…"
            self.song.set_label(song_title)

            artist_list = metadata["xesam:artist"]
            artist_name = artist_list[0] if artist_list else "Unknown Artist"
            if len(artist_name) > _max_chars:
                artist_name = artist_name[: _max_chars - 1] + "…"
            self.artist.set_label(artist_name)
            if "mpris:artUrl" in keys:
                art_url = metadata["mpris:artUrl"]
                import threading

                def _set_album_art(art_url):
                    GLib.idle_add(
                        lambda: (self.set_style(f"background-image:url('{art_url}')"))
                    )

                threading.Thread(
                    target=_set_album_art, args=(art_url,), daemon=True
                ).start()

                self.set_style(f"background-image:url('{art_url}')")
                parsed = urllib.parse.urlparse(art_url)
                if parsed.scheme == "file":
                    local_art_url = urllib.parse.unquote(parsed.path)
                    import subprocess

                    result = subprocess.run(
                        [
                            "matugen",
                            "image",
                            parsed.path,
                            "-c",
                            "/home/aman/fabric/config/matugen/player_runtime.toml",
                            "-j",
                            "hex",
                        ],
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        print("Matugen error:", result.stderr)
                    else:
                        import json

                        # try:
                        theme_json = json.loads(result.stdout)
                        self.play_pause_button.set_style(
                            f"background-color: {(theme_json['colors']['dark']['primary'])}"
                        )
                        self.player_name.set_style(
                            f"color: {(theme_json['colors']['dark']['primary'])}"
                        )
                        # except json.JSONDecodeError as e:
                        #     print("Failed to parse JSON:", e)
                        #     print("Raw output:", result.stdout)
                    # exec_shell_command(
                    #     f"matugen image {local_art_url} -c {info.HOME_DIR}/fabric/config/matugen/player_config.toml"
                    # )
                elif parsed.scheme in ("http", "https"):
                    GLib.Thread.new(
                        "download-artwork", self._download_and_set_artwork, art_url
                    )
                print(metadata["mpris:artUrl"], "======")

        if (
            player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        ):
            self.on_play(self._player)

        if player.props.shuffle == True:
            self.shuffle_button.get_child().set_markup(icons.disable_shuffle)
            self.shuffle_button.get_child().set_name("disable-shuffle")
        else:
            self.shuffle_button.get_child().set_markup(icons.shuffle)
            self.shuffle_button.get_child().set_name("shuffle")

    def _download_and_set_artwork(self, art_url):
        cache_dir = Path("/tmp/zenith_player")
        cache_dir.mkdir(parents=True, exist_ok=True)

        parsed = urllib.parse.urlparse(art_url)
        suffix = os.path.splitext(parsed.path)[1] or ".png"
        filename_hash = hashlib.md5(art_url.encode()).hexdigest()
        local_arturl = cache_dir / f"{filename_hash}{suffix}"

        if not local_arturl.exists():
            with urllib.request.urlopen(art_url) as response:
                data = response.read()

            with open(local_arturl, "wb") as f:
                f.write(data)

            print(local_arturl, "downloaded artwork for matugen")
        else:
            print(local_arturl, "already cached, skipping download")

        exec_shell_command_async(
            f"matugen image {local_arturl} -c {info.HOME_DIR}/fabric/config/matugen/player_config.toml"
        )

    def on_pause(self, sender):
        self.play_pause_button.get_child().set_markup(icons.play)
        self.play_pause_button.get_child().set_name("pause-label")
        self.wiggly.dragging = True
        self.wiggly.update_amplitude(True)
        self.wiggly.pause = True
        self.play_pause_button.add_style_class("pause-track")

    def on_play(self, sender):
        self.play_pause_button.get_child().set_markup(icons.pause)
        self.play_pause_button.get_child().set_name("play-label")
        self.wiggly.pause = False
        self.wiggly.dragging = False
        self.wiggly.update_amplitude(False)
        self.play_pause_button.remove_style_class("pause-track")

    def on_shuffle(self, sender, player, status):
        print("callback status", status)
        if status == False:
            self.shuffle_button.get_child().set_markup(icons.shuffle)
            self.shuffle_button.get_child().set_name("shuffle")
        else:
            self.shuffle_button.get_child().set_markup(icons.disable_shuffle)
            self.shuffle_button.get_child().set_name("disable-shuffle")

        self.shuffle_button.get_child().set_style("color: white")

    def handle_next(self, player):
        self._player._player.next()

    def handle_prev(self, player):
        self._player._player.previous()

    def handle_play_pause(self, player):
        is_playing = (
            self._player._player.props.playback_status.value_name
            == "PLAYERCTL_PLAYBACK_STATUS_PLAYING"
        )

        def _set_play_ui():
            self.play_pause_button.get_child().set_markup(icons.pause)
            self.play_pause_button.remove_style_class("pause-track")
            self.play_pause_button.get_child().set_name("pause-label")

        def _set_pause_ui():
            self.play_pause_button.get_child().set_markup(icons.play)
            self.play_pause_button.add_style_class("pause-track")
            self.play_pause_button.get_child().set_name("play-label")

        if is_playing:
            _set_pause_ui()
        else:
            _set_play_ui()

        try:
            self._player._player.play_pause()
        except Exception as e:
            # revert if signal failed
            if is_playing:
                _set_pause_ui()
            else:
                _set_play_ui()
            logger.warning("Failed to toggle playback:", e)

    def handle_shuffle(self, shuffle_button, player):
        print("shuffle", player.props.shuffle)
        if player.props.shuffle == False:
            player.set_shuffle(True)
            print("setting to true", player.props.player_name)
        else:
            player.set_shuffle(False)
        shuffle_button.get_child().set_style("color: var(--outline)")


class Placheholder(Box):
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

        self.placeholder_player = Placheholder()
        self.stack = Stack(
            name="player-container",
            transition_type="crossfade",
            transition_duration=100,
            children=[self.placeholder_player],
        )

        self.player_stack = Stack(
            name="player-stack",
            transition_type="crossfade",
            transition_duration=100,
            children=[],
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
        print(player)
        new_player = Player(player=player)
        new_player.wiggly_bar.queue_draw()
        new_player.set_name(player.props.player_name)
        self.players.append(new_player)
        print("stacking", player.props.player_name)
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
        self.window.add_keybinding("p", lambda *_: self.handle_play_pause())
        self.window.add_keybinding("j", lambda *_: self.handle_prev())
        self.window.add_keybinding("k", lambda *_: self.handle_skip_backward())
        self.window.add_keybinding("l", lambda *_: self.handle_skip_forward())
        self.window.add_keybinding("semicolon", lambda *_: self.handle_next())
        self.window.add_keybinding("Tab", lambda *_: self.switch_relative_player(True))
        self.window.add_keybinding(
            "Shift ISO_Left_Tab", lambda *_: self.switch_relative_player(False)
        )

    def unregister_keybindings(self):
        self.window.remove_keybinding("p")
        self.window.remove_keybinding("j")
        self.window.remove_keybinding("k")
        self.window.remove_keybinding("l")
        self.window.remove_keybinding("semicolon")
        self.window.remove_keybinding("Tab")
        self.window.remove_keybinding("Shift ISO_Left_Tab")

    def handle_play_pause(self):
        if current := self.stack.get_visible_child():
            current.handle_play_pause(current._player)

    def handle_prev(self):
        if current := self.stack.get_visible_child():
            current.handle_prev(current._player)

    def handle_next(self):
        if current := self.stack.get_visible_child():
            current.handle_next(current._player)

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
