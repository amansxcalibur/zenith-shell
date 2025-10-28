import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango, PangoCairo

from fabric.widgets.label import Label


class VariableFontMixin:
    """Mixin for handling variable font variations"""

    # default variation ranges - can be overridden by subclasses
    VARIATION_DEFAULTS = {}

    def __init__(self, size=48, **variations):
        self.size = size
        self.variations = {**self.VARIATION_DEFAULTS, **variations}
        self._font_applied = False

    def _build_variation_string(self):
        """Build the OpenType variation string from current values"""
        return ",".join(f"{k}={v}" for k, v in self.variations.items())

    def set_variations(self, **kwargs):
        """Update font variations with any provided keyword arguments"""
        self.variations.update({k: v for k, v in kwargs.items() if v is not None})
        self._update_font()

    def get_variation(self, key):
        """Get a specific variation value"""
        return self.variations.get(key)


class BaseMaterialLabel(Label, VariableFontMixin):
    """Base class for labels with variable font support"""

    FONT_FAMILY = "sans-serif"  # override in subclasses

    def __init__(self, text, size=48, style_classes=None, **variations):
        Label.__init__(self, style_classes=style_classes or [])
        VariableFontMixin.__init__(self, size=size, **variations)

        self.text = text
        self.set_text(text)

        self._update_font()
        self.connect("draw", self._on_first_draw)

    def _on_first_draw(self, widget, cr):
        """Apply font on first draw when layout is guaranteed to exist"""
        if not self._font_applied:
            self._update_font()
            self._font_applied = True
        return False

    def _update_font(self):
        self.set_text(self.text)
        layout = self.get_layout()
        if not layout:
            return

        font_desc = self._create_font_description()
        layout.set_font_description(font_desc)
        self.queue_draw()

        if self._should_debug():
            self._debug_font_info(font_desc)

    def _create_font_description(self):
        """Create a Pango font description with variations"""
        font_desc = Pango.FontDescription.from_string(f"{self.FONT_FAMILY} {self.size}")
        variation_string = self._build_variation_string()
        if variation_string:
            font_desc.set_variations(variation_string)
        return font_desc

    def _should_debug(self):
        return False

    def _debug_font_info(self, font_desc):
        context = self.get_pango_context()
        print(f"=== {self.__class__.__name__} Debug ===")
        print(f"Text: {self.text}")
        print(f"Family: {context.get_font_description().get_family()}")
        print(f"Font Description: {font_desc.to_string()}")
        print(f"Variations: {font_desc.get_variations()}")

    def set_text_content(self, text):
        self.text = text
        self.set_text(text)
        self._update_font()


class MaterialIconLabel(BaseMaterialLabel):
    """Label for Material Symbols with variable font features"""

    FONT_FAMILY = "Material Symbols Rounded"
    VARIATION_DEFAULTS = {
        "FILL": 1,
        "wght": 400,
        "GRAD": 0,
        "opsz": 48,
    }

    def __init__(self, icon_text, size=48, fill=1, wght=400, grad=0, opsz=48, **kwargs):
        super().__init__(
            text=icon_text,
            size=size,
            style_classes=["material-label"],
            FILL=fill,
            wght=wght,
            GRAD=grad,
            opsz=opsz,
            **kwargs,
        )

    def set_variations(
        self,
        FILL: float | None = None,
        wght: int | None = None,
        opsz: int | None = None,
        GRAD: int | None = None,
    ) -> None:
        super().set_variations(FILL=FILL, wght=wght, opsz=opsz, GRAD=GRAD)

    def set_icon(self, icon_text):
        self.set_text_content(icon_text)


class MaterialFontLabel(BaseMaterialLabel):
    """Label for Roboto Flex with extensive variable font features"""

    FONT_FAMILY = "Roboto Flex"
    VARIATION_DEFAULTS = {
        "wght": 400,
        "GRAD": 0,
        "opsz": 48,
        "wdth": 100,
        "ital": 0,
        "slnt": 0,
        "XTRA": 468,
    }

    def __init__(
        self,
        text,
        size=48,
        wght=400,
        grad=0,
        opsz=48,
        wdth=100,
        ital=0,
        slnt=0,
        xtra=468,
        **kwargs,
    ):
        super().__init__(
            text=text,
            size=size,
            wght=wght,
            GRAD=grad,
            opsz=opsz,
            wdth=wdth,
            ital=ital,
            slnt=slnt,
            XTRA=xtra,
            **kwargs,
        )

    def set_variations(
        self,
        wght: int | None = None,
        GRAD: int | None = None,
        opsz: int | None = None,
        wdth: int | None = None,
        ital: int | None = None,
        slnt: int | None = None,
        XTRA: int | None = None,
    ) -> None:
        super().set_variations(
            wght=wght,
            opsz=opsz,
            GRAD=GRAD,
            wdth=wdth,
            ital=ital,
            slnt=slnt,
            XTRA=XTRA,
        )

    def set_icon(self, icon_text):
        self.set_text_content(icon_text)

    def set_icon(self, text):
        self.set_text_content(text)


# I'll just put this implementation here for now
class MaterialIconLabelRaw(Gtk.DrawingArea, VariableFontMixin):
    """
    A drawing-area-based widget for Material Icons with variable font support.
    Uses direct Cairo rendering for more control over font rendering.
    """

    FONT_FAMILY = "Material Symbols Rounded"
    VARIATION_DEFAULTS = {
        "FILL": 1,
        "wght": 400,
        "GRAD": 0,
        "opsz": 48,
    }

    def __init__(self, icon_text, size=48, fill=1, wght=400, grad=0, opsz=48):
        Gtk.DrawingArea.__init__(self)
        VariableFontMixin.__init__(
            self, size=size, FILL=fill, wght=wght, GRAD=grad, opsz=opsz
        )

        self.icon_text = icon_text
        self.set_size_request(size + 10, size + 10)
        self.connect("draw", self._on_draw)

    def _on_draw(self, widget, cr):
        layout = PangoCairo.create_layout(cr)

        # create font description with variations
        font_desc = Pango.FontDescription.from_string(f"{self.FONT_FAMILY} {self.size}")
        variation_string = self._build_variation_string()
        if variation_string:
            font_desc.set_variations(variation_string)

        # configure layout
        layout.set_font_description(font_desc)
        layout.set_text(self.icon_text)

        # center the icon
        ink_rect, logical_rect = layout.get_pixel_extents()
        width = self.get_allocated_width()
        height = self.get_allocated_height()

        x = (width - logical_rect.width) // 2
        y = (height - logical_rect.height) // 2

        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)

        if self._should_debug():
            self._debug_font_info(font_desc)

        return False

    def _should_debug(self):
        return False

    def _debug_font_info(self, font_desc):
        print(f"=== {self.__class__.__name__} Debug ===")
        print(f"Text: {self.icon_text}")
        print(f"Family: {font_desc.get_family()}")
        print(f"Variations: {font_desc.get_variations()}")

    def set_icon(self, icon_text):
        self.icon_text = icon_text
        self.queue_draw()

    def _update_font(self):
        self.queue_draw()
