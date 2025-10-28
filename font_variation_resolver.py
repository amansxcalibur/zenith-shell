from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.scale import Scale
from fabric.widgets.button import Button
from fabric.widgets.stack import Stack
from fabric.widgets.x11 import X11Window as Window
from fabric.utils import get_relative_path, monitor_file

from widgets.material_label import MaterialIconLabel, MaterialFontLabel

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango

# This could be a foundation for settings/config setup


class DragHandler:
    """Handles window dragging functionality"""

    def __init__(self, window):
        self.window = window
        self.dragging = False
        self.offset_x = 0
        self.offset_y = 0
        self.start_pos = None

    def on_button_press(self, source, event):
        if event.button == 1:
            self.dragging = True
            win_x, win_y = self.window.get_position()
            self.offset_x = event.x_root - win_x
            self.offset_y = event.y_root - win_y
            self.start_pos = (win_x, win_y)

    def on_motion(self, source, event):
        if not self.dragging:
            return

        new_x = int(event.x_root - self.offset_x)
        new_y = int(event.y_root - self.offset_y)

        self.window.get_window().move(new_x, new_y)

    def on_button_release(self, source, event):
        if event.button == 1 and self.dragging:
            self.dragging = False


class IconDemoTab:
    """Manages the icon demonstration tab with static and interactive examples"""

    DEMO_ICONS = ["\ue88a", "\ue8b6", "\ue8b8", "\ue5c8", "\ue3c9", "\ue3ab"]

    def __init__(self):
        self.container = Box(name="resolver-container", orientation="v", spacing=20)
        self.icon_widget = None
        self.fill_scale = None
        self.wght_scale = None
        self.grad_scale = None
        self.opsz_scale = None

        self._build_ui()

    def _build_ui(self):
        title = Label(markup="<b>Material Icon Label Test</b>")
        self.container.pack_start(title, False, False, 0)

        self._add_static_examples()
        self._add_interactive_demo()

    def _add_static_examples(self):
        frame = Gtk.Frame(label="Static Examples")
        frame.set_label_align(0.1, 0.4)

        examples_box = Box(
            orientation="h",
            spacing=20,
            children=[
                self._create_example(fill=0, wght=100),
                self._create_example(fill=0, wght=400),
                self._create_example(fill=1, wght=700),
                self._create_example(fill=1, wght=400, grad=200),
            ],
        )
        examples_box.set_border_width(10)

        frame.add(examples_box)
        self.container.add(frame)

    def _create_example(self, fill, wght, grad=0):
        return Box(
            orientation="v",
            spacing=5,
            children=[
                MaterialIconLabel("\ue88a", size=48, fill=fill, wght=wght, grad=grad),
                Label(label=f"FILL={fill}\nwght={wght}\nGRAD={grad}"),
            ],
        )

    def _add_interactive_demo(self):
        frame = Gtk.Frame(label="Interactive Demo")
        frame.set_label_align(0.1, 0.4)
        box = Box(orientation="v", spacing=10)
        box.set_border_width(10)

        # main icon
        self.icon_widget = MaterialIconLabel("\ue88a", size=64, fill=1, wght=400)
        box.pack_start(self.icon_widget, False, False, 10)

        # control sliders
        self.fill_scale = self._create_slider(box, "FILL", 0, 1, 0.1, 1)
        self.wght_scale = self._create_slider(box, "wght", 100, 700, 50, 400)
        self.grad_scale = self._create_slider(box, "GRAD", -25, 200, 25, 0)
        self.opsz_scale = self._create_slider(box, "OPSZ", 10, 200, 25, 0)

        # icon selection buttons
        box.pack_start(self._create_icon_selector(), False, False, 0)

        frame.add(box)
        self.container.pack_start(frame, True, True, 0)

    def _create_slider(self, parent, label, min_val, max_val, step, default):
        scale_box = Box(orientation="h", spacing=10)
        scale_box.pack_start(
            Label(style_classes=["variation-type-label"], label=f"{label}:"),
            False,
            False,
            0,
        )

        scale = Scale(
            name="control-slider-mui",
            style_classes=["variation-scale"],
            orientation="h",
            min_value=min_val,
            max_value=max_val,
            increments=(step, step),
            h_expand=True,
        )
        scale.set_value(default)
        scale.connect("value-changed", self._update_icon)

        scale_box.pack_start(scale, True, True, 0)
        parent.pack_start(scale_box, False, False, 0)
        return scale

    def _create_icon_selector(self):
        icon_box = Box(orientation="h", spacing=10)
        icon_box.pack_start(Label(label="Icon:"), False, False, 0)

        for icon_char in self.DEMO_ICONS:
            btn = Button(
                label=icon_char,
                on_clicked=lambda w, ic=icon_char: self._change_icon(ic),
            )
            btn_label = btn.get_child()
            btn_label.modify_font(
                Pango.FontDescription.from_string("Material Symbols Rounded 24")
            )
            icon_box.pack_start(btn, False, False, 0)

        return icon_box

    def _change_icon(self, icon_char):
        self.icon_widget.set_icon(icon_char)

    def _update_icon(self, widget):
        self.icon_widget.set_variations(
            FILL=self.fill_scale.get_value(),
            wght=int(self.wght_scale.get_value()),
            GRAD=int(self.grad_scale.get_value()),
            opsz=int(self.opsz_scale.get_value()),
        )


