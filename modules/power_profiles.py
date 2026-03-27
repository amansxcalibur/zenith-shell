from fabric.widgets.box import Box
from fabric.widgets.button import Button
from fabric.widgets.overlay import Overlay
from fabric.widgets.eventbox import EventBox
from fabric.power_profiles.service import PowerProfiles

from widgets.popup_window.shared_popup_window import SharedPopupWindow
from widgets.material_label import MaterialIconLabel, MaterialFontLabel

import icons

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk


class PowerProfilesSelector(EventBox):
    ICON_MAP = {
        "power-saver": icons.energy_savings_leaf,
        "balanced": icons.balance,
        "performance": icons.rocket_launch,
    }

    def __init__(self, **kwargs):
        super().__init__(spacing=3)

        self.service = PowerProfiles()

        self._profile_buttons = []

        for profile_obj in self.service.profiles:
            profile = profile_obj["Profile"]
            icon = self.ICON_MAP.get(profile, icons.balance)

            btn = Button(
                name=f"battery-{profile}",
                child=MaterialIconLabel(
                    style_classes="power-profile-btn",
                    icon_text=icon.symbol(),
                ),
                tooltip_text=f"{profile.replace('-', ' ').title()} mode",
            )
            self._profile_buttons.append((profile, btn))

        self._left_spacer = Box(name="power-profile-spacer-left")
        self._slider_pill = Box(name="power-profile-slider")
        self._right_spacer = Box(name="power-profile-spacer-right")

        self.profile_label = MaterialFontLabel(
            name="profile-label",
            h_align="center",
            text=self.service.active_profile,
            ROND=100,
            wght=500,
        )

        slider_layer = Box(
            name="power-profile-slider-layer",
            children=[self._left_spacer, self._slider_pill, self._right_spacer],
        )

        button_layer = Box(
            name="power-profile-button-layer",
            children=[btn for _, btn in self._profile_buttons],
        )

        profiles_overlay = Overlay(
            name="power-profiles-overlay",
            child=slider_layer,
            overlays=[button_layer],
        )

        self.size_group = Gtk.SizeGroup.new(Gtk.SizeGroupMode.BOTH)
        self.size_group.add_widget(button_layer)
        self.size_group.add_widget(slider_layer)

        self.profile_icon = MaterialIconLabel(
            name="power-profile-icon",
            icon_text=self.ICON_MAP.get(
                self.service.active_profile, icons.balance
            ).symbol(),
        )

        self.add(Box(name="power-mode-switcher", children=self.profile_icon))

        self.popup_win = SharedPopupWindow()
        self.popup_win.add_child(
            pointing_widget=self,
            child=Box(
                name="power-profiles",
                orientation="v",
                h_expand=True,
                spacing=4,
                children=[
                    self.profile_label,
                    Box(
                        name="power-profiles-container",
                        children=Box(
                            children=[profiles_overlay],
                        ),
                    ),
                ],
            ),
        )

        for mode, btn in self._profile_buttons:
            btn.connect("clicked", lambda _, m=mode: self.set_power_mode(m))
            btn.connect("enter-notify-event", lambda _, e, m=mode: self._on_hover(m))
            btn.connect("leave-notify-event", lambda _, e: self._on_leave())

        self.service.connect("changed", self._on_service_changed)

        self._allocation_handler_id = button_layer.connect(
            "size-allocate", self._on_first_allocation
        )

    def _on_service_changed(self, _):
        new_mode = self.service.active_profile

        self.profile_label.set_label(new_mode)
        icon = self.ICON_MAP.get(new_mode, icons.balance)
        self.profile_icon.set_icon(icon.symbol())

        self.update_button_styles()
        self._slide_to(self._mode_index(new_mode))

    def _on_first_allocation(self, widget, allocation):
        self._slide_to(self._mode_index(self.service.active_profile))
        if self._allocation_handler_id:
            widget.disconnect(self._allocation_handler_id)
            self._allocation_handler_id = None

    def _mode_index(self, mode):
        for i, (m, _) in enumerate(self._profile_buttons):
            if m == mode:
                return i
        return 0

    def _slide_to(self, idx):
        if idx >= len(self._profile_buttons):
            return
        offset = sum(
            pair[1].get_allocation().width for pair in self._profile_buttons[:idx]
        )
        self._left_spacer.set_style(f"min-width: {offset}px;")

    def _on_hover(self, mode):
        self._slide_to(self._mode_index(mode))

    def _on_leave(self):
        self._slide_to(self._mode_index(self.service.active_profile))

    def set_power_mode(self, mode):
        self.service.active_profile = mode

    def update_button_styles(self):
        current = self.service.active_profile
        for mode, btn in self._profile_buttons:
            if mode == current:
                btn.add_style_class("active")
            else:
                btn.remove_style_class("active")
