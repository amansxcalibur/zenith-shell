This is how the bar works. Will complete it later.

## Hover workflow:

## Unhover workflow:
There are four cases for an unhover trigger:
1. Hover inside the widget, ie **INFERIOR** (ignored. The hole remains opened)
2. Leave the bar => hole collapses
3. Hover to the fallback edges => hole collapses (same as leaving the bar)
4. Hover to another widget : `hole-index` signal emitted.

When you leave the bar, two seperate functions are invoked:
 1. The widget is lowered in `ModuleOverlay`
 2. The placeholder/background hole state is set to collapse in `LayoutManager.set_hole_state()` function.

> Something important to note here is that `last_hover_time` of `starter` and `ender` boxes are updated so that the `_delayed_clear_style_edges()`, scheduled to be run on a previous hover, doesn't run after the delay. Or else, the starter box will be transparent instead of black.

The `curr_hovered_index` is reset to -1.