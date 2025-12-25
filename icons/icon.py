class Icon:
    __slots__ = ("_symbol",)

    def __init__(self, symbol: str):
        self._symbol = symbol

    def symbol(self) -> str:
        """For MaterialIconLabel / Pango layout"""
        return self._symbol

    def markup(self) -> str:
        """For Gtk.Label"""
        raise NotImplementedError
