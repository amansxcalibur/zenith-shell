from fabric.widgets.box import Box
from fabric.widgets.label import Label
import icons.icons as icons

class Tile(Box):
    def __init__(self, *, menu: bool, markup: str, label: str, props: Label, **kwargs):
        super().__init__(style_classes="tile", **kwargs)
        self.props = props
        self.icon = Label(style_classes="tile-icon", markup=markup)
        self.tile_label = Label(
            style_classes="tile-label", label=label, h_align="start"
        )

        self.type_box = Box(
            style_classes="tile-type",
            orientation="v",
            v_expand=True,
            h_expand=True,
            v_align="center",
            children=[self.tile_label, self.props],
        )

        self.children = [self.icon, self.type_box] + (
            [Label(style_classes="tile-icon", markup=icons.arrow_head)] if menu else []
        )
