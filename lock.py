from fabric.widgets.box import Box
from fabric.widgets.entry import Entry
from fabric.widgets.label import Label


from modules.wavy_clock import WavyCircle
from config.info import USERNAME

import pam
from loguru import logger

try:
    from Xlib import X, display, XK
except ImportError:
    logger.warning("Install python-xlib for grabbing functionality.")
    display = None

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib

KEYSYM_MAP = {
    XK.XK_Return: "Return",
    XK.XK_BackSpace: "BackSpace",
    XK.XK_Escape: "Escape",
    XK.XK_Delete: "Delete",
    # XK.XK_Tab: "Tab",
    # XK.XK_space: " ", # works
}


class LockScreen(Gtk.Window):
    def __init__(self):
        super().__init__(title="Lock Screen")
        self.set_decorated(False)
        self.fullscreen()
        self.set_opacity(1)

        self._running = True
        self._authenticating = False
        self.d = None
        self.win = None

        self.label = Label(label="Enter password (secret)", style="color:white")

        self.entry = Entry(
            name="search-entry",
            placeholder="Search Applications...",
            h_expand=True,
            on_activate=lambda entry, *_: print("on activate"),
            on_key_press_event=lambda *_: print("key presser"),
        )
        self.entry.set_visibility(False)
        self.entry.connect("activate", self.on_enter)

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
                self.label,
                self.entry,
            ],
        )

        self.add(box)
        self.set_keep_above(True)
        self.set_app_paintable(True)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual is not None:
            self.set_visual(visual)

        self.connect("map-event", self.on_mapped)
        self.connect("destroy", Gtk.main_quit)
        self.connect("destroy", lambda *_: (self.cleanup_grab(), Gtk.main_quit()))

    def on_mapped(self, *_):
        self.entry.grab_focus()
        if not display:
            logger.error("python-xlib not available; skipping input grab")
            return
        GLib.idle_add(self.try_grab_inputs)

    def try_grab_inputs(self):
        gdk_window = self.get_window()
        xid = gdk_window.get_xid()

        self.d = display.Display()
        self.win = self.d.create_resource_object("window", xid)

        self.win.change_attributes(
            override_redirect=True, event_mask=X.KeyPressMask | X.KeyReleaseMask
        )

        k = self.win.grab_keyboard(
            owner_events=False,
            pointer_mode=X.GrabModeAsync,
            keyboard_mode=X.GrabModeAsync,
            time=X.CurrentTime,
        )

        if k == X.GrabSuccess:
            logger.info("Keyboard grab successful.")
            # start event listener thread
            import threading

            threading.Thread(target=self.x_event_loop, daemon=True).start()
        else:
            logger.warning(f"Keyboard grab failed ({k}); retrying...")
            GLib.timeout_add(100, self.try_grab_inputs)
            return False

        self.d.sync()
        return False

    def x_event_loop(self):
        """Captures X11 events directly (blocking)."""
        while self._running:
            if self.d.pending_events():
                e = self.d.next_event()  # blocking
                if e.type == X.KeyPress and not self._authenticating:
                    keysym = self.d.keycode_to_keysym(e.detail, e.state)
                    print(keysym, XK.XK_BackSpace)
                    keyname = XK.keysym_to_string(keysym)
                    if keysym in KEYSYM_MAP:
                        keyname = KEYSYM_MAP[keysym]
                    GLib.idle_add(self.handle_keypress, keyname)
            # else:
            #     import time
            #     time.sleep(0.01)

    def handle_keypress(self, keyname):
        """Runs in GTK main thread via GLib.idle_add"""
        if keyname:
            logger.info(f"Key pressed: {keyname}, {type(keyname)}")
            if keyname == "Return":
                self.on_enter(self.entry)
            elif keyname == "BackSpace":
                self.entry.set_text(self.entry.get_text()[:-1])
            elif keyname == "Delete":
                self.entry.set_text(self.entry.get_text()[1:])
            else:
                self.entry.set_text(self.entry.get_text() + keyname)
        return False

    def cleanup_grab(self):
        """Stop thread and clean up X11 resources"""
        self._running = False  # signal thread to stop

        try:
            if hasattr(self, "d") and self.d:
                self.d.ungrab_keyboard(X.CurrentTime)
                self.d.ungrab_pointer(X.CurrentTime)
                self.d.flush()
                self.d.close()  # close the display connection
                logger.info("Keyboard and pointer ungrabbed cleanly.")
        except Exception as e:
            logger.warning(f"Failed to ungrab: {e}")

    def on_enter(self, entry):
        if getattr(self, "_authenticating", False):
            return  # avoid double entry presses

        self._authenticating = True
        password = entry.get_text()
        self.label.set_label("Authenticating...")
        
        def auth_thread():
            success = pam.authenticate(USERNAME, password)
            GLib.idle_add(self.on_auth_result, success)
        
        import threading
        threading.Thread(target=auth_thread, daemon=True).start()

    def on_auth_result(self, success):
        # GTK main thread
        self._authenticating = False
        if success:
            logger.info("Unlocked!")
            self.cleanup_grab()
            Gtk.main_quit()
        else:
            self.label.set_label("Incorrect password")
            self.entry.set_text("")
            logger.warning("Incorrect password.")



if __name__ == "__main__":
    win = LockScreen()
    win.show_all()
    Gtk.main()
