import pulsectl
import threading
import subprocess
from loguru import logger
from dataclasses import dataclass
from collections.abc import Callable

from fabric.core.service import Service, Signal
from gi.repository import GLib  # type: ignore

PA_INVALID_INDEX = 0xFFFFFFFF  # a source's monitor_of_sink when it's a real input

MAX_VOLUME = 1.5
MAX_VOLUME_REASON = "Goes up to 150%.\nPast 100% the sound is boosted, and can distort."
MAX_MIC_VOLUME = 1.0
MAX_APP_VOLUME = 1.0
RECONNECT_DELAY_S = 2  # between attempts to reach a sound server that went away


def _limit(volume: float, limit: float, current: float) -> float:
    volume = max(volume, 0.0)
    if volume > limit:
        volume = max(limit, min(volume, current))
    return volume


@dataclass
class AudioDevice:
    volume: float = 0.0
    muted: bool = False

    def changed(self, vol: float, muted: bool) -> bool:
        return vol != self.volume or muted != self.muted

    def update(self, vol: float, muted: bool):
        self.volume, self.muted = vol, muted


@dataclass(frozen=True)
class SoundDevice:
    name: str  # pulse's id for it
    description: str  # what to call it
    icon: str  # "headphones", "headset", "bluetooth", "hdmi", "speaker" or "mic"
    active: bool  # the default one
    port: str = ""  # the jack in use, when a card has a few (e.g. "Headphones")

    @property
    def label(self) -> str:
        return self.port or self.description

    @property
    def full_name(self) -> str:
        if self.port:
            return f"{self.port} · {self.description}"
        return self.description


@dataclass(frozen=True)
class AppStream:
    """An app playing sound, or recording from the mic."""

    index: int
    app: str
    title: str  # what it's playing, if it says
    icon_name: str | None  # from the icon theme
    volume: float = 0.0
    muted: bool = False


# a card's jacks, by what's plugged into them; others keep pulse's description
PORT_NAMES = {
    "analog-input-internal-mic": "Internal microphone",
    "analog-input-mic": "Headset microphone",
    "analog-input-headset-mic": "Headset microphone",
    "analog-input-headphone-mic": "Headset microphone",
    "analog-output-speaker": "Speakers",
    "analog-output-headphones": "Headphones",
}


def _active_port(info):
    # a wired earphone isn't a device of its own, just the card's other jack
    return info.port_active if len(info.port_list) > 1 else None


def _port_name(info) -> str:
    port = _active_port(info)
    if port is None:
        return ""
    return PORT_NAMES.get(port.name, port.description)


def _sound_device(info, fallback_icon: str, default_name: str) -> SoundDevice:
    return SoundDevice(
        name=info.name,
        description=info.description,
        icon=_device_icon(info, fallback_icon),
        active=info.name == default_name,
        port=_port_name(info),
    )


def _device_icon(info, fallback: str) -> str:
    text = f"{info.name} {info.description}".lower()
    form = info.proplist.get("device.form_factor", "")
    if "bluez" in text or info.proplist.get("device.bus") == "bluetooth":
        return "bluetooth"
    port = _active_port(info)
    port = port.name.lower() if port else ""
    if "internal" in port:
        return fallback
    if fallback == "mic" and "input" in port and "mic" in port:
        return "headset"  # the jack's mic: an earphone's
    if form in ("headphone", "headset") or "headphone" in text + port:
        return "headphones"
    if "speaker" in port:
        return "speaker"
    if "hdmi" in text or "displayport" in text:
        return "hdmi"
    return fallback


def _app_stream(info, volume=True) -> AppStream:
    props = info.proplist
    app = props.get("application.name") or props.get(
        "application.process.binary", "Unknown"
    )
    title = props.get("media.name", "")
    if title == app:
        title = ""
    return AppStream(
        index=info.index,
        app=app,
        title=title,
        icon_name=props.get("application.icon_name")
        or props.get("application.process.binary"),
        volume=info.volume.value_flat if volume else 0.0,
        muted=bool(info.mute) if volume else False,
    )


