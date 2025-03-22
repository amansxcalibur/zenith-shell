import fabric
from fabric import Application
from fabric.widgets.widget import Widget
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.datetime import DateTime
from fabric.widgets.button import Button
from fabric.widgets.centerbox import CenterBox
from fabric.utils import get_relative_path
from fabric.widgets.x11 import X11Window as Window

class DockBar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="status-bar",
            layer="overlay",
            geometry="top",
            type_hint="dock",
            # type="normal",
            **kwargs
        )
        self.children = Box(
          orientation="v",
          children=[
            # Label(label="Fabric Buttons Demo", name="hello"),
            CenterBox(
              # orientation="h",
              center_children=[
                # CenterBox(
                #     label="L",
                #     name="left",
                #     center_children=[Label(label="L", name="left-in")]
                #     ),
                Label(label="aman@brewery", name="middle"),
                # CenterBox(
                #     label="R",
                #     name="right", 
                #     center_children=[Label(label="R", name="right-in")]
                #     )
              ],
            ),
          ],
        )
        self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])
        # self.date_time = DateTime()
        # self.children = CenterBox(center_children=self.date_time)

class ExpandingBar(Widget):
    def __init__(self, expanded=False):
        super().__init__()
        self.expanded = expanded
        print("Init")
        self.classy = "expanding-bar" if expanded else "collapsed-bar"

    def toggle(self, b):
        self.expanded = not self.expanded
        print("hello", self.expanded, self.classy)
        self.classy = "expanding-bar" if self.expanded else "collapsed-bar"
        if self.expanded:
          b.set_label("Might add something here")
        else:
          b.set_label("aman@brewery")
        return self.classy

class StatusBar(Window):
  def __init__(self, **kwargs):
      super().__init__(
          name="status-bar",
          layer="overlay",
          geometry="top",
          type_hint="notification", #"notification" in case the polybar reserves space at the top else "dock"
          **kwargs
      )
      self.set_name("status-bar") 
      self.bar = ExpandingBar(expanded=False)
      self.children = Box(
        orientation="v",
        children=[
          # Label(label="Fabric Buttons Demo", name="hello"),
          CenterBox(
            # orientation="h",
            center_children=[
              CenterBox(
                  label="L",
                  name="left", 
                  v_align="start",
                  center_children=[Label(label="L", name="left-dum", v_expand=False)],
                  v_expand=False
                  ),
              Button(label="aman@brewery", name=self.bar.classy, on_clicked=lambda b, *_:b.set_name(self.bar.toggle(b))),
              CenterBox(
                  label="R",
                  name="right", 
                  v_align="start",
                  center_children=[Label(label="R", name="right-dum", v_expand=False)],
                  v_expand=False
                  ),
            ],
          ),
        ],
      )
      self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
      self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])
      # self.date_time = DateTime()
      # self.children = CenterBox(center_children=self.date_time)

        

if __name__ == "__main__":
    bar = StatusBar()
    dockBar = DockBar()
    dockApp = Application('placeholder-dock', dockBar)
    app = Application("bar-example", bar)

    # FASS-based CSS file
    
    app.set_stylesheet_from_file(get_relative_path("./styles/main.css"))

    app.run()
