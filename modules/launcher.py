import operator
from collections.abc import Iterator
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.button import Button
from fabric.widgets.entry import Entry
from fabric.widgets.scrolledwindow import ScrolledWindow
from fabric.utils import DesktopApp, get_desktop_applications, idle_add, remove_handler
from gi.repository import GLib, Gdk
import json
import os
import re
import math
import subprocess
import icons.icons as icons
import config.info as info

class AppLauncher(Box):
    def __init__(self, **kwargs):
        super().__init__(
            name="app-launcher",
            visible=False,
            all_visible=False,
            **kwargs,
        )

        self.notch = kwargs["notch"]
        self.selected_index = -1  # Track the selected item index

        self._arranger_handler: int = 0
        self._all_apps = get_desktop_applications()

        # Calculator history initialization
        # self.calc_history_path = os.path.expanduser("~/.cache/zenith-shell/calc.json")
        # if os.path.exists(self.calc_history_path):
        #     with open(self.calc_history_path, "r") as f:
        #         self.calc_history = json.load(f)
        # else:
        #     self.calc_history = []
        
        self.viewport = Box(name="viewport", spacing=4, v_align="end", orientation="v")
        self.search_entry = Entry(
            name="search-entry",
            placeholder="Search Applications...",
            h_expand=True,
            notify_text=lambda entry, *_: (
                self.update_calculator_viewport() if entry.get_text().startswith("=")
                else self.arrange_viewport(entry.get_text())
            ),
            on_activate=lambda entry, *_: self.on_search_entry_activate(entry.get_text()),
            on_key_press_event=self.on_search_entry_key_press,  # Handle key presses
        )
        self.search_entry.props.xalign = 0.5
        self.scrolled_window = ScrolledWindow(
            name="scrolled-window",
            spacing=10,
            style_classes="" if not info.VERTICAL else "vertical",
            min_content_size=(450, 105),
            max_content_size=(450, 105),
            child=self.viewport,
        )

        self.header_box = Box(
            name="header-box",
            spacing=10,
            orientation="h",
            children=[
                self.search_entry,
                Button(
                    name="close-button",
                    child=Label(name="close-label", markup=icons.cancel),
                    tooltip_text="Exit",
                    on_clicked=lambda *_: self.close_launcher()
                ),
            ],
        )
        
        self.launcher_box = Box(
            name="launcher-box",
            spacing=10,
            h_expand=True,
            orientation="v",
            children=[
                self.scrolled_window,
                self.header_box,
            ],
        )

        self.resize_viewport()

        self.add(self.launcher_box)
        self.show_all()

    def close_launcher(self):
        self.viewport.children = []
        self.selected_index = -1  # Reset selection
        self.notch.close()
        # self.notch.close_notch()

    def open_launcher(self):
        self._all_apps = get_desktop_applications()
        self.arrange_viewport()

    def arrange_viewport(self, query: str = ""):
        if query.startswith("="):
            # In calculator mode, update history view once (not per keystroke)
            self.update_calculator_viewport()
            return
        remove_handler(self._arranger_handler) if self._arranger_handler else None
        self.viewport.children = []
        self.selected_index = -1  # Clear selection when viewport changes

        filtered_apps_iter = iter(
            reversed(sorted(
                [
                    app
                    for app in self._all_apps
                    if query.casefold()
                    in (
                        (app.display_name or "")
                        + (" " + app.name + " ")
                        + (app.generic_name or "")
                    ).casefold()
                ],
                key=lambda app: (app.display_name or "").casefold(),
            ))
        )
        should_resize = operator.length_hint(filtered_apps_iter) == len(self._all_apps)

        self._arranger_handler = idle_add(
            lambda apps_iter: self.add_next_application(apps_iter) or self.handle_arrange_complete(should_resize, query),
            filtered_apps_iter,
            pin=True,
        )
        

    def handle_arrange_complete(self, should_resize, query):
        if should_resize:
            self.resize_viewport()
        # Only auto-select last item(most relevant) if query exists
        if query.strip() != "" and self.viewport.get_children():
            last_index = len(self.viewport.get_children()) - 1
            GLib.idle_add(lambda: self.update_selection(last_index))

        if query.strip() == "":
            # runs on launcher startup
            def on_layout_complete(widget, allocation):
                adj = self.scrolled_window.get_vadjustment()
                adj.set_value(adj.get_upper())
                widget.disconnect(on_layout_complete_id)  # disconnect after one use

            on_layout_complete_id = self.viewport.connect("size-allocate", on_layout_complete)

        return False

    def add_next_application(self, apps_iter: Iterator[DesktopApp]):
        if not (app := next(apps_iter, None)):
            return False
        self.viewport.add(self.bake_application_slot(app))
        return True

    def resize_viewport(self):
        # self.scrolled_window.set_min_content_width(
        #     self.viewport.get_allocation().width  # type: ignore
        # )
        # return False
        viewport_width = self.viewport.get_allocation().width
        max_width = self.scrolled_window.get_max_content_width()
        self.scrolled_window.set_min_content_width(min(viewport_width, max_width))
        return False

    def bake_application_slot(self, app: DesktopApp, **kwargs) -> Button:
        button = Button(
            name="app-slot-button",
            child=Box(
                name="app-slot-box",
                orientation="h",
                spacing=10,
                children=[
                    Label(
                        name="app-label",
                        label=app.display_name or "Unknown",
                        ellipsization="end",
                        v_align="center",
                        h_align="center",
                    ),
                ],
            ),
            tooltip_text=app.description,
            on_clicked=lambda *_: (app.launch(), self.close_launcher()),
            **kwargs,
        )
        return button

    def update_selection(self, new_index: int):
        # Unselect current
        if self.selected_index != -1 and self.selected_index < len(self.viewport.get_children()):
            current_button = self.viewport.get_children()[self.selected_index]
            current_button.get_style_context().remove_class("selected")
        # Select new
        if new_index != -1 and new_index < len(self.viewport.get_children()):
            new_button = self.viewport.get_children()[new_index]
            new_button.get_style_context().add_class("selected")
            self.selected_index = new_index
            self.scroll_to_selected(new_button)
        else:
            self.selected_index = -1

    def scroll_to_selected(self, button):
        def scroll_to_allocation(allocation):
            adj = self.scrolled_window.get_vadjustment()
            y = allocation.y
            height = allocation.height
            page_size = adj.get_page_size()
            current_value = adj.get_value()

            visible_top = current_value
            visible_bottom = current_value + page_size

            if y < visible_top:
                adj.set_value(y)
            elif y + height > visible_bottom:
                adj.set_value(y + height - page_size)

        allocation = button.get_allocation()
        # wait for button allocation
        if allocation.height > 0 and allocation.y >= 0:
            scroll_to_allocation(allocation)
        else:
            def on_size_allocate(widget, alloc):
                scroll_to_allocation(alloc)
                widget.disconnect(handler_id)

            handler_id = button.connect("size-allocate", on_size_allocate)

    def on_search_entry_activate(self, text):
        if text.startswith("="):
            # If in calculator mode and no history item is selected, evaluate new expression.
            if self.selected_index == -1:
                self.evaluate_calculator_expression(text)
            return
        match text:
            case ":w":
                self.notch.open_notch("wallpapers")
            case ":d":
                self.notch.open_notch("dashboard")
            case ":p":
                self.notch.open_notch("power")
            case _:
                children = self.viewport.get_children()
                if children:
                    # Only activate if we have selection or non-empty query
                    if text.strip() == "" and self.selected_index == -1:
                        return  # Prevent accidental activation when empty
                    selected_index = self.selected_index if self.selected_index != -1 else len(children)-1
                    if 0 <= selected_index < len(children):
                        children[selected_index].clicked()

    def on_search_entry_key_press(self, widget, event):
        text = widget.get_text()
        if text.startswith("="):
            if event.keyval == Gdk.KEY_Down:
                self.move_selection(1)
                return True
            elif event.keyval == Gdk.KEY_Up:
                self.move_selection(-1)
                return True
            elif event.keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
                # In calculator mode, if a history item is highlighted, copy it.
                if self.selected_index != -1:
                    if event.state & Gdk.ModifierType.SHIFT_MASK:
                        self.delete_selected_calc_history()
                    else:
                        selected_text = self.calc_history[self.selected_index]
                        self.copy_text_to_clipboard(selected_text)
                        # Clear selection so new expressions are evaluated on further Return presses.
                        self.selected_index = -1
                else:
                    self.evaluate_calculator_expression(text)
                return True
            elif event.keyval == Gdk.KEY_Escape:
                # self.close_launcher() handled in notch. Subject to change
                return True
            return False
        else:
            # Normal app mode behavior
            if event.keyval == Gdk.KEY_Down:
                self.move_selection(1)
                return True
            elif event.keyval == Gdk.KEY_Up:
                self.move_selection(-1)
                return True
            elif event.keyval == Gdk.KEY_Escape:
                # self.close_launcher() handled in notch. Subject to change
                return True
            return False

    def move_selection(self, delta: int):
        children = self.viewport.get_children()
        
        if not children:
            return
        # Allow starting selection from nothing when empty
        if self.selected_index == -1 and delta == 1:
            new_index = len(children)-1
        else:
            if self.selected_index == -1:
                new_index = len(children) + delta
            else: new_index = self.selected_index + delta
        new_index = max(0, min(new_index, len(children) - 1))
        self.update_selection(new_index)

    # def save_calc_history(self):
    #     with open(self.calc_history_path, "w") as f:
    #         json.dump(self.calc_history, f)

    def evaluate_calculator_expression(self, text: str):
        # Remove the '=' prefix and extra spaces
        expr = text.lstrip("=").strip()
        if not expr:
            return
        # Replace operators: '^' -> '**', and '×' -> '*'
        expr = expr.replace("^", "**").replace("×", "*")
        # Replace factorial: e.g. 5! -> math.factorial(5)
        expr = re.sub(r'(\d+)!', r'math.factorial(\1)', expr)
        # Replace brackets: allow [] and {} as ()
        for old, new in [("[", "("), ("]", ")"), ("{", "("), ("}", ")")]:
            expr = expr.replace(old, new)
        try:
            result = eval(expr, {"__builtins__": None, "math": math})
        except Exception as e:
            result = f"Error: {e}"
        # Prepend to history (newest first)
        self.calc_history.insert(0, f"{text} => {result}")
        self.save_calc_history()
        self.update_calculator_viewport()

    def update_calculator_viewport(self):
        self.viewport.children = []
        for item in self.calc_history:
            btn = self.create_calc_history_button(item)
            self.viewport.add(btn)
        # Remove resetting selected_index unconditionally so that a highlighted result isn't lost.
        # Optionally, only reset if the input is not more than "=".
        # if self.search_entry.get_text().strip() != "=":
        #     self.selected_index = -1

    def create_calc_history_button(self, text: str) -> Button:
        btn = Button(
            name="app-slot-button",  # reuse existing CSS styling
            child=Box(
                name="calc-slot-box",
                orientation="h",
                spacing=10,
                children=[
                    Label(
                        name="calc-label",
                        label=text,
                        ellipsization="end",
                        v_align="center",
                        h_align="center",
                    ),
                ],
            ),
            tooltip_text=text,
            on_clicked=lambda *_: self.copy_text_to_clipboard(text),
        )
        return btn

    def copy_text_to_clipboard(self, text: str):
        # Split the text on "=>" and copy only the result part if available
        parts = text.split("=>", 1)
        copy_text = parts[1].strip() if len(parts) > 1 else text
        try:
            subprocess.run(["wl-copy"], input=copy_text.encode(), check=True)
        except subprocess.CalledProcessError as e:
            print(f"Clipboard copy failed: {e}")

    def delete_selected_calc_history(self):
        if self.selected_index != -1 and self.selected_index < len(self.calc_history):
            del self.calc_history[self.selected_index]
            self.save_calc_history()
            self.update_calculator_viewport()