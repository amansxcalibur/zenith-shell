from i3ipc import Connection, Event
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
import threading

# class i3Window:
#     def __init__(self):
#         pass
class i3Connector:
    _instance = None
    _thread = None

    @classmethod
    def _get_instance(cls, **kwargs):
        if cls._instance == None:
            cls._instance = i3Connector(**kwargs)
        return cls._instance

    def __init__(self, **kwargs):
        self.workspace = kwargs["workspace"]
        self.i3 = Connection()

        self.callbacks = {
            Event.WORKSPACE: []
        }

        self.focused = self.i3.get_tree().find_focused()
        print(self.focused.name, self.focused.workspace().name)
        # i3.command("focus left")
        for con in self.i3.get_tree():
            print(con.name)
        self.i3.on(Event.WORKSPACE_FOCUS, self.on_workspace_focus)
        self.i3.on(Event.WINDOW_FOCUS, self.on_window_focus)
        # self.i3.main()

    def on_workspace_focus(self, i3, e):
        if e.current:
            print("Window in workspacez", e.current.num)
            # for w in e.current.leaves():
            #     print(w)
            # self.workspace.set_active_window(e.current.num)
            for callback in self.callbacks[Event.WORKSPACE]:
                callback(i3, e)
                print("hihi")

    def on_window_focus(self, i3, e):
        focused = i3.get_tree().find_focused()
        ws_name = "%s %s" % (focused.workspace().num, focused.window_class)
        print(ws_name)
        self.workspace.setter_label(ws_name)

    def start(self):
        if self._thread is None or not self.thread.is_alive():
            self._thread = threading.Thread(target=self.i3.main, daemon=True)
            self._thread.start()

    def register_callback(self, event_type, callback):
        print(event_type)
        if event_type in self.callbacks:
            self.callbacks[event_type].append(callback)
            print("its in there")

class Workspaces(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="workspaces",
            visible=True,
            all_visible=True,
            orientation="h",
            h_align="fill",
            v_align="center"
        )

        self.i3 = i3Connector._get_instance(workspace=self)
        self.i3.start()

        self.i3.register_callback(Event.WORKSPACE, self.set_active_window)

        self.active_window = Label(label="hello workspaces")
        self.all_workspaces = Box(children = self.buttons())
        self.children = Box(children=[self.active_window, self.all_workspaces])
    
    def setter_label(self, ws_name):
        # change label
        self.active_window.set_label(ws_name)
        # print("Printing label window")

    def buttons(self):
        buttons=[]
        for i in range(10):
            buttons.append(Button(name="%i" % (i+1), label="%i" % (i+1)))
            if i==0:
                buttons[i].add_style_class("active-workspace")
            else:
                buttons[i].add_style_class("workspace-button")
        return buttons
    
    def set_active_window(self, i3, e):
        print("hererer", e.current.num)
        # curr_workspace = self.i3.get_tree().find_focused().workspace()
        curr_workspace = e.current.num-1
        for i, btn in enumerate(self.all_workspaces.children):
            if i==curr_workspace:
                btn.remove_style_class("workspace-button")
                btn.add_style_class("active-workspace")
                print(btn)
            else:
                btn.remove_style_class("active-workspace")
                btn.add_style_class("workspace-button")