import pulsectl
import threading
import subprocess
from loguru import logger
from typing import Callable
from dataclasses import dataclass

from fabric.core.service import Service, Signal
from gi.repository import GLib


@dataclass
class AudioDevice:
    volume: float = 0.0
    muted: bool = False

    def changed(self, vol: float, muted: bool) -> bool:
        return vol != self.volume or muted != self.muted

    def update(self, vol: float, muted: bool):
        self.volume, self.muted = vol, muted


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
                pulse.volume_set(
                    device,
                    pulsectl.PulseVolumeInfo([volume] * len(device.volume.values)),
                )
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

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_singleton()
        return cls._instance

    def _init_singleton(self):
        super().__init__()
        self._pulse = None
        self._current_device_name = "__"
        self._stop_monitoring = threading.Event()

        self._sink = AudioDevice()
        self._source = AudioDevice()

        self._start_monitoring()

    def _start_monitoring(self):
        threading.Thread(target=self._monitor_volume, daemon=True).start()

    def _monitor_volume(self):
        try:
            with pulsectl.Pulse("volume-service") as pulse:
                self._pulse = pulse
                self._update_current_volume()
                pulse.event_mask_set("sink", "source")
                pulse.event_callback_set(self._on_pulse_event)
                while not self._stop_monitoring.is_set():
                    pulse.event_listen()
                    self._update_current_volume()
        except Exception as e:
            logger.error(f"Failed to monitor volume: {e}")
        finally:
            self._pulse = None

    def _on_pulse_event(self, event):
        relevant_facilities = {
            pulsectl.PulseEventFacilityEnum.sink,
            pulsectl.PulseEventFacilityEnum.source,
        }
        relevant_types = {
            pulsectl.PulseEventTypeEnum.change,
            pulsectl.PulseEventTypeEnum.new,
        }
        if (
            getattr(event, "facility", None) in relevant_facilities
            and getattr(event, "t", None) in relevant_types
        ):
            raise pulsectl.PulseLoopStop()

    def _update_current_volume(self):
        try:
            if not self._pulse:
                logger.warning("No pulse connection")
                return

            server = self._pulse.server_info()
            self._update_sink(server)
            self._update_source(server)

        except Exception as e:
            logger.error(f"Failed to update volume: {e}")

    def _update_sink(self, server):
        info = self._pulse.get_sink_by_name(server.default_sink_name)
        vol = info.volume.values[0] if info.volume.values else 0.0
        muted = bool(info.mute)
        name = info.description

        if self._sink.changed(vol, muted):
            self._sink.update(vol, muted)
            GLib.idle_add(lambda: self.speaker_volume_changed(vol, 1, muted) or False)

        if name != self._current_device_name:
            self._current_device_name = name
            logger.info(f"Audio device switched to: {name}")
            GLib.idle_add(lambda: self.speaker_device_changed(name) or False)

    def _update_source(self, server):
        info = self._pulse.get_source_by_name(server.default_source_name)
        vol = info.volume.values[0] if info.volume.values else 0.0
        muted = bool(info.mute)

        if self._source.changed(vol, muted):
            self._source.update(vol, muted)
            GLib.idle_add(lambda: self.mic_volume_changed(vol, 1, muted) or False)

    def get_current_device_name(self) -> str:
        return self._current_device_name

    def get_current_volume(self) -> tuple[float, bool]:
        return self._sink.volume, self._sink.muted

    def set_volume(self, volume: float):
        _pulse_set_volume(
            "volume-setter",
            lambda pulse, name: pulse.get_sink_by_name(name),
            "default_sink_name",
            volume,
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

    def get_mic_status(self) -> tuple[float, bool]:
        return self._source.volume, self._source.muted

    def set_mic_volume(self, volume: float):
        _pulse_set_volume(
            "mic-setter",
            lambda pulse, name: pulse.get_source_by_name(name),
            "default_source_name",
            volume,
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
            )
            return volume, "yes" in out_mute.stdout.lower()
        except subprocess.CalledProcessError:
            return None, None

    def cleanup(self):
        self._stop_monitoring.set()
