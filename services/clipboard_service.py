import os
import json
import hashlib
import threading
from dataclasses import dataclass, field
from loguru import logger

from fabric.core.service import Service, Signal

from config.info import CACHE_DIR

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, Gio, GLib, Gtk  # type: ignore


HISTORY_FILE = os.path.join(CACHE_DIR, "clipboard_history.json")
IMAGE_DIR = os.path.join(CACHE_DIR, "clipboard")

# targets password managers (KeePassXC, Bitwarden, ...) attach to secrets
_SENSITIVE_TARGETS = ("x-kde-passwordManagerHint",)
# file managers copy references to files, not their contents
_GNOME_FILES_TARGET = "x-special/gnome-copied-files"
_URI_LIST_TARGET = "text/uri-list"


@dataclass(eq=False)
class ClipEntry:
    kind: str  # "text" | "image" (pixel data) | "files" (references, e.g. Nautilus)
    key: str  # identity used for deduplication
    text: str = ""  # files: their paths, one per line (searchable)
    image_path: str = ""
    width: int = 0
    height: int = 0
    uris: list[str] = field(default_factory=list)

    @property
    def is_image(self) -> bool:
        return self.kind == "image"

    @property
    def is_files(self) -> bool:
        return self.kind == "files"

    @property
    def paths(self) -> list[str]:
        return [Gio.File.new_for_uri(u).get_path() or u for u in self.uris]

    def to_json(self) -> dict:
        if self.is_files:
            return {"kind": "files", "key": self.key, "uris": self.uris}
        if self.is_image:
            return {
                "kind": "image",
                "key": self.key,
                "image_path": self.image_path,
                "width": self.width,
                "height": self.height,
            }
        return {"kind": "text", "key": self.key, "text": self.text}

    @classmethod
    def from_json(cls, data) -> "ClipEntry | None":
        if isinstance(data, str):  # history written before image support
            return cls.for_text(data)
        if not isinstance(data, dict):
            return None
        if data.get("kind") == "files":
            uris = data.get("uris")
            if (
                isinstance(uris, list)
                and uris
                and all(isinstance(u, str) for u in uris)
            ):
                return cls.for_files(uris)
            return None
        if data.get("kind") == "image":
            path = data.get("image_path", "")
            if not (path and os.path.isfile(path)):
                return None
            return cls(
                kind="image",
                key=str(data.get("key") or path),
                image_path=path,
                width=int(data.get("width", 0)),
                height=int(data.get("height", 0)),
            )
        text = data.get("text")
        return cls.for_text(text) if isinstance(text, str) else None

    @classmethod
    def for_text(cls, text: str) -> "ClipEntry":
        return cls(kind="text", key="t:" + _digest(text.encode()), text=text)

    @classmethod
    def for_files(cls, uris: list[str]) -> "ClipEntry":
        entry = cls(
            kind="files", key="f:" + _digest("\n".join(uris).encode()), uris=uris
        )
        entry.text = "\n".join(entry.paths)
        return entry


class _FileSelectionOwner:
    """Owns a selection and serves file references the way file managers do.

    PyGObject can't use Gtk.Clipboard.set_with_data (custom targets), so this
    goes through the lower-level selection API instead."""

    _TARGETS = (
        (_GNOME_FILES_TARGET, 0),  # Nautilus, Nemo, Caja, ...
        (_URI_LIST_TARGET, 1),  # everything else that takes files
        ("UTF8_STRING", 2),  # plain paths for text fields
        ("text/plain;charset=utf-8", 2),
        ("text/plain", 2),
    )

    def __init__(self, selection: Gdk.Atom):
        self._selection = selection
        self._uris: list[str] = []
        self._paths: list[str] = []
        self._widget = Gtk.Invisible()
        self._widget.connect("selection-get", self._on_selection_get)

    def own(self, entry: ClipEntry) -> bool:
        self._uris = list(entry.uris)
        self._paths = entry.paths
        Gtk.selection_clear_targets(self._widget, self._selection)
        for name, info in self._TARGETS:
            Gtk.selection_add_target(
                self._widget, self._selection, Gdk.Atom.intern(name, False), info
            )
        return Gtk.selection_owner_set(
            self._widget, self._selection, Gtk.get_current_event_time()
        )

    def _on_selection_get(self, _widget, data: Gtk.SelectionData, info, _time):
        if info == 0:
            payload = "copy\n" + "\n".join(self._uris)
            data.set(data.get_target(), 8, payload.encode())
        elif info == 1:
            data.set_uris(self._uris)
        else:
            data.set_text("\n".join(self._paths), -1)


