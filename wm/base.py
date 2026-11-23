from abc import ABC, abstractmethod


class WindowManager(ABC):
    name: str  # key in wm.detect.BACKENDS
    label: str = ""  # display name
    can_round_corners = False
    can_blur = False  # for glass mode

    def bootstrap(self, runtime: bool = False):
        self.add_autostart()
        self.write_keybinds(reload=runtime)
        self.write_general(reload=runtime)
        self.write_theme(reload=runtime)

    @abstractmethod
    def add_autostart(self): ...

    @abstractmethod
    def write_keybinds(self, reload: bool = False): ...

    @abstractmethod
    def write_general(self, reload: bool = False):  # gaps, borders, window rules
        ...

    def write_theme(self, color: str | None = None, reload: bool = False):
        pass

    @abstractmethod
    def reload(self): ...

    @abstractmethod
    def exit_session(self): ...

    # X11 only, wayland pills take the keyboard through layer shell
    def focus_shell_window(self, role: str):
        pass

    def unfocus_shell_window(self):
        pass

    def get_screen_size(self) -> tuple[int, int]:
        from utils.helpers import get_screen_resolution_gdk

        return get_screen_resolution_gdk()

    def find_conflicts(self, config_path=None) -> list:
        return []

    def get_corner_radius(self) -> int | None:
        return None

    @abstractmethod
    def build_workspaces(self, vertical: bool = False): ...

    @abstractmethod
    def build_active_window(self): ...
