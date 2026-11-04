import math
from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple

import cairo
from loguru import logger

from config.config import config

DOCK_THICKNESS = 40  # px, used until the dock has a real allocation


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
