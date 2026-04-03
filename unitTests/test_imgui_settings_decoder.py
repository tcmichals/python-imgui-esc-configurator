from __future__ import annotations

from imgui_bundle_esc_config.app_state import create_app_state
from imgui_bundle_esc_config.settings_decoder import (
    build_settings_payload,
    decode_settings_payload,
    get_editable_field_values,
    get_visible_fields,
    validate_setting_edits,
)
from imgui_bundle_esc_config.worker import EventSettingsLoaded


def _put_ascii(buf: bytearray, offset: int, size: int, text: str) -> None:
    encoded = text.encode("ascii")[:size]
    buf[offset:offset + size] = b" " * size
    buf[offset:offset + len(encoded)] = encoded


def test_decode_blheli_s_settings_payload() -> None:
    payload = bytearray([0x00] * 0x70)
    payload[0x00] = 16
    payload[0x01] = 9
    payload[0x02] = 33
    payload[0x0B] = 2
    payload[0x15] = 4
    payload[0x1F] = 3
    payload[0x1D] = 4
    payload[0x23] = 1
    payload[0x27] = 1
    _put_ascii(payload, 0x40, 16, "A_H_30")
    _put_ascii(payload, 0x50, 16, "EFM8BB21")
    _put_ascii(payload, 0x60, 16, "BLHeli_S")

    decoded = decode_settings_payload(bytes(payload), start_address=0)

    assert decoded.family == "BLHeli_S"
    assert decoded.layout_revision == 33
    assert decoded.firmware_name == "BLHeli_S"
    assert decoded.layout_name == "A_H_30"
    assert decoded.mcu_name == "EFM8BB21"

    by_name = {field.name: field for field in decoded.fields}
    assert by_name["MOTOR_DIRECTION"].display_value == "Reversed"
    assert by_name["COMMUTATION_TIMING"].display_value == "MediumHigh / 22.5°"
    assert by_name["BRAKE_ON_STOP"].display_value == "Enabled"


def test_decode_bluejay_settings_payload() -> None:
    payload = bytearray([0x00] * 0xFF)
    payload[0x00] = 0
    payload[0x01] = 22
    payload[0x02] = 209
    payload[0x04] = 51
    payload[0x07] = 5
    payload[0x0A] = 48
    payload[0x2A] = 1
    payload[0x2B] = 170
    payload[0x2C] = 85
    _put_ascii(payload, 0x40, 16, "A_X_20")
    _put_ascii(payload, 0x50, 16, "EFM8BB21F16G")
    _put_ascii(payload, 0x60, 16, "Bluejay")

    decoded = decode_settings_payload(bytes(payload), start_address=0)

    assert decoded.family == "Bluejay"
    assert decoded.layout_revision == 209
    assert decoded.firmware_name == "Bluejay"

    by_name = {field.name: field for field in decoded.fields}
    assert by_name["STARTUP_POWER_MIN"].display_value == "51"
    assert by_name["PWM_FREQUENCY"].display_value == "48kHz"
    assert by_name["FORCE_EDT_ARM"].display_value == "Enabled"


def test_app_state_applies_structured_settings_decode() -> None:
    state = create_app_state()
    payload = bytearray([0x00] * 0x70)
    payload[0x02] = 33
    payload[0x0B] = 1
    _put_ascii(payload, 0x60, 16, "BLHeli_S")

    state.apply_event(EventSettingsLoaded(data=bytes(payload), address=0))

    assert state.decoded_settings is not None
    assert state.decoded_settings.family == "BLHeli_S"
    assert state.settings_size == 0x70
    assert state.settings_hex_preview


def test_get_editable_field_values_and_roundtrip_encode() -> None:
    payload = bytearray([0x00] * 0x70)
    payload[0x02] = 33
    payload[0x0B] = 1
    payload[0x15] = 3
    payload[0x1D] = 2
    payload[0x27] = 0
    _put_ascii(payload, 0x60, 16, "BLHeli_S")

    decoded = decode_settings_payload(bytes(payload), start_address=0)
    editable = get_editable_field_values(decoded)

    assert editable["MOTOR_DIRECTION"] == 1
    assert editable["COMMUTATION_TIMING"] == 3
    assert editable["BEACON_DELAY"] == 2
    assert editable["BRAKE_ON_STOP"] == 0

    updated_payload = build_settings_payload(
        decoded,
        {
            "MOTOR_DIRECTION": 2,
            "COMMUTATION_TIMING": 5,
            "BRAKE_ON_STOP": 1,
        },
    )

    assert updated_payload[0x0B] == 2
    assert updated_payload[0x15] == 5
    assert updated_payload[0x27] == 1
    assert updated_payload[0x60:0x68] == payload[0x60:0x68]


