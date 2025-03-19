import fabric
from gi.repository import Gtk
import fabric
from fabric import Application
from fabric.widgets.label import Label
from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.datetime import DateTime
from fabric.widgets.centerbox import CenterBox
from fabric.utils import get_relative_path
from fabric.widgets.x11 import X11Window as Window

class ExpandableBar(Window):
    def __init__(self):
        super().__init__(title="Expandable Bar", size=(300, 100))
        
        # Bar Container
        self.bar = Box(
            style="background: #3498db; min-height: 50px; min-width: 100px; border-radius: 10px;",
            h_align="center",
            v_align="center",
        )

        # Button in the center
        self.button = Button(label="Expand", h_align="center", v_align="center")
        self.button.on("clicked", self.toggle_expand)

        # Animator for smooth expansion
        self.animator = (
            Animator(
                bezier_curve=(0.34, 1.56, 0.64, 1.0),  # Smooth easing
                duration=0.5,
                min_value=100,  # Initial width
                max_value=300,  # Expanded width
                tick_widget=self.bar,
                notify_value=lambda p, *_: self.bar.set_style(f"min-width: {p.value}px;"),
            )
            .build()
            .unwrap()
        )

        self.expanded = False  # Track state
        self.bar.add(self.button)
        self.set_child(self.bar)

    def toggle_expand(self, *_):
        if self.expanded:
            self.animator.min_value, self.animator.max_value = 300, 100  # Collapse
        else:
            self.animator.min_value, self.animator.max_value = 100, 300  # Expand
        
        self.expanded = not self.expanded
        self.animator.play()

# Run the application
app = ExpandableBar()
app.run()
