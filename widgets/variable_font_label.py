from enum import StrEnum
from typing import Any, ClassVar

from fabric.widgets.label import Label

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango  # type: ignore


class Font(StrEnum):
    ROBOTO_FLEX = "Roboto Flex"
    GOOGLE_SANS_FLEX = "Google Sans Flex"
    MATERIAL_SYMBOLS = "Material Symbols Rounded"


class VariableFontMixin:
    VARIATION_DEFAULTS: ClassVar[dict[str, float]] = {}

    def __init__(self, **variations: float) -> None:
        self.variations = {**self.VARIATION_DEFAULTS, **variations}

    def _get_variation_string(self) -> str:
        return ",".join(f"{k}={v}" for k, v in self.variations.items())

    def set_variations(self, **kwargs: float | None) -> None:
        changed = False
        for k, v in kwargs.items():
            if v is not None and self.variations.get(k) != v:
                self.variations[k] = v
                changed = True

        if changed and hasattr(self, "_update_attributes"):
            self._update_attributes()


class BaseVariableFontLabel(Label, VariableFontMixin):
    FONT_FAMILY: str = "sans-serif"

    def __init__(
        self,
        text: str = "",
        font_size: float | None = None,  # Default to None to allow CSS styling
        style_classes: str | list[str] | None = None,
        h_expand: bool = False,
        v_expand: bool = False,
        **kwargs: Any,
    ) -> None:
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

    def set_font_size(self, size: float | None) -> None:
        """Set the font size. Pass None to revert to CSS styling."""
        self._font_size = size
        self._update_attributes()

    def _update_attributes(self) -> None:
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


class VariableIconLabel(BaseVariableFontLabel):
    FONT_FAMILY = Font.MATERIAL_SYMBOLS

    VARIATION_DEFAULTS: ClassVar[dict[str, float]] = {
        "FILL": 1,
        "wght": 600,
        "GRAD": 0,
        "opsz": 48,
    }
    VARIATION_KEYS: ClassVar[set[str]] = set(VARIATION_DEFAULTS.keys())

    def __init__(
        self, icon_text: str, font_family: Font = Font.MATERIAL_SYMBOLS, **kwargs: Any
    ) -> None:
        self.FONT_FAMILY = font_family
        for k, v in self.VARIATION_DEFAULTS.items():
            kwargs.setdefault(k, v)

        super().__init__(
            text=icon_text,
            # style_classes=["material-label"],
            **kwargs,
        )

    def set_icon(self, icon_text: str) -> None:
        self.set_text(icon_text)


class VariableFontLabel(BaseVariableFontLabel):
    FONT_FAMILY = Font.ROBOTO_FLEX

    VARIATION_DEFAULTS: ClassVar[dict[str, float]] = {
        "wght": 400,
        "GRAD": 0,
        "opsz": 48,
        "wdth": 100,
        "ital": 0,
        "slnt": 0,
        "XTRA": 468,
        "ROND": 100,
    }
    VARIATION_KEYS: ClassVar[set[str]] = set(VARIATION_DEFAULTS.keys())

    def __init__(
        self, text: str, font_family: Font = Font.ROBOTO_FLEX, **kwargs: Any
    ) -> None:
        self.FONT_FAMILY = font_family
        for k, v in self.VARIATION_DEFAULTS.items():
            kwargs.setdefault(k, v)

        super().__init__(text=text, **kwargs)
