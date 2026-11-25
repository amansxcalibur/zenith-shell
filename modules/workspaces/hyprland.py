import json

from fabric.utils.helpers import bulk_connect
from fabric.hyprland.service import HyprlandEvent
from fabric.core.widgets import (
    Workspaces as FabricWorkspaces,
    WorkspaceButton as FabricWorkspaceButton,
)
from fabric.hyprland.widgets import (
    HyprlandActiveWindow as FabricActiveWindow,
    get_hyprland_connection,
)


def query(name: str):
    return json.loads(get_hyprland_connection().send_command(f"j/{name}").reply)


# fabric's own crashes on named and special workspaces, they have no number
class HyprlandWorkspaces(FabricWorkspaces):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.connection = get_hyprland_connection()

        bulk_connect(
            self.connection,
            {
                "event::workspacev2": self.on_workspace,
                "event::focusedmonv2": self.on_monitor,
                "event::createworkspacev2": self.on_create_workspace,
                "event::destroyworkspacev2": self.on_destroy_workspace,
                "event::urgent": self.on_urgent,
            },
        )
        self.connect("scroll-event", self.do_handle_scroll)

        for workspace in query("workspaces"):
            self.emit_numbered(self.workspace_created, workspace.get("id"))
        self.emit_numbered(self.workspace_activated, query("activeworkspace").get("id"))

    @staticmethod
    def emit_numbered(signal, ws_id: int | str | None):
        if str(ws_id).isdigit():
            signal(int(ws_id))

    def on_workspace(self, _, event: HyprlandEvent):
        self.emit_numbered(self.workspace_activated, event.data[0])

    def on_monitor(self, _, event: HyprlandEvent):
        self.emit_numbered(self.workspace_activated, event.data[-1])

    def on_create_workspace(self, _, event: HyprlandEvent):
        self.emit_numbered(self.workspace_created, event.data[0])

    def on_destroy_workspace(self, _, event: HyprlandEvent):
        self.emit_numbered(self.workspace_destroyed, event.data[0])

    def on_urgent(self, _, event: HyprlandEvent):
        for client in query("clients"):
            if client["address"] == f"0x{event.data[0]}":
                self.emit_numbered(self.urgent, client["workspace"].get("id"))

    def focus_workspace(self, workspace: int | str):
        self.connection.send_command(
            f'dispatch hl.dsp.focus({{ workspace = "{workspace}" }})'
        )

    # override signals from super class
    def do_action_next(self):
        self.focus_workspace("m+1")

    def do_action_previous(self):
        self.focus_workspace("m-1")

    def do_button_clicked(self, button: FabricWorkspaceButton):
        self.focus_workspace(button.id)


class HyprlandActiveWindow(FabricActiveWindow):
    def do_initialize(self):
        window = query("activewindow")
        self.window_activated(window.get("class", ""), window.get("title", ""))

    def on_active_window(self, _, event: HyprlandEvent):
        # titles can have commas
        win_class, *title = event.data
        self.window_activated(win_class, ",".join(title))
