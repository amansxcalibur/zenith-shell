from fabric import Application
from fabric.widgets.x11 import X11Window as Window
from fabric.widgets.widget import Widget
from fabric.widgets.button import Button
from fabric.utils import get_relative_path

class ExpandingBar(Widget):
    def __init__(self, expanded=False):
        super().__init__()
        self.expanded = expanded
        print("Init")
        self.classy = "expanding-bar" if expanded else "collapsed-bar"

    def toggle(self):
        self.expanded = not self.expanded
        print("hello", self.expanded, self.classy)
        self.classy = "expanding-bar" if self.expanded else "collapsed-bar"
        return self.classy

class ExpandingBarApp(Window):
    def __init__(self):
        super().__init__()
        self.bar = ExpandingBar(expanded=False)
        # self.button = Button(label="Toggle Bar", on_clicked=self.toggle_bar)
        self.children = Button(label="toggle-bar", name=self.bar.classy, on_clicked=lambda b, *_:b.set_name(self.bar.toggle()))
        # self.main = Container(self.bar, self.button)"expanding-bar"

    def toggle_bar(self, _):
        self.bar.toggle()


bar = ExpandingBarApp()
app = Application('bar', bar)
app.set_stylesheet_from_file(get_relative_path('style.css'))
app.run()