class FontDemoTab:
    """Manages the font variation demonstration tab"""

    SLIDER_CONFIGS = [
        ("wght", 100, 1000, 50),
        ("GRAD", -200, 150, 1),
        ("OPSZ", 6, 144, 1),
        ("wdth", 25, 151, 1),
        ("ital", 0, 1, 1),
        ("slnt", -10, 0, 1),
        ("XTRA", 323, 603, 1),
    ]

    def __init__(self):
        self.container = None
        self.font_label = None
        self.locked = False
        self.scales = {}
        self.master_scale = None

        self._build_ui()

    def _build_ui(self):
        """Build the complete font demo tab"""
        frame = Gtk.Frame(label="Font Variation Demo")
        frame.set_label_align(0.1, 0.4)
        box = Box(name="resolver-container", orientation="v", spacing=10)
        box.set_border_width(10)

        # main font label
        self.font_label = MaterialFontLabel("WOW", size=64, fill=1, wght=400)
        box.pack_start(self.font_label, False, False, 10)

        # lock toggle
        self.lock_btn = Button(label="Lock OFF")
        self.lock_btn.connect("clicked", self._toggle_lock)
        box.pack_start(self.lock_btn, False, False, 0)

        # master control slider
        self.master_scale = self._create_slider(box, "master", 0, 100, 1, 0)

        # individual variation sliders
        for name, min_val, max_val, step in self.SLIDER_CONFIGS:
            self.scales[name] = self._create_slider(
                box, name, min_val, max_val, step, 0
            )

        frame.add(box)
        self.container = frame

    def _create_slider(self, parent, label, min_val, max_val, step, default):
        scale_box = Box(orientation="h", spacing=10)
        scale_box.pack_start(
            Label(style_classes=["variation-type-label"], label=f"{label}:"),
            False,
            False,
            0,
        )

        scale = Scale(
            name="control-slider-mui",
            style_classes=["variation-scale"],
            orientation="h",
            min_value=min_val,
            max_value=max_val,
            increments=(step, step),
            h_expand=True,
        )
        scale.set_value(default)
        scale.connect("value-changed", self._update_font)

        scale_box.pack_start(scale, True, True, 0)
        parent.pack_start(scale_box, False, False, 0)
        return scale

    def _toggle_lock(self, button):
        self.locked = not self.locked
        button.set_label("Lock ON" if self.locked else "Lock OFF")
        self._update_font(None)

    def _update_font(self, widget):
        if self.locked:
            self._apply_master_control()

        self.font_label.set_variations(
            wght=int(self.scales["wght"].get_value()),
            GRAD=int(self.scales["GRAD"].get_value()),
            opsz=int(self.scales["OPSZ"].get_value()),
            wdth=int(self.scales["wdth"].get_value()),
            ital=int(self.scales["ital"].get_value()),
            slnt=int(self.scales["slnt"].get_value()),
            XTRA=int(self.scales["XTRA"].get_value()),
        )

    def _apply_master_control(self):
        """Apply master slider value to all variation sliders"""
        master_val = self.master_scale.get_value()

        updates = {
            "wght": self._scale_value(master_val, "wght"),
            "GRAD": self._scale_value(master_val, "GRAD"),
            "OPSZ": self._scale_value(100 - master_val, "OPSZ"),  # Inverted
            "wdth": self._scale_value(master_val, "wdth"),
            "slnt": self._scale_value(100 - master_val, "slnt"),  # Inverted
            "XTRA": self._scale_value(master_val, "XTRA"),
        }

        # update sliders without triggering callbacks
        for name, value in updates.items():
            scale = self.scales[name]
            scale.handler_block_by_func(self._update_font)
            scale.set_value(value)
            scale.handler_unblock_by_func(self._update_font)

    def _scale_value(self, master_val, scale_name):
        """Scale master value to target range"""
        scale = self.scales[scale_name]
        min_val = scale.min_value
        max_val = scale.max_value
        return int(min_val + master_val * (max_val - min_val) / 100)