def _digest(data: bytes) -> str:
    return hashlib.sha1(data, usedforsecurity=False).hexdigest()


class ClipboardService(Service):
    """Keeps a deduplicated, persisted history of copied text and images,
    newest first."""

    MAX_ENTRIES = 100
    MAX_ENTRY_CHARS = 100_000
    MAX_IMAGE_BYTES = 64 * 1024 * 1024  # raw pixel data
    _SAVE_DELAY_MS = 500

    _instance = None

    @Signal
    def changed(self) -> None: ...

    @classmethod
    def get_default(cls) -> "ClipboardService":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._entries: list[ClipEntry] = self._load()
        self._save_source_id: int | None = None
        # set while our own copy() takes the selection, so the owner-change it
        # triggers isn't recorded a second time (an image may not round-trip
        # to identical pixels)
        self._own_copy_pending = False

        self._clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self._clipboard.connect("owner-change", self._on_owner_change)
        self._file_owner = _FileSelectionOwner(Gdk.SELECTION_CLIPBOARD)

    @property
    def entries(self) -> list[ClipEntry]:
        return list(self._entries)

    # history
    def copy(self, entry: ClipEntry):
        """Put `entry` back on the clipboard; it moves to the top of the history."""
        if entry.is_files:
            # as files again, so pasting in a file manager pastes the files
            self._own_copy_pending = True
            if not self._file_owner.own(entry):
                self._own_copy_pending = False
                logger.warning("[Clipboard] couldn't take the clipboard for files")
                return
            self._push(entry)
            return
        if entry.is_image:
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file(entry.image_path)
            except GLib.Error as e:
                logger.warning(f"[Clipboard] couldn't load {entry.image_path}: {e}")
                return
            self._own_copy_pending = True
            self._clipboard.set_image(pixbuf)
        else:
            self._own_copy_pending = True
            self._clipboard.set_text(entry.text, -1)
        # keep it after we lose ownership (needs a clipboard manager)
        self._clipboard.store()
        self._push(entry)

    def remove(self, entry: ClipEntry):
        if entry in self._entries:
            self._entries.remove(entry)
            self._delete_image(entry)
            self._commit()

    def clear(self):
        if not self._entries:
            return
        # unlink after emptying the list: _delete_image skips referenced files
        dropped, self._entries = self._entries, []
        for entry in dropped:
            self._delete_image(entry)
        self._commit()

    def _push(self, entry: ClipEntry):
        if self._entries and self._entries[0].key == entry.key:
            return
        for old in self._entries:
            if old.key == entry.key:
                self._entries.remove(old)
                # keep the stored file, drop the newly written duplicate
                if entry.is_image and entry.image_path != old.image_path:
                    self._delete_image(entry)
                entry = old
                break
        self._entries.insert(0, entry)
        dropped = self._entries[self.MAX_ENTRIES :]
        del self._entries[self.MAX_ENTRIES :]
        for old in dropped:
            self._delete_image(old)
        self._commit()

    def _commit(self):
        self.changed()
        self._schedule_save()

    # clipboard monitoring
    def _on_owner_change(self, clipboard: Gtk.Clipboard, event):
        if self._own_copy_pending and event.owner is not None:
            self._own_copy_pending = False
            return
        clipboard.request_targets(self._on_targets)

    def _on_targets(self, clipboard: Gtk.Clipboard, targets, *_):
        if not targets:
            return
        names = {t.name() for t in targets}
        if any(t in names for t in _SENSITIVE_TARGETS):
            return
        # files first: file managers also offer the paths as plain text
        if _URI_LIST_TARGET in names or _GNOME_FILES_TARGET in names:
            clipboard.request_uris(self._on_uris, targets)
        else:
            self._request_content(clipboard, targets)

    def _request_content(self, clipboard: Gtk.Clipboard, targets):
        # text wins: apps often offer a rendered image of copied text as well
        if Gtk.targets_include_text(targets):
            clipboard.request_text(self._on_text)
        elif Gtk.targets_include_image(targets, True):
            clipboard.request_image(self._on_image)

    def _on_uris(self, clipboard: Gtk.Clipboard, uris, targets):
        uris = [u for u in uris or () if u]
        # only local files count; a browser's uri-list of web links is text
        if uris and all(u.startswith("file://") for u in uris):
            self._push(ClipEntry.for_files(uris))
        else:
            self._request_content(clipboard, targets)

    def _on_text(self, _clipboard: Gtk.Clipboard, text: str | None, *_):
        if text and text.strip() and len(text) <= self.MAX_ENTRY_CHARS:
            self._push(ClipEntry.for_text(text))

    def _on_image(self, _clipboard: Gtk.Clipboard, pixbuf, *_):
        if pixbuf is None:
            return
        if pixbuf.get_byte_length() > self.MAX_IMAGE_BYTES:
            logger.info("[Clipboard] image too large for history, skipped")
            return
        # hashing + PNG encoding can take a while for screenshots
        threading.Thread(target=self._store_image, args=(pixbuf,), daemon=True).start()

    def _store_image(self, pixbuf: GdkPixbuf.Pixbuf):
        w, h = pixbuf.get_width(), pixbuf.get_height()
        key = "i:" + _digest(
            f"{w}x{h}x{pixbuf.get_rowstride()}:".encode() + pixbuf.get_pixels()
        )
        path = os.path.join(IMAGE_DIR, key[2:] + ".png")
        try:
            os.makedirs(IMAGE_DIR, mode=0o700, exist_ok=True)
            if not os.path.exists(path):
                tmp = path + ".tmp"
                pixbuf.savev(tmp, "png", [], [])
                os.chmod(tmp, 0o600)
                os.replace(tmp, path)
        except (OSError, GLib.Error) as e:
            logger.warning(f"[Clipboard] couldn't store image: {e}")
            return
        entry = ClipEntry(kind="image", key=key, image_path=path, width=w, height=h)
        GLib.idle_add(lambda: self._push(entry) and False)

    def _delete_image(self, entry: ClipEntry):
        if not entry.is_image:
            return
        if any(e.image_path == entry.image_path for e in self._entries):
            return  # still referenced
        try:
            os.remove(entry.image_path)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning(f"[Clipboard] couldn't delete {entry.image_path}: {e}")

    # persistence
    def _load(self) -> list[ClipEntry]:
        try:
            with open(HISTORY_FILE) as f:
                data = json.load(f)
        except FileNotFoundError:
            data = []
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"[Clipboard] couldn't read history: {e}")
            data = []
        if not isinstance(data, list):
            data = []

        entries, seen = [], set()
        for item in data:
            entry = ClipEntry.from_json(item)
            if entry is not None and entry.key not in seen:
                seen.add(entry.key)
                entries.append(entry)
        entries = entries[: self.MAX_ENTRIES]
        self._remove_orphan_images(entries)
        return entries

    @staticmethod
    def _remove_orphan_images(entries: list[ClipEntry]):
        try:
            files = os.listdir(IMAGE_DIR)
        except FileNotFoundError:
            return
        kept = {os.path.basename(e.image_path) for e in entries if e.is_image}
        for name in files:
            if name not in kept:
                try:
                    os.remove(os.path.join(IMAGE_DIR, name))
                except OSError:
                    pass

    def _schedule_save(self):
        if self._save_source_id is not None:
            GLib.source_remove(self._save_source_id)
        self._save_source_id = GLib.timeout_add(self._SAVE_DELAY_MS, self._save)

    def _save(self):
        self._save_source_id = None
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = HISTORY_FILE + ".tmp"
            # history can hold anything that was copied: owner-only
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as f:
                json.dump([e.to_json() for e in self._entries], f)
            os.replace(tmp, HISTORY_FILE)
        except OSError as e:
            logger.warning(f"[Clipboard] couldn't save history: {e}")
        return False
