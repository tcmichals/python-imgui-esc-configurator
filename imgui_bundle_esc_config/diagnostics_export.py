"""Diagnostics export helpers for the ImGui ESC configurator."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
from typing import Any

from .runtime_logging import flush_runtime_logging, get_runtime_log_path


def export_diagnostics_bundle(state: Any, output_root: str | None = None) -> Path:
    """Export UI logs, protocol traces, and runtime metadata to a timestamped folder."""

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    root = Path(output_root).expanduser() if output_root else (Path.cwd() / "diagnostics")
    bundle_dir = root / f"esc-config-diagnostics-{timestamp}"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    logs_payload = [
        {
            "timestamp": getattr(entry, "timestamp", ""),
            "level": getattr(entry, "level", ""),
            "source": getattr(entry, "source", ""),
            "message": getattr(entry, "message", ""),
        }
        for entry in list(getattr(state, "logs", []))
    ]
    (bundle_dir / "ui_logs.json").write_text(json.dumps(logs_payload, indent=2), encoding="utf-8")

    protocol_payload = [
        {
            "timestamp": getattr(entry, "timestamp", ""),
            "channel": getattr(entry, "channel", ""),
            "message": getattr(entry, "message", ""),
        }
        for entry in list(getattr(state, "protocol_traces", []))
    ]
    (bundle_dir / "protocol_traces.json").write_text(json.dumps(protocol_payload, indent=2), encoding="utf-8")

    metadata = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "status_text": getattr(state, "status_text", ""),
        "connected": bool(getattr(state, "connected", False)),
        "connected_port": getattr(state, "connected_port", ""),
        "connection_protocol_mode": getattr(state, "connection_protocol_mode", ""),
        "passthrough_active": bool(getattr(state, "passthrough_active", False)),
        "passthrough_motor": int(getattr(state, "passthrough_motor", 0)),
        "detected_esc_count": int(getattr(state, "detected_esc_count", 0)),
        "motor_count": int(getattr(state, "motor_count", 0)),
        # FCSP capability/link snapshot (optimized mode)
        "fcsp_connected_peer": getattr(state, "fcsp_connected_peer", ""),
        "fcsp_cap_esc_count": getattr(state, "fcsp_cap_esc_count", None),
        "fcsp_cap_feature_flags": getattr(state, "fcsp_cap_feature_flags", None),
        "fcsp_capability_entry_count": len(list(getattr(state, "fcsp_cap_descriptions", []) or [])),
        "fcsp_capability_descriptions": list(getattr(state, "fcsp_cap_descriptions", []) or []),
        "fcsp_supported_ops_bitmap_hex": getattr(state, "fcsp_supported_ops_bitmap_hex", ""),
        "fcsp_supported_spaces_bitmap_hex": getattr(state, "fcsp_supported_spaces_bitmap_hex", ""),
        "fcsp_supports_get_link_status": getattr(state, "fcsp_supports_get_link_status", None),
        "fcsp_supports_read_block": getattr(state, "fcsp_supports_read_block", None),
        "fcsp_supports_write_block": getattr(state, "fcsp_supports_write_block", None),
        "fcsp_supports_pt_enter": getattr(state, "fcsp_supports_pt_enter", None),
        "fcsp_supports_pt_exit": getattr(state, "fcsp_supports_pt_exit", None),
        "fcsp_supports_esc_scan": getattr(state, "fcsp_supports_esc_scan", None),
        "fcsp_supports_set_motor_speed": getattr(state, "fcsp_supports_set_motor_speed", None),
        "fcsp_supports_esc_eeprom_space": getattr(state, "fcsp_supports_esc_eeprom_space", None),
        "fcsp_supports_flash_space": getattr(state, "fcsp_supports_flash_space", None),
        "fcsp_supports_pwm_io_space": getattr(state, "fcsp_supports_pwm_io_space", None),
        "fcsp_supports_dshot_io_space": getattr(state, "fcsp_supports_dshot_io_space", None),
        "fcsp_settings_read_native_available": getattr(state, "fcsp_settings_read_native_available", lambda: None)(),
        "fcsp_settings_write_native_available": getattr(state, "fcsp_settings_write_native_available", lambda: None)(),
        "fcsp_passthrough_native_available": getattr(state, "fcsp_passthrough_native_available", lambda: None)(),
        "fcsp_motor_speed_native_available": getattr(state, "fcsp_motor_speed_native_available", lambda: None)(),
        "fcsp_dshot_io_native_available": getattr(state, "fcsp_dshot_io_native_available", lambda: None)(),
        "fcsp_pwm_io_native_available": getattr(state, "fcsp_pwm_io_native_available", lambda: None)(),
        "fcsp_flash_native_available": getattr(state, "fcsp_flash_native_available", lambda: None)(),
        "block_read_space": getattr(state, "block_read_space", None),
        "block_read_address": getattr(state, "block_read_address", None),
        "block_read_size": (
            len(getattr(state, "block_read_data", b"") or b"")
            if getattr(state, "block_read_data", None) is not None
            else None
        ),
        "block_read_preview_hex": (
            bytes(getattr(state, "block_read_data", b"") or b"")[:32].hex(" ").upper()
            if getattr(state, "block_read_data", None) is not None
            else ""
        ),
        "block_write_space": getattr(state, "block_write_space", None),
        "block_write_address": getattr(state, "block_write_address", None),
        "block_write_size": getattr(state, "block_write_size", None),
        "block_write_verified": bool(getattr(state, "block_write_verified", False)),
        "fcsp_link_flags": getattr(state, "fcsp_link_flags", None),
        "fcsp_link_rx_drops": getattr(state, "fcsp_link_rx_drops", None),
        "fcsp_link_crc_err": getattr(state, "fcsp_link_crc_err", None),
        "fcsp_capability_summary_line": getattr(state, "fcsp_capability_summary_line", lambda: "")(),
        "fcsp_native_paths_summary_line": getattr(state, "fcsp_native_paths_summary_line", lambda: "")(),
        "fcsp_last_block_io_summary_line": getattr(state, "fcsp_last_block_io_summary_line", lambda: "")(),
        "msp_total": int(getattr(state, "msp_total", 0)),
        "msp_errors": int(getattr(state, "msp_errors", 0)),
        "msp_success_percent": float(getattr(state, "msp_success_percent", 0.0)),
        "msp_error_percent": float(getattr(state, "msp_error_percent", 0.0)),
        "msp_messages_per_second": float(getattr(state, "msp_messages_per_second", 0.0)),
        "last_error": getattr(state, "last_error", ""),
        # decoded settings snapshot
        "decoded_settings_family": getattr(getattr(state, "decoded_settings", None), "family", ""),
        "decoded_settings_layout": getattr(getattr(state, "decoded_settings", None), "layout_name", ""),
        "decoded_settings_revision": getattr(getattr(state, "decoded_settings", None), "layout_revision", None),
        "decoded_settings_field_count": len(getattr(getattr(state, "decoded_settings", None), "fields", []) or []),
        "decoded_settings_firmware_name": getattr(getattr(state, "decoded_settings", None), "firmware_name", ""),
        # firmware flash history
        "firmware_last_flash_name": getattr(state, "firmware_last_flash_name", ""),
        "firmware_last_flash_size": int(getattr(state, "firmware_last_flash_size", 0) or 0),
        "firmware_last_flash_verified": bool(getattr(state, "firmware_last_flash_verified", False)),
        "flash_all_total": int(getattr(state, "flash_all_total", 0) or 0),
        "flash_all_succeeded": int(getattr(state, "flash_all_succeeded", 0) or 0),
        # firmware catalog state
        "firmware_catalog_loaded": getattr(state, "firmware_catalog", None) is not None,
        "firmware_catalog_source_count": len(getattr(state, "firmware_catalog", None) or []),
    }
    (bundle_dir / "session_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    flush_runtime_logging()
    runtime_log_path = get_runtime_log_path()
    if runtime_log_path.exists():
        shutil.copy2(runtime_log_path, bundle_dir / runtime_log_path.name)

    return bundle_dir
