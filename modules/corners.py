from fabric.widgets.box import Box
from fabric.widgets.shapes import Corner

from widgets.overrides import PatchedX11Window as Window


class MyCorner(Box):
    def __init__(self, corner, radius: int):
        super().__init__(
            name="corner-container",
            children=Corner(
                name="corner",
                orientation=corner,
                size=radius,
            ),
        )


class Corners(Window):
    def __init__(self, radius: int):
        super().__init__(
            name="notch",
            layer="top",
            geometry="top",
            type_hint="normal",
            focusable=False,
            margin="-8px -4px -8px -4px",
            visible=True,
            pass_through=True,
            all_visible=True,
            opacity=0.5,
        )

        self.all_corners = Box(
            name="all-corners",
            orientation="v",
            pass_through=True,
            focusable=False,
            h_expand=True,
            v_expand=True,
            h_align="fill",
            v_align="fill",
            children=[
                Box(
                    name="top-corners",
                    orientation="h",
                    h_align="fill",
                    children=[
                        MyCorner("top-left", radius),
                        Box(h_expand=True),
                        MyCorner("top-right", radius),
                    ],
                ),
                Box(v_expand=True),
                Box(
                    name="bottom-corners",
                    orientation="h",
                    h_align="fill",
                    children=[
                        MyCorner("bottom-left", radius),
                        Box(h_expand=True),
                        MyCorner("bottom-right", radius),
                    ],
                ),
            ],
        )

        self.add(self.all_corners)

        self.show_all()