class _Volume(pulsectl.PulseVolumeInfo):
    """Overrides PulseVolumeInfo.to_struct from pulsectl 24.12.0, which cuts every
    value to 152.5% (PA_VOLUME_UI_MAX) before sending it, with no error. Our
    limit lives in _limit instead."""

    # override
    def to_struct(self):
        return pulsectl._pulsectl.PA_CVOLUME(
            len(self.values),
            tuple(round(v * pulsectl._pulsectl.PA_VOLUME_NORM) for v in self.values),
        )


def _run_in_thread(fn):
    # fire and forget
    threading.Thread(target=fn, daemon=True).start()


def _pulse_set_volume(
    client_name: str,
    lookup: Callable[[pulsectl.Pulse, str], any],
    server_key: str,
    volume: float,
):
    def _run():
        try:
            with pulsectl.Pulse(client_name) as pulse:
                name = getattr(pulse.server_info(), server_key)
                device = lookup(pulse, name)
                pulse.volume_set(device, _Volume([volume] * len(device.volume.values)))
        except Exception as e:
            logger.error(f"[{client_name}] Failed to set volume: {e}")

    _run_in_thread(_run)


def _pulse_set_mute(
    client_name: str,
    lookup: Callable[[pulsectl.Pulse, str], any],
    server_key: str,
    muted: bool,
):
    def _run():
        try:
            with pulsectl.Pulse(client_name) as pulse:
                name = getattr(pulse.server_info(), server_key)
                device = lookup(pulse, name)
                pulse.mute(device, muted)
        except Exception as e:
            logger.error(f"[{client_name}] Failed to set mute: {e}")

    _run_in_thread(_run)


