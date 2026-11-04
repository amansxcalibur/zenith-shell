# Dock

The dock sits on the bottom, left or right screen edge (`bar.POSITION`, applied on
restart). Everything that depends on the edge goes through `DockPlacement`.

- `placement.py`: the edge, and what follows from it (anchors, axes, cairo transform).
- `surface.py`: `DockSurface` paints the dock as one cairo path with notches cut out,
  beneath its children. `AnimatedNotch` eases a notch towards its target.
- `hole_controller.py`: a row of modules and the hole that follows the hovered one.
- `module_overlay.py`: reports hovers on a module and raises it.
- `bar.py`: the window; builds the rows and, on a bottom dock, the pill's slot.

Notches are drawn in dock space, where x runs along the dock and y is the distance
from the edge facing the screen's centre. The same path therefore works on every edge.

## Hole behaviour

- Hovering a module moves the hole to it. An open hole slides; a closed one opens in place.
- Leaving the row, or hovering the empty end of it, collapses the hole.
- After 500ms idle the hole rests on the module nearest the row's screen-side end.

## Pill and side docks

Only a bottom dock seats the pill: `placement.seats_pill` is false on a side, and there
is no pill slot or notch. `DockBar.insets` reports the room the dock takes, and the
window managers offset both pills by it when they snap to that side. The `insets-changed`
signal fires when that room changes (dock hidden or shown, rail resized).

A rail narrower than a module grows to fit it. Style side-dock versions of a module in
`styles/dock_widget.css` under `.dock-left` and `.dock-right`.