def test_app_state_tracks_dirty_settings_edits() -> None:
    state = create_app_state()
    payload = bytearray([0x00] * 0x70)
    payload[0x02] = 33
    payload[0x0B] = 1
    _put_ascii(payload, 0x60, 16, "BLHeli_S")

    state.apply_event(EventSettingsLoaded(data=bytes(payload), address=0))

    assert state.settings_dirty() is False
    state.settings_edit_values["MOTOR_DIRECTION"] = 2
    assert state.settings_dirty() is True


def test_bluejay_dynamic_pwm_visibility_and_sanitize() -> None:
    payload = bytearray([0x00] * 0xFF)
    payload[0x02] = 209
    payload[0x0A] = 0
    payload[0x2B] = 170
    payload[0x2C] = 85
    _put_ascii(payload, 0x60, 16, "Bluejay")

    decoded = decode_settings_payload(bytes(payload), start_address=0)
    visible_names = {field.name for field in get_visible_fields(decoded, get_editable_field_values(decoded))}
    assert "THRESHOLD_48to24" in visible_names
    assert "THRESHOLD_96to48" in visible_names

    updated_payload = build_settings_payload(
        decoded,
        {
            "PWM_FREQUENCY": 0,
            "THRESHOLD_96to48": 200,
            "THRESHOLD_48to24": 100,
        },
    )

    assert updated_payload[0x2B] == 100
    assert updated_payload[0x2C] == 100


def test_bluejay_threshold_validation_fails_without_sanitize_path() -> None:
    payload = bytearray([0x00] * 0xFF)
    payload[0x02] = 209
    payload[0x0A] = 0
    _put_ascii(payload, 0x60, 16, "Bluejay")
    decoded = decode_settings_payload(bytes(payload), start_address=0)

    errors = validate_setting_edits(
        decoded,
        {
            "PWM_FREQUENCY": 0,
            "THRESHOLD_96to48": 200,
            "THRESHOLD_48to24": 100,
        },
    )
    assert any("96→48 <= 48→24" in error for error in errors)


def test_blheli_visibility_hides_3d_only_field_when_not_3d() -> None:
    payload = bytearray([0xFF] * 0xFF)
    payload[0x02] = 209
    payload[0x0A] = 24
    payload[0x0B] = 1
    _put_ascii(payload, 0x60, 16, "Bluejay")
    decoded = decode_settings_payload(bytes(payload), start_address=0)

    visible_names = {field.name for field in get_visible_fields(decoded, get_editable_field_values(decoded))}
    assert "PPM_CENTER_THROTTLE" not in visible_names

    visible_3d = {
        field.name
        for field in get_visible_fields(decoded, {**get_editable_field_values(decoded), "MOTOR_DIRECTION": 3})
    }
    assert "PPM_CENTER_THROTTLE" in visible_3d


def test_bluejay_startup_melody_field_is_decoded_as_bytes() -> None:
    """STARTUP_MELODY is a 128-byte raw-bytes field — not a string or integer."""
    payload = bytearray([0x00] * 0xFF)
    payload[0x02] = 209
    _put_ascii(payload, 0x60, 16, "Bluejay")
    # Set a non-trivial melody region
    for i in range(128):
        payload[0x70 + i] = (i * 3) & 0xFF

    decoded = decode_settings_payload(bytes(payload), start_address=0)

    melody_field = next((f for f in decoded.fields if f.name == "STARTUP_MELODY"), None)
    assert melody_field is not None, "STARTUP_MELODY field missing from Bluejay decoded settings"
    assert melody_field.field_type == "bytes"
    assert melody_field.size == 128
    assert isinstance(melody_field.raw_value, bytes)
    assert len(melody_field.raw_value) == 128
    assert melody_field.editable is False
    # Display value should summarise non-zero count, not dump raw hex
    assert "bytes" in melody_field.display_value