class VolumeService(Service):
    _instance = None

    @Signal
    def speaker_device_changed(self, device_name: str) -> None: ...

    @Signal
    def speaker_volume_changed(
        self, new_value: float, max_value: float, is_muted: bool
    ) -> None: ...

    @Signal
    def mic_volume_changed(
        self, new_value: float, max_value: float, is_muted: bool
    ) -> None: ...

    @Signal
    def mic_available_changed(self, available: bool) -> None: ...

    @Signal
    def outputs_changed(self, outputs: object) -> None: ...  # list[SoundDevice]

    @Signal
    def inputs_changed(self, inputs: object) -> None: ...  # list[SoundDevice], mics

    @Signal
    def apps_changed(self, apps: object) -> None: ...  # list[AppStream], playing

    @Signal
    def mic_users_changed(self, apps: object) -> None: ...  # list[AppStream]

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls, *args, **kwargs)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        super().__init__()

        self._pulse = None
        self._current_device: SoundDevice | None = None  # the default output
        self._stop_monitoring = threading.Event()
        # set by an event that came in while we were reading pulse, which
        # event_listen() would otherwise never hear about
        self._stale = False

        self._sink = AudioDevice()
        self._source = AudioDevice()
        self._mic_available = False
        self._outputs: list[SoundDevice] = []
        self._inputs: list[SoundDevice] = []
        self._apps: list[AppStream] = []
        self._mic_users: list[AppStream] = []

        self._start_monitoring()

        self._initialized = True

    def _start_monitoring(self):
        threading.Thread(target=self._monitor_volume, daemon=True).start()

    def _monitor_volume(self):
        # the sound server could restart
        self._reported_outage = False
        while not self._stop_monitoring.is_set():
            try:
                self._listen()
            except Exception as e:
                # once per outage, not every attempt
                if not self._reported_outage:
                    logger.error(f"No sound server, will keep retrying: {e}")
                    self._reported_outage = True
            finally:
                self._pulse = None
            self._stop_monitoring.wait(RECONNECT_DELAY_S)

    def _listen(self):
        with pulsectl.Pulse("volume-service") as pulse:
            self._pulse = pulse
            self._reported_outage = False
            logger.info("Connected to the sound server")
            self._update_current_volume()
            # server: the default device changing; card: a jack being
            # plugged in or pulled out
            pulse.event_mask_set(
                "sink", "source", "sink_input", "source_output", "server", "card"
            )
            pulse.event_callback_set(self._on_pulse_event)
            while not self._stop_monitoring.is_set():
                if not self._stale:
                    pulse.event_listen()
                # a burst (a jack replugged) settles over several events;
                # read again until one comes through without any more
                self._stale = False
                self._update_current_volume()

    def _on_pulse_event(self, event):
        relevant_facilities = {
            pulsectl.PulseEventFacilityEnum.sink,
            pulsectl.PulseEventFacilityEnum.source,
            pulsectl.PulseEventFacilityEnum.sink_input,
            pulsectl.PulseEventFacilityEnum.source_output,
            pulsectl.PulseEventFacilityEnum.server,
            pulsectl.PulseEventFacilityEnum.card,
        }
        relevant_types = {
            pulsectl.PulseEventTypeEnum.change,
            pulsectl.PulseEventTypeEnum.new,
            pulsectl.PulseEventTypeEnum.remove,
        }
        if (
            getattr(event, "facility", None) in relevant_facilities
            and getattr(event, "t", None) in relevant_types
        ):
            self._stale = True
            raise pulsectl.PulseLoopStop()

    def _update_current_volume(self):
        try:
            if not self._pulse:
                logger.warning("No pulse connection")
                return

            server = self._pulse.server_info()
        except Exception as e:
            logger.error(f"Failed to update volume: {e}")
            return

        # each on its own: mid-replug the default sink can be briefly missing,
        # which mustn't keep the device list from being read
        for update in (
            lambda: self._update_sink(server),
            lambda: self._update_source(server),
            lambda: self._update_devices(server),
            self._update_streams,
        ):
            try:
                update()
            except Exception as e:
                logger.error(f"Failed to update volume: {e}")

    def _update_sink(self, server):
        info = self._pulse.get_sink_by_name(server.default_sink_name)
        vol = info.volume.values[0] if info.volume.values else 0.0
        muted = bool(info.mute)
        # the port too: a jack switching keeps the card the same
        device = _sound_device(info, "speaker", server.default_sink_name)

        if self._sink.changed(vol, muted):
            self._sink.update(vol, muted)
            GLib.idle_add(lambda: self.speaker_volume_changed(vol, 1, muted) or False)

        if device != self._current_device:
            self._current_device = device
            logger.info(f"Audio device switched to: {device.full_name}")
            GLib.idle_add(
                lambda: self.speaker_device_changed(device.full_name) or False
            )

    def _update_source(self, server):
        try:
            info = self._pulse.get_source_by_name(server.default_source_name)
        except pulsectl.PulseIndexError:
            info = None
        # with no input device, the default source is an output's monitor
        available = info is not None and info.monitor_of_sink == PA_INVALID_INDEX
        if available != self._mic_available:
            self._mic_available = available
            GLib.idle_add(lambda: self.mic_available_changed(available) or False)
        if info is None:
            return

        vol = info.volume.values[0] if info.volume.values else 0.0
        muted = bool(info.mute)

        if self._source.changed(vol, muted):
            self._source.update(vol, muted)
            GLib.idle_add(lambda: self.mic_volume_changed(vol, 1, muted) or False)

    def _update_devices(self, server):
        outputs = [
            _sound_device(info, "speaker", server.default_sink_name)
            for info in self._pulse.sink_list()
        ]
        if outputs != self._outputs:
            self._outputs = outputs
            GLib.idle_add(lambda: self.outputs_changed(outputs) or False)

        inputs = [
            _sound_device(info, "mic", server.default_source_name)
            for info in self._pulse.source_list()
            if info.monitor_of_sink == PA_INVALID_INDEX
        ]
        if inputs != self._inputs:
            self._inputs = inputs
            GLib.idle_add(lambda: self.inputs_changed(inputs) or False)

    def _update_streams(self):
        apps = [_app_stream(info) for info in self._pulse.sink_input_list()]
        if apps != self._apps:
            self._apps = apps
            GLib.idle_add(lambda: self.apps_changed(apps) or False)

        # recording from a real input, not an output's monitor or a level meter
        mics = {
            info.index
            for info in self._pulse.source_list()
            if info.monitor_of_sink == PA_INVALID_INDEX
        }
        users = [
            _app_stream(info, volume=False)
            for info in self._pulse.source_output_list()
            if info.source in mics
            and "peak detect" not in info.proplist.get("media.name", "").lower()
        ]
        if users != self._mic_users:
            self._mic_users = users
            GLib.idle_add(lambda: self.mic_users_changed(users) or False)

    def get_outputs(self) -> list[SoundDevice]:
        return self._outputs

    def get_inputs(self) -> list[SoundDevice]:
        return self._inputs

    def get_apps(self) -> list[AppStream]:
        return self._apps

    def get_mic_users(self) -> list[AppStream]:
        return self._mic_users

    def set_default_output(self, name: str):
        def _run():
            try:
                with pulsectl.Pulse("output-switcher") as pulse:
                    pulse.sink_default_set(name)
                    sink = pulse.get_sink_by_name(name)
                    for stream in pulse.sink_input_list():
                        if stream.sink != sink.index:
                            pulse.sink_input_move(stream.index, sink.index)
            except Exception as e:
                logger.error(f"[output-switcher] Failed to switch output: {e}")

        _run_in_thread(_run)

    def set_default_input(self, name: str):
        def _run():
            try:
                with pulsectl.Pulse("input-switcher") as pulse:
                    pulse.source_default_set(name)
                    source = pulse.get_source_by_name(name)
                    mics = {
                        info.index
                        for info in pulse.source_list()
                        if info.monitor_of_sink == PA_INVALID_INDEX
                    }
                    for stream in pulse.source_output_list():
                        if stream.source in mics and stream.source != source.index:
                            pulse.source_output_move(stream.index, source.index)
            except Exception as e:
                logger.error(f"[input-switcher] Failed to switch input: {e}")

        _run_in_thread(_run)

    def set_app_volume(self, index: int, volume: float):
        def _run():
            try:
                with pulsectl.Pulse("app-volume-setter") as pulse:
                    stream = pulse.sink_input_info(index)
                    volume_ = _limit(volume, MAX_APP_VOLUME, stream.volume.value_flat)
                    pulse.volume_set(
                        stream, _Volume([volume_] * len(stream.volume.values))
                    )
            except Exception as e:
                logger.error(f"[app-volume-setter] Failed to set volume: {e}")

        _run_in_thread(_run)

    def get_current_device(self) -> SoundDevice | None:
        return self._current_device

    def get_current_volume(self) -> tuple[float, bool]:
        return self._sink.volume, self._sink.muted

    def set_volume(self, volume: float):
        _pulse_set_volume(
            "volume-setter",
            lambda pulse, name: pulse.get_sink_by_name(name),
            "default_sink_name",
            _limit(volume, MAX_VOLUME, self._sink.volume),
        )

    def set_mute(self, muted: bool):
        _pulse_set_mute(
            "volume-muter",
            lambda pulse, name: pulse.get_sink_by_name(name),
            "default_sink_name",
            muted,
        )

    def toggle_mute(self):
        self.set_mute(not self._sink.muted)

    def increment(self, diff: float):
        self.set_volume(self._sink.volume + diff)

    def is_mic_available(self) -> bool:
        return self._mic_available

    def get_mic_status(self) -> tuple[float, bool]:
        return self._source.volume, self._source.muted

    def set_mic_volume(self, volume: float):
        _pulse_set_volume(
            "mic-setter",
            lambda pulse, name: pulse.get_source_by_name(name),
            "default_source_name",
            _limit(volume, MAX_MIC_VOLUME, self._source.volume),
        )

    def set_mic_mute(self, muted: bool):
        _pulse_set_mute(
            "mic-muter",
            lambda pulse, name: pulse.get_source_by_name(name),
            "default_source_name",
            muted,
        )

    def toggle_mic_mute(self):
        self.set_mic_mute(not self._source.muted)

    def get_current_volume_via_subprocess(self) -> tuple[int | None, bool]:
        try:
            out = subprocess.run(
                "pactl get-sink-volume @DEFAULT_SINK@ | awk '{print $5}' | tr -d '%'",
                shell=True,
                text=True,
                capture_output=True,
                check=True,
            )
            volume = int(out.stdout.strip()) if out.stdout.strip().isdigit() else None

            out_mute = subprocess.run(
                "pactl get-sink-mute @DEFAULT_SINK@",
                shell=True,
                text=True,
                capture_output=True,
                check=True,
            )
            return volume, "yes" in out_mute.stdout.lower()
        except subprocess.CalledProcessError:
            return None, None

    def cleanup(self):
        self._stop_monitoring.set()
