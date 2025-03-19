# import gi

from fabric.utils.helpers import (
    exec_shell_command,
    exec_shell_command_async,
    FormattedString,
)
from typing import Literal

# gi.require_version("Gtk", "3.0")
from gi.repository import Gio


def formatted_exec_shell_command(
    unformatted_cmd: str, **kwargs
) -> str | Literal[False]:
    return exec_shell_command(FormattedString(unformatted_cmd).format(**kwargs))


def formatted_exec_shell_command_async(
    unformatted_cmd: str, **kwargs
) -> tuple[Gio.Subprocess | None, Gio.DataInputStream]:
    return exec_shell_command_async(FormattedString(unformatted_cmd).format(**kwargs))