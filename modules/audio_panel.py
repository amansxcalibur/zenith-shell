from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer
from fabric.widgets.scale import Scale
from fabric.widgets.scrolledwindow import ScrolledWindow

import icons
from services.volume_service import AppStream, SoundDevice, VolumeService
from widgets.material_label import MaterialIconLabel

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk  # type: ignore

PANEL_WIDTH = 250  # px
APP_ICON_SIZE = 24  # px
NAME_CHARS = 26

DEVICE_ICONS = {
    "headphones": icons.headphones,
    "headset": icons.headset_mic,
    "bluetooth": icons.bluetooth,
    "hdmi": icons.tv,
    "speaker": icons.speaker,
    "mic": icons.mic,
}


def _toggle_class(widget, name: str, on: bool) -> None:
    if on:
        widget.add_style_class(name)
    else:
        widget.remove_style_class(name)


def _set_shown(widget: Gtk.Widget, shown: bool) -> None:
    # kept out of the popup's show_all() while hidden
    widget.set_no_show_all(not shown)
    widget.set_visible(shown)


def _clear(box: Gtk.Container) -> None:
    for child in box.get_children():
        box.remove(child)


def _name_label(name: str, **kwargs) -> Label:
    return Label(
        name=name,
        h_align="start",
        ellipsization="end",
        max_chars_width=NAME_CHARS,
        **kwargs,
    )


def _heading(icon, title: str) -> Box:
    return Box(
        name="panel-heading",
        spacing=8,
        children=[
            MaterialIconLabel(name="heading-icon", icon_text=icon.symbol()),
            Label(name="heading-title", label=title),
        ],
    )


def _app_icon(stream: AppStream) -> Gtk.Widget:
    theme = Gtk.IconTheme.get_default()
    for name in filter(None, (stream.icon_name, (stream.icon_name or "").lower())):
        if theme.has_icon(name):
            image = Gtk.Image.new_from_icon_name(name, Gtk.IconSize.LARGE_TOOLBAR)
            image.set_pixel_size(APP_ICON_SIZE)
            image.set_hexpand(True)  # centred in its tile
            return image
    return MaterialIconLabel(
        name="app-icon-fallback",
        icon_text=icons.music_note.symbol(),
        h_align="center",
        h_expand=True,
    )


class DeviceCard(Box):
    def __init__(self, on_pick):
        super().__init__(name="device-card", orientation="v")
        self.on_pick = on_pick
        self.choices = False

        self.icon = MaterialIconLabel(
            name="card-icon",
            icon_text=icons.speaker.symbol(),
            h_align="center",
            h_expand=True,
        )
        self.device = _name_label("card-device")
        self.level = _name_label("card-level")
        self.arrow = MaterialIconLabel(
            name="card-arrow", icon_text=icons.expand_more.symbol()
        )
        self.header = Button(
            name="card-header",
            child=Box(
                spacing=12,
                children=[
                    Box(name="card-icon-shape", v_align="center", children=self.icon),
                    Box(
                        orientation="v",
                        h_expand=True,
                        v_align="center",
                        children=[self.device, self.level],
                    ),
                    self.arrow,
                ],
            ),
            on_clicked=lambda *_: self.set_open(not self.dropdown.get_reveal_child()),
        )
        self.options = Box(name="card-options", orientation="v", spacing=2)
        self.dropdown = Revealer(
            child=self.options,
            transition_type="slide-down",
            transition_duration=250,
        )
        self.children = [self.header, self.dropdown]

    def set_open(self, open_: bool) -> None:
        open_ = open_ and self.choices
        self.dropdown.set_reveal_child(open_)
        _toggle_class(self, "open", open_)
        self.arrow.set_icon(
            (icons.expand_less if open_ else icons.expand_more).symbol()
        )

    def show_devices(self, devices: list[SoundDevice]) -> None:
        active = next((d for d in devices if d.active), None)
        if active is None:
            self.device.set_label("None")
        else:
            self.icon.set_icon(DEVICE_ICONS[active.icon].symbol())
            self.device.set_label(active.label)
        self.header.set_tooltip_text(active.full_name if active else None)

        # nothing to switch to: no dropdown
        self.choices = len(devices) > 1
        _set_shown(self.arrow, self.choices)
        _toggle_class(self, "static", not self.choices)
        if not self.choices:
            self.set_open(False)

        _clear(self.options)
        for device in devices:
            self.options.add(self._option(device))

    def show_level(self, volume: float, muted: bool) -> None:
        self.level.set_label("Muted" if muted else f"{round(volume * 100)}%")

    def _option(self, device: SoundDevice) -> Button:
        def pick(*_):
            self.on_pick(device.name)
            self.set_open(False)

        check = MaterialIconLabel(
            name="option-check", icon_text=icons.check_material.symbol()
        )
        button = Button(
            name="device-option",
            tooltip_text=device.full_name,
            child=Box(
                spacing=10,
                children=[
                    MaterialIconLabel(
                        name="option-icon",
                        icon_text=DEVICE_ICONS[device.icon].symbol(),
                    ),
                    _name_label("option-name", label=device.label, h_expand=True),
                    check,
                ],
            ),
            on_clicked=pick,
        )
        _toggle_class(button, "active", device.active)
        button.show_all()
        _set_shown(check, device.active)
        return button


