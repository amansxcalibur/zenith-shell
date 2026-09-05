import os
import sys
import shlex
import hashlib
import subprocess
from pathlib import Path
from loguru import logger
from collections.abc import Callable

from fabric.utils.helpers import bulk_replace
from config.info import ROOT_DIR

from gi.repository import Gdk, Gio, GLib  # type: ignore


def toggle_class(widget, remove, add):
    widget.remove_style_class(remove)
    widget.add_style_class(add)


_settings_process: subprocess.Popen | None = None


def open_settings():
    global _settings_process

    if _settings_process is not None and _settings_process.poll() is None:
        return

    logger.debug(f"Opening settings module from root: {ROOT_DIR}")

    # shell_command = f"cd {ROOT_DIR} && {sys.executable} -m settings"

    # _settings_process, _ = exec_shell_command_async_with_cwd(
    #     cmd=["sh", "-c", shell_command], cwd=ROOT_DIR
    # )

    _settings_process = subprocess.Popen(
        [sys.executable, "-m", "settings"], cwd=ROOT_DIR
    )


def exec_shell_command_async_with_cwd(
    cmd: str | list[str],
    callback: Callable | None = None,
    cwd: str | None = None,
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
                logger.error(f"Error reading stream: {e}")

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
    from gi.repository import Gdk  # type: ignore

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


def format_accel_to_keybind(accel_name: str) -> str:
    return bulk_replace(
        accel_name,
        ["<Mod2>", "<Shift>", "<Primary>", "<Mod4><Super>", "<Alt>"],
        [" ", "Shift ", "Ctrl ", "Super ", "Alt "],
    )


def bind_group_toggle(switch, targets):
    def apply(active):
        for w in targets:
            w.set_sensitive(active)
            w.set_opacity(1.0 if active else 0.4)

    apply(switch.get_active())
    switch.connect("notify::active", lambda s, _p: apply(s.get_active()))


def get_absolute_wayland_widget_position(widget):
    """Compute widget's current absolute (x, y) screen position."""
    from gi.repository import GtkLayerShell  # type: ignore

    toplevel = widget.get_toplevel()
    win = toplevel.get_window()
    display = Gdk.Display.get_default()
    monitor = display.get_monitor_at_window(win) or display.get_monitor(0)
    geo = monitor.get_geometry()

    # window (toplevel) position via anchors/margins, as before
    win_alloc = toplevel.get_allocation()
    win_w, win_h = win_alloc.width, win_alloc.height

    anchored_top = GtkLayerShell.get_anchor(toplevel, GtkLayerShell.Edge.TOP)
    anchored_bottom = GtkLayerShell.get_anchor(toplevel, GtkLayerShell.Edge.BOTTOM)
    anchored_left = GtkLayerShell.get_anchor(toplevel, GtkLayerShell.Edge.LEFT)
    anchored_right = GtkLayerShell.get_anchor(toplevel, GtkLayerShell.Edge.RIGHT)

    margin_top = GtkLayerShell.get_margin(toplevel, GtkLayerShell.Edge.TOP)
    margin_bottom = GtkLayerShell.get_margin(toplevel, GtkLayerShell.Edge.BOTTOM)
    margin_left = GtkLayerShell.get_margin(toplevel, GtkLayerShell.Edge.LEFT)
    margin_right = GtkLayerShell.get_margin(toplevel, GtkLayerShell.Edge.RIGHT)

    if anchored_left and not anchored_right:
        win_x = geo.x + margin_left
    elif anchored_right and not anchored_left:
        win_x = geo.x + geo.width - margin_right - win_w
    elif anchored_left and anchored_right:
        win_x = geo.x + margin_left
    else:
        win_x = geo.x + (geo.width - win_w) // 2

    if anchored_top and not anchored_bottom:
        win_y = geo.y + margin_top
    elif anchored_bottom and not anchored_top:
        win_y = geo.y + geo.height - margin_bottom - win_h
    elif anchored_top and anchored_bottom:
        win_y = geo.y + margin_top
    else:
        win_y = geo.y + (geo.height - win_h) // 2

    return True, win_x, win_y
