def toggle_class(widget, remove, add):
    widget.remove_style_class(remove)
    widget.add_style_class(add)


# todo
# def toggle_style_class(widget, style_class):
#     if widget.has_style_class(style_class):
#         widget.remove_style_class(style_class)
#     else:
#         widget.add_style_class(style_class)


def toggle_config_vertical_flag():
    import os

    CONFIG_PATH = os.path.expanduser("~/fabric/config/info.py")
    with open(CONFIG_PATH, "r") as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        if line.strip().startswith("VERTICAL"):
            current_value = "True" in line
            new_value = "False" if current_value else "True"
            new_lines.append(f"VERTICAL = {new_value}\n")
        else:
            new_lines.append(line)

    with open(CONFIG_PATH, "w") as f:
        f.writelines(new_lines)


_settings_process = None


def open_settings():
    global _settings_process

    if _settings_process and not _settings_process.get_if_exited():
        return

    # from fabric.utils.helpers import exec_shell_command_async
    from config.info import ROOT_DIR
    import sys

    print(f"Opening settings module from root: {ROOT_DIR}")

    shell_command = f"cd {ROOT_DIR} && {sys.executable} -m settings"

    # _settings_process, _ = exec_shell_command_async(
    #     cmd=["sh", "-c", shell_command], cwd=ROOT_DIR
    # )
    import subprocess
    subprocess.Popen(["python3", "-m", "settings"], cwd=ROOT_DIR)

from gi.repository import Gio, GLib
import shlex
import os

def exec_shell_command_async(
    cmd: str | list[str],
    callback: callable = None,
    cwd: str = None,
) -> tuple[Gio.Subprocess | None, Gio.DataInputStream]:
    launcher = Gio.SubprocessLauncher.new(Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE)
    
    if cwd:
        launcher.set_cwd(os.fspath(cwd))

    process = launcher.spawnv(
        shlex.split(cmd) if isinstance(cmd, str) else cmd
    )

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
                    reader_loop(stream) # Continue reading
            except Exception as e:
                print(f"Error reading stream: {e}")

        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, read_line)

    reader_loop(stdout)
    return process, stdout