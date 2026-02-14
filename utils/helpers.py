import os
import sys
import shlex
import hashlib
import subprocess
from pathlib import Path
from loguru import logger

from gi.repository import Gio, GLib

from config.info import ROOT_DIR


def toggle_class(widget, remove, add):
    widget.remove_style_class(remove)
    widget.add_style_class(add)

_settings_process: Gio.Subprocess | None = None

def open_settings():
    global _settings_process

    if _settings_process and not _settings_process.get_if_exited():
        return

    logger.debug(f"Opening settings module from root: {ROOT_DIR}")

    # shell_command = f"cd {ROOT_DIR} && {sys.executable} -m settings"

    # _settings_process, _ = exec_shell_command_async_with_cwd(
    #     cmd=["sh", "-c", shell_command], cwd=ROOT_DIR
    # )

    subprocess.Popen([sys.executable, "-m", "settings"], cwd=ROOT_DIR)


def exec_shell_command_async_with_cwd(
    cmd: str | list[str],
    callback: callable = None,
    cwd: str = None,
) -> tuple[Gio.Subprocess | None, Gio.DataInputStream]:
    launcher = Gio.SubprocessLauncher.new(
        Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
    )

    if cwd:
        launcher.set_cwd(os.fspath(cwd))

    process = launcher.spawnv(shlex.split(cmd) if isinstance(cmd, str) else cmd)

    stdout = Gio.DataInputStream(
        base_stream=process.get_stdout_pipe(),
        close_base_stream=True,
    )

    def reader_loop(stream: Gio.DataInputStream):
        def read_line(stream: Gio.DataInputStream, res: Gio.AsyncResult):
            try:
                output, *_ = stream.read_line_finish_utf8(res)
                if output is not None:
                    if callback:
                        callback(output)
                    reader_loop(stream)
            except Exception as e:
                print(f"Error reading stream: {e}")

        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, read_line)

    reader_loop(stdout)
    return process, stdout


def restart_shell():
    subprocess.Popen([sys.executable] + sys.argv)
    os._exit(0)


def hash_file(file_path: Path) -> str:
    mtime = file_path.stat().st_mtime
    identity_string = f"{file_path.absolute()}_{mtime}"
    file_hash = hashlib.md5(identity_string.encode("utf-8")).hexdigest()

    return file_hash


def get_screen_resolution_gdk() -> tuple[int, int]:
    from gi.repository import Gdk

    display = Gdk.Display.get_default()
    if not display:
        raise RuntimeError("No Gdk display")

    monitor = display.get_primary_monitor()
    if not monitor:
        raise RuntimeError("No primary monitor")

    geometry = monitor.get_geometry()
    return geometry.width, geometry.height


def get_screen_resolution_i3() -> tuple[int, int]:
    from fabric.i3.service import I3MessageType
    from fabric.i3.widgets import get_i3_connection

    i3_conn = get_i3_connection()
    i3_response = i3_conn.send_command("", I3MessageType.GET_OUTPUTS)

    active = [
        o
        for o in i3_response.reply
        if o.get("active") and not o["name"].startswith("xroot")
    ]

    if not active:
        raise RuntimeError("No active i3 outputs")

    max_x = max(o["rect"]["x"] + o["rect"]["width"] for o in active)
    max_y = max(o["rect"]["y"] + o["rect"]["height"] for o in active)

    return max_x, max_y