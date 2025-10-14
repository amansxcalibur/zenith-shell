from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.label import Label
from fabric.widgets.stack import Stack
from fabric.widgets.eventbox import EventBox
from fabric.widgets.centerbox import CenterBox
from fabric.widgets.x11 import X11Window as Window
from fabric.utils.helpers import get_relative_path, monitor_file

from widgets.shapes import Pill, Circle, WavyCircle, Ellipse, Pentagon
from modules.weather import WeatherPill
from modules.wavy_clock import WavyClock
from config.info import USERNAME

import pam
from loguru import logger
import threading
import time
from typing import Optional


try:
    from Xlib import X, XK
    from Xlib.display import Display

    XLIB_AVAILABLE = True
except ImportError:
    logger.warning("Install python-xlib for grabbing functionality.")
    XLIB_AVAILABLE = False
    display = None

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Gdk


class InputGrabber:
    """Handles X11 keyboard and pointer grabbing."""

    def __init__(self, window, on_keypress_callback):
        self.window = window
        self.on_keypress = on_keypress_callback
        self.display: Optional[Display] = None
        self.xwin = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.special_keys = {
            XK.XK_Return: "Return",
            XK.XK_KP_Enter: "Return",  # Numpad Enter
            XK.XK_BackSpace: "BackSpace",
            XK.XK_Escape: "Escape",
            XK.XK_Delete: "Delete",
            XK.XK_KP_Delete: "Delete",  # Numpad Delete
        }

        self.ignored_keys = {
            XK.XK_Caps_Lock,
            XK.XK_Shift_L,
            XK.XK_Shift_R,
            XK.XK_Control_L,
            XK.XK_Control_R,
            XK.XK_Alt_L,
            XK.XK_Alt_R,
            XK.XK_Meta_L,
            XK.XK_Meta_R,
            XK.XK_Super_L,
            XK.XK_Super_R,
            XK.XK_Hyper_L,
            XK.XK_Hyper_R,
            XK.XK_Num_Lock,
            XK.XK_Scroll_Lock,
        }

    def try_grab(self) -> bool:
        """Attempt to grab keyboard and pointer input."""
        if not XLIB_AVAILABLE:
            logger.error("python-xlib not available; skipping input grab")
            return False

        gdk_window = self.window.get_window()
        if not gdk_window:
            return False

        xid = gdk_window.get_xid()
        self.display = Display()
        self.xwin = self.display.create_resource_object("window", xid)

        self.xwin.change_attributes(
            # override_redirect=True,
            event_mask=X.KeyPressMask
            | X.KeyReleaseMask
        )

        # grab inputs
        keyboard_result = self.xwin.grab_keyboard(
            owner_events=False,
            pointer_mode=X.GrabModeAsync,
            keyboard_mode=X.GrabModeAsync,
            time=X.CurrentTime,
        )
        pointer_result = self.xwin.grab_pointer(
            owner_events=False,
            event_mask=X.ButtonPressMask | X.ButtonReleaseMask | X.PointerMotionMask,
            pointer_mode=X.GrabModeAsync,
            keyboard_mode=X.GrabModeAsync,
            confine_to=X.NONE,
            cursor=X.NONE,
            time=X.CurrentTime,
        )

        # hide cursor
        display = gdk_window.get_display()
        cursor = Gdk.Cursor.new_for_display(display, Gdk.CursorType.BLANK_CURSOR)
        gdk_window.set_cursor(cursor)

        if keyboard_result == X.GrabSuccess:
            logger.info("Keyboard grab successful")
            if pointer_result == X.GrabSuccess:
                logger.info("Pointer grab successful")
            else:
                logger.warning(f"Pointer grab failed ({pointer_result})")
            self._start_event_loop()
            self.display.sync()
            return True
        else:
            logger.warning(f"Keyboard grab failed (result={keyboard_result})")
            return False

    def _start_event_loop(self):
        """Start the X11 event listener thread."""
        self._running = True
        self._thread = threading.Thread(target=self._event_loop, daemon=True)
        self._thread.start()

    def _event_loop(self):
        """Captures X11 events directly (blocking)."""
        while self._running and self.display:
            try:
                if self.display.pending_events():
                    event = self.display.next_event()
                    if event.type == X.KeyPress:
                        self._process_keypress(event)
                else:
                    time.sleep(0.01)
            except Exception as e:
                logger.error(f"Error in X event loop: {e}")
                break

    def _process_keypress(self, event):
        """Process X11 KeyPress events using Xlib's built-in conversion."""
        keycode = event.detail

        # check modifier state
        shift = bool(event.state & X.ShiftMask)
        ctrl = bool(event.state & X.ControlMask)
        alt = bool(event.state & X.Mod1Mask)
        caps_lock = bool(event.state & X.LockMask)

        keysym = self.display.keycode_to_keysym(keycode, 1 if shift else 0)

        # ignore modifier keys
        if keysym in self.ignored_keys:
            return

        # handle special keys
        if keysym in self.special_keys:
            keyname = self.special_keys[keysym]
            logger.debug(f"Special key: {keyname}")
            GLib.idle_add(self.on_keypress, keyname)
            return

        try:
            char = XK.keysym_to_string(keysym)
            if char and len(char) == 1:
                if caps_lock and char.isalpha():
                    char = char.lower() if shift else char.upper()

                # only process printable characters
                if char.isprintable():
                    GLib.idle_add(self.on_keypress, char)
                else:
                    logger.debug(f"Non-printable character (ord={ord(char)})")
            else:
                keysym_base = self.display.keycode_to_keysym(keycode, 0)
                keyname = XK.keysym_to_string(keysym_base)
                logger.debug(f"Unhandled keysym: {keysym} (name={keyname})")

        except Exception as e:
            logger.debug(f"Failed to convert keysym {keysym}: {e}")

    def cleanup(self):
        """Release X11 grabs and cleanup resources."""
        self._running = False

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

        if self.display:
            try:
                self.display.ungrab_keyboard(X.CurrentTime)
                self.display.ungrab_pointer(X.CurrentTime)
                self.display.flush()
                self.display.close()
                logger.info("Input grabs released cleanly")
            except Exception as e:
                logger.warning(f"Failed to cleanup grabs: {e}")
            finally:
                self.display = None


