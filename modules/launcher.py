from collections.abc import Iterator

from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.image import Image
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.revealer import Revealer
from fabric.widgets.eventbox import EventBox
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.utils import DesktopApp, get_desktop_applications, idle_add, remove_handler

from widgets.material_label import MaterialIconLabel

import icons
from config.config import config

from gi.repository import GLib, Gdk

class AppCommands:
    POWER = "power"
    DASHBOARD = "dashboard"
    WALLPAPERS = "wallpapers"
    PLAYER = "player"
    SETTINGS = "settings"


class AppLauncher(Box):
    LAUNCH_MODES = [">", ":", "="]
    MODE_APP = ">"
    MODE_COMMAND = ":"
    MODE_CALC = "="

    COMMANDS = [
        {"title": "Power", "cmd": ":p", "id": AppCommands.POWER, "icon": icons.power},
        {"title": "Player", "cmd": ":u", "id": AppCommands.PLAYER, "icon": icons.disc},
        {
            "title": "Dashboard",
            "cmd": ":d",
            "id": AppCommands.DASHBOARD,
            "icon": icons.dashboard,
        },
        {
            "title": "Wallpapers",
            "cmd": ":w",
            "id": AppCommands.WALLPAPERS,
            "icon": icons.wallpaper,
        },
        {
            "title": "Zenith Settings",
            "cmd": ":s",
            "id": AppCommands.SETTINGS,
            "icon": icons.settings,
        },
    ]

    def __init__(self, pill, **kwargs):
        super().__init__(
            name="app-launcher",
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self._pill = pill
        self.selected_index = -1
        self._arranger_handler = 0
        self._all_apps = get_desktop_applications()
        self.current_mode = self.MODE_APP

        self._build_mode_selector()
        self._build_search_interface()
        self._build_main_layout()

        self.show_all()

    def _build_mode_selector(self):
        self.curr_launch_mode_btn = Button(
            style_classes=["launch-mode-btn"],
            label=self.current_mode,
            on_clicked=lambda _: self.launcher_options_revealer.set_reveal_child(
                not self.launcher_options_revealer.get_reveal_child()
            ),
        )

        self.launch_options_list = Box(spacing=5, name="launch-options-box")
        self.launcher_options_revealer = Revealer(
            child=self.launch_options_list,
            transition_type="slide-left",
            transition_duration=150,
        )

        self.launch_mode = Box(
            name="launch-mode-box",
            children=[self.curr_launch_mode_btn, self.launcher_options_revealer],
        )

        self.launch_mode_event_box = EventBox(
            name="launch-mode-event-container", child=self.launch_mode, events="all"
        )
        self.launch_mode_event_box.connect("enter-notify-event", self._on_hover_enter)
        self.launch_mode_event_box.connect("leave-notify-event", self._on_hover_leave)

        self._rebuild_mode_options()

    def _build_search_interface(self):
        self.viewport = Box(name="viewport", spacing=4, v_align="end", orientation="v")

        self.search_entry = Entry(
            name="search-entry",
            placeholder="Search Applications...",
            h_expand=True,
            notify_text=lambda entry, *_: self._on_entry_changed(entry),
            on_activate=lambda entry, *_: self._on_search_entry_activate(
                entry.get_text()
            ),
            on_key_press_event=self._on_search_entry_key_press,
        )
        self.search_entry.props.xalign = 0.5

        self.scrolled_window = ScrolledWindow(
            name="scrolled-window",
            spacing=10,
            style_classes="" if not config.VERTICAL else "vertical",
            min_content_size=(400, 150),
            max_content_size=(400, 150),
            child=self.viewport,
        )

    def _build_main_layout(self):
        self.header_box = Box(
            name="header-box",
            spacing=10,
            orientation="h",
            children=[
                self.launch_mode_event_box,
                self.search_entry,
                Button(
                    name="close-button",
                    child=MaterialIconLabel(name="close-label", icon_text=icons.close.symbol()),
                    tooltip_text="Exit",
                    on_clicked=lambda *_: self.close_launcher(),
                ),
            ],
        )

        self.launcher_box = Box(
            name="launcher-box",
            spacing=10,
            h_expand=True,
            orientation="v",
            children=[self.scrolled_window, self.header_box],
        )

        self.add(self.launcher_box)

    def _on_hover_enter(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.launcher_options_revealer.set_reveal_child(True)
        return False

    def _on_hover_leave(self, widget, event):
        if event.detail != Gdk.NotifyType.INFERIOR:
            self.launcher_options_revealer.set_reveal_child(False)
        self._refocus_search_entry()
        return False

    def _refocus_search_entry(self):
        self.search_entry.grab_focus()
        self.search_entry.select_region(0, 0)
        self.search_entry.set_position(-1)

    def _rebuild_mode_options(self):
        self.launch_options_list.children = []

        for mode in self.LAUNCH_MODES:
            if mode != self.current_mode:
                btn = Button(
                    label=mode,
                    style_classes=["launch-mode-btn"],
                    on_clicked=lambda b, m=mode: self._select_mode(m),
                )
                self.launch_options_list.add(btn)

        self.launch_options_list.show_all()

    def _select_mode(self, mode):
        self.current_mode = mode
        self.curr_launch_mode_btn.set_label(mode)
        self._rebuild_mode_options()

        # strip old mode prefix and add new one
        current_text = self.search_entry.get_text()
        for m in [m for m in self.LAUNCH_MODES if m != self.MODE_APP]:
            if current_text.startswith(m):
                current_text = current_text[len(m) :].lstrip()
                break

        new_prefix = "" if mode == self.MODE_APP else mode
        self.search_entry.set_text(f"{new_prefix}{current_text}")
        self._refocus_search_entry()
        self.arrange_viewport(self.search_entry.get_text())

    def _sync_mode_from_text(self, text):
        first_char = text[0] if text else ""
        target_mode = first_char if first_char in self.LAUNCH_MODES else self.MODE_APP

        if target_mode != self.current_mode:
            self.current_mode = target_mode
            self.curr_launch_mode_btn.set_label(target_mode)
            self._rebuild_mode_options()

    def _on_entry_changed(self, entry):
        text = entry.get_text()
        self._sync_mode_from_text(text)
        self.arrange_viewport(text)

    def _on_search_entry_activate(self, text):
        if text.startswith(self.MODE_CALC):
            if self.selected_index == -1:
                self._evaluate_calculator_expression(text)
            return

        for cmd in self.COMMANDS:
            if text == cmd["cmd"]:
                self._pill.open_pill(cmd["id"])
                return

        # activate selected or last item
        children = self.viewport.get_children()
        if children and (text.strip() or self.selected_index != -1):
            selected_index = (
                self.selected_index if self.selected_index != -1 else len(children) - 1
            )
            if 0 <= selected_index < len(children):
                children[selected_index].clicked()

    def _on_search_entry_key_press(self, widget, event):
        # mode switching with Shift + Left/Right
        if event.state & Gdk.ModifierType.SHIFT_MASK:
            if event.keyval in (Gdk.KEY_Left, Gdk.KEY_Right):
                delta = -1 if event.keyval == Gdk.KEY_Left else 1
                current_index = self.LAUNCH_MODES.index(self.current_mode)
                new_index = (current_index + delta) % len(self.LAUNCH_MODES)
                self._select_mode(self.LAUNCH_MODES[new_index])
                return True

        # navigation
        if event.keyval == Gdk.KEY_Down:
            self._move_selection(1)
            return True
        elif event.keyval == Gdk.KEY_Up:
            self._move_selection(-1)
            return True

        return False

    def arrange_viewport(self, query: str = ""):
        if query.startswith(self.MODE_CALC):
            self._update_calculator_viewport()
            return

        if query.startswith(self.MODE_COMMAND):
            self._arrange_command_mode(query)
            return

        self._arrange_app_mode(query)

    def _arrange_command_mode(self, query):
        self._clear_viewport()

        search_term = query.casefold()
        filtered = [
            cmd
            for cmd in self.COMMANDS
            if search_term in cmd["title"].casefold() or search_term in cmd["cmd"]
        ]

        for cmd in filtered:
            self.viewport.add(self._create_command_slot(cmd))

        if filtered:
            GLib.idle_add(lambda: self._update_selection(len(filtered) - 1))

    def _arrange_app_mode(self, query):
        self._clear_viewport()

        filtered_apps = self._get_filtered_apps(query)

        self._arranger_handler = idle_add(
            lambda apps_iter: self._add_next_application(apps_iter)
            or self._handle_arrange_complete(query),
            iter(reversed(filtered_apps)),
            pin=True,
        )

    def _get_filtered_apps(self, query):
        query_lower = query.casefold()
        filtered = [
            app
            for app in self._all_apps
            if query_lower
            in f"{app.display_name or ''} {app.name} {app.generic_name or ''}".casefold()
        ]
        return sorted(filtered, key=lambda app: (app.display_name or "").casefold())

    def _clear_viewport(self):
        remove_handler(self._arranger_handler) if self._arranger_handler else None
        self.viewport.children = []
        self.selected_index = -1

    def _handle_arrange_complete(self, query):
        children = self.viewport.get_children()

        # auto-select last item if query exists
        if query.strip():
            if children:
                GLib.idle_add(lambda: self._update_selection(len(children) - 1))

        # scroll to bottom on empty query (launcher startup)
        else:

            def on_layout_complete(widget, allocation):
                adj = self.scrolled_window.get_vadjustment()
                adj.set_value(adj.get_upper())
                widget.disconnect(handler_id)

            handler_id = self.viewport.connect("size-allocate", on_layout_complete)

        return False

    def _add_next_application(self, apps_iter: Iterator[DesktopApp]):
        if app := next(apps_iter, None):
            self.viewport.add(self._create_application_slot(app))
            return True
        return False

    def _create_application_slot(self, app: DesktopApp) -> Button:
        return Button(
            name="app-slot-button",
            child=Box(
                name="app-slot-box",
                orientation="h",
                spacing=12,
                children=[
                    Image(
                        name="app-icon",
                        pixbuf=app.get_icon_pixbuf(size=32),
                        h_align="start",
                    ),
                    Box(
                        orientation="v",
                        children=[
                            Label(
                                name="app-label",
                                label=app.display_name or "Unknown",
                                ellipsization="end",
                                v_align="center",
                                h_align="start",
                            ),
                            Label(
                                name="app-desc",
                                label=app.description or "__",
                                ellipsization="end",
                                v_align="center",
                                h_align="start",
                                max_chars_width=40,
                                h_expand=True,
                            ),
                        ],
                    ),
                ],
            ),
            tooltip_text=app.description,
            on_clicked=lambda *_: (app.launch(), self.close_launcher()),
        )

    def _create_command_slot(self, cmd_data: dict) -> Button:
        icon = cmd_data["icon"]
        return Button(
            name="app-slot-button",
            child=Box(
                name="app-slot-box",
                orientation="h",
                spacing=12,
                children=[
                    MaterialIconLabel(
                        name="app-icon",
                        style_classes="command",
                        icon_text=icon.symbol()
                        if hasattr(icon, "symbol")
                        else icon,
                        v_align="center",
                    ),
                    Box(
                        orientation="v",
                        children=[
                            Label(
                                name="app-label",
                                label=cmd_data["title"],
                                h_align="start",
                            ),
                            Label(
                                name="app-desc",
                                label=f"Run command {cmd_data['cmd']}",
                                h_align="start",
                            ),
                        ],
                    ),
                ],
            ),
            on_clicked=lambda *_: self._pill.open_pill(cmd_data["id"]),
        )

    def _update_selection(self, new_index: int):
        children = self.viewport.get_children()

        if 0 <= self.selected_index < len(children):
            children[self.selected_index].get_style_context().remove_class("selected")

        if 0 <= new_index < len(children):
            children[new_index].get_style_context().add_class("selected")
            self.selected_index = new_index
            self._scroll_to_selected(children[new_index])
        else:
            self.selected_index = -1

    def _scroll_to_selected(self, button):
        def scroll_to_allocation(allocation):
            adj = self.scrolled_window.get_vadjustment()
            visible_top = adj.get_value()
            visible_bottom = visible_top + adj.get_page_size()

            if allocation.y < visible_top:
                adj.set_value(allocation.y)
            elif allocation.y + allocation.height > visible_bottom:
                adj.set_value(allocation.y + allocation.height - adj.get_page_size())

        allocation = button.get_allocation()
        if allocation.height > 0 and allocation.y >= 0:
            scroll_to_allocation(allocation)
        else:
            handler_id = button.connect(
                "size-allocate",
                lambda widget, alloc: (
                    scroll_to_allocation(alloc),
                    widget.disconnect(handler_id),
                ),
            )

    def _move_selection(self, delta: int):
        children = self.viewport.get_children()
        if not children:
            return

        if self.selected_index == -1:
            new_index = len(children) - 1 if delta == 1 else len(children) + delta
        else:
            new_index = self.selected_index + delta

        new_index = max(0, min(new_index, len(children) - 1))
        self._update_selection(new_index)

    # Calculator Mode, kinda unnecessary
    def _update_calculator_viewport(self):
        self._clear_viewport()
        return

    def _evaluate_calculator_expression(self, text: str):
        return

    def close_launcher(self):
        self.viewport.children = []
        self.selected_index = -1
        self._pill.close()

    def open_launcher(self):
        self._all_apps = get_desktop_applications()
        self.arrange_viewport()
