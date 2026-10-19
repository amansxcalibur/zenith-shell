from fabric.widgets.label import Label

from modules.tile import TileSimple
from services.theme import ThemeMode, ThemeService
import icons


class ThemeSwitchTile(TileSimple):
    def __init__(self, **kwargs):
        self.label = Label(
            style_classes=["desc-label", "off"],
            label="Off",
            h_align="start",
        )
        self.state = None
        super().__init__(
            markup=icons.contrast.symbol(),
            label="Dark Theme",
            status_label_widget=self.label,
            style_classes=["off"],
            **kwargs,
        )
        self.service = ThemeService()
        self.update_visual()

    def update_visual(self):
        is_active = self.service.theme == ThemeMode.DARK
        self.set_active_style(is_active)
        self.props.set_label("On" if is_active else "Off")

    def handle_state_toggle(self, *_):
        self.service.toggle_theme_mode()
        self.update_visual()
        return super().handle_state_toggle(*_)
