from fabric import Application
from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label
from fabric.widgets.x11 import X11Window as Window
from fabric.utils.helpers import get_relative_path, monitor_file

from modules.wavy_clock import WavyCircle
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
from gi.repository import Gtk, GLib


class InputGrabber:
    """Handles X11 keyboard and pointer grabbing."""
    
    KEYSYM_MAP = {
        XK.XK_Return: "Return",
        XK.XK_BackSpace: "BackSpace",
        XK.XK_Escape: "Escape",
        XK.XK_Delete: "Delete",
    }
    
    def __init__(self, window, on_keypress_callback):
        self.window = window
        self.on_keypress = on_keypress_callback
        self.display: Optional[Display] = None
        self.xwin = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
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
            override_redirect=True,
            event_mask=X.KeyPressMask | X.KeyReleaseMask
        )
        
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
        
        if keyboard_result == X.GrabSuccess:
            logger.info("Keyboard grab successful")
            if pointer_result == X.GrabSuccess:
                logger.info("Pointer grab successful")
            self._start_event_loop()
            self.display.sync()
            return True
        else:
            logger.warning(f"Keyboard grab failed ({keyboard_result})")
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
        keysym = self.display.keycode_to_keysym(event.detail, event.state)
        
        if keysym in self.KEYSYM_MAP:
            keyname = self.KEYSYM_MAP[keysym]
        else:
            keyname = XK.keysym_to_string(keysym)
        
        if keyname:
            GLib.idle_add(self.on_keypress, keyname)
    
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


class LockScreen(Window):
    def __init__(self):
        super().__init__(title="Lock Screen", layer='top', type_hint="normal")
        
        self.fullscreen()
        self.set_keep_above(True)
        self.set_app_paintable(True)
        
        self.grabber = InputGrabber(self, self.handle_keypress)
        self.authenticator = Authenticator(USERNAME)
        
        self._build_ui()
        
        self.connect("map-event", self._on_mapped)
        self.connect("destroy", self._on_destroy)
    
    def _build_ui(self):
        self.status_label = Label(
            label="Enter password",
            style="color: white; font-size: 14px;"
        )
        
        self.entry = Entry(
            name="search-entry",
            placeholder="Password",
            h_expand=True,
        )
        self.entry.set_visibility(False)  # hide password text
        self.entry.connect("activate", self._on_entry_activate)
        
        box = Box(
            orientation="v",
            v_align="center",
            h_expand=True,
            v_expand=True,
            h_align="center",
            spacing=10,
            children=[
                Box(
                    h_expand=True,
                    v_expand=True,
                    h_align="fill",
                    v_align="fill",
                    orientation="v",
                    children=WavyCircle(),
                ),
                self.status_label,
                self.entry,
            ],
        )
        
        self.add(box)
    
    def _on_mapped(self, *_):
        self.entry.grab_focus()
        GLib.idle_add(self._try_grab_input_with_retry)
    
    def _try_grab_input_with_retry(self):
        if not self.grabber.try_grab():
            logger.warning("Grab failed, retrying in 100ms...")
            GLib.timeout_add(100, self._try_grab_input_with_retry)
            return False
        return False
    
    def handle_keypress(self, keyname: str) -> bool:
        """Handle keypresses from X11 grab."""
        if self.authenticator._authenticating:
            return False
        
        if keyname == "Return":
            self._on_entry_activate(self.entry)
        elif keyname == "BackSpace":
            text = self.entry.get_text()
            self.entry.set_text(text[:-1] if text else "")
        elif keyname == "Delete":
            text = self.entry.get_text()
            self.entry.set_text(text[1:] if text else "")
        elif keyname == "Escape":
            self.entry.set_text("")
        elif keyname and len(keyname) == 1:  # Only single characters
            self.entry.set_text(self.entry.get_text() + keyname)
        
        return False
    
    def _on_entry_activate(self, entry):
        """Handle Enter key press."""
        password = entry.get_text()
        if not password:
            return
        
        self.status_label.set_label("Authenticating...")
        self.authenticator.authenticate(password, self._on_auth_result)
    
    def _on_auth_result(self, success: bool, message: Optional[str]):
        if success:
            logger.info("Authentication successful - unlocking")
            self._unlock()
        else:
            self.status_label.set_label(message or "Incorrect password")
            self.entry.set_text("")
            logger.warning(f"Authentication failed: {message}")
        
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
        Gtk.main_quit()

if __name__ == "__main__":
    lock_win = LockScreen()
    app = Application("lockscreen", lock_win)
    
    def set_css(*args):
        app.set_stylesheet_from_file(get_relative_path("./main.css"))

    app.style_monitor = monitor_file(get_relative_path("./styles"))
    app.style_monitor.connect("changed", set_css)
    set_css()
    
    app.run()