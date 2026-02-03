from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from widgets.material_label import MaterialIconLabel, MaterialFontLabel

import icons
from ..base import BaseWidget, SliderConfig, SliderControlMixin, LayoutBuilder


class IconVariationsTab(BaseWidget, SliderControlMixin):

    DEMO_ICONS = [icons.home.symbol(), icons.search.symbol(), icons.settings_material.symbol(), icons.arrow_forward.symbol(), icons.edit_material.symbol(), icons.brightness_material.symbol()]

    def __init__(self):
        SliderControlMixin.__init__(self)
        self.icon_widget = None
        BaseWidget.__init__(self)

    def _build_ui(self):
        self.container = Box(name="resolver-container", orientation="v", spacing=20)

        self._add_static_examples()
        self._add_interactive_demo()

        self.container.add(Box(v_expand=True))

    def _add_static_examples(self):
        examples = Box(
            orientation="h",
            spacing=20,
            children=[
                self._create_example(fill=0, wght=100),
                self._create_example(fill=0, wght=400),
                self._create_example(fill=1, wght=700),
                self._create_example(fill=1, wght=400, grad=200),
            ],
        )

        self.container.add(LayoutBuilder.section("Static Examples", examples))

    def _create_example(self, fill, wght, grad=0):
        return Box(
            orientation="v",
            spacing=5,
            children=[
                MaterialIconLabel(
                    icon_text=icons.home.symbol(), font_size=48, FILL=fill, wght=wght, GRAD=grad
                ),
                Label(label=f"FILL={fill}\nwght={wght}\nGRAD={grad}"),
            ],
        )

    def _add_interactive_demo(self):
        self.icon_widget = MaterialIconLabel(
            icon_text=icons.home.symbol(), font_size=64, fill=1, wght=400
        )
        icon_box = Box(orientation="v", style='min-width: 200px', children=self.icon_widget)

        # Create sliders using mixin
        slider_configs = [
            SliderConfig("FILL", 0, 1, 0.1, 1),
            SliderConfig("wght", 100, 700, 50, 400),
            SliderConfig("GRAD", -25, 200, 25, 0),
            SliderConfig("opsz", 20, 48, 4, 48),
        ]
        slider_box = Box(orientation="v", h_expand=True, spacing=10)
        self.create_sliders(slider_box, slider_configs, self._update_icon)

        icon_list_box = self._create_icon_selector()
        icon_control_box = Box(children=[icon_box, slider_box])

        box = Box(
            orientation="v",
            spacing=20,
            children=[
                icon_list_box,
                icon_control_box,
            ],
        )

        self.container.pack_start(
            LayoutBuilder.section("Interactive Demo", box), True, True, 0
        )

    def _create_icon_selector(self):
        icon_box = Box(name='config-path-box', h_align='start')
        icon_box.add(Label(label="Icons:", style='margin-right: 10px'))

        for icon_char in self.DEMO_ICONS:
            btn = Button(
                child=MaterialIconLabel(icon_text=icon_char, font_size=24),
                on_clicked=lambda w, ic=icon_char: self.icon_widget.set_icon(ic),
            )
            icon_box.add(btn)

        return icon_box

    def _update_icon(self, widget):
        if self._updating:
            return

        self.icon_widget.set_variations(
            FILL=self.scales["FILL"].get_value(),
            wght=int(self.scales["wght"].get_value()),
            GRAD=int(self.scales["GRAD"].get_value()),
            opsz=int(self.scales["opsz"].get_value()),
        )


class FontVariationsTab(BaseWidget, SliderControlMixin):

    SLIDER_CONFIGS = [
        SliderConfig("wght", 100, 1000, 50),
        SliderConfig("GRAD", -200, 150, 1),
        SliderConfig("OPSZ", 6, 144, 1),
        SliderConfig("wdth", 25, 151, 1),
        SliderConfig("ital", 0, 1, 1),
        SliderConfig("slnt", -10, 0, 1),
        SliderConfig("XTRA", 323, 603, 1),
    ]

    def __init__(self):
        SliderControlMixin.__init__(self)
        self.font_label = None
        self.locked = False
        self.master_scale = None
        BaseWidget.__init__(self)

    def _build_ui(self):
        box = Box(name="resolver-container", orientation="v", spacing=10)

        self.font_label = MaterialFontLabel("WOW", font_size=64, fill=1, wght=400)
        box.pack_start(self.font_label, False, False, 10)

        self.lock_btn = Button(label="Lock OFF", on_clicked=self._toggle_lock)
        box.pack_start(self.lock_btn, False, False, 0)

        self.master_scale = LayoutBuilder.labeled_slider(
            box, "master", 0, 100, 1, 0, self._update_font
        )

        self.create_sliders(box, self.SLIDER_CONFIGS, self._update_font)

        self.container = LayoutBuilder.section("Font Variation Demo", box)

    def _toggle_lock(self, button):
        self.locked = not self.locked
        button.set_label("Lock ON" if self.locked else "Lock OFF")
        self._update_font(None)

    def _update_font(self, widget):
        if self._updating:
            return

        if self.locked:
            self._apply_master_control()

        values = self.get_slider_values()
        self.font_label.set_variations(
            wght=int(values["wght"]),
            GRAD=int(values["GRAD"]),
            opsz=int(values["OPSZ"]),
            wdth=int(values["wdth"]),
            ital=int(values["ital"]),
            slnt=int(values["slnt"]),
            XTRA=int(values["XTRA"]),
        )

    def _apply_master_control(self):
        master_val = self.master_scale.get_value()

        updates = {
            "wght": self._scale_value(master_val, "wght"),
            "GRAD": self._scale_value(master_val, "GRAD"),
            "OPSZ": self._scale_value(100 - master_val, "OPSZ"),
            "wdth": self._scale_value(master_val, "wdth"),
            "slnt": self._scale_value(100 - master_val, "slnt"),
            "XTRA": self._scale_value(master_val, "XTRA"),
        }

        self.batch_update_sliders(updates)

    def _scale_value(self, master_val, scale_name):
        scale = self.scales[scale_name]
        return int(
            scale.min_value + master_val * (scale.max_value - scale.min_value) / 100
        )