class Authenticator:
    def __init__(self, username: str):
        self.username = username
        self._authenticating = False

    def authenticate(self, password: str, callback):
        """Authenticate in a background thread."""
        if self._authenticating:
            return

        self._authenticating = True

        def auth_thread():
            try:
                success = pam.authenticate(self.username, password)
                if success:
                    GLib.idle_add(callback, True, None)
                else:
                    GLib.idle_add(callback, False, "Incorrect password")
            except Exception as e:
                logger.error(f"PAM authentication error: {e}")
                GLib.idle_add(callback, False, "Authentication error")
            finally:
                self._authenticating = False

        threading.Thread(target=auth_thread, daemon=True).start()

    def is_authenticating(self):
        return self._authenticating


class LockScreen(Window):
    def __init__(self):
        super().__init__(title="Lock Screen", layer="top", type_hint="normal")

        self.fullscreen()
        # self.set_keep_above(True)
        # self.set_app_paintable(True)

        self.grabber = InputGrabber(self, self.handle_keypress)
        self.authenticator = Authenticator(USERNAME)

        self._build_ui()

        self.connect("map-event", self._on_mapped)
        self.connect("destroy", self._on_destroy)

    def _build_ui(self):
        self.status_label = Label(
            label="Enter password",
            style="color: white; font-size: 14px;",
            size_request=(250, -1),
        )

        self.text = ""

        self.shapes = Stack(
            h_align="center",
            children=[
                Pill(dark=True),
                Circle(dark=True),
                WavyCircle(dark=True),
                Ellipse(dark=True),
                Pentagon(dark=True),
            ],
        )

        self.children = CenterBox(
            spacing=10,
            h_expand=True,
            v_expand=True,
            v_align="fill",
            center_children=[
                Box(
                    spacing=10,
                    v_align="center",
                    children=[WavyClock(size=(400, 400)), WeatherPill(size=(400, 400))],
                ),
            ],
            end_children=Box(
                orientation="v",
                v_align="end",
                spacing=10,
                style="margin:20px;",
                children=[
                    EventBox(child=self.shapes), # event box stops whole window redraw for some reason
                    # self.status_label,
                ],
            ),
        )

    def _on_mapped(self, *_):
        GLib.idle_add(self._try_grab_input_with_retry)

    def _try_grab_input_with_retry(self):
        if not self.grabber.try_grab():
            logger.warning("Grab failed, retrying in 100ms...")
            GLib.timeout_add(100, self._try_grab_input_with_retry)
            return False
        return False

    def handle_keypress(self, keyname: str) -> bool:
        """Handle keypresses from X11 grab."""
        if self.authenticator.is_authenticating():
            return False

        if keyname == "Return":
            self._on_entry_activate(self.text)
        elif keyname == "BackSpace":
            self._handle_backspace()
        elif keyname == "Delete":
            pass
        elif keyname == "Escape":
            self._handle_escape()
        elif keyname and len(keyname) == 1:  # Only single characters
            self._handle_character(keyname)

        return False

    def _handle_backspace(self):
        """Handle backspace key - remove last character."""
        if self.text:
            self._cycle_through_shape(forward=False)
            if len(self.text) == 1:
                self._flash_color([1, 1, 1])  # white
            else:
                self._flash_color([1, 0, 0])  # red
            self.text = self.text[:-1]
        else:
            self._flash_color([1, 1, 1])  # white

    def _handle_escape(self):
        """Handle escape key - clear all input."""
        self.text = ""
        self.shapes.set_visible_child(self.shapes.get_children()[0])
        self._flash_color([1, 1, 1])  # white - reset

    def _handle_character(self, char: str):
        """Handle printable character input."""
        self.text += char
        self._cycle_through_shape(forward=True)

    def _flash_color(self, rgb: list):
        """Temporarily flash a color on the current shape."""
        shape = self.shapes.get_visible_child()
        shape.set_color(rgb=rgb, redraw=True)
        GLib.idle_add(lambda: shape.set_color(rgb=None, redraw=False))

    def _cycle_through_shape(self, forward: bool = True):
        if not self.shapes:
            return

        widget_list = self.shapes.get_children()

        current_shape = self.shapes.get_visible_child()
        current_index = widget_list.index(current_shape)

        next_index = (current_index + (1 if forward else -1)) % len(widget_list)
        next_shape = widget_list[next_index]
        self.shapes.set_visible_child(next_shape)

    def _on_entry_activate(self, entry):
        """Handle Enter key press."""
        password = self.text
        if not password:
            return

        self.status_label.set_label("Authenticating...")
        self.shapes.get_visible_child().set_color(rgb=[0, 0, 1], redraw=True)  # blue
        GLib.idle_add(
            lambda: self.shapes.get_visible_child().set_color(rgb=None, redraw=False)
        )
        self.authenticator.authenticate(password, self._on_auth_result)

        self.text = ""

    def _on_auth_result(self, success: bool, message: Optional[str]):
        if success:
            self._flash_color(rgb=[0, 1, 0])
            logger.info("Authentication successful - unlocking")
            self._unlock()
        else:
            self.shapes.get_visible_child().set_color(rgb=[1, 0, 0], redraw=True)  # red
            self.status_label.set_label(message or "Incorrect password")
            self.text = ""
            logger.warning(f"Authentication failed: {message}")
        GLib.idle_add(
            lambda: self.shapes.get_visible_child().set_color(rgb=None, redraw=False)
        )

        return False

    def _unlock(self):
        """Unlock and quit the application."""
        self.grabber.cleanup()
        app = self.get_application()
        if app:
            app.quit()

    def _on_destroy(self, *_):
        """Cleanup on window destroy."""
        self.grabber.cleanup()
        app = self.get_application()
        if app:
            app.quit()


if __name__ == "__main__":
    lock_win = LockScreen()
    app = Application("lockscreen", lock_win)

    def set_css(*args):
        app.set_stylesheet_from_file(get_relative_path("./main.css"))

    app.style_monitor = monitor_file(get_relative_path("./styles"))
    app.style_monitor.connect("changed", set_css)
    set_css()

    app.run()
