from fabric.core.service import Service, Signal
from fabric import Fabricator

from config.info import config, TEMP_DIR, ROOT_DIR

import json
import hashlib
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from loguru import logger

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
        super().__init__(**kwargs)
        self._player: Playerctl.Player = player
        self._current_artwork_hash = ""
        self._current_theme = None
        self._current_artwork_path = ""
        self._theme_cache = {}
        self._is_cleaning_up = False
        self._signal_ids = []  # track signal connection IDs

        if player.props.player_name in config.ALLOWED_PLAYERS:
            # store signal IDs for proper disconnection
            self._signal_ids.append(
                self._player.connect("playback-status::playing", self.on_play)
            )
            self._signal_ids.append(
                self._player.connect("playback-status::paused", self.on_pause)
            )
            self._signal_ids.append(self._player.connect("shuffle", self.on_shuffle))
            self._signal_ids.append(self._player.connect("metadata", self.on_metadata))
            self._signal_ids.append(self._player.connect("seeked", self.on_seeked))
            logger.info(
                f"Connected {len(self._signal_ids)} signals for {player.props.player_name}"
            )

        self.status = self._player.props.playback_status
        self.pos_fabricator = Fabricator(
            interval=1000,  # 1s
            poll_from=lambda f, *_: self.get_position(),
            on_changed=lambda f, *_: self.fabricating(),
        )
        self.poll_progress()

        try:
            metadata = self._player.props.metadata
            if metadata:
                self.meta_change(metadata, self._player)
                self._handle_artwork(metadata, metadata.keys())
        except Exception as e:
            logger.warning(f"Failed to initialize metadata: {e}")

    def on_seeked(self, player, position):
        if self._is_cleaning_up:
            return
        if self.status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING":
            self.pos_fabricator.start()

    def get_artwork(self):
        return self._current_artwork_path

    def get_theme(self):
        return self._current_theme

    def get_position(self):
        if self._is_cleaning_up:
            return 0
        try:
            position = self._player.get_position()
        except Exception as e:
            logger.warning(f"Could not get position: {e}")
            position = 0
        return position

    def set_position(self, pos: float):
        if self._is_cleaning_up:
            return
        logger.debug("Seeking in the service")
        self.pos_fabricator.stop()
        micro_pos = int(pos * 1_000_000)
        try:
            self._player.set_position(micro_pos)
            logger.debug(f"Set position to {micro_pos}")
        except GLib.Error as e:
            logger.error(f"Failed to seek: {e}")

    def poll_progress(self):
        if self._is_cleaning_up:
            return
        if self.status.value_name == "PLAYERCTL_PLAYBACK_STATUS_PLAYING":
            self.pos_fabricator.start()
        else:
            self.pos_fabricator.stop()

    def fabricating(self):
        if self._is_cleaning_up:
            return
        try:
            pos = self._player.get_position() / 1_000_000  # seconds
            keys = self._player.props.metadata.keys()
            if "mpris:length" in keys:
                dur = self._player.props.metadata["mpris:length"] / 1_000_000  # seconds
            else:
                dur = 0
            self.track_position(pos, dur)
        except GLib.Error as e:
            logger.warning(f"Failed to get position in fabricating: {e}")

    def on_play(self, player, status):
        if self._is_cleaning_up:
            return
        logger.debug(f"Player is playing: {player.props.player_name}")
        self.status = player.props.playback_status
        self.poll_progress()
        self.play()

    def on_pause(self, player, status):
        if self._is_cleaning_up:
            return
        logger.debug(f"Player is paused: {player.props.player_name}")
        self.status = player.props.playback_status
        self.poll_progress()
        self.pause()

    def on_shuffle(self, player, status):
        if self._is_cleaning_up:
            return
        logger.debug(f"Shuffle status changed for: {player.props.player_name}")
        self.shuffle_toggle(player, status)

    def on_metadata(self, player, metadata):
        if self._is_cleaning_up:
            return
        keys = metadata.keys()
        if "xesam:artist" in keys and "xesam:title" in keys:
            logger.info(f"{metadata['xesam:artist'][0]} - {metadata['xesam:title']}")
        self.meta_change(metadata, player)
        self._handle_artwork(metadata, keys)

    def _handle_artwork(self, metadata, keys):
        if self._is_cleaning_up:
            return
        if "mpris:artUrl" not in keys:
            return

        art_url = metadata["mpris:artUrl"]
        artwork_hash = hashlib.md5(art_url.encode()).hexdigest()

        if artwork_hash == self._current_artwork_hash:
            logger.debug("Artwork unchanged, skipping processing")
            return

        self._current_artwork_hash = artwork_hash
        logger.info(f"Processing new artwork: {art_url}")

        parsed = urllib.parse.urlparse(art_url)

        if parsed.scheme == "file":
            self._process_local_artwork(urllib.parse.unquote(parsed.path), artwork_hash)
        elif parsed.scheme in ("http", "https"):
            GLib.Thread.new(
                "download-artwork",
                self._download_and_process_artwork,
                art_url,
                artwork_hash,
            )

    def _process_local_artwork(self, art_url, artwork_hash):
        if self._is_cleaning_up:
            return

        # signal artwork change
        self._current_artwork_path = art_url
        self.artwork_change(self._current_artwork_path)

        if artwork_hash in self._theme_cache:
            logger.debug("Using cached theme colors")
            self._current_theme = self._theme_cache[artwork_hash]
            # signal cached theme
            self.theme_change(self._theme_cache[artwork_hash])
            return

        try:
            result = subprocess.run(
                [
                    "matugen",
                    "image",
                    self._current_artwork_path,
                    "-c",
                    f"{ROOT_DIR}/config/matugen/player_runtime.toml",
                    "-j",
                    "hex",
                    "-t",
                    "scheme-fidelity",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,  # to handle paths with spaces
            )

            if result.returncode == 0:
                try:
                    theme_json = json.loads(result.stdout)
                    self._theme_cache[artwork_hash] = theme_json
                    self._current_theme = theme_json
                    self.theme_change(theme_json)
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Failed to parse color theme: {e}")
            else:
                logger.error(f"Matugen error: {result.stderr}")
        except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
            logger.error(f"Matugen process failed: {e}")

    def _download_and_process_artwork(self, art_url, artwork_hash):
        if self._is_cleaning_up:
            return

        try:
            cache_dir = Path(TEMP_DIR) / "player-art"
            cache_dir.mkdir(parents=True, exist_ok=True)

            parsed = urllib.parse.urlparse(art_url)
            suffix = Path(parsed.path).suffix or ".png"
            filename_hash = hashlib.md5(art_url.encode()).hexdigest()
            local_arturl = cache_dir / f"{filename_hash}{suffix}"

            if not local_arturl.exists():
                with urllib.request.urlopen(art_url, timeout=5) as response:
                    data = response.read()

                temp_file = local_arturl.with_suffix(".tmp")
                temp_file.write_bytes(data)
                temp_file.replace(local_arturl)

                logger.info(f"Downloaded artwork: {local_arturl}")
            else:
                logger.debug(f"Using cached artwork: {local_arturl}")

            self._process_local_artwork(str(local_arturl), artwork_hash)

            # legacy reference
            # exec_shell_command_async(
            #     f"matugen image {local_arturl} -c {info.HOME_DIR}/fabric/config/matugen/player_config.toml"
            # )

        except Exception as e:
            logger.error(f"Failed to download/process artwork: {e}")

    def cleanup(self):
        """Stop all background tasks and disconnect signals"""
        if self._is_cleaning_up:
            logger.warning(
                f"Cleanup already in progress for {self._player.props.player_name}"
            )
            return

        self._is_cleaning_up = True
        logger.info(f"Cleaning up PlayerService for {self._player.props.player_name}")

        # stop the fabricator
        try:
            if hasattr(self, "pos_fabricator") and self.pos_fabricator:
                logger.debug("Stopping fabricator")
                self.pos_fabricator.stop()
        except Exception as e:
            logger.error(f"Error stopping fabricator: {e}")

        # disconnect signals using stored IDs
        if self._signal_ids:
            logger.debug(f"Disconnecting {len(self._signal_ids)} signals")
            for signal_id in self._signal_ids:
                try:
                    self._player.disconnect(signal_id)
                except Exception as e:
                    logger.warning(f"Error disconnecting signal {signal_id}: {e}")
            self._signal_ids.clear()

        # clear caches
        self._theme_cache.clear()
        self._current_artwork_path = ""
        self._current_theme = None

        logger.info(f"Cleanup complete for {self._player.props.player_name}")


class PlayerManager(Service):
    _instance = None

    @Signal
    def new_player(self, player_name: str, service: PlayerService) -> None: ...

    @Signal
    def player_vanish(self, player_name: str) -> None: ...

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            logger.debug("Creating Singeton")
            cls._instance._init_singleton()
        else:
            logger.debug("Sharing Singeton")
        return cls._instance

    def _init_singleton(self):
        super().__init__()
        self._manager = Playerctl.PlayerManager()
        self._services = {}  # map player_name -> PlayerService
        self._player_objects = {}  # map player_name -> Playerctl.Player

        self._manager.connect("name-appeared", self._on_name_appeared, self._manager)
        self._manager.connect(
            "player-vanished", self._on_player_vanished, self._manager
        )
        self.init_all_players()
        logger.info("PlayerManager initialized")

    def init_all_players(self):
        logger.info("Initializing all existing players")
        for player_obj in self._manager.props.player_names:
            name_str = player_obj.name
            if name_str in config.ALLOWED_PLAYERS:
                logger.info(f"Initializing existing player: {name_str}")
                self._create_and_register_player(player_obj)

    def _create_and_register_player(self, name_obj):
        """Create PlayerService and register it"""
        name_str = name_obj.name

        # avoid duplicate registration
        if name_str in self._services:
            logger.warning(f"Player {name_str} already registered, skipping")
            return

        try:
            player = Playerctl.Player.new_from_name(name_obj)
            self._manager.manage_player(player)

            # create service instance
            player_service = PlayerService(player)

            # store references
            self._services[name_str] = player_service
            self._player_objects[name_str] = player

            logger.info(f"Registered player service for {name_str}")
            # emit signal
            self.new_player(name_str, player_service)

        except Exception as e:
            logger.error(f"Failed to create player service for {name_str}: {e}")

    def _on_name_appeared(self, sender, name, manager):
        name_str = name.name
        logger.info(f"Player appeared: {name_str}")

        if name_str in config.ALLOWED_PLAYERS:
            self._create_and_register_player(name)
        else:
            logger.debug(f"Player {name_str} not in allowed list")

    def _on_player_vanished(self, sender, player, manager):
        player_name = player.props.player_name
        logger.info(f"Player vanished: {player_name}")

        # clean up the service
        if player_name in self._services:
            try:
                player_service = self._services[player_name]
                player_service.cleanup()
                del self._services[player_name]
                logger.info(f"Cleaned up service for {player_name}")
            except Exception as e:
                logger.error(f"Error cleaning up service for {player_name}: {e}")

        # remove player object reference
        if player_name in self._player_objects:
            del self._player_objects[player_name]

        # emit signal
        self.player_vanish(player_name)

    def get_player_service(self, player_name: str) -> PlayerService | None:
        return self._services.get(player_name)

    def get_all_services(self) -> dict[str, PlayerService]:
        return self._services.copy()

    def cleanup_all(self):
        logger.info("Cleaning up all players")
        for player_name, service in list(self._services.items()):
            try:
                service.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up {player_name}: {e}")

        self._services.clear()
        self._player_objects.clear()
        logger.info("All players cleaned up")
