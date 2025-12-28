# Author: Yousef EL-Darsh
# License (SPDX): AGPL-3.0-or-later

import math
import cairo
from typing import cast
from fabric.widgets.box import Box


class ClippingBox(Box):
    """A regular `Box` that replicates the CSS behaviour of `overflow: hidden` because GTK failed at it."""

    @staticmethod
    def render_shape(cr: cairo.Context, width: int, height: int, radius: int = 0):
        radius = max(0, min(radius, width / 2, height / 2))

        if radius == 0:
            cr.rectangle(0, 0, width, height)
            return

        cr.move_to(radius, 0)
        cr.line_to(width - radius, 0)
        cr.arc(width - radius, radius, radius, -(math.pi / 2), 0)
        cr.line_to(width, height - radius)
        cr.arc(width - radius, height - radius, radius, 0, (math.pi / 2))
        cr.line_to(radius, height)
        cr.arc(radius, height - radius, radius, (math.pi / 2), math.pi)
        cr.line_to(0, radius)
        cr.arc(radius, radius, radius, math.pi, (3 * (math.pi / 2)))

        return cr.close_path()

    def do_draw(self, cr: cairo.Context):
        cr.save()
        ClippingBox.render_shape(
            cr,
            self.get_allocated_width(),
            self.get_allocated_height(),
            cast(
                int,
                self.get_style_context().get_property(
                    "border-radius", self.get_state_flags()
                ),
            ),
        )
        cr.clip()

        Box.do_draw(self, cr)

        cr.restore()
        return True