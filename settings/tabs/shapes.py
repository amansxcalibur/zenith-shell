from expressive_shapes.shapes.shape_presets import (
    fan,
    gem,
    bun,
    pill,
    star,
    oval,
    arch,
    boom,
    heart,
    arrow,
    sunny,
    flower,
    shield,
    circle,
    square,
    slanted,
    diamond,
    triangle,
    pentagon,
    cookie_4,
    cookie_8,
    clamshell,
    ghost_ish,
    cookie_12,
    very_sunny,
    semicircle,
    pixel_circle,
    organic_blob,
    leaf_clover_4,
    leaf_clover_8,
    puffy_diamond,
    pixel_triangle,
)

from fabric.widgets.box import Box
from fabric.widgets.label import Label
from widgets.clipping_box import ClippingBox
from widgets.shapes.expressive.morphing_shapes import ExpressiveShape

from ..base import BaseWidget, SectionBuilderMixin, LayoutBuilder

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class ShapesTab(BaseWidget, SectionBuilderMixin):
    """Display launcher integrated modules"""

    COLUMNS: int = 4
    SHAPE_SIZE: int = 120

    def _build_ui(self):
        self.container = Box(orientation="v", spacing=25)

        self.shapes = [
            {"name": "Circle", "obj": circle},
            {"name": "Square", "obj": square},
            {"name": "Slanted", "obj": slanted},
            {"name": "Arch", "obj": arch},
            {"name": "Semicircle", "obj": semicircle},
            {"name": "Oval", "obj": oval},
            {"name": "Pill", "obj": pill},
            {"name": "Triangle", "obj": triangle},
            {"name": "Arrow", "obj": arrow},
            {"name": "Fan", "obj": fan},
            {"name": "Diamond", "obj": diamond},
            {"name": "Clamshell", "obj": clamshell},
            {"name": "Pentagon", "obj": pentagon},
            {"name": "Gem", "obj": gem},
            {"name": "Very Sunny", "obj": very_sunny},
            {"name": "Sunny", "obj": sunny},
            {"name": "Cookie-4", "obj": cookie_4},
            {"name": "Cookie-8", "obj": cookie_8},
            {"name": "Cookie-12", "obj": cookie_12},
            {"name": "Clover-4", "obj": leaf_clover_4},
            {"name": "Clover-8", "obj": leaf_clover_8},
            {"name": "Boom", "obj": boom},
            {"name": "Puffy Diamond", "obj": puffy_diamond},
            {"name": "Flower", "obj": flower},
            {"name": "Ghost-ish", "obj": ghost_ish},
            {"name": "Pixel Circle", "obj": pixel_circle},
            {"name": "Pixel Triangle", "obj": pixel_triangle},
            {"name": "Bun", "obj": bun},
            {"name": "Heart", "obj": heart},
            {"name": "Organic Blob", "obj": organic_blob},
            {"name": "Shield", "obj": shield},
            {"name": "Star", "obj": star},
        ]

        self.container.add(
            LayoutBuilder.section(
                "Expressive Shapes",
                Box(
                    orientation="v",
                    children=[
                        Label(
                            style_classes="section-subheading",
                            style="margin-bottom: 5px",
                            h_align="start",
                            label="These are shrines of god. You may worship them",
                        ),
                        Box(
                            children=ClippingBox(
                                children=self.build_grid(),
                                h_expand=True,
                                v_expand=True,
                                style="border-radius: 17px;",
                            ),
                            style="border: solid 1px var(--surface-bright); border-radius: 17px;",
                        ),
                    ],
                ),
            )
        )

    def build_grid(self) -> Box:
        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_name("settings-shapes-flowbox")
        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.flowbox.set_activate_on_single_click(True)
        self.flowbox.set_column_spacing(1)
        self.flowbox.set_row_spacing(1)
        self.flowbox.set_homogeneous(True)
        self.flowbox.set_max_children_per_line(self.COLUMNS)
        self.flowbox.set_min_children_per_line(self.COLUMNS)
        self.flowbox.set_vexpand(False)
        self.flowbox.set_hexpand(True)
        self.flowbox.set_valign(Gtk.Align.START)

        for shape_data in self.shapes:
            shape_widget = ExpressiveShape(
                name="settings-shapes-morph", shape=shape_data["obj"]
            )
            shape_widget.set_size_request(self.SHAPE_SIZE, self.SHAPE_SIZE)

            name_label = Label(
                label=shape_data["name"],
                style_classes="shape-grid-label",
            )

            tile = Box(
                orientation="v",
                style="background-color:var(--surface-dull); padding: 10px",
                children=[shape_widget, name_label],
            )

            self.flowbox.add(tile)

        self.flowbox.show_all()
        return self.flowbox
