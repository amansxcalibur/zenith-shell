import sys
import shutil
import subprocess
from pathlib import Path
from loguru import logger
from PIL import Image, ImageFilter

from fabric.utils.helpers import exec_shell_command_async

from .helpers import get_screen_resolution_i3

from config.config import config
from config.info import ROOT_DIR, CACHE_DIR as cache_dir_str, IS_WAYLAND

CACHE_DIR = Path(cache_dir_str)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
LOCKSCREEN_RESOURCE_DIR = Path(CACHE_DIR) / "lockscreen"
LOCKSCREEN_IMG_FILE = LOCKSCREEN_RESOURCE_DIR / "lockscreen.png"
LOCKSCREEN_BLURRED_IMG_FILE = LOCKSCREEN_RESOURCE_DIR / "lockscreen_blurred.png"


def lock_screen():
    if config.get("system.LOCKSCREEN") == "zenith":
        lock_path = ROOT_DIR / "lock"

        if lock_path.exists():
            subprocess.Popen(
                [sys.executable, "-m", "lock"],
                cwd=ROOT_DIR,
                start_new_session=True,
            )
    else:
        _lock_with_external_locker()


def get_cached_lockscreen(
    wallpaper: Path,
) -> Path:
    # width, height = get_screen_resolution()

    # mtime = int(wallpaper.stat().st_mtime)
    # cache_name = f"lock_{mtime}_{width}x{height}.png"
    # cached = CACHE_DIR / cache_name

    # if cached.exists():
    #     return cached

    if LOCKSCREEN_IMG_FILE.exists():
        return LOCKSCREEN_IMG_FILE
    else:
        # maybe I shouldn't do this (causes delay)
        return generate_lockscreen_image(wallpaper)


def _lock_with_external_locker() -> None:
    from modules.wallpaper import WallpaperService

    lock_app = "swaylock" if IS_WAYLAND else "i3lock"
    if not shutil.which(lock_app):
        logger.error(f"'{lock_app}' binary not found.")
        exec_shell_command_async(
            f"notify-send -a 'Zenith Utils' 'Zenith Error' '\"{lock_app}\" not found. Failed to lock screen.'"
        )
        return

    wallpaper = WallpaperService().get_wallpaper_path()
    if wallpaper is None:
        subprocess.Popen([lock_app], start_new_session=True)
        return

    cached_img = get_cached_lockscreen(Path(wallpaper))
    subprocess.Popen([lock_app, "-i", str(cached_img)], start_new_session=True)


def get_available_external_locker() -> str | None:
    preferred = "swaylock" if IS_WAYLAND else "i3lock"
    if shutil.which(preferred):
        return preferred
    return None


def generate_lockscreen_image(image_path: str | Path) -> Path | None:
    try:
        LOCKSCREEN_RESOURCE_DIR.mkdir(parents=True, exist_ok=True)

        tmp = LOCKSCREEN_IMG_FILE.with_suffix(".tmp")
        tmp_blurred = LOCKSCREEN_BLURRED_IMG_FILE.with_suffix(".tmp")
        width, height = get_screen_resolution_i3()

        with Image.open(image_path) as img:
            img = img.convert("RGB")
            iw, ih = img.size

            scale = max(width / iw, height / ih)
            new_size = (int(iw * scale), int(ih * scale))
            img = img.resize(new_size, Image.LANCZOS)

            # Center crop
            left = (img.width - width) // 2
            top = (img.height - height) // 2
            right = left + width
            bottom = top + height

            img = img.crop((left, top, right, bottom))

            # blurred
            scale_factor = 0.5
            small_size = (int(width * scale_factor), int(height * scale_factor))
            blurred_img = img.resize(small_size, Image.Resampling.BILINEAR)
            blurred_img = blurred_img.filter(
                ImageFilter.GaussianBlur(radius=10 * scale_factor)
            )
            blurred_img = blurred_img.resize((width, height), Image.Resampling.BILINEAR)

            LOCKSCREEN_IMG_FILE.parent.mkdir(parents=True, exist_ok=True)
            img.save(tmp, "PNG")
            blurred_img.save(tmp_blurred, "PNG")

        tmp.replace(LOCKSCREEN_IMG_FILE)
        tmp_blurred.replace(LOCKSCREEN_BLURRED_IMG_FILE)

        # returning in case we do hashing and caching later
        return LOCKSCREEN_IMG_FILE

    except Exception as e:
        logger.error(f"Lockscreen generation failed for {image_path}: {e}")
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
