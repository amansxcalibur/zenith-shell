# ── Animation constants ────────────────────────────────────────────────────────
TRANSITION_DURATION = "0.25s"
FOCUS_TRANSITION_DURATION = "0.1s"
EASING = "cubic-bezier(0.5, 0.25, 0, 1)"

DEFAULT_PADDING = 2   # px — resting vertical pad on a module
FOCUS_PADDING   = 3   # px — raised vertical pad on hover
EDGE_HALF       = 20  # px — half the space reserved for the main hole at edges
HOLE_HEIGHT     = 40  # px
SPACING         = 0   # px — gap between modules


# ── Transition helpers ─────────────────────────────────────────────────────────
def _transition(*props: str, duration: str = TRANSITION_DURATION) -> str:
    """Build a CSS transition string for one or more properties."""
    return ", ".join(f"{p} {duration} {EASING}" for p in props)


def _style(**props) -> str:
    """
    Build an inline CSS string from keyword arguments.
    Underscores in keys become hyphens: min_width → min-width.
    Values that are integers are treated as px values.
    Pass transition= to append a transition rule.
    """
    transition = props.pop("transition", None)
    parts = []
    for k, v in props.items():
        css_key = k.replace("_", "-")
        css_val = f"{v}px" if isinstance(v, int) else v
        parts.append(f"{css_key}:{css_val}")
    if transition:
        parts.append(f"transition:{transition}")
    return "; ".join(parts) + ";"


# ── Pre-built style factories ──────────────────────────────────────────────────

# — hole / placeholder —
def hole_open(width: int, animated: bool = True) -> str:
    return _style(
        min_height=HOLE_HEIGHT,
        min_width=width,
        transition=_transition("min-width", "min-height") if animated else None,
    )

def hole_closed(animated: bool = True) -> str:
    return _style(
        min_height=0,
        min_width=0,
        margin_top=0,
        transition=_transition("min-height", "min-width", "margin-top") if animated else None,
    )

def hole_container(width: int, animated: bool = True) -> str:
    return _style(
        min_height=0,
        min_width=width,
        margin_top=0,
        transition=_transition("min-height", "min-width", "margin-top") if animated else None,
    )

def placeholder_width(width: int, animated: bool = True) -> str:
    return _style(
        min_width=width,
        transition=_transition("min-width") if animated else None,
    )

def placeholder_clear() -> str:
    return _style(min_width=0, background_color="transparent")

# — module raise / lower —
def module_raised() -> str:
    return _style(
        padding_bottom=FOCUS_PADDING,
        padding_left=FOCUS_PADDING,
        padding_right=FOCUS_PADDING,
        transition=_transition(
            "padding-bottom", "padding-top",
            duration=FOCUS_TRANSITION_DURATION,
        ),
    )

def module_lowered() -> str:
    return _style(
        padding_left=FOCUS_PADDING,
        padding_right=FOCUS_PADDING,
        padding_bottom=DEFAULT_PADDING,
        padding_top=DEFAULT_PADDING,
        transition=_transition(
            "padding-bottom", "padding-top",
            duration=FOCUS_TRANSITION_DURATION,
        ),
    )

# — edge boxes —
def edge_hidden() -> str:
    return _style(min_width=0)

def edge_visible() -> str:
    return _style(min_width=EDGE_HALF)

def edge_clear() -> str:
    return _style(min_width=0, background_color="transparent")