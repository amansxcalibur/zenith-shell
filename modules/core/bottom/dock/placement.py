import math
import cairo
from enum import Enum
from loguru import logger
from typing import NamedTuple
from dataclasses import dataclass

from config.config import config

MODULE_SIZE = 36  # px, a module's height (or width on a side dock)
MODULE_RADIUS = 18  # px, the corners of a fully rounded module
# the compact dock: holes reach the screen edge and hovered modules rise, with
# their padding in styles/dock_widget.css. Any other padding is equal all around.
COMPACT_PADDING = 2
COMPACT_MODULE_SIDE_PADDING = 3  # px, #dock-module's padding along the dock
DOCK_PADDING: int = config.get("bar.PADDING")  # px around each module


def edge_band(padding: int) -> int:
    """Px of dock left between a hole's floor and the screen edge."""
    return 0 if padding == COMPACT_PADDING else 4


DOCK_EDGE_BAND = edge_band(DOCK_PADDING)
DOCK_THICKNESS = MODULE_SIZE + 2 * DOCK_PADDING + DOCK_EDGE_BAND
PILL_RADIUS = 23  # px, the pill's corners
PILL_WINDOW_PADDING = 2  # px, #pill-container's padding around the visible pill
# how far the pill's hole reaches past its window to leave DOCK_PADDING all around
PILL_HOLE_EXTRA = DOCK_PADDING - PILL_WINDOW_PADDING


class DockEdge(Enum):
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"


class DockInsets(NamedTuple):
    """Space the dock takes from each screen side."""

    left: int = 0
    right: int = 0
    bottom: int = 0


@dataclass(frozen=True)
class DockPlacement:
    edge: DockEdge

    @property
    def vertical(self) -> bool:
        return self.edge is not DockEdge.BOTTOM

    @property
    def orientation(self) -> str:
        return "v" if self.vertical else "h"

    @property
    def seats_pill(self) -> bool:
        """Only a bottom dock has room for the pill to sit inside it."""
        return self.edge is DockEdge.BOTTOM

    @property
    def layer_anchor(self) -> str:
        return {
            DockEdge.BOTTOM: "bottom left right",
            DockEdge.LEFT: "left top bottom",
            DockEdge.RIGHT: "right top bottom",
        }[self.edge]

    @property
    def style_class(self) -> str:
        return f"dock-{self.edge.value}"

    @property
    def thickness_style(self) -> str:
        side = "min-width" if self.vertical else "min-height"
        return f"{side}: {DOCK_THICKNESS}px;"

    @property
    def module_padding_style(self) -> str | None:
        if DOCK_PADDING == COMPACT_PADDING:
            return None  # the stylesheet's, which changes when raised

        # equal all around a module; the band is extra on the screen's side
        gap, outer = DOCK_PADDING, DOCK_PADDING + DOCK_EDGE_BAND
        top, right, bottom, left = {
            DockEdge.BOTTOM: (gap, gap, outer, gap),
            DockEdge.LEFT: (gap, gap, gap, outer),
            DockEdge.RIGHT: (gap, outer, gap, gap),
        }[self.edge]
        return f"padding: {top}px {right}px {bottom}px {left}px;"

    def expand_along(self) -> dict[str, bool]:
        """Widget kwargs that make a widget grow along the dock."""
        return {"v_expand": True} if self.vertical else {"h_expand": True}

    def transform(self, cr: cairo.Context, width: int, height: int) -> None:
        """
        Map dock space onto the widget. In dock space x runs along the dock
        (left to right, or top to bottom) and y is the distance from the edge
        that faces the screen's centre, so y = thickness is the screen edge.
        """
        if self.edge is DockEdge.LEFT:
            cr.translate(width, 0)
            cr.rotate(math.pi / 2)
        elif self.edge is DockEdge.RIGHT:
            cr.rotate(math.pi / 2)
            cr.scale(1, -1)

    def length(self, width: int, height: int) -> int:
        return height if self.vertical else width

    def thickness(self, width: int, height: int) -> int:
        return width if self.vertical else height

    def along(self, x: int, y: int, width: int, height: int) -> tuple[int, int]:
        """(start, size) of a rectangle on the dock's main axis."""
        return (y, height) if self.vertical else (x, width)


def current_placement() -> DockPlacement:
    position = config.get("bar.POSITION")
    try:
        return DockPlacement(DockEdge(position))
    except ValueError:
        logger.warning(f"Unsupported bar.POSITION {position!r}, using 'bottom'")
        return DockPlacement(DockEdge.BOTTOM)
