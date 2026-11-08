import json
import hashlib
import mimetypes
import shutil
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from loguru import logger
from PIL import Image, ImageFilter, ImageOps

from fabric.core.service import Service, Signal, Property

from config.config import config
from config.info import TEMP_DIR

import gi

gi.require_version("Playerctl", "2.0")
from gi.repository import Playerctl, GLib, Gio  # type: ignore


PROPERTY_QUERY_TIMEOUT_MS = 1000
POSITION_POLL_INTERVAL_MS = 1000
SEEK_SETTLE_MS = 2000  # how long a player gets to apply a seek before polling resumes


def get_player_property(bus_name, prop, on_result):
    if not bus_name:
        on_result(None)
        return

    if not bus_name.startswith("org.mpris.MediaPlayer2."):
        bus_name = f"org.mpris.MediaPlayer2.{bus_name}"

    if not Gio.dbus_is_name(bus_name):
        on_result(None)
        return

    def on_reply(connection, result, *_):
        try:
            value = connection.call_finish(result).unpack()[0]
        except GLib.Error:
            value = None
        on_result(value)

    # setup D-Bus proxy
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)

    # call 'Get' on the standard Properties interface
    # Param 1: interface name ('org.mpris.MediaPlayer2.Player')
    # Param 2: property name
    params = GLib.Variant("(ss)", ("org.mpris.MediaPlayer2.Player", prop))

    connection.call(
        bus_name,
        "/org/mpris/MediaPlayer2",
        "org.freedesktop.DBus.Properties",
        "Get",
        params,
        None,
        Gio.DBusCallFlags.NONE,
        PROPERTY_QUERY_TIMEOUT_MS,
        None,
        on_reply,
    )


def get_track_labels(metadata) -> tuple[str, str]:
    keys = metadata.keys()
    title = metadata["xesam:title"] if "xesam:title" in keys else ""
    artists = metadata["xesam:artist"] if "xesam:artist" in keys else []
    return title or "Unknown Title", artists[0] if artists else "Unknown Artist"


