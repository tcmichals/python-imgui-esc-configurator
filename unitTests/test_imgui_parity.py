"""
Parity tests — verify that AppState correctly reflects all user-visible
workflows end-to-end: firmware download, firmware flash progress, settings dirty
tracking, disconnect reset, recommended_next_step state machine, etc.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from imgui_bundle_esc_config.app_state import create_app_state
from imgui_bundle_esc_config.firmware_catalog import FirmwareCatalogSnapshot, FirmwareRelease
from imgui_bundle_esc_config.ui_main import _ellipsize, _status_layout_params, _status_metrics_text
from imgui_bundle_esc_config.worker import (
    EventConnected,
    EventDisconnected,
    EventError,
    EventEscScanResult,
    EventFirmwareCatalogLoaded,
    EventFirmwareDownloaded,
    EventFirmwareFlashed,
    EventMspStats,
    EventMotorCount,
    EventOperationCancelled,
    EventPassthroughState,
    EventProgress,
    EventSettingsLoaded,
    EventSettingsWritten,
    EventFourWayIdentity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_snapshot(*, with_bluejay: bool = True, with_blheli: bool = True) -> FirmwareCatalogSnapshot:
    bluejay_release = FirmwareRelease(
        source="Bluejay",
        family="Bluejay",
        key="v0.21.0",
        name="0.21.0",
        download_url_template="https://example.invalid/bluejay/",
        assets=(("TEST_LAYOUT_48_v0.21.0.hex", "https://example.invalid/TEST_LAYOUT_48_v0.21.0.hex"),),
    )
    blheli_release = FirmwareRelease(
        source="BLHeli_S",
        family="BLHeli_S",
        key="16.7",
        name="16.7",
        download_url_template="https://example.invalid/blheli/",
    )
    releases: dict[str, tuple[FirmwareRelease, ...]] = {}
    if with_bluejay:
        releases["Bluejay"] = (bluejay_release,)
    if with_blheli:
        releases["BLHeli_S"] = (blheli_release,)
    return FirmwareCatalogSnapshot(
        refreshed_at="2026-03-22T00:00:00+00:00",
        releases_by_source=releases,
        layouts_by_source={},
    )


def make_bluejay_settings_payload() -> bytes:
    """Return minimal Bluejay-family raw EEPROM payload."""
    payload = bytearray([0x00] * 0xFF)
    payload[0x02] = 200
    payload[0x60:0x60 + len(b"Bluejay")] = b"Bluejay"
    payload[0x40:0x40 + len(b"TEST_LAYOUT")] = b"TEST_LAYOUT"
    payload[0x50:0x50 + len(b"EFM8BB2")] = b"EFM8BB2"
    return bytes(payload)


def make_blheli_settings_payload() -> bytes:
    """Return minimal BLHeli_S-family raw EEPROM payload."""
    payload = bytearray([0x00] * 0x70)
    payload[0x02] = 32
    payload[0x60:0x60 + len(b"BLHeli_S")] = b"BLHeli_S"
    payload[0x40:0x40 + len(b"TEST_LAYOUT")] = b"TEST_LAYOUT"
    payload[0x50:0x50 + len(b"EFM8BB2")] = b"EFM8BB2"
    return bytes(payload)


# ---------------------------------------------------------------------------
# recommended_next_step() state machine
# ---------------------------------------------------------------------------

def test_recommended_next_step_when_not_connected() -> None:
    state = create_app_state()
    msg = state.recommended_next_step()
    assert "Connect" in msg or "connect" in msg.lower()


def test_recommended_next_step_connected_no_passthrough() -> None:
    state = create_app_state()
    state.apply_event(EventConnected(port="/dev/ttyUSB0", baudrate=115200))
    msg = state.recommended_next_step()
    assert "passthrough" in msg.lower() or "motor" in msg.lower()


def test_recommended_next_step_passthrough_no_escs() -> None:
    state = create_app_state()
    state.apply_event(EventConnected(port="/dev/ttyUSB0", baudrate=115200))
    state.apply_event(EventPassthroughState(active=True, motor_index=0, esc_count=0))
    msg = state.recommended_next_step()
    assert "scan" in msg.lower() or "esc" in msg.lower()


def test_recommended_next_step_passthrough_with_escs_no_settings() -> None:
    state = create_app_state()
    state.apply_event(EventConnected(port="/dev/ttyUSB0", baudrate=115200))
    state.apply_event(EventPassthroughState(active=True, motor_index=0, esc_count=2))
    msg = state.recommended_next_step()
    assert "read settings" in msg.lower() or "settings" in msg.lower()


def test_recommended_next_step_settings_loaded_no_catalog() -> None:
    state = create_app_state()
    state.apply_event(EventConnected(port="/dev/ttyUSB0", baudrate=115200))
    state.apply_event(EventPassthroughState(active=True, motor_index=0, esc_count=2))
    state.apply_event(EventSettingsLoaded(data=make_blheli_settings_payload(), address=0))
    msg = state.recommended_next_step()
    assert "catalog" in msg.lower() or "firmware" in msg.lower()


def test_recommended_next_step_fully_ready() -> None:
    state = create_app_state()
    state.apply_event(EventConnected(port="/dev/ttyUSB0", baudrate=115200))
    state.apply_event(EventPassthroughState(active=True, motor_index=0, esc_count=2))
    state.apply_event(EventSettingsLoaded(data=make_blheli_settings_payload(), address=0))
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=_make_snapshot()))
    msg = state.recommended_next_step()
    # final stage — should mention review/browse/settings/firmware
    assert any(kw in msg.lower() for kw in ("review", "settings", "firmware", "release"))


# ---------------------------------------------------------------------------
# EventFirmwareDownloaded → AppState fields
# ---------------------------------------------------------------------------

def test_app_state_applies_firmware_downloaded_event() -> None:
    state = create_app_state()
    state.firmware_flash_confirmed = True  # should be reset

    state.apply_event(
        EventFirmwareDownloaded(
            file_path="/tmp/test_fw.hex",
            image_name="TEST_LAYOUT_48_v0.21.0.hex",
            family="Bluejay",
            source="Bluejay",
            byte_count=1024,
        )
    )

    assert state.firmware_local_file_path == "/tmp/test_fw.hex"
    assert state.firmware_local_family == "Bluejay"
    assert state.firmware_download_active is False
    assert "TEST_LAYOUT_48_v0.21.0.hex" in state.firmware_download_message
    assert state.firmware_flash_confirmed is False
    assert "TEST_LAYOUT_48_v0.21.0.hex" in state.status_text


# ---------------------------------------------------------------------------
# EventProgress download branch → AppState fields
# ---------------------------------------------------------------------------

def test_app_state_download_progress_active_during_stages() -> None:
    state = create_app_state()

    state.apply_event(EventProgress(operation="download", stage="download", current=0, total=100, message="Downloading…"))
    assert state.firmware_download_active is True
    assert "Downloading" in state.firmware_download_message

    state.apply_event(EventProgress(operation="download", stage="complete", current=100, total=100, message="Done"))
    assert state.firmware_download_active is False
    assert state.firmware_download_message == "Done"


def test_app_state_download_progress_inactive_on_failed_stage() -> None:
    state = create_app_state()
    state.apply_event(EventProgress(operation="download", stage="failed", current=0, total=1, message="Network error"))
    assert state.firmware_download_active is False
    assert "Network error" in state.firmware_download_message


# ---------------------------------------------------------------------------
# EventProgress flash branch → AppState fields
# ---------------------------------------------------------------------------

def test_app_state_flash_progress_updates_stage_and_counts() -> None:
    state = create_app_state()

    state.apply_event(EventProgress(operation="flash", stage="erase", current=1, total=8, message="Erasing page 1"))
    assert state.firmware_flash_active is True
    assert state.firmware_flash_stage == "erase"
    assert state.firmware_flash_current == 1
    assert state.firmware_flash_total == 8
    assert "Erasing page 1" in state.firmware_flash_message

    state.apply_event(EventProgress(operation="flash", stage="complete", current=8, total=8, message="Flash complete"))
    assert state.firmware_flash_active is False
    assert state.firmware_flash_stage == "complete"


def test_app_state_flash_progress_failed_stage_clears_active() -> None:
    state = create_app_state()
    state.apply_event(EventProgress(operation="flash", stage="failed", current=0, total=1, message="Write error"))
    assert state.firmware_flash_active is False
    assert state.firmware_flash_stage == "failed"


# ---------------------------------------------------------------------------
# EventFirmwareFlashed → AppState fields
# ---------------------------------------------------------------------------

def test_app_state_applies_firmware_flashed_event() -> None:
    state = create_app_state()
    state.firmware_flash_active = True  # should be cleared

    state.apply_event(
        EventFirmwareFlashed(
            byte_count=4096,
            verified=True,
            display_name="TEST_LAYOUT_48_v0.21.0.hex",
            family="Bluejay",
            motor_index=0,
        )
    )

    assert state.firmware_flash_active is False
    assert state.firmware_last_flash_size == 4096
    assert state.firmware_last_flash_verified is True
    assert state.firmware_last_flash_name == "TEST_LAYOUT_48_v0.21.0.hex"
    assert state.firmware_flash_stage == "complete"
    assert "TEST_LAYOUT_48_v0.21.0.hex" in state.status_text


# ---------------------------------------------------------------------------
# EventDisconnected resets firmware + diagnostics state
# ---------------------------------------------------------------------------

def test_app_state_disconnect_clears_firmware_and_diagnostics_state() -> None:
    state = create_app_state()
    # Populate state with various values
    state.apply_event(EventConnected(port="/dev/ttyUSB0", baudrate=115200))
    state.firmware_flash_confirmed = True
    state.firmware_download_active = True
    state.firmware_download_message = "Downloading test"
    state.firmware_last_flash_name = "some.hex"
    state.diagnostics_last_export_path = "/tmp/diag"
    state.settings_loaded_motor = 2

    state.apply_event(EventDisconnected(reason="cable pulled"))

    assert state.firmware_flash_confirmed is False
    assert state.firmware_download_active is False
    assert state.firmware_download_message == ""
    assert state.diagnostics_last_export_path == ""
    assert state.settings_loaded_motor == -1
    assert state.connected is False
    assert "cable pulled" in state.status_text


# ---------------------------------------------------------------------------
# EventMspStats → AppState fields
# ---------------------------------------------------------------------------

def test_app_state_applies_msp_stats_event() -> None:
    state = create_app_state()
    state.apply_event(
        EventMspStats(
            total=500,
            errors=10,
            success_percent=98.0,
            error_percent=2.0,
            messages_per_second=50.0,
        )
    )
    assert state.msp_total == 500
    assert state.msp_errors == 10
    assert state.msp_success_percent == 98.0
    assert state.msp_error_percent == 2.0
    assert state.msp_messages_per_second == 50.0


# ---------------------------------------------------------------------------
# select_firmware_source() + visible_firmware_releases() helpers
# ---------------------------------------------------------------------------

def test_app_state_select_firmware_source_updates_key_to_first_release() -> None:
    state = create_app_state()
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=_make_snapshot()))

    state.select_firmware_source("BLHeli_S")

    assert state.selected_firmware_source == "BLHeli_S"
    assert state.selected_firmware_release_key == "16.7"


def test_app_state_visible_releases_empty_without_catalog() -> None:
    state = create_app_state()
    assert state.firmware_catalog is None
    releases = state.visible_firmware_releases()
    assert releases == ()


def test_app_state_visible_releases_returns_all_when_settings_not_loaded() -> None:
    state = create_app_state()
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=_make_snapshot(with_blheli=False)))
    # No settings → all releases shown
    assert state.decoded_settings is None
    releases = state.visible_firmware_releases()
    assert len(releases) == 1
    assert releases[0].family == "Bluejay"


def test_app_state_visible_releases_filters_to_compatible_after_settings_loaded() -> None:
    state = create_app_state()
    compatible = FirmwareRelease(
        source="Bluejay",
        family="Bluejay",
        key="v0.21.0",
        name="0.21.0",
        download_url_template="",
        assets=(("TEST_LAYOUT_48_v0.21.0.hex", "https://example.invalid/"),),
    )
    incompatible = FirmwareRelease(
        source="Bluejay",
        family="Bluejay",
        key="v0.20.0",
        name="0.20.0",
        download_url_template="",
        assets=(("OTHER_LAYOUT_48_v0.20.0.hex", "https://example.invalid/"),),
    )
    snapshot = FirmwareCatalogSnapshot(
        refreshed_at="2026-03-22T00:00:00+00:00",
        releases_by_source={"Bluejay": (incompatible, compatible)},
        layouts_by_source={},
    )
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot))
    state.apply_event(EventSettingsLoaded(data=make_bluejay_settings_payload(), address=0))

    releases = state.visible_firmware_releases()
    assert [r.key for r in releases] == ["v0.21.0"]


# ---------------------------------------------------------------------------
# selected_firmware_release() fallback and alignment
# ---------------------------------------------------------------------------

def test_app_state_selected_release_falls_back_to_first_when_key_missing() -> None:
    state = create_app_state()
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=_make_snapshot(with_blheli=False)))
    state.selected_firmware_release_key = "nonexistent-key"

    release = state.selected_firmware_release()
    # Should fall back to first available
    assert release is not None
    assert release.family == "Bluejay"


def test_app_state_selected_release_returns_none_without_catalog() -> None:
    state = create_app_state()
    assert state.selected_firmware_release() is None


# ---------------------------------------------------------------------------
# selected_firmware_family() delegation
# ---------------------------------------------------------------------------

def test_app_state_selected_family_uses_local_file_family_when_set() -> None:
    state = create_app_state()
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=_make_snapshot()))
    state.firmware_local_family = "BLHeli_S"

    assert state.selected_firmware_family() == "BLHeli_S"


def test_app_state_selected_family_defaults_to_release_family_when_no_local() -> None:
    state = create_app_state()
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=_make_snapshot(with_blheli=False)))
    state.firmware_local_family = ""

    assert state.selected_firmware_family() == "Bluejay"


# ---------------------------------------------------------------------------
# firmware_sources() helper
# ---------------------------------------------------------------------------

def test_app_state_firmware_sources_empty_without_catalog() -> None:
    state = create_app_state()
    assert state.firmware_sources() == []


def test_app_state_firmware_sources_returns_sorted_source_keys() -> None:
    state = create_app_state()
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=_make_snapshot()))
    sources = state.firmware_sources()
    assert "BLHeli_S" in sources
    assert "Bluejay" in sources
    assert sources == sorted(sources)


# ---------------------------------------------------------------------------
# settings_dirty() tracking
# ---------------------------------------------------------------------------

def test_app_state_settings_dirty_false_before_edit() -> None:
    state = create_app_state()
    state.apply_event(EventSettingsLoaded(data=make_blheli_settings_payload(), address=0))
    assert state.decoded_settings is not None
    # Immediately after load, edit values should match decoded settings → not dirty
    assert state.settings_dirty() is False


def test_app_state_settings_dirty_true_after_manual_edit() -> None:
    state = create_app_state()
    state.apply_event(EventSettingsLoaded(data=make_blheli_settings_payload(), address=0))
    assert state.decoded_settings is not None
    # Mutate one edit value arbitrarily
    for key in state.settings_edit_values:
        original = state.settings_edit_values[key]
        state.settings_edit_values[key] = object()  # guaranteed different
        break
    assert state.settings_dirty() is True


def test_app_state_settings_dirty_false_without_decoded_settings() -> None:
    state = create_app_state()
    assert state.decoded_settings is None
    assert state.settings_dirty() is False


# ---------------------------------------------------------------------------
# EventFirmwareCatalogLoaded auto-selects compatible release after settings read
# ---------------------------------------------------------------------------

def test_app_state_catalog_loaded_after_settings_aligns_release_key() -> None:
    """If the catalog is loaded AFTER settings are read, the selected release
    should auto-align to a compatible entry for the active ESC family."""
    state = create_app_state()
    # Load settings first
    state.apply_event(EventSettingsLoaded(data=make_bluejay_settings_payload(), address=0))
    assert state.firmware_catalog is None

    # Now load catalog — should auto-pick Bluejay source and v0.21.0
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=_make_snapshot()))

    assert state.selected_firmware_source == "Bluejay"
    assert state.selected_firmware_release_key == "v0.21.0"


# ---------------------------------------------------------------------------
# MSP connection state fields
# ---------------------------------------------------------------------------

def test_app_state_connected_port_and_status_set_on_connect() -> None:
    state = create_app_state()
    assert state.connected is False
    state.apply_event(EventConnected(port="/dev/ttyACM0", baudrate=230400))
    assert state.connected is True
    assert state.connected_port == "/dev/ttyACM0"
    assert "/dev/ttyACM0" in state.status_text
    assert "230400" in state.status_text


def test_app_state_fourway_identity_stored_on_event() -> None:
    state = create_app_state()
    state.apply_event(
        EventFourWayIdentity(
            interface_name="Pico4way",
            protocol_version=108,
            interface_version="200.6",
        )
    )
    assert state.fourway_interface_name == "Pico4way"
    assert state.fourway_protocol_version == 108
    assert state.fourway_interface_version == "200.6"


def test_app_state_esc_scan_result_updates_detected_count() -> None:
    state = create_app_state()
    state.apply_event(EventEscScanResult(motor_index=1, esc_count=6))
    assert state.detected_esc_count == 6
    assert "6" in state.status_text


def test_app_state_settings_written_event_updates_write_metadata() -> None:
    state = create_app_state()
    state.apply_event(EventSettingsWritten(address=0x0020, size=128, verified=True))
    assert state.settings_last_write_size == 128
    assert state.settings_last_write_verified is True


# ---------------------------------------------------------------------------
# EventAllEscsFlashed → AppState batch flash state
# ---------------------------------------------------------------------------

def test_app_state_applies_all_escs_flashed_event_success() -> None:
    from imgui_bundle_esc_config.worker import EventAllEscsFlashed
    state = create_app_state()
    state.flash_all_active = True

    state.apply_event(EventAllEscsFlashed(total_attempted=4, total_succeeded=4, motor_indices=(0, 1, 2, 3)))

    assert state.flash_all_active is False
    assert state.flash_all_total == 4
    assert state.flash_all_succeeded == 4
    assert "4/4" in state.flash_all_message
    assert "4/4" in state.status_text


def test_app_state_applies_all_escs_flashed_event_partial_failure() -> None:
    from imgui_bundle_esc_config.worker import EventAllEscsFlashed
    state = create_app_state()
    state.flash_all_active = True

    state.apply_event(EventAllEscsFlashed(total_attempted=4, total_succeeded=2, motor_indices=(1, 3)))

    assert state.flash_all_active is False
    assert state.flash_all_total == 4
    assert state.flash_all_succeeded == 2
    assert "2/4" in state.flash_all_message


def test_app_state_disconnect_clears_flash_all_state() -> None:
    from imgui_bundle_esc_config.worker import EventAllEscsFlashed
    state = create_app_state()
    state.apply_event(EventConnected(port="/dev/ttyUSB0", baudrate=115200))
    state.apply_event(EventAllEscsFlashed(total_attempted=2, total_succeeded=2, motor_indices=(0, 1)))

    state.apply_event(EventDisconnected(reason="test"))

    assert state.flash_all_active is False
    assert state.flash_all_total == 0
    assert state.flash_all_succeeded == 0
    assert state.flash_all_message == ""


def test_app_state_flash_all_progress_event_marks_active() -> None:
    state = create_app_state()
    assert state.flash_all_active is False

    state.apply_event(EventProgress(operation="flash_all", stage="start", current=0, total=4, message="Flash 1/4"))
    assert state.flash_all_active is True
    assert "Flash 1/4" in state.flash_all_message

    state.apply_event(EventProgress(operation="flash_all", stage="complete", current=4, total=4, message="Done"))
    assert state.flash_all_active is False


def test_event_error_resets_all_busy_states() -> None:
    """EventError must reset firmware_flash_active, firmware_download_active, and flash_all_active."""
    state = create_app_state()

    state.firmware_flash_active = True
    state.firmware_download_active = True
    state.flash_all_active = True

    state.apply_event(EventError(message="serial timeout"))

    assert state.firmware_flash_active is False
    assert state.firmware_flash_stage == "failed"
    assert state.firmware_download_active is False
    assert state.flash_all_active is False
    assert state.last_error == "serial timeout"
    assert state.status_text == "serial timeout"


def test_event_operation_cancelled_flash_resets_flash_active() -> None:
    """EventOperationCancelled(operation='flash') must clear flash busy state."""
    state = create_app_state()
    state.firmware_flash_active = True
    state.firmware_flash_stage = "write"

    state.apply_event(EventOperationCancelled(operation="flash"))

    assert state.firmware_flash_active is False
    assert state.firmware_flash_stage == "cancelled"
    assert state.firmware_flash_message == "Cancelled by user"
    assert "cancelled" in state.status_text.lower()


def test_event_operation_cancelled_download_resets_download_active() -> None:
    """EventOperationCancelled(operation='download') must clear download busy state."""
    state = create_app_state()
    state.firmware_download_active = True
    state.firmware_download_message = "Downloading…"

    state.apply_event(EventOperationCancelled(operation="download"))

    assert state.firmware_download_active is False
    assert "cancelled" in state.firmware_download_message.lower()
    assert "cancelled" in state.status_text.lower()


def test_event_operation_cancelled_flash_all_resets_both_states() -> None:
    """EventOperationCancelled(operation='flash_all') must clear both flash and flash_all state."""
    state = create_app_state()
    state.firmware_flash_active = True
    state.flash_all_active = True

    state.apply_event(EventOperationCancelled(operation="flash_all"))

    assert state.firmware_flash_active is False
    assert state.flash_all_active is False
    assert state.firmware_flash_stage == "cancelled"
    assert "cancelled" in state.flash_all_message.lower()


# ---------------------------------------------------------------------------
# Catalog offline cache flag and search filter tests
# ---------------------------------------------------------------------------

def _make_catalog_snapshot(keys: list[str]) -> FirmwareCatalogSnapshot:
    releases = tuple(
        FirmwareRelease(
            source="Bluejay",
            family="Bluejay",
            key=key,
            name=key.lstrip("v"),
            download_url_template=f"https://example.invalid/bluejay/{key}/",
            assets=(),
        )
        for key in keys
    )
    return FirmwareCatalogSnapshot(
        refreshed_at="2024-01-01T00:00:00Z",
        releases_by_source={"Bluejay": releases},
        layouts_by_source={"Bluejay": ()},
    )


def test_event_firmware_catalog_loaded_sets_from_cache_true() -> None:
    """EventFirmwareCatalogLoaded with from_cache=True should set firmware_catalog_from_cache."""
    state = create_app_state()
    snapshot = _make_catalog_snapshot(["v0.21.0"])

    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot, from_cache=True))

    assert state.firmware_catalog_from_cache is True


def test_event_firmware_catalog_loaded_clears_from_cache_on_live_refresh() -> None:
    """EventFirmwareCatalogLoaded with from_cache=False (default) should clear the flag."""
    state = create_app_state()
    state.firmware_catalog_from_cache = True  # pre-set from eager cache
    snapshot = _make_catalog_snapshot(["v0.21.0"])

    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot))

    assert state.firmware_catalog_from_cache is False


def test_firmware_release_search_field_starts_empty() -> None:
    state = create_app_state()
    assert state.firmware_release_search == ""


def test_log_search_field_starts_empty() -> None:
    state = create_app_state()
    assert state.log_search == ""


def test_filtered_logs_matches_message_or_source_case_insensitive() -> None:
    state = create_app_state()
    state.append_log("info", "Firmware download finished", source="worker")
    state.append_log("warning", "Passthrough timeout", source="esc")

    state.log_search = "DownLOAD"
    by_message = state.filtered_logs()
    assert len(by_message) == 1
    assert "download" in by_message[0].message.lower()

    state.log_search = "ESC"
    by_source = state.filtered_logs()
    assert len(by_source) == 1
    assert by_source[0].source == "ESC"


def test_filtered_firmware_releases_matches_name_and_key_case_insensitive() -> None:
    state = create_app_state()
    snapshot = _make_catalog_snapshot(["v0.21.0", "v0.20.0"])
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot))

    state.firmware_release_search = "0.21"
    by_name = state.filtered_firmware_releases()
    assert [release.key for release in by_name] == ["v0.21.0"]

    state.firmware_release_search = "V0.20.0"
    by_key = state.filtered_firmware_releases()
    assert [release.key for release in by_key] == ["v0.20.0"]


def test_cached_catalog_age_helpers_report_label_and_stale_state() -> None:
    state = create_app_state()
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
    snapshot = FirmwareCatalogSnapshot(
        refreshed_at=stale_time,
        releases_by_source={"Bluejay": ()},
        layouts_by_source={"Bluejay": ()},
    )
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot, from_cache=True))

    age_seconds = state.firmware_catalog_cache_age_seconds()
    assert age_seconds is not None
    assert age_seconds >= 29 * 3600
    assert state.firmware_catalog_cache_age_label() != ""
    assert state.firmware_catalog_cache_is_stale(threshold_hours=24.0) is True


def test_cached_catalog_age_helpers_handle_invalid_timestamp_gracefully() -> None:
    state = create_app_state()
    snapshot = FirmwareCatalogSnapshot(
        refreshed_at="not-a-timestamp",
        releases_by_source={"Bluejay": ()},
        layouts_by_source={"Bluejay": ()},
    )
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot, from_cache=True))

    assert state.firmware_catalog_cache_age_seconds() is None
    assert state.firmware_catalog_cache_age_label() == ""
    assert state.firmware_catalog_cache_is_stale() is False


def test_firmware_catalog_status_label_live_source() -> None:
    state = create_app_state()
    snapshot = _make_catalog_snapshot(["v0.21.0", "v0.20.0"])
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot, from_cache=False))

    assert state.firmware_catalog_total_releases() == 2
    assert state.firmware_catalog_source_label() == "Releases: 2"


def test_firmware_catalog_status_label_cached_source_with_age() -> None:
    state = create_app_state()
    cached_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    snapshot = FirmwareCatalogSnapshot(
        refreshed_at=cached_time,
        releases_by_source={"Bluejay": _make_catalog_snapshot(["v0.21.0"]).releases_by_source["Bluejay"]},
        layouts_by_source={"Bluejay": ()},
    )
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot, from_cache=True))

    label = state.firmware_catalog_source_label()
    assert label.startswith("Releases: 1 (cached, age ")
    assert state.firmware_catalog_cache_is_stale(threshold_hours=24.0) is False


def test_firmware_catalog_status_label_cached_source_without_parseable_age() -> None:
    state = create_app_state()
    snapshot = FirmwareCatalogSnapshot(
        refreshed_at="(cached)",
        releases_by_source={"Bluejay": _make_catalog_snapshot(["v0.21.0"]).releases_by_source["Bluejay"]},
        layouts_by_source={"Bluejay": ()},
    )
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot, from_cache=True))

    assert state.firmware_catalog_source_label() == "Releases: 1 (cached)"


def test_stale_warning_helper_visible_for_stale_cached_catalog() -> None:
    state = create_app_state()
    stale_time = (datetime.now(timezone.utc) - timedelta(hours=26)).isoformat()
    snapshot = FirmwareCatalogSnapshot(
        refreshed_at=stale_time,
        releases_by_source={"Bluejay": _make_catalog_snapshot(["v0.21.0"]).releases_by_source["Bluejay"]},
        layouts_by_source={"Bluejay": ()},
    )
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot, from_cache=True))

    assert state.show_firmware_catalog_stale_warning(threshold_hours=24.0) is True
    assert "older than 24h" in state.firmware_catalog_stale_warning_text(threshold_hours=24.0)


def test_stale_warning_helper_hidden_for_fresh_cached_catalog() -> None:
    state = create_app_state()
    fresh_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    snapshot = FirmwareCatalogSnapshot(
        refreshed_at=fresh_time,
        releases_by_source={"Bluejay": _make_catalog_snapshot(["v0.21.0"]).releases_by_source["Bluejay"]},
        layouts_by_source={"Bluejay": ()},
    )
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot, from_cache=True))

    assert state.show_firmware_catalog_stale_warning(threshold_hours=24.0) is False
    assert state.firmware_catalog_stale_warning_text(threshold_hours=24.0) == ""


def test_stale_warning_helper_hidden_for_live_catalog() -> None:
    state = create_app_state()
    snapshot = _make_catalog_snapshot(["v0.21.0"])
    state.apply_event(EventFirmwareCatalogLoaded(snapshot=snapshot, from_cache=False))

    assert state.show_firmware_catalog_stale_warning(threshold_hours=24.0) is False
    assert state.firmware_catalog_stale_warning_text(threshold_hours=24.0) == ""


def test_status_bar_ellipsize_short_text_unchanged() -> None:
    assert _ellipsize("Connected", 20) == "Connected"


def test_status_bar_ellipsize_long_text_truncated_with_ellipsis() -> None:
    source = "This is a deliberately long status message that should truncate"
    out = _ellipsize(source, 20)
    assert len(out) == 20
    assert out.endswith("…")


def test_status_metrics_text_compact_mode() -> None:
    compact = _status_metrics_text(
        msp_success_percent=98.0,
        msp_error_percent=2.0,
        msp_messages_per_second=50.5,
        motor_count=4,
        compact=True,
    )
    assert "MSP 98%" in compact
    assert "Err 2%" in compact
    assert "50.5/s" in compact
    assert "M4" in compact


def test_status_metrics_text_full_mode() -> None:
    full = _status_metrics_text(
        msp_success_percent=99.0,
        msp_error_percent=1.0,
        msp_messages_per_second=12.3,
        motor_count=8,
        compact=False,
    )
    assert "MSP: 99%" in full
    assert "Err: 1%" in full
    assert "Rate: 12.3/s" in full
    assert "Motors: 8" in full


def test_status_layout_params_compact_threshold_behavior() -> None:
    compact_just_below = _status_layout_params(759.9)
    compact_at_boundary = _status_layout_params(760.0)

    assert compact_just_below[0] is True
    assert compact_at_boundary[0] is False


def test_status_layout_params_compact_limits() -> None:
    compact, status_chars, port_chars, metrics_chars = _status_layout_params(500.0)
    assert compact is True
    assert status_chars == 42
    assert port_chars == 28
    assert metrics_chars == 70


def test_status_layout_params_full_limits() -> None:
    compact, status_chars, port_chars, metrics_chars = _status_layout_params(1024.0)
    assert compact is False
    assert status_chars == 120
    assert port_chars == 80
    assert metrics_chars == 120


# ---------------------------------------------------------------------------
# FCSP capability-gated availability computed properties
# ---------------------------------------------------------------------------

def _make_caps_event_with_ops_and_spaces(
    ops_bitmap_bytes: bytes | None,
    spaces_bitmap_bytes: bytes | None,
) -> object:
    """Build an EventFcspCapabilities with explicit bitmaps encoded into TLVs."""
    from comm_proto.fcsp import (
        FCSP_CAP_TLV_SUPPORTED_OPS,
        FCSP_CAP_TLV_SUPPORTED_SPACES,
        FcspTlv,
    )
    from imgui_bundle_esc_config.worker import EventFcspCapabilities

    tlvs: list = []
    if ops_bitmap_bytes is not None:
        tlvs.append(FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_OPS, value=ops_bitmap_bytes))
    if spaces_bitmap_bytes is not None:
        tlvs.append(FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_SPACES, value=spaces_bitmap_bytes))
    return EventFcspCapabilities(peer_name="Tang9k FC", esc_count=4, feature_flags=None, tlvs=tuple(tlvs))


def test_fcsp_computed_props_no_bitmap_returns_none() -> None:
    """When no ops/spaces bitmaps are present, all computed properties return None."""
    state = create_app_state()
    state.apply_event(_make_caps_event_with_ops_and_spaces(None, None))

    assert state.fcsp_settings_read_native_available() is None
    assert state.fcsp_settings_write_native_available() is None
    assert state.fcsp_passthrough_native_available() is None
    assert state.fcsp_motor_speed_native_available() is None
    assert state.fcsp_dshot_io_native_available() is None
    assert state.fcsp_pwm_io_native_available() is None
    assert state.fcsp_flash_native_available() is None


def test_fcsp_computed_props_all_zero_bitmaps_return_false() -> None:
    """All-zero bitmaps → all computed properties return False (nothing advertised)."""
    state = create_app_state()
    state.apply_event(_make_caps_event_with_ops_and_spaces(b"\x00\x00\x00", b"\x00\x00\x00"))

    assert state.fcsp_settings_read_native_available() is False
    assert state.fcsp_settings_write_native_available() is False
    assert state.fcsp_passthrough_native_available() is False
    assert state.fcsp_motor_speed_native_available() is False
    assert state.fcsp_dshot_io_native_available() is False
    assert state.fcsp_pwm_io_native_available() is False
    assert state.fcsp_flash_native_available() is False


def test_fcsp_computed_props_read_block_esc_eeprom_advertised() -> None:
    """READ_BLOCK (op 0x10) + ESC_EEPROM space (0x02) → settings_read_native_available True."""
    from comm_proto.fcsp import FcspAddressSpace, FcspControlOp

    # Set bit for READ_BLOCK (0x10=16) in ops bitmap.
    # Bitmap is LSB-first: bit 16 is byte[2] bit 0
    ops_bm = bytearray(4)
    ops_bm[int(FcspControlOp.READ_BLOCK) // 8] |= 1 << (int(FcspControlOp.READ_BLOCK) % 8)

    # Set bit for ESC_EEPROM (0x02) in spaces bitmap.
    spaces_bm = bytearray(4)
    spaces_bm[int(FcspAddressSpace.ESC_EEPROM) // 8] |= 1 << (int(FcspAddressSpace.ESC_EEPROM) % 8)

    state = create_app_state()
    state.apply_event(_make_caps_event_with_ops_and_spaces(bytes(ops_bm), bytes(spaces_bm)))

    assert state.fcsp_settings_read_native_available() is True
    assert state.fcsp_settings_write_native_available() is False  # WRITE_BLOCK not set
    assert state.fcsp_dshot_io_native_available() is False        # DSHOT_IO space not set


def test_fcsp_computed_props_pt_enter_advertised() -> None:
    """PT_ENTER (op 0x01) advertised → passthrough_native_available True; motor speed still False."""
    from comm_proto.fcsp import FcspControlOp

    ops_bm = bytearray(4)
    ops_bm[int(FcspControlOp.PT_ENTER) // 8] |= 1 << (int(FcspControlOp.PT_ENTER) % 8)

    state = create_app_state()
    state.apply_event(_make_caps_event_with_ops_and_spaces(bytes(ops_bm), None))

    assert state.fcsp_passthrough_native_available() is True
    assert state.fcsp_motor_speed_native_available() is False  # SET_MOTOR_SPEED not set
    assert state.fcsp_settings_read_native_available() is None  # spaces bitmap not present


def test_fcsp_cap_flags_reset_to_none_on_disconnect() -> None:
    """After disconnect, all new op flags and block I/O state are cleared."""
    from comm_proto.fcsp import FcspControlOp, FcspAddressSpace
    from imgui_bundle_esc_config.worker import EventBlockRead, EventBlockWritten

    ops_bm = bytearray(4)
    ops_bm[int(FcspControlOp.PT_ENTER) // 8] |= 1 << (int(FcspControlOp.PT_ENTER) % 8)

    state = create_app_state()
    state.apply_event(EventConnected(port="/dev/ttyUSB0", baudrate=115200))
    state.apply_event(_make_caps_event_with_ops_and_spaces(bytes(ops_bm), None))
    state.apply_event(EventBlockRead(space=int(FcspAddressSpace.DSHOT_IO), address=0, data=b"\x01\x02"))
    state.apply_event(EventBlockWritten(space=int(FcspAddressSpace.PWM_IO), address=0x10, size=3, verified=True))

    # Confirm data was received
    assert state.fcsp_supports_pt_enter is True
    assert state.block_read_data == b"\x01\x02"
    assert state.block_write_verified is True

    state.apply_event(EventDisconnected(reason="test"))

    assert state.fcsp_supports_pt_enter is None
    assert state.fcsp_supports_pt_exit is None
    assert state.fcsp_supports_esc_scan is None
    assert state.fcsp_supports_set_motor_speed is None
    assert state.block_read_space is None
    assert state.block_read_address is None
    assert state.block_read_data is None
    assert state.block_write_space is None
    assert state.block_write_size is None
    assert state.block_write_verified is False


def test_app_state_event_block_read_updates_state() -> None:
    """EventBlockRead stores space/address/data and updates status_text."""
    from comm_proto.fcsp import FcspAddressSpace
    from imgui_bundle_esc_config.worker import EventBlockRead

    state = create_app_state()
    state.apply_event(EventBlockRead(space=int(FcspAddressSpace.DSHOT_IO), address=0x20, data=b"\xAA\xBB\xCC"))

    assert state.block_read_space == int(FcspAddressSpace.DSHOT_IO)
    assert state.block_read_address == 0x20
    assert state.block_read_data == b"\xAA\xBB\xCC"
    assert "0x11" in state.status_text  # DSHOT_IO = 0x11


def test_app_state_event_block_written_updates_state() -> None:
    """EventBlockWritten stores space/address/size/verified and updates status_text."""
    from comm_proto.fcsp import FcspAddressSpace
    from imgui_bundle_esc_config.worker import EventBlockWritten

    state = create_app_state()
    state.apply_event(EventBlockWritten(space=int(FcspAddressSpace.PWM_IO), address=0x00, size=4, verified=True))

    assert state.block_write_space == int(FcspAddressSpace.PWM_IO)
    assert state.block_write_size == 4
    assert state.block_write_verified is True
    assert "verified" in state.status_text


def test_fcsp_summary_lines_include_capability_native_and_block_io_context() -> None:
    """AppState summary helpers should emit concise, operator-readable FCSP status strings."""
    from comm_proto.fcsp import FcspAddressSpace
    from imgui_bundle_esc_config.worker import EventBlockRead, EventBlockWritten

    state = create_app_state()
    state.fcsp_connected_peer = "Tang9k FC"
    state.fcsp_cap_esc_count = 4
    state.fcsp_cap_feature_flags = 0x3
    state.fcsp_cap_descriptions = ["Supported ops bitmap: FF FF"]
    state.fcsp_supports_pt_enter = True
    state.fcsp_supports_set_motor_speed = False
    state.fcsp_supports_read_block = True
    state.fcsp_supports_write_block = True
    state.fcsp_supports_esc_eeprom_space = True
    state.fcsp_supports_pwm_io_space = True
    state.fcsp_supports_dshot_io_space = False
    state.fcsp_supports_flash_space = True

    state.apply_event(EventBlockRead(space=int(FcspAddressSpace.DSHOT_IO), address=0x20, data=b"\xAA\xBB"))
    state.apply_event(EventBlockWritten(space=int(FcspAddressSpace.PWM_IO), address=0x10, size=4, verified=True))

    caps_summary = state.fcsp_capability_summary_line()
    native_summary = state.fcsp_native_paths_summary_line()
    block_summary = state.fcsp_last_block_io_summary_line()

    assert "peer=Tang9k FC" in caps_summary
    assert "ESCs=4" in caps_summary
    assert "Flags=0x3" in caps_summary

    assert "PT=yes" in native_summary
    assert "MOTOR=no" in native_summary
    assert "SETTINGS-R=yes" in native_summary
    assert "DSHOT_IO=no" in native_summary
    assert "FLASH=yes" in native_summary

    assert "read(space=0x11" in block_summary
    assert "write(space=0x10" in block_summary
    assert "verified=yes" in block_summary
