from fabric.core.service import Service, Signal

import subprocess
import pulsectl
import threading
from loguru import logger

from gi.repository import GLib


class VolumeService(Service):
    _instance = None

    @Signal
    def value_changed(self, new_value: float, max_value: float, is_muted: bool) -> None: ...

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_singleton()
        return cls._instance

    def _init_singleton(self):
        super().__init__()
        self._pulse = None
        self._monitor_thread = None
        self._current_volume = 0
        self._is_muted = False
        self._stop_monitoring = threading.Event()

        self._start_monitoring()

    def _start_monitoring(self):
        self._monitor_thread = threading.Thread(
            target=self._monitor_volume, daemon=True
        )
        self._monitor_thread.start()

    def _monitor_volume(self):
        try:
            with pulsectl.Pulse("volume-service") as pulse:
                self._pulse = pulse

                # Get initial volume
                self._update_current_volume()

                pulse.event_mask_set("sink")
                pulse.event_callback_set(self._on_pulse_event)

                while not self._stop_monitoring.is_set():
                    pulse.event_listen()
                    self._update_current_volume()

        except Exception as e:
            logger.error(f"Failed to monitor volume: {e}")
        finally:
            self._pulse = None

    def _on_pulse_event(self, event):
        # logger.debug(f"Processing PulseAudio event: {event}")

        if (
            hasattr(event, "facility")
            and event.facility == pulsectl.PulseEventFacilityEnum.sink
            and hasattr(event, "t")
            and event.t
            in [pulsectl.PulseEventTypeEnum.change, pulsectl.PulseEventTypeEnum.new]
        ):
            raise pulsectl.PulseLoopStop()  # this makes event_listen() return

    def _update_current_volume(self):
        """Update volume - called outside event loop, so blocking calls are safe"""
        try:
            if not self._pulse:
                logger.warning("No pulse connection")
                return

            server_info = self._pulse.server_info()
            sink_info = self._pulse.get_sink_by_name(server_info.default_sink_name)

            if sink_info.volume.values:
                volume_raw = sink_info.volume.values[0]
            else:
                volume_raw = 0

            is_muted = bool(sink_info.mute)

            if volume_raw != self._current_volume or is_muted != self._is_muted:
                self._current_volume = volume_raw
                self._is_muted = is_muted

                # emit signal
                GLib.idle_add(self._emit_volume_changed, volume_raw, is_muted)
                # logger.info(f"Volume changed: {volume_raw}%, Muted: {is_muted}")

        except Exception as e:
            logger.error(f"Failed to update volume: {e}")

    def increment(self, diff):
        self.set_volume(self._current_volume+diff)

    def _emit_volume_changed(self, volume, is_muted):
        self.value_changed.emit(volume, 1, is_muted)
        return False

    def get_current_volume(self):
        return self._current_volume, self._is_muted

    def set_volume(self, volume: float):
        def _set_volume_thread():
            try:
                with pulsectl.Pulse("volume-setter") as pulse:
                    server_info = pulse.server_info()
                    sink_info = pulse.get_sink_by_name(server_info.default_sink_name)

                    volume_raw = volume

                    new_volume = pulsectl.PulseVolumeInfo(
                        [volume_raw] * len(sink_info.volume.values)
                    )
                    pulse.volume_set(sink_info, new_volume)

            except Exception as e:
                logger.error(f"Failed to set volume: {e}")

        threading.Thread(target=_set_volume_thread, daemon=True).start()

    def set_mute(self, muted: bool):
        def _set_mute_thread():
            try:
                with pulsectl.Pulse("volume-muter") as pulse:
                    server_info = pulse.server_info()
                    sink_info = pulse.get_sink_by_name(server_info.default_sink_name)

                    pulse.mute(sink_info, muted)

            except Exception as e:
                logger.error(f"Failed to set mute: {e}")

        threading.Thread(target=_set_mute_thread, daemon=True).start()

    def toggle_mute(self):
        self.set_mute(not self._is_muted)

    def cleanup(self):
        self._stop_monitoring.set()
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=1.0)

    def get_current_volume_via_subprocess(self):
        try:
            output = subprocess.run(
                "pactl get-sink-volume @DEFAULT_SINK@ | awk '{print $5}' | tr -d '%'",
                shell=True,
                text=True,
                capture_output=True,
                check=True,
            )
            volume_percent = (
                int(output.stdout.strip()) if output.stdout.strip().isdigit() else None
            )

            output_mute = subprocess.run(
                "pactl get-sink-mute @DEFAULT_SINK@",
                shell=True,
                text=True,
                capture_output=True,
            )
            is_muted = "yes" in output_mute.stdout.lower()

            return volume_percent, is_muted
        except subprocess.CalledProcessError:
            return None, None
