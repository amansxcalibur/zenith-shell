from fabric.widgets.box import Box
from fabric.i3.widgets import (
    # I3Language,
    I3ActiveWindow,
    I3Workspaces,
    WorkspaceButton,
)

import threading
from i3ipc import Connection, Event

import config.info as info


class i3Connector:
    _instance = None
    _thread = None

    @classmethod
    def _get_instance(cls, **kwargs):
        if cls._instance is None:
            cls._instance = i3Connector(**kwargs)
        return cls._instance

    def __init__(self, **kwargs):
        self.workspace = kwargs.get("workspace", None)
        self.active_window = kwargs.get("active", None)
        self.i3 = Connection(auto_reconnect=True)
        self.i3.command("gaps left all set 3px")
        self.i3.command("gaps top all set 3px")
        self.i3.command("gaps bottom all set 3px")

        self.callbacks = {Event.WORKSPACE: []}

        self.focused = self.i3.get_tree().find_focused()
        # print(self.focused.name, self.focused.workspace().name)
        # i3.command("focus left")
        # for con in self.i3.get_tree():
        #    print(con.name)
        self.i3.on(Event.WORKSPACE_FOCUS, self.on_workspace_focus)
        self.i3.on(Event.WINDOW_FOCUS, self.on_window_focus)
        self.i3.on(Event.WINDOW_TITLE, self.on_window_title_change)
        self.i3.on(Event.SHUTDOWN_RESTART, self.on_session_restart)

    def on_workspace_focus(self, i3, e):
        if e.current:
            # print("Window in workspace", e.current.num)
            # for w in e.current.leaves():
            #     #print(w)
            # self.workspace.set_active_window(e.current.num)
            for callback in self.callbacks[Event.WORKSPACE]:
                callback(i3, e)

    def on_window_focus(self, i3, e):
        # focused = i3.get_tree().find_focused()
        # ws_name = "%s %s" % (focused.workspace().num, focused.window_class)
        # print(e.container.name)
        # self.active_window.setter_label(focused.name)
        self.active_window.setter_label(e.container.name)

    def on_window_title_change(self, i3, e):
        self.active_window.setter_label(e.container.name)

    def on_session_restart(self, i3, e):
        if info.VERTICAL:
            i3.command("gaps left all set 44px")
            i3.command("gaps top all set 3px")
        else:
            self.i3.command("gaps left all set 3px")
            self.i3.command("gaps top all set 3px")
            self.i3.command("gaps bottom all set 3px")

    def start(self):
        if self._thread is None or not self.thread.is_alive():
            self._thread = threading.Thread(target=self.i3.main, daemon=True)
            self._thread.start()

    def register_callback(self, event_type, callback):
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)

    def command(self, cmd):
        return self.i3.command(cmd)


class Workspaces(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="workspaces-container",
            visible=True,
            all_visible=True,
            style_classes="" if not info.VERTICAL else "vertical",
            orientation="h" if not info.VERTICAL else "v",
            h_align="fill",
        )

        self.children = (
            I3Workspaces(
                name="workspaces",
                v_align="center",
                spacing=8,
                buttons=[
                    WorkspaceButton(id=ws_id, label=None) for ws_id in range(1, 11)
                ],
                buttons_factory=lambda ws_id: WorkspaceButton(id=ws_id, label=None),
            ),
        )

        # self.i3_connector = i3Connector._get_instance(workspace=self)
        # self.i3_connector.start()
        # self.i3_connector.register_callback(Event.WORKSPACE, self.set_active_window)

        # self.all_workspaces = Box(name="workspace-container", orientation="v" if info.VERTICAL else "h", spacing=8, children = self.buttons())
        # self.children = Box(children=[self.all_workspaces])

        # self._init_workspaces()

    # def buttons(self):
    #     buttons = []
    #     for i in range(10):
    #         buttons.append(
    #             Button(
    #                 name="%i" % (i + 1),
    #                 on_clicked=lambda b, num=i: self.switch_workspace(num),
    #             )
    #         )
    #         buttons[i].add_style_class("workspace-button")
    #     return buttons

    # def set_active_window(self, i3, e):
    #     curr_workspace = e.current.num - 1
    #     used_workspaces = []
    #     for con in i3.get_workspaces():
    #         used_workspaces.append(int(con.name))
    #     for i, btn in enumerate(self.all_workspaces.children):
    #         if i == curr_workspace:
    #             btn.remove_style_class("workspace-button")
    #             btn.remove_style_class("used-workspace")
    #             btn.add_style_class("active-workspace")
    #             if info.VERTICAL:
    #                 btn.add_style_class("vertical")
    #         else:
    #             btn.remove_style_class("active-workspace")
    #             if info.VERTICAL:
    #                 btn.remove_style_class("vertical")
    #             btn.add_style_class("workspace-button")
    #             if (i + 1) in used_workspaces:
    #                 btn.add_style_class("used-workspace")
    #             else:
    #                 btn.remove_style_class("used-workspace")

    # def _init_workspaces(self):
    #     """Mock events for initializing workspace module"""
    #     curr_workspace = self.i3_connector.i3.get_tree().find_focused().workspace().name
    #     mock_event = type("", (), {})()
    #     mock_event.current = type("", (), {})()
    #     mock_event.current.num = int(curr_workspace)
    #     self.set_active_window(self.i3_connector.i3, mock_event)

    # def switch_workspace(self, num):
    #     self.i3_connector.command(f"workspace {num + 1}")


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

        # self.active_window = Label(label="", name="active-window")
        # self.i3_connector = i3Connector._get_instance(active=self)

    # def setter_label(self, curr_window):
    #     self.active_window.set_label(curr_window)