class PlayerService(Service):
    @Signal
    def shuffle_toggle(self, player: Playerctl.Player, status: bool) -> None: ...

    @Signal
    def meta_change(self, metadata: GLib.Variant, player: Playerctl.Player) -> None: ...

    @Signal
    def artwork_change(self, local_path: str, blurred_local_path: str) -> None: ...

    @Signal
    def theme_change(self, theme_json: object) -> None: ...

    @Signal
    def pause(self) -> None: ...

    @Signal
    def play(self) -> None: ...

    @Signal
    def track_position(self, pos: float, dur: float) -> None: ...

    @Property(bool, "readable", default_value=False)
    def can_go_previous(self) -> bool:
        return self._player.get_property("can_go_previous")

    @Property(bool, "readable", default_value=False)
    def can_go_next(self) -> bool:
        return self._player.get_property("can_go_next")

    @Property(bool, "readable", default_value=False)
    def can_pause(self) -> bool:
        return self._player.get_property("can_pause")

    @Property(bool, "readable", default_value=False)
    def can_play(self) -> bool:
        return self._player.get_property("can_play")

    @Property(bool, "readable", default_value=False)
    def can_seek(self) -> bool:
        return self._player.get_property("can_seek")

    @Property(bool, "readable", default_value=False)
    def can_control(self) -> bool:
        return self._player.get_property("can_control")

    @Property(bool, "readable", default_value=False)
    def can_shuffle(self) -> bool:
        return self._can_shuffle

    def __init__(self, player: Playerctl.Player, **kwargs):
        super().__init__(**kwargs)
        self._player: Playerctl.Player = player
        self._can_shuffle = False
        self._poll_source_id = None
        self._latest_position_query = 0  # replies to older queries are out of date
        self._duration_track = None
        self._duration = 0.0
        self._current_artwork_hash = ""
        self._current_theme = None
        self._current_artwork_path = ""
        self._current_blurred_artwork_path = ""
        self._theme_cache = {}
        self._is_cleaning_up = False
        self._signal_ids = []  # track signal connection IDs

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
        self.poll_progress()
        self._refresh_can_shuffle()

        try:
            metadata = self._player.props.metadata
            if metadata:
                self.meta_change(metadata, self._player)
                self._handle_artwork(metadata, metadata.keys())
        except Exception as e:
            logger.warning(f"Failed to initialize metadata: {e}")

    def on_seeked(self, player, position):
        self._stop_polling()
        self.fabricating()
        self.poll_progress()

    def _refresh_can_shuffle(self):
        get_player_property(
            self._player.get_property("player_instance"),
            "Shuffle",
            self._on_shuffle_support,
        )

    def _on_shuffle_support(self, shuffle):
        can_shuffle = shuffle is not None
        if self._is_cleaning_up or can_shuffle == self._can_shuffle:
            return
        self._can_shuffle = can_shuffle
        self.notify("can-shuffle")

    def get_artwork(self) -> str:
        return self._current_artwork_path

    def get_blurred_240x60_artwork(self) -> str:
        return self._current_blurred_artwork_path

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

    def get_duration(self) -> float:
        """Length of the current track in seconds, 0 if the player doesn't report one."""
        metadata = self._player.props.metadata
        keys = metadata.keys() if metadata else []
        track = get_track_labels(metadata) if keys else None
        if track != self._duration_track:
            self._duration_track = track
            self._duration = 0.0
        # Firefox drops the length after a seek, keep it until the track changes
        if "mpris:length" in keys:
            self._duration = metadata["mpris:length"] / 1_000_000
        return self._duration

    def _is_length_missing(self) -> bool:
        metadata = self._player.props.metadata
        return not metadata or "mpris:length" not in metadata.keys()  # noqa: SIM118 its a GLib.Variant

    def set_position(self, pos: float):
        if self._is_cleaning_up:
            return
        logger.debug("Seeking in the service")
        # no reads until the player reports the seek, not every player does though
        self._latest_position_query += 1
        self._stop_polling()
        micro_pos = int(pos * 1_000_000)
        try:
            self._player.set_position(micro_pos)
            logger.debug(f"Set position to {micro_pos}")
        except GLib.Error as e:
            logger.error(f"Failed to seek: {e}")
        self._poll_source_id = GLib.timeout_add(SEEK_SETTLE_MS, self._on_seek_settled)

    def _on_seek_settled(self):
        self._poll_source_id = None
        self.fabricating()
        self.poll_progress()
        return False

    def poll_progress(self):
        if self._is_cleaning_up:
            return
        if self.status.value_name != "PLAYERCTL_PLAYBACK_STATUS_PLAYING":
            self._stop_polling()
        elif self._poll_source_id is None:
            self._poll_source_id = GLib.timeout_add(
                POSITION_POLL_INTERVAL_MS, self._on_poll
            )

    def _stop_polling(self):
        if self._poll_source_id is not None:
            GLib.source_remove(self._poll_source_id)
            self._poll_source_id = None

    def _on_poll(self):
        self.fabricating()
        return True

    def fabricating(self):
        if self._is_cleaning_up:
            return
        self._latest_position_query += 1
        query = self._latest_position_query
        get_player_property(
            self._player.get_property("player_instance"),
            "Position",
            lambda position: self._on_position(query, position),
        )

    def _on_position(self, query, position):
        if self._is_cleaning_up or query != self._latest_position_query:
            return
        if position is None:
            logger.debug("Player did not report a position")
            return
        duration = self.get_duration()
        # Firefox also reports a position of 0 for as long as the length is gone
        if duration and self._is_length_missing():
            logger.debug("Ignoring position from a player that lost its track length")
            return
        self.track_position(position / 1_000_000, duration)  # seconds

    def on_play(self, player, status):
        if self._is_cleaning_up:
            return
        logger.debug(f"Player is playing: {player.props.player_name}")
        self.status = player.props.playback_status
        self.fabricating()
        self.poll_progress()
        self.play()

    def on_pause(self, player, status):
        if self._is_cleaning_up:
            return
        logger.debug(f"Player is paused: {player.props.player_name}")
        self.status = player.props.playback_status
        self.fabricating()
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
        title, artist = get_track_labels(metadata)
        logger.info(f"{artist} - {title}")
        self._refresh_can_shuffle()
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
            GLib.Thread.new(
                "process-artwork",
                self._process_local_artwork,
                urllib.parse.unquote(parsed.path),
                artwork_hash,
            )
        elif parsed.scheme in ("http", "https"):
            GLib.Thread.new(
                "download-artwork",
                self._download_and_process_artwork,
                art_url,
                artwork_hash,
            )

    def _blur_image(self, source_path: Path, destination_path: Path, radius: int = 20):
        try:
            logger.debug(f"Blurring and resizing image to: {destination_path}")
            with Image.open(source_path) as img:
                # convert to RGB if it's RGBA to avoid transparency issues
                if img.mode in ("RGBA", "LA"):
                    img = img.convert("RGB")

                # blur effect
                processed_img = img.filter(ImageFilter.GaussianBlur(radius=radius))

                # fit, crop from center, scale to 240x60
                target_size = (240, 60)
                processed_img = ImageOps.fit(
                    processed_img, target_size, centering=(0.5, 0.5)
                )
                processed_img.save(destination_path)

        except Exception as e:
            logger.error(f"Failed to blur and resize image: {e}")

    def _is_artwork_stale(self, artwork_hash) -> bool:
        return self._is_cleaning_up or artwork_hash != self._current_artwork_hash

    def _with_image_suffix(self, path: Path, artwork_hash) -> Path:
        # matugen and Pillow's save pick the format from the extension, but Chrome
        # names its artwork /tmp/.com.google.Chrome.XXXXXX, so copy those under a real one
        if path.suffix.lower() in Image.registered_extensions():
            return path

        with Image.open(path) as img:
            suffix = f".{img.format.lower()}"

        cache_dir = Path(TEMP_DIR) / "player-art"
        cache_dir.mkdir(parents=True, exist_ok=True)
        named_path = cache_dir / f"{artwork_hash}{suffix}"
        if not named_path.exists():
            shutil.copyfile(path, named_path)
        return named_path

    def _process_local_artwork(self, art_url, artwork_hash):
        # runs off the main thread, so a newer track can overtake this one
        if self._is_artwork_stale(artwork_hash):
            return

        try:
            input_path = self._with_image_suffix(Path(art_url), artwork_hash)
        except OSError as e:
            logger.error(f"Failed to read artwork {art_url}: {e}")
            return

        art_url = str(input_path)
        blurred_dir = Path(TEMP_DIR) / "player-art" / "blurred"
        blurred_dir.mkdir(parents=True, exist_ok=True)

        suffix = input_path.suffix or ".png"
        blurred_artwork_path = blurred_dir / f"{artwork_hash}{suffix}"

        if not blurred_artwork_path.exists():
            self._blur_image(input_path, blurred_artwork_path)

        if self._is_artwork_stale(artwork_hash):
            return

        # signal artwork change
        self._current_artwork_path = art_url
        self._current_blurred_artwork_path = blurred_artwork_path
        self.artwork_change(
            self._current_artwork_path, self._current_blurred_artwork_path
        )

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
                    # "-c",
                    # f"{ROOT_DIR}/config/matugen/player_runtime.toml",
                    "-j",
                    "hex",
                    "-t",
                    "scheme-fidelity",
                    "--source-color-index",
                    "0",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                shell=False,  # to handle paths with spaces
                check=True,
            )

            try:
                theme_json = json.loads(result.stdout)
                if self._is_artwork_stale(artwork_hash):
                    return
                self._theme_cache[artwork_hash] = theme_json
                self._current_theme = theme_json
                self.theme_change(theme_json)
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Failed to parse color theme: {e}")
        except subprocess.CalledProcessError as e:
            logger.error(f"Matugen error: {e.stderr.strip()}")
        except (subprocess.SubprocessError, OSError) as e:
            logger.error(f"Matugen process failed: {e}")

    def _download_and_process_artwork(self, art_url, artwork_hash):
        if self._is_cleaning_up:
            return

        try:
            cache_dir = Path(TEMP_DIR) / "player-art"
            cache_dir.mkdir(parents=True, exist_ok=True)

            parsed = urllib.parse.urlparse(art_url)
            filename_hash = hashlib.md5(art_url.encode()).hexdigest()
            local_arturl = None
            url_suffix = Path(parsed.path).suffix
            if url_suffix:
                test_path = cache_dir / f"{filename_hash}{url_suffix}"
                if test_path.exists():
                    local_arturl = test_path
            else:
                existing = list(cache_dir.glob(f"{filename_hash}.*"))
                if existing:
                    local_arturl = existing[0]

            if not local_arturl:
                with urllib.request.urlopen(art_url, timeout=5) as response:
                    data = response.read()
                    content_type = response.info().get_content_type()
                    suffix = mimetypes.guess_extension(content_type) or ".png"

                    local_arturl = cache_dir / f"{filename_hash}{suffix}"

                    temp_file = local_arturl.with_suffix(".tmp")
                    temp_file.write_bytes(data)
                    temp_file.replace(local_arturl)

                    logger.info(f"Downloaded artwork: {local_arturl}")
            else:
                logger.debug(f"Using cached artwork: {local_arturl}")

            self._process_local_artwork(str(local_arturl), artwork_hash)

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

        self._stop_polling()

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

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        super().__init__()

        self._manager = Playerctl.PlayerManager()
        # keyed by instance, as e.g. two browser windows share a player name
        self._services = {}  # map player_instance -> PlayerService
        self._player_objects = {}  # map player_instance -> Playerctl.Player

        self._manager.connect("name-appeared", self._on_name_appeared, self._manager)
        self._manager.connect(
            "player-vanished", self._on_player_vanished, self._manager
        )
        config.connect("changed", self._on_config_changed)
        self.init_all_players()
        logger.info("PlayerManager initialized")

        self._initialized = True

    @staticmethod
    def _is_ignored(player_name: str) -> bool:
        return player_name in (config.IGNORED_PLAYERS or [])

    def init_all_players(self):
        logger.info("Initializing all existing players")
        for player_obj in self._manager.props.player_names:
            if self._is_ignored(player_obj.name):
                continue
            if player_obj.instance in self._services:
                continue
            logger.info(f"Initializing existing player: {player_obj.instance}")
            self._create_and_register_player(player_obj)

    def _on_config_changed(self, _config, keys, _value):
        if list(keys) == ["system", "IGNORED_PLAYERS"]:
            GLib.idle_add(self._sync_ignored_players)

    def _sync_ignored_players(self):
        for instance, service in list(self._services.items()):
            if self._is_ignored(service._player.props.player_name):
                logger.info(f"Player {instance} is now ignored, removing")
                self._unregister_player(instance)
        self.init_all_players()
        return GLib.SOURCE_REMOVE

    def _create_and_register_player(self, name_obj):
        instance = name_obj.instance

        # avoid duplicate registration
        if instance in self._services:
            logger.warning(f"Player {instance} already registered, skipping")
            return

        try:
            player = Playerctl.Player.new_from_name(name_obj)
            self._manager.manage_player(player)

            # create service instance
            player_service = PlayerService(player)

            # store references
            self._services[instance] = player_service
            self._player_objects[instance] = player

            logger.info(f"Registered player service for {instance}")
            # emit signal
            self.new_player(instance, player_service)

        except Exception as e:
            logger.error(f"Failed to create player service for {instance}: {e}")

    def _on_name_appeared(self, sender, name, manager):
        name_str = name.name
        logger.info(f"Player appeared: {name_str}")

        if self._is_ignored(name_str):
            logger.debug(f"Player {name_str} is ignored")
            return
        self._create_and_register_player(name)

    def _on_player_vanished(self, sender, player, manager):
        instance = player.props.player_instance
        logger.info(f"Player vanished: {instance}")
        self._unregister_player(instance)

    def _unregister_player(self, instance: str):
        # players that were never registered (e.g. ignored ones) have no UI to remove
        service = self._services.pop(instance, None)
        self._player_objects.pop(instance, None)
        if service is None:
            return

        try:
            service.cleanup()
            logger.info(f"Cleaned up service for {instance}")
        except Exception as e:
            logger.error(f"Error cleaning up service for {instance}: {e}")

        self.player_vanish(instance)

    def get_player_service(self, player_instance: str) -> PlayerService | None:
        return self._services.get(player_instance)

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
