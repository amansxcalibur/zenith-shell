from fabric import Application, Fabricator
from fabric.widgets.x11 import X11Window as Window
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.datetime import DateTime
from fabric.widgets.centerbox import CenterBox
from fabric.utils import get_relative_path


# lambda symbols
# f: is the fabricator itself, v: is the new value
counter_fabricator = Fabricator(
    interval=50,  # ms
    default_value=0,
    poll_from=lambda f: f.get_value() + 1,
    on_changed=lambda f, v: (
        (f.stop(), print("Counter Stopped"))
        if v == 43
        else print(f"Counter Value: {v}")
    ),
)

# example output:
# Counter Value: 1
# Counter Value: 2
# Counter Value: 3
# ...
# Counter Value: 42
# Counter Stopped

weather_fabricator = Fabricator(
    interval=1000 * 60,  # 1min
    poll_from="curl https://wttr.in/?format=Weather+in+%l:+%t+(Feels+Like+%f),+%C+%c",
    on_changed=lambda f, v: print(v.strip()),
)

# example output:
# Weather in Homenland:, +15°C (Feels Like +15°C), Clear ☀️
# ...

date_fabricator = Fabricator(
    interval=500,
    poll_from="date",
    on_changed=lambda f, v: print(f"Current Date: {v.strip()}"),
)

# example output:
# current date and time: Fri Nov 29 03:45:32 AM EET 2024
# current date and time: Fri Nov 29 03:45:32 AM EET 2024
# ...


# example output:
# [Playing] Something - HomenArtsHouse
# [Paused] Something - HomenArtsHouse
# [Playing] The Stars - HomenArtsHouse
# ...


# NOTE: this is just an example, the use of something like os would be better
documents_fabricator = Fabricator(
    interval=1000,  # 1 second
    poll_from="du -sh /home/aman/Documents/",  # NOTE: edit this
    on_changed=lambda f, v: print(f"Size of Documents: {v.split()[0]}"),
)

# example output:
# Size of Documents: 1G
# Size of Documents: 1.1G
# ...

class Bar(Window):
    def __init__(self, **kwargs):
        super().__init__(
            name="status-bar",
            layer="overlay",
            geometry="top",
            type_hint="dock", #"notification" in case the polybar reserves space at the top
            **kwargs
        )
        # self.set_name("status-bar") 
        # self.children = Box(
        #   orientation="v",
        #   children=[
        #     # Label(label="Fabric Buttons Demo", name="hello"),
        #     CenterBox(
        #       # orientation="h",
        #       center_children=[
        #         CenterBox(
        #             label="L",
        #             name="left", 
        #             center_children=[Label(label="L", name="left-in")]
        #             ),
        #         Label(label="aman@brewery", name="middle"),
        #         CenterBox(
        #             label="R",
        #             name="right", 
        #             center_children=[Label(label="R", name="right-in")]
        #             )
        #       ],
        #     ),
        #   ],
        # )
        self.weather_label = Label(label="Weather: ...")
        weather_fabricator.connect("changed", lambda _, v:self.weather_label.set_label(f"{v}"))
        weather_fabricator.start()
        self.children = CenterBox(
            center_children=self.weather_label
        )
        self.connect("button-press-event", self.on_click)
        self.set_properties("_NET_WM_STATE", ["_NET_WM_STATE_ABOVE"])
        self.set_properties("_NET_WM_WINDOW_TYPE", ["_NET_WM_WINDOW_TYPE_DOCK"])
    
    def on_click(self, widget, event):
        """Toggles size when clicked."""
        if self.height == 40:  # Default height
            self.height = 800  # Expand
            self.centerbox.spacing = 20  # Increase spacing
        else:
            self.height = 40  # Shrink
            self.centerbox.spacing = 10  


if __name__ == "__main__":
    bar = Bar()
    app = Application("bar-example-test2", bar)

    # FASS-based CSS file
    # app.set_stylesheet_from_file(get_relative_path("main.css"))

    app.run()