class TabConfig:
    """Configuration for a settings tab"""

    def __init__(self, id, label, icon, widget_factory, category=None):
        self.id = id
        self.label = label
        self.icon = icon
        self.widget_factory = widget_factory
        self.category = category
        self._widget = None

    @property
    def widget(self):
        """Lazy-load the widget on first access"""
        if self._widget is None:
            self._widget = self.widget_factory()
        return self._widget


class IconResolverWindow(Window):
    def __init__(self):
        super().__init__(
            layer="top",
            geometry="center",  # This prevents the window from snapping back to its init pos
                                # when it loses focus. You can also remove the size-reallocate 
                                # hook in the source to prevent snap back. See PopupWindow.
            type_hint="dialog",
            visible=True,
            all_visible=True,
        )

        self.buttons = {}
        self.stack = None
        self.drag_handler = DragHandler(self)
        self.tabs = self._register_tabs()

        self._build_ui()
        self._setup_drag_events()

    def _register_tabs(self):
        return [
            TabConfig(
                id="icon_variations",
                label="Icon Variations",
                icon="\ue3ab",
                widget_factory=lambda: IconDemoTab().container,
                category="Appearance",
            ),
            TabConfig(
                id="font_variations",
                label="Font Variations",
                icon="\ue167",
                widget_factory=lambda: FontDemoTab().container,
                category="Appearance",
            ),
            # ...
        ]

    def _build_ui(self):
        main_box = Box(
            name="settings", orientation="h", spacing=20, h_expand=True, v_expand=True
        )

        # create stack and switcher
        switch_box = self._create_tab_switcher()

        main_box.add(switch_box)
        main_box.add(self.stack)

        self.children = main_box

    def _create_tab_switcher(self):
        switch_box = Box(name="stack-switcher", orientation="v", spacing=2)
        self.stack = Stack(name="settings-stack")

        # group tabs by category if needed
        current_category = None
        for tab_config in self.tabs:
            if tab_config.category and tab_config.category != current_category:
                if current_category is not None:  # Not first category
                    separator = Box(name="category-separator", spacing=0)
                    separator.set_size_request(-1, 10)
                    switch_box.pack_start(separator, False, False, 0)
                current_category = tab_config.category

            # create button for this tab
            button = self._create_tab_button(tab_config)
            switch_box.pack_start(button, False, False, 0)

            # add widget to stack (lazy-loaded)
            self.stack.add_titled(tab_config.widget, tab_config.id, tab_config.label)

        return switch_box

    def _create_tab_button(self, tab_config):
        button = Button(style_classes=["settings-option-btn"])
        box = Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        icon = MaterialIconLabel(icon_text=tab_config.icon, size=17)
        label = Label(style_classes=["settings-option-label"], markup=tab_config.label)

        box.pack_start(icon, False, False, 0)
        box.pack_start(label, False, False, 0)
        button.add(box)

        button.connect("clicked", lambda b: self._on_tab_clicked(tab_config.id))
        self.buttons[tab_config.id] = button

        return button

    def _on_tab_clicked(self, tab_id):
        self.stack.set_visible_child_name(tab_id)
        self._set_active_tab(tab_id)

    def _set_active_tab(self, tab_id):
        for key, btn in self.buttons.items():
            if key == tab_id:
                btn.add_style_class("checked")
            else:
                btn.remove_style_class("checked")

    def _setup_drag_events(self):
        self.connect("button-press-event", self.drag_handler.on_button_press)
        self.connect("motion-notify-event", self.drag_handler.on_motion)
        self.connect("button-release-event", self.drag_handler.on_button_release)


def main():
    win = IconResolverWindow()
    win.show_all()

    app = Application("material-icon-test", test_window=win, open_inspector=True)

    def load_css(*args):
        app.set_stylesheet_from_file(get_relative_path("./main.css"))

    app.style_monitor = monitor_file(get_relative_path("./styles"))
    app.style_monitor.connect("changed", load_css)
    load_css()

    app.run()


if __name__ == "__main__":
    main()