class StatusRow(Box):
    def __init__(self, on_more=None, more_tooltip: str | None = None):
        super().__init__(name="status-row", spacing=12)
        self.icon = MaterialIconLabel(name="status-icon", icon_text=icons.mic.symbol())
        self.title = _name_label("status-title")
        self.detail = _name_label("status-detail")
        # given on_more, a round button on the end opens more on what's in
        # use; it's only there while something is
        self.more = None
        if on_more is not None:
            self.more = Button(
                name="status-more",
                v_align="center",
                tooltip_text=more_tooltip,
                child=MaterialIconLabel(
                    name="status-more-icon", icon_text=icons.chevron_right.symbol()
                ),
                on_clicked=lambda *_: on_more(),
            )
        self.children = [
            self.icon,
            Box(
                orientation="v",
                h_expand=True,
                v_align="center",
                children=[self.title, self.detail],
            ),
            *([self.more] if self.more else []),
        ]

    def set_status(
        self, icon, title: str, detail: str, alert: bool = False, active: bool = False
    ) -> None:
        self.icon.set_icon(icon.symbol())
        self.title.set_label(title)
        self.detail.set_label(detail)
        self.detail.set_tooltip_text(detail)
        _toggle_class(self, "alert", alert)
        _toggle_class(self, "active", active and not alert)
        if self.more is not None:
            _set_shown(self.more, alert or active)


class UserRow(Box):
    def __init__(self, stream: AppStream):
        super().__init__(name="user-row", spacing=12)
        detail = stream.title or "Recording"
        self.set_tooltip_text(detail)
        self.children = [
            Box(name="app-icon-shape", v_align="center", children=_app_icon(stream)),
            Box(
                orientation="v",
                h_expand=True,
                v_align="center",
                children=[
                    _name_label("app-name", label=stream.app),
                    _name_label("user-detail", label=detail),
                ],
            ),
        ]


class AppCard(Box):
    def __init__(self, stream: AppStream, service: VolumeService):
        super().__init__(name="app-card", spacing=12)
        self.index = stream.index
        self.dragging = False

        self.name = _name_label("app-name")
        self.level = Label(name="app-level")
        self.slider = Scale(
            name="app-volume-slider",
            min_value=0,
            max_value=1,
            increments=(0.01, 0.1),
            digits=2,  # fabric's default of 1 would round drags to 10% steps
            h_expand=True,
        )
        self.slider.connect("change-value", self._on_change, service)
        for signal, pressed in (
            ("button-press-event", True),
            ("button-release-event", False),
        ):
            self.slider.connect(signal, self._on_press, pressed)

        self.children = [
            Box(name="app-icon-shape", v_align="center", children=_app_icon(stream)),
            Box(
                orientation="v",
                h_expand=True,
                v_align="center",
                spacing=2,
                children=[
                    self.name,
                    Box(spacing=10, children=[self.slider, self.level]),
                ],
            ),
        ]
        self.update(stream)

    def _on_change(self, _widget, _scroll, value: float, service) -> bool:
        value = min(max(value, 0), 1)
        self.level.set_label(f"{round(value * 100)}%")
        service.set_app_volume(self.index, value)
        return False

    def _on_press(self, _widget, _event, pressed: bool) -> bool:
        self.dragging = pressed
        return False

    def update(self, stream: AppStream) -> None:
        self.name.set_label(stream.app)
        self.set_tooltip_text(stream.title or None)  # what it's playing
        if not self.dragging:  # not from under the pointer
            self.slider.set_value(stream.volume)
            self.level.set_label(
                "Muted" if stream.muted else f"{round(stream.volume * 100)}%"
            )
        _toggle_class(self, "muted", stream.muted)


