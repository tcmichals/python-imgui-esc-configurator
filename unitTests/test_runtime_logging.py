from __future__ import annotations

from pathlib import Path

from imgui_bundle_esc_config.app_state import create_app_state
from imgui_bundle_esc_config.runtime_logging import configure_runtime_logging, flush_runtime_logging, get_runtime_log_path


def test_runtime_logging_writes_ui_and_protocol_entries(tmp_path: Path) -> None:
    log_path = configure_runtime_logging(tmp_path)
    assert log_path == get_runtime_log_path(tmp_path)

    state = create_app_state()
    state.append_log("warning", "ui warning message")
    state.append_protocol_trace("MSP", "TX cmd=245 len=2")
    flush_runtime_logging()

    contents = log_path.read_text(encoding="utf-8")
    assert "Application initialized" in contents
    assert "ui warning message" in contents
    assert "[MSP] TX cmd=245 len=2" in contents
