from fabric.widgets.box import Box
from fabric.i3.widgets import (
    # I3Language,
    I3ActiveWindow,
    I3Workspaces,
    # WorkspaceButton,
)

from .workspace_button import WorkspaceButton


class Workspaces(Box):
    def __init__(self, vertical: bool = False, **kwargs):
        super().__init__(
            name="workspaces-container",
            visible=True,
            all_visible=True,
            style_classes="" if not vertical else "vertical",
            orientation="h" if not vertical else "v",
            h_align="fill",
        )

        self.children = (
            I3Workspaces(
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
    def __init__(self, **kwargs):
        super().__init__(
            name="active-windows",
            visible=True,
            all_visible=True,
            orientation="h",
            h_align="center",
            v_align="center",
            **kwargs,
        )
        self.active_window = I3ActiveWindow(name="active-window")
