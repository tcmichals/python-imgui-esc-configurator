from __future__ import annotations

import json
from pathlib import Path

from imgui_bundle_esc_config.app_state import create_app_state
from imgui_bundle_esc_config.diagnostics_export import export_diagnostics_bundle


def test_export_diagnostics_bundle_writes_expected_files(tmp_path: Path) -> None:
    state = create_app_state()
    state.append_log("info", "hello diagnostics", source="test")
    state.append_protocol_trace("MSP", "TX MSP_SET_PASSTHROUGH")
    state.connected = True
    state.connected_port = "/dev/ttyUSB0"
    state.passthrough_active = True
    state.passthrough_motor = 2
    state.detected_esc_count = 4
    state.motor_count = 8
    state.msp_total = 42
    state.msp_errors = 2
    state.msp_success_percent = 95.238
    state.msp_error_percent = 4.762
    state.msp_messages_per_second = 31.5
    state.connection_protocol_mode = "optimized_tang9k"
    state.fcsp_connected_peer = "Tang9k FC"
    state.fcsp_cap_esc_count = 4
    state.fcsp_cap_feature_flags = 0x00000003
    state.fcsp_cap_descriptions = ["Supported ops bitmap: FF FF", "DSHOT motor count: 4"]
    state.fcsp_supported_ops_bitmap_hex = "FF FF"
    state.fcsp_supported_spaces_bitmap_hex = "FF"
    state.fcsp_supports_get_link_status = True
    state.fcsp_supports_read_block = True
    state.fcsp_supports_write_block = True
    state.fcsp_supports_esc_eeprom_space = True
    state.fcsp_link_flags = 0x0003
    state.fcsp_link_rx_drops = 5
    state.fcsp_link_crc_err = 2

    bundle_dir = export_diagnostics_bundle(state, output_root=str(tmp_path))

    assert bundle_dir.exists()
    assert bundle_dir.is_dir()

    ui_logs_path = bundle_dir / "ui_logs.json"
    traces_path = bundle_dir / "protocol_traces.json"
    metadata_path = bundle_dir / "session_metadata.json"

    assert ui_logs_path.exists()
    assert traces_path.exists()
    assert metadata_path.exists()

    ui_logs = json.loads(ui_logs_path.read_text(encoding="utf-8"))
    traces = json.loads(traces_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

    assert any(entry["message"] == "hello diagnostics" for entry in ui_logs)
    assert any(entry["message"] == "TX MSP_SET_PASSTHROUGH" for entry in traces)
    assert metadata["connected"] is True
    assert metadata["connected_port"] == "/dev/ttyUSB0"
    assert metadata["passthrough_active"] is True
    assert metadata["passthrough_motor"] == 2
    assert metadata["detected_esc_count"] == 4
    assert metadata["motor_count"] == 8
    assert metadata["msp_total"] == 42
    assert metadata["msp_errors"] == 2
    assert metadata["connection_protocol_mode"] == "optimized_tang9k"
    assert metadata["fcsp_connected_peer"] == "Tang9k FC"
    assert metadata["fcsp_cap_esc_count"] == 4
    assert metadata["fcsp_cap_feature_flags"] == 0x00000003
    assert metadata["fcsp_capability_entry_count"] == 2
    assert metadata["fcsp_capability_descriptions"][0].startswith("Supported ops bitmap")
    assert metadata["fcsp_supported_ops_bitmap_hex"] == "FF FF"
    assert metadata["fcsp_supported_spaces_bitmap_hex"] == "FF"
    assert metadata["fcsp_supports_get_link_status"] is True
    assert metadata["fcsp_supports_read_block"] is True
    assert metadata["fcsp_supports_write_block"] is True
    assert metadata["fcsp_supports_esc_eeprom_space"] is True
    assert metadata["fcsp_link_flags"] == 0x0003
    assert metadata["fcsp_link_rx_drops"] == 5
    assert metadata["fcsp_link_crc_err"] == 2


def test_export_diagnostics_bundle_includes_decoded_settings_and_flash_state(tmp_path: Path) -> None:
    """session_metadata.json must include decoded settings snapshot and flash history."""
    from imgui_bundle_esc_config.settings_decoder import decode_settings_payload

    def _put_ascii(buf: bytearray, offset: int, size: int, text: str) -> None:
        enc = text.encode("ascii")[:size]
        buf[offset:offset + size] = b" " * size
        buf[offset:offset + len(enc)] = enc

    state = create_app_state()

    payload = bytearray([0x00] * 0x70)
    payload[0x02] = 33
    payload[0x0B] = 1
    _put_ascii(payload, 0x40, 16, "A_H_30")
    _put_ascii(payload, 0x50, 16, "EFM8BB21")
    _put_ascii(payload, 0x60, 16, "BLHeli_S")
    state.decoded_settings = decode_settings_payload(bytes(payload), start_address=0)

    state.firmware_last_flash_name = "Bluejay_0.22.0_A_H_30.hex"
    state.firmware_last_flash_size = 4096
    state.firmware_last_flash_verified = True
    state.flash_all_total = 4
    state.flash_all_succeeded = 3

    bundle_dir = export_diagnostics_bundle(state, output_root=str(tmp_path))
    metadata = json.loads((bundle_dir / "session_metadata.json").read_text(encoding="utf-8"))

    assert metadata["decoded_settings_family"] == "BLHeli_S"
    assert metadata["decoded_settings_layout"] == "A_H_30"
    assert metadata["decoded_settings_revision"] == 33
    assert metadata["decoded_settings_field_count"] > 0
    assert metadata["firmware_last_flash_name"] == "Bluejay_0.22.0_A_H_30.hex"
    assert metadata["firmware_last_flash_size"] == 4096
    assert metadata["firmware_last_flash_verified"] is True
    assert metadata["flash_all_total"] == 4
    assert metadata["flash_all_succeeded"] == 3
    assert "firmware_catalog_loaded" in metadata
