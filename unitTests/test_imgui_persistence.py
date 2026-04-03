"""Tests for session persistence (load_prefs / save_prefs)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from imgui_bundle_esc_config.app_state import create_app_state
from imgui_bundle_esc_config.persistence import load_prefs, save_prefs


def test_save_prefs_writes_json_file(tmp_path: Path, monkeypatch) -> None:
    """save_prefs must write a valid JSON file with expected keys."""
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr("imgui_bundle_esc_config.persistence._PREFS_PATH", prefs_path)

    state = create_app_state()
    state.connection.manual_port = "/dev/ttyUSB0"
    state.connection.baud_rate = 9600
    state.firmware_local_file_path = "/tmp/bluejay.hex"
    state.firmware_remote_pwm_khz = 24

    save_prefs(state)

    assert prefs_path.exists()
    data = json.loads(prefs_path.read_text(encoding="utf-8"))
    assert data["connection.manual_port"] == "/dev/ttyUSB0"
    assert data["connection.baud_rate"] == 9600
    assert data["firmware_local_file_path"] == "/tmp/bluejay.hex"
    assert data["firmware_remote_pwm_khz"] == 24


def test_load_prefs_restores_state(tmp_path: Path, monkeypatch) -> None:
    """load_prefs must restore previously saved values into a fresh AppState."""
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr("imgui_bundle_esc_config.persistence._PREFS_PATH", prefs_path)

    # Write prefs directly to simulate a previous session
    prefs_path.write_text(json.dumps({
        "connection.manual_port": "/dev/ttyACM1",
        "connection.baud_rate": 115200,
        "firmware_local_file_path": "/home/user/fw.hex",
        "firmware_local_family": "Bluejay",
        "firmware_remote_pwm_khz": 96,
        "selected_firmware_source": "Bluejay",
        "settings_rw_address": 0,
        "settings_rw_length": 255,
        "show_protocol_window": False,
    }), encoding="utf-8")

    state = create_app_state()
    load_prefs(state)

    assert state.connection.manual_port == "/dev/ttyACM1"
    assert state.connection.baud_rate == 115200
    assert state.firmware_local_file_path == "/home/user/fw.hex"
    assert state.firmware_local_family == "Bluejay"
    assert state.firmware_remote_pwm_khz == 96
    assert state.selected_firmware_source == "Bluejay"
    assert state.settings_rw_length == 255
    assert state.show_protocol_window is False


def test_load_prefs_missing_file_is_noop(tmp_path: Path, monkeypatch) -> None:
    """load_prefs must not raise when no prefs file exists."""
    prefs_path = tmp_path / "nonexistent.json"
    monkeypatch.setattr("imgui_bundle_esc_config.persistence._PREFS_PATH", prefs_path)

    state = create_app_state()
    original_baud = state.connection.baud_rate
    load_prefs(state)  # must not raise

    assert state.connection.baud_rate == original_baud


def test_load_prefs_corrupt_file_is_noop(tmp_path: Path, monkeypatch) -> None:
    """load_prefs must not raise when prefs file contains invalid JSON."""
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr("imgui_bundle_esc_config.persistence._PREFS_PATH", prefs_path)
    prefs_path.write_text("{ not valid json {{", encoding="utf-8")

    state = create_app_state()
    original_baud = state.connection.baud_rate
    load_prefs(state)  # must not raise

    assert state.connection.baud_rate == original_baud


def test_save_load_roundtrip(tmp_path: Path, monkeypatch) -> None:
    """save_prefs followed by load_prefs must produce identical state values."""
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr("imgui_bundle_esc_config.persistence._PREFS_PATH", prefs_path)

    state_a = create_app_state()
    state_a.connection.manual_port = "/dev/ttyUSB2"
    state_a.connection.baud_rate = 57600
    state_a.firmware_local_file_path = "/mnt/fw/blheli.hex"
    state_a.firmware_local_family = "BLHeli_S"
    state_a.firmware_remote_pwm_khz = 48
    state_a.settings_rw_length = 192
    state_a.show_protocol_window = True

    save_prefs(state_a)

    state_b = create_app_state()
    load_prefs(state_b)

    assert state_b.connection.manual_port == state_a.connection.manual_port
    assert state_b.connection.baud_rate == state_a.connection.baud_rate
    assert state_b.firmware_local_file_path == state_a.firmware_local_file_path
    assert state_b.firmware_local_family == state_a.firmware_local_family
    assert state_b.firmware_remote_pwm_khz == state_a.firmware_remote_pwm_khz
    assert state_b.settings_rw_length == state_a.settings_rw_length
    assert state_b.show_protocol_window == state_a.show_protocol_window


def test_partial_prefs_file_leaves_unset_keys_at_default(tmp_path: Path, monkeypatch) -> None:
    """A prefs file with only some keys must leave missing keys at default values."""
    prefs_path = tmp_path / "prefs.json"
    monkeypatch.setattr("imgui_bundle_esc_config.persistence._PREFS_PATH", prefs_path)
    prefs_path.write_text(json.dumps({"connection.baud_rate": 38400}), encoding="utf-8")

    state = create_app_state()
    load_prefs(state)

    assert state.connection.baud_rate == 38400
    # Unset key must remain at its default
    assert state.connection.manual_port == ""
    assert state.firmware_local_file_path == ""
