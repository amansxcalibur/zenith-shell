from fabric.widgets.box import Box
from fabric.core.widgets import (
    ActiveWindow as FabricActiveWindow,
    Workspaces as FabricWorkspaces,
)

from .workspace_button import WorkspaceButton


class Workspaces(Box):
    def __init__(
        self,
        workspaces_class: type[FabricWorkspaces],
        vertical: bool = False,
        **kwargs,
    ):
        super().__init__(
            name="workspaces-container",
            visible=True,
            all_visible=True,
            style_classes="" if not vertical else "vertical",
            orientation="h" if not vertical else "v",
            h_align="fill",
        )

        self.children = (
            workspaces_class(
                name="workspaces",
                orientation="h" if not vertical else "v",
                buttons=[
                    WorkspaceButton(
                        id=ws_id,
                    )
                    for ws_id in range(1, 11)
                ],
                # for special workspaces (multi monitor, etc)
                buttons_factory=lambda ws_id: WorkspaceButton(id=ws_id),
            ),
        )


class ActiveWindow(Box):
    def __init__(self, active_window_class: type[FabricActiveWindow], **kwargs):
        super().__init__(
            name="active-windows",
            visible=True,
            all_visible=True,
            orientation="h",
            h_align="center",
            v_align="center",
            **kwargs,
        )
        self.active_window = active_window_class(name="active-window")
