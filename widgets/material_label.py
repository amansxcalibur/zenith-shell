import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gtk, Pango

from fabric.widgets.label import Label


class VariableFontMixin:
    VARIATION_DEFAULTS = {}

    def __init__(self, **variations):
        self.variations = {**self.VARIATION_DEFAULTS, **variations}

    def _get_variation_string(self):
        return ",".join(f"{k}={v}" for k, v in self.variations.items())

    def set_variations(self, **kwargs):
        changed = False
        for k, v in kwargs.items():
            if v is not None and self.variations.get(k) != v:
                self.variations[k] = v
                changed = True

        if changed and hasattr(self, "_update_attributes"):
            self._update_attributes()


class BaseMaterialLabel(Label, VariableFontMixin):
    FONT_FAMILY = "sans-serif"

    def __init__(
        self,
        text="",
        font_size=None,  # Default to None to allow CSS styling
        style_classes=None,
        h_expand=False,
        v_expand=False,
        **kwargs,
    ):
        variation_kwargs = {}
        label_kwargs = {}

        known_variations = getattr(self, "VARIATION_KEYS", set())

        for key, value in kwargs.items():
            if key in known_variations:
                variation_kwargs[key] = value
            else:
                label_kwargs[key] = value

        VariableFontMixin.__init__(self, **variation_kwargs)

        Label.__init__(
            self,
            label=text,
            style_classes=style_classes or [],
            h_expand=h_expand,
            v_expand=v_expand,
            **label_kwargs,
        )

        self._font_size = font_size
        self._update_attributes()

    def set_font_size(self, size):
        """Set the font size. Pass None to revert to CSS styling."""
        self._font_size = size
        self._update_attributes()

    def _update_attributes(self):
        font_desc_str = f"{self.FONT_FAMILY}"

        if self._font_size is not None:
            font_desc_str += f" {self._font_size}"

        font_desc = Pango.FontDescription.from_string(font_desc_str)

        # apply variations
        vars_str = self._get_variation_string()
        if vars_str:
            font_desc.set_variations(vars_str)

        # create Attribute List
        attr_list = Pango.AttrList()
        attr = Pango.AttrFontDesc.new(font_desc)

        attr.start_index = 0
        attr.end_index = 0xFFFFFFFF

        attr_list.insert(attr)
        self.set_attributes(attr_list)


class MaterialIconLabel(BaseMaterialLabel):
    """Label for Material Symbols."""

    FONT_FAMILY = "Material Symbols Rounded"

    VARIATION_DEFAULTS = {
        "FILL": 1,
        "wght": 400,
        "GRAD": 0,
        "opsz": 48,
    }
    VARIATION_KEYS = set(VARIATION_DEFAULTS.keys())

    def __init__(self, icon_text, **kwargs):
        for k, v in self.VARIATION_DEFAULTS.items():
            kwargs.setdefault(k, v)

        super().__init__(
            text=icon_text,
            # style_classes=["material-label"],
            **kwargs,
        )

    def set_icon(self, icon_text):
        self.set_text(icon_text)


class MaterialFontLabel(BaseMaterialLabel):
    """Label for Variable Font (Roboto Flex)."""

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
    VARIATION_KEYS = set(VARIATION_DEFAULTS.keys())

    def __init__(self, text, **kwargs):
        for k, v in self.VARIATION_DEFAULTS.items():
            kwargs.setdefault(k, v)

        super().__init__(text=text, **kwargs)