def test_bluejay_startup_melody_wait_ms_is_decoded_as_uint16() -> None:
    """STARTUP_MELODY_WAIT_MS is a 2-byte big-endian uint16 at 0xF0."""
    payload = bytearray([0x00] * 0xFF)
    payload[0x02] = 209
    _put_ascii(payload, 0x60, 16, "Bluejay")
    # 2500 ms → big-endian 0x09 0xC4
    payload[0xF0] = 0x09
    payload[0xF1] = 0xC4

    decoded = decode_settings_payload(bytes(payload), start_address=0)

    wait_field = next((f for f in decoded.fields if f.name == "STARTUP_MELODY_WAIT_MS"), None)
    assert wait_field is not None, "STARTUP_MELODY_WAIT_MS field missing from Bluejay decoded settings"
    assert wait_field.field_type == "number"
    assert wait_field.editable is True
    assert int(wait_field.raw_value) == 2500


def test_bluejay_startup_melody_survives_payload_roundtrip() -> None:
    """build_settings_payload must preserve STARTUP_MELODY bytes unchanged."""
    payload = bytearray([0x00] * 0xFF)
    payload[0x02] = 209
    _put_ascii(payload, 0x60, 16, "Bluejay")
    # Non-trivial melody
    for i in range(128):
        payload[0x70 + i] = (i + 1) & 0xFF

    decoded = decode_settings_payload(bytes(payload), start_address=0)
    edits = get_editable_field_values(decoded)
    built = build_settings_payload(decoded, edits)

    # Melody bytes must be preserved exactly
    assert built[0x70:0x70 + 128] == bytes(payload[0x70:0x70 + 128])


def test_blheli_s_low_rpm_protection_and_startup_beep_fields_decoded() -> None:
    """BLHeli_S payload must decode LOW_RPM_POWER_PROTECTION (0x13 bool, safety)
    and STARTUP_BEEP (0x1A bool, beacon)."""
    payload = bytearray([0x00] * 0x70)
    payload[0x02] = 33
    payload[0x13] = 1  # LOW_RPM_POWER_PROTECTION enabled
    payload[0x1A] = 1  # STARTUP_BEEP enabled
    _put_ascii(payload, 0x60, 16, "BLHeli_S")

    decoded = decode_settings_payload(bytes(payload), start_address=0)
    by_name = {f.name: f for f in decoded.fields}

    assert "LOW_RPM_POWER_PROTECTION" in by_name
    field_lrpp = by_name["LOW_RPM_POWER_PROTECTION"]
    assert field_lrpp.field_type == "bool"
    assert field_lrpp.group == "safety"
    assert field_lrpp.display_value == "Enabled"

    assert "STARTUP_BEEP" in by_name
    field_sb = by_name["STARTUP_BEEP"]
    assert field_sb.field_type == "bool"
    assert field_sb.group == "beacon"
    assert field_sb.display_value == "Enabled"


def test_blheli_s_rampup_rpm_protection_field_decoded() -> None:
    """BLHeli_S payload must decode RAMPUP_RPM_POWER_PROTECTION (0x24 bool, safety)."""
    payload = bytearray([0x00] * 0x70)
    payload[0x02] = 33
    payload[0x24] = 1  # RAMPUP_RPM_POWER_PROTECTION enabled
    _put_ascii(payload, 0x60, 16, "BLHeli_S")

    decoded = decode_settings_payload(bytes(payload), start_address=0)
    by_name = {f.name: f for f in decoded.fields}

    assert "RAMPUP_RPM_POWER_PROTECTION" in by_name
    field = by_name["RAMPUP_RPM_POWER_PROTECTION"]
    assert field.field_type == "bool"
    assert field.group == "safety"
    assert field.display_value == "Enabled"


def test_settings_fields_grouped_by_attribute() -> None:
    """get_visible_fields must return fields with correct group attributes for grouping UI."""
    payload = bytearray([0x00] * 0x70)
    payload[0x02] = 33
    _put_ascii(payload, 0x60, 16, "BLHeli_S")

    decoded = decode_settings_payload(bytes(payload), start_address=0)
    visible = get_visible_fields(decoded, {})

    groups = {f.group for f in visible if f.group}
    # BLHeli_S fields must span at least safety, beacon, and general groups
    assert "safety" in groups
    assert "beacon" in groups
