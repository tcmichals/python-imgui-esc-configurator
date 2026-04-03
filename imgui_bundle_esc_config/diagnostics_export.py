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
        "passthrough_active": bool(getattr(state, "passthrough_active", False)),
        "passthrough_motor": int(getattr(state, "passthrough_motor", 0)),
        "detected_esc_count": int(getattr(state, "detected_esc_count", 0)),
        "motor_count": int(getattr(state, "motor_count", 0)),
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
