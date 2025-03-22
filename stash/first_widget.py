import fabric
from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.window import Window
from fabric.utils import get_relative_path

def create_button(): # define a "factory function"
    return Button(label="Click Me", on_clicked=lambda b, *_: b.set_label("you clicked me"))


if __name__ == "__main__":
    box = Box(
      orientation="v",
      children=[
        Label(label="Fabric Buttons Demo", style="color:red"),
        Box(
          orientation="h",
          children=[
            create_button(),
            create_button(),
            create_button(),
            create_button(),
          ],
        ),
      ],
    )
    window = Window(child=box)
    app = Application("default", window)
    # app.set_stylesheet_from_file(get_relative_path("main.css"))

    app.run()