"""Session persistence helpers — save/restore user preferences across app runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .app_state import AppState

_PREFS_PATH = Path.home() / ".config" / "pico-msp-bridge" / "prefs.json"

# Keys written to / read from the prefs file.
_PREF_KEYS = [
    ("connection.manual_port", str, ""),
    ("connection.baud_rate", int, 115200),
    ("firmware_local_file_path", str, ""),
    ("firmware_local_family", str, ""),
    ("firmware_remote_pwm_khz", int, 48),
    ("selected_firmware_source", str, ""),
    ("settings_rw_address", int, 0),
    ("settings_rw_length", int, 128),
    ("show_protocol_window", bool, True),
]


def _nested_get(state: "AppState", key: str) -> Any:
    parts = key.split(".", 1)
    obj = getattr(state, parts[0])
    if len(parts) == 2:
        return getattr(obj, parts[1])
    return obj


def _nested_set(state: "AppState", key: str, value: Any) -> None:
    parts = key.split(".", 1)
    if len(parts) == 2:
        obj = getattr(state, parts[0])
        try:
            setattr(obj, parts[1], value)
        except AttributeError:
            pass
    else:
        try:
            setattr(state, parts[0], value)
        except AttributeError:
            pass


def save_prefs(state: "AppState") -> None:
    """Persist operator preferences to disk."""
    prefs: dict[str, Any] = {}
    for key, _type, _default in _PREF_KEYS:
        try:
            prefs[key] = _nested_get(state, key)
        except (AttributeError, TypeError):
            pass
    try:
        _PREFS_PATH.parent.mkdir(parents=True, exist_ok=True)
        _PREFS_PATH.write_text(json.dumps(prefs, indent=2), encoding="utf-8")
    except OSError:
        pass  # non-fatal — just skip saving if disk is unavailable


def load_prefs(state: "AppState") -> None:
    """Restore operator preferences from disk into state."""
    if not _PREFS_PATH.exists():
        return
    try:
        raw = json.loads(_PREFS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for key, cast, default in _PREF_KEYS:
        value = raw.get(key, default)
        try:
            _nested_set(state, key, cast(value))
        except (TypeError, ValueError, AttributeError):
            pass
