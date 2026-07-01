from fabric.core.service import Service, Property

from config.config import config

class NotificationConfig:
    WIDTH = 360
    MAX_CHARS_PER_LINE = 27
    MAX_CHARS_PER_COLLAPSED_LINE = 33
    LINE_LIMIT = 3
    IMAGE_SIZE = 50
    TIMEOUT = 5 * 1000  # 5 seconds
    TRANSITION_DURATION = 250
    REVEALER_TRANSITION_TYPE = "slide-down"
    MAX_ACTIVE_NOTIFS = 2
    WINDOW_MIN_HEIGHT = 10
    WINDOW_MIN_WIDTH = 364
    WINDOW_MAX_HEIGHT = 700
    WINDOW_MAX_WIDTH = 1900
    SPACING = 3
    MARGIN = 3
    IMAGE_BORDER_RADIUS = 18
    SNAP_THRESHOLD = 50
    SILENT = config.SILENT

class NotificationNotifier(Service):
    _instance = None

    @Property(bool, default_value=False, flags="read-write")
    def has_unread(self) -> bool:
        return self._has_unread

    @has_unread.setter
    def has_unread(self, value: bool) -> None:
        self._has_unread = value
        return

    @Property(bool, default_value=False, flags="read-write")
    def has_urgent_unread(self) -> bool:
        return self._has_urgent_unread

    @has_urgent_unread.setter
    def has_urgent_unread(self, value: bool) -> None:
        self._has_urgent_unread = value
        return

    @Property(bool, default_value=False, flags="read-write")
    def silent(self) -> bool:
        return self._silent

    @silent.setter
    def silent(self, value: bool) -> None:
        self._silent = value
        config.SILENT = value
        return

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        super().__init__()
        self._initialized = True

        self._has_unread = False
        self._has_urgent_unread = False
        self._silent = config.SILENT