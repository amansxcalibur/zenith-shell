from fabric.utils import bulk_connect
from fabric.core.service import Service, Signal
from fabric import Fabricator

from config.info import ALLOWED_PLAYERS, CACHE_DIR, HOME_DIR

import urllib.parse, urllib.request
import os
import hashlib
import subprocess
import json
from pathlib import Path
import gi

gi.require_version("Playerctl", "2.0")
from gi.repository import Playerctl, GLib


class PlayerService(Service):

    @Signal
    def shuffle_toggle(self, player: Playerctl.Player, status: bool) -> None: ...

    @Signal
    def meta_change(self, metadata: GLib.Variant, player: Playerctl.Player) -> None: ...

    @Signal
    def artwork_change(self, local_path: str) -> None: ...

    @Signal
    def theme_change(self, theme_json: object) -> None: ...

    @Signal
    def pause(self) -> None: ...

    @Signal
    def play(self) -> None: ...

    @Signal
    def track_position(self, pos: float, dur: float) -> None: ...

    def __init__(self, player: Playerctl.Player, **kwargs):
        self._player: Playerctl.Player = player
        self._current_artwork_hash = ""
        self._current_theme = None
        self._current_artwork_path = ""
        self._theme_cache = {}
        super().__init__(**kwargs)
        if player.props.player_name in ALLOWED_PLAYERS:
            self._player.connect("playback-status::playing", self.on_play)
            self._player.connect("playback-status::paused", self.on_pause)
            self._player.connect("shuffle", self.on_shuffle)
            self._player.connect("metadata", self.on_metadata)
            self._player.connect("seeked", self.on_seeked)
            print(type(player))

        self.status = self._player.props.playback_status
        self.pos_fabricator = Fabricator(
            interval=1000,  # 1s
            poll_from=lambda f, *_: self._player.get_position(),
            on_changed=lambda f, *_: self.fabricating(),
        )
        self.poll_progress()
        try:
            metadata = self._player.props.metadata
            self.meta_change(metadata, self._player)
            self._handle_artwork(metadata, metadata.keys())
        except Exception:
            pass

    def on_seeked(self, player, position):
        if self.status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING":
            self.pos_fabricator.start()

    def get_artwork(self):
        return self._current_artwork_path
        
    def get_theme(self):
        return self._current_theme

    def set_position(self, pos: float):
        print("seeking in the service")
        self.pos_fabricator.stop()
        micro_pos = int(pos * 1_000_000)
        try:
            self._player.set_position(micro_pos)
            print(f"Set position to {micro_pos}")
        except GLib.Error as e:
            print(f"Failed to seek: {e}")

    def poll_progress(self):
        if self.status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING":
            self.pos_fabricator.start()
        else:
            self.pos_fabricator.stop()

    def fabricating(self):
        pos = self._player.get_position() / 1_000_000  # seconds
        dur = self._player.props.metadata["mpris:length"] / 1_000_000  # seconds
        # print(self._player.get_position())
        # print(f"[progress] {pos:.2f}s / {dur:.2f}s")
        self.track_position(pos, dur)

    def on_play(self, player, status):
        print("player is playing: {}".format(player.props.player_name))
        self.status = player.props.playback_status
        self.poll_progress()
        self.play()

    def on_pause(self, player, status):
        print("player is paused: {}".format(player.props.player_name))
        self.status = player.props.playback_status
        self.poll_progress()
        self.pause()

    def on_shuffle(self, player, status):
        print("suffle status changed for: {}".format(player.props.player_name))
        print(type(status), "here is the status type")
        self.shuffle_toggle(player, status)

    def on_metadata(self, player, metadata):
        keys = metadata.keys()
        if "xesam:artist" in keys and "xesam:title" in keys:
            print(
                "{} - {}".format(metadata["xesam:artist"][0], metadata["xesam:title"])
            )
        self.meta_change(metadata, player)
        self._handle_artwork(metadata, keys)

    def _handle_artwork(self, metadata, keys):
        if "mpris:artUrl" not in keys:
            return

        art_url = metadata["mpris:artUrl"]

        artwork_hash = hashlib.md5(art_url.encode()).hexdigest()
        if artwork_hash == self._current_artwork_hash:
            print("Artwork unchanged, skipping processing")
            return

        self._current_artwork_hash = artwork_hash
        print(f"Processing new artwork: {art_url}")

        parsed = urllib.parse.urlparse(art_url)

        if parsed.scheme == "file":
            self._process_local_artwork(parsed.path, artwork_hash)
        elif parsed.scheme in ("http", "https"):
            GLib.Thread.new(
                "download-artwork",
                self._download_and_process_artwork,
                art_url,
                artwork_hash,
            )

    def _process_local_artwork(self, art_url, artwork_hash):
        # signal artwork change
        self._current_artwork_path = art_url
        self.artwork_change(art_url)

        if artwork_hash in self._theme_cache:
            print("Using cached theme colors")
            # signal cached theme
            self._current_theme = self._theme_cache[artwork_hash]
            self.theme_change(self._theme_cache[artwork_hash])
            return

        try:
            result = subprocess.run(
                [
                    "matugen",
                    "image",
                    art_url,
                    "-c",
                    f"{HOME_DIR}/fabric/config/matugen/player_runtime.toml",
                    "-j",
                    "hex",
                    "-t",
                    "scheme-fidelity"
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                try:
                    theme_json = json.loads(result.stdout)
                    self._theme_cache[artwork_hash] = theme_json
                    # signal new theme change
                    self._current_theme = theme_json
                    self.theme_change(theme_json)

                except (json.JSONDecodeError, KeyError) as e:
                    print(f"Failed to parse color theme: {e}")
            else:
                print(f"Matugen error: {result.stderr}")
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            print(f"Matugen process failed: {e}")

    def _download_and_process_artwork(self, art_url, artwork_hash):
        try:
            cache_dir = Path(f"{CACHE_DIR}/zenith_player")
            cache_dir.mkdir(parents=True, exist_ok=True)

            parsed = urllib.parse.urlparse(art_url)
            suffix = os.path.splitext(parsed.path)[1] or ".png"
            filename_hash = hashlib.md5(art_url.encode()).hexdigest()
            local_arturl = cache_dir / f"{filename_hash}{suffix}"

            if not local_arturl.exists():
                with urllib.request.urlopen(art_url, timeout=10) as response:
                    data = response.read()
                with open(local_arturl, "wb") as f:
                    f.write(data)
                print(f"Downloaded artwork: {local_arturl}")
            else:
                print(f"Using cached artwork: {local_arturl}")

            self._process_local_artwork(local_arturl, artwork_hash)

            # legacy reference
            # exec_shell_command_async(
            #     f"matugen image {local_arturl} -c {info.HOME_DIR}/fabric/config/matugen/player_config.toml"
            # )
        except Exception as e:
            print(f"Failed to download/process artwork: {e}")


class PlayerManager(Service):

    @Signal
    def new_player(self, player: Playerctl.Player) -> Playerctl.Player: ...

    @Signal
    def player_vanish(self, player: Playerctl.Player) -> None: ...

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._manager = Playerctl.PlayerManager()
        self._manager.connect("name-appeared", self._on_name_appeared, self._manager)
        self._manager.connect(
            "player-vanished", self._on_player_vanished, self._manager
        )
        print("playerctl init done")

        self._players = {}

    def init_all_players(self):
        # invoked in the UI
        for player_obj in self._manager.props.player_names:
            name_str = player_obj.name
            print(f"{name_str} appeared")
            if name_str in ALLOWED_PLAYERS:
                player = Playerctl.Player.new_from_name(player_obj)
                self._manager.manage_player(player)
                self.new_player(player)

    def _on_name_appeared(self, sender, name, manager):
        name_str = name.name
        print(f"{name_str} appeared")
        if name_str in ALLOWED_PLAYERS:
            player = Playerctl.Player.new_from_name(name)
            self._manager.manage_player(player)
            self.new_player(player)

    def _on_player_vanished(self, sender, player, manager):
        print("player has exited: {}".format(player.props.player_name))
        print(type(player))
        self.player_vanish(player)
