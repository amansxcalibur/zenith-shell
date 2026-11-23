import functools
import importlib

from wm.base import WindowManager
from wm.detect import BACKENDS, bootstrap_wm, detect_session


@functools.cache
def get_wm() -> WindowManager:
    from config.info import IS_WAYLAND

    name = bootstrap_wm() or detect_session()
    if name not in BACKENDS:
        name = "sway" if IS_WAYLAND else "i3"
    module, cls = BACKENDS[name][1].split(":")
    return getattr(importlib.import_module(module), cls)()


@functools.cache
def glass_mode() -> bool:
    from config.config import config
    from config.info import IS_WAYLAND

    return bool(config.get("theme.glass")) and IS_WAYLAND and get_wm().can_blur


def wm_corner_radius() -> int | None:
    return get_wm().get_corner_radius()
