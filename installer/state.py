import datetime
import json

from installer.paths import STATE_FILE


def load_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(
    wms: list[str],
    distro: str,
    packages: list[str] | None = None,
    tools: list[str] | None = None,
) -> None:
    """Merge into the state file. Nothing is ever 'forgotten' automatically."""
    state = load_state()
    state["wms"] = sorted(set(state.get("wms", [])) | set(wms))
    state["packages"] = sorted(set(state.get("packages", [])) | set(packages or []))
    state["tools"] = sorted(set(state.get("tools", [])) | set(tools or []))
    state["distro"] = distro
    state["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def update_state(**fields) -> None:
    """Set (or, with None, remove) individual keys in the state file."""
    state = load_state()
    for key, value in fields.items():
        if value is None:
            state.pop(key, None)
        else:
            state[key] = value
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))