class AudioPanel(Box):
    def __init__(self, service: VolumeService):
        super().__init__(name="audio-panel", orientation="v")
        self.set_size_request(PANEL_WIDTH, -1)
        self.service = service
        self._cards: dict[int, AppCard] = {}

        self.input_card = DeviceCard(service.set_default_input)
        self.output_card = DeviceCard(service.set_default_output)
        self.mic_status = StatusRow(
            lambda: self.show_page("mic-users"), "Apps using the microphone"
        )
        self.apps_status = StatusRow(
            lambda: self.show_page("apps"), "Apps playing audio"
        )

        main = Box(
            orientation="v",
            spacing=6,
            children=[
                _heading(icons.mic, "Microphone"),
                self.input_card,
                self.mic_status,
                _heading(icons.volume_up, "Sound"),
                self.output_card,
                self.apps_status,
            ],
        )

        # each list a page of its own, as tall as the panel
        self.users = Box(name="user-list", orientation="v", spacing=2)
        self.apps = Box(name="app-list", orientation="v", spacing=2)

        # pages share one size, so the popup doesn't jump between them
        self.stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT,
            transition_duration=250,
            vexpand=True,
        )
        self.stack.add_named(main, "main")
        self.stack.add_named(
            self._page("Using the microphone", self.users), "mic-users"
        )
        self.stack.add_named(self._page("Applications", self.apps), "apps")
        self.children = [self.stack]

        for signal in (
            "outputs-changed",
            "inputs-changed",
            "speaker-volume-changed",
            "mic-volume-changed",
        ):
            service.connect(signal, lambda *_: self._update_devices())
        service.connect("apps-changed", lambda *_: self._update_apps())
        service.connect("mic-users-changed", lambda *_: self._update_mic_users())

        self.show_all()
        self._update_devices()
        self._update_mic_users()
        self._update_apps()

    def _page(self, title: str, content: Gtk.Widget) -> Box:
        return Box(
            orientation="v",
            spacing=6,
            children=[
                Box(
                    name="page-header",
                    spacing=8,
                    children=[
                        Button(
                            name="page-back",
                            tooltip_text="Back",
                            child=MaterialIconLabel(
                                name="page-back-icon",
                                icon_text=icons.arrow_back.symbol(),
                            ),
                            on_clicked=lambda *_: self.show_page("main"),
                        ),
                        Label(name="heading-title", label=title),
                    ],
                ),
                # never makes the popup (and the sliders) taller
                ScrolledWindow(
                    h_scrollbar_policy="never",
                    v_scrollbar_policy="automatic",
                    propagate_height=False,
                    v_expand=True,
                    child=content,
                ),
            ],
        )

    def show_page(self, name: str) -> None:
        self.stack.set_visible_child_name(name)

    def _update_devices(self) -> None:
        self.input_card.show_devices(self.service.get_inputs())
        self.input_card.show_level(*self.service.get_mic_status())
        self.output_card.show_devices(self.service.get_outputs())
        self.output_card.show_level(*self.service.get_current_volume())

    def _update_mic_users(self) -> None:
        streams = self.service.get_mic_users()
        _clear(self.users)
        for stream in streams:
            row = UserRow(stream)
            self.users.add(row)
            row.show_all()
        if not streams and self.stack.get_visible_child_name() == "mic-users":
            self.show_page("main")  # nothing left to list

        users = list(dict.fromkeys(user.app for user in streams))
        if users:
            self.mic_status.set_status(
                icons.mic, "In use", ", ".join(users), alert=True
            )
        else:
            self.mic_status.set_status(
                icons.mic_off,
                "Not in use",
                "No apps are using it",
            )

    def _update_apps(self) -> None:
        apps = self.service.get_apps()
        # keep cards that stay, so a slider being dragged isn't rebuilt
        current = {stream.index for stream in apps}
        for index in list(self._cards):
            if index not in current:
                self.apps.remove(self._cards.pop(index))
        for stream in apps:
            card = self._cards.get(stream.index)
            if card is None:
                card = self._cards[stream.index] = AppCard(stream, self.service)
                self.apps.add(card)
                card.show_all()
            card.update(stream)

        names = list(dict.fromkeys(stream.app for stream in apps))
        if names:
            count = len(apps)
            self.apps_status.set_status(
                icons.music_note,
                f"{count} app{'s' if count > 1 else ''} playing",
                ", ".join(names),
                active=True,
            )
        else:
            self.apps_status.set_status(
                icons.music_off, "Nothing playing", "No apps playing audio"
            )
            if self.stack.get_visible_child_name() == "apps":
                self.show_page("main")  # nothing left to list
