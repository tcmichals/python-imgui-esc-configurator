"""Minimal structured EEPROM/settings decoding for the ImGui ESC configurator.

This module intentionally starts with the shared BLHeli_S / Bluejay core header
and a small but useful field-description layer. It is designed so the app can
move from raw hex previews toward a parity-oriented structured settings UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


@dataclass(frozen=True)
class SettingOption:
    value: int
    label: str


@dataclass(frozen=True)
class SettingDescriptor:
    name: str
    label: str
    field_type: str
    size: int
    offset: int
    options: tuple[SettingOption, ...] = ()
    group: str = "general"
    editable: bool = True
    min_value: int | None = None
    max_value: int | None = None
    visible_if: Callable[[dict[str, int | str | bytes]], bool] | None = None


@dataclass(frozen=True)
class ParsedSetting:
    name: str
    label: str
    field_type: str
    raw_value: int | str | bytes
    display_value: str
    group: str
    offset: int
    size: int
    editable: bool
    options: tuple[SettingOption, ...] = ()
    min_value: int | None = None
    max_value: int | None = None
    visible_if: Callable[[dict[str, int | str | bytes]], bool] | None = None


@dataclass(frozen=True)
class DecodedSettings:
    family: str
    layout_revision: int | None
    firmware_name: str
    layout_name: str
    mcu_name: str
    start_address: int
    byte_count: int
    source_data: bytes
    fields: tuple[ParsedSetting, ...] = field(default_factory=tuple)


def _enum_options(*pairs: tuple[int, str]) -> tuple[SettingOption, ...]:
    return tuple(SettingOption(value=value, label=label) for value, label in pairs)


def _visible_when_3d(settings: dict[str, int | str | bytes]) -> bool:
    try:
        return int(settings.get("MOTOR_DIRECTION", 0)) in {3, 4}
    except (TypeError, ValueError):
        return False


def _visible_when_dynamic_pwm(settings: dict[str, int | str | bytes]) -> bool:
    try:
        return int(settings.get("PWM_FREQUENCY", 24)) == 0
    except (TypeError, ValueError):
        return False


CORE_DESCRIPTORS: tuple[SettingDescriptor, ...] = (
    SettingDescriptor("MAIN_REVISION", "Main Revision", "number", 1, 0x00, editable=False),
    SettingDescriptor("SUB_REVISION", "Sub Revision", "number", 1, 0x01, editable=False),
    SettingDescriptor("LAYOUT_REVISION", "Layout Revision", "number", 1, 0x02, editable=False),
    SettingDescriptor(
        "MOTOR_DIRECTION",
        "Motor Direction",
        "enum",
        1,
        0x0B,
        _enum_options(
            (1, "Normal"),
            (2, "Reversed"),
            (3, "Forward/Reverse (3D)"),
            (4, "Forward/Reverse (3D) Reversed"),
        ),
        "individual",
    ),
    SettingDescriptor(
        "COMMUTATION_TIMING",
        "Commutation Timing",
        "enum",
        1,
        0x15,
        _enum_options(
            (1, "Low / 0°"),
            (2, "MediumLow / 7.5°"),
            (3, "Medium / 15°"),
            (4, "MediumHigh / 22.5°"),
            (5, "High / 30°"),
        ),
    ),
    SettingDescriptor(
        "DEMAG_COMPENSATION",
        "Demag Compensation",
        "enum",
        1,
        0x1F,
        _enum_options((1, "Off"), (2, "Low"), (3, "High")),
    ),
    SettingDescriptor("BEEP_STRENGTH", "Beep Strength", "number", 1, 0x1B, group="beacon", min_value=0, max_value=255),
    SettingDescriptor("BEACON_STRENGTH", "Beacon Strength", "number", 1, 0x1C, group="beacon", min_value=0, max_value=255),
    SettingDescriptor(
        "BEACON_DELAY",
        "Beacon Delay",
        "enum",
        1,
        0x1D,
        _enum_options(
            (1, "1 minute"),
            (2, "2 minutes"),
            (3, "5 minutes"),
            (4, "10 minutes"),
            (5, "Infinite"),
        ),
        "beacon",
    ),
    SettingDescriptor("LOW_RPM_POWER_PROTECTION", "Low RPM Power Protection", "bool", 1, 0x13, group="safety"),
    SettingDescriptor("STARTUP_BEEP", "Startup Beep", "bool", 1, 0x1A, group="beacon"),
    SettingDescriptor("TEMPERATURE_PROTECTION", "Temperature Protection", "number", 1, 0x23, group="safety", min_value=0, max_value=255),
    SettingDescriptor("RAMPUP_RPM_POWER_PROTECTION", "Rampup RPM Power Protection", "bool", 1, 0x24, group="safety"),
    SettingDescriptor("BRAKE_ON_STOP", "Brake On Stop", "bool", 1, 0x27, group="brake"),
    SettingDescriptor("LED_CONTROL", "LED Control", "number", 1, 0x28, group="individual", min_value=0, max_value=255),
    SettingDescriptor("LAYOUT", "Layout", "string", 16, 0x40, group="identity", editable=False),
    SettingDescriptor("MCU", "MCU", "string", 16, 0x50, group="identity", editable=False),
    SettingDescriptor("NAME", "Firmware Name", "string", 16, 0x60, group="identity", editable=False),
)

BLUEJAY_EXTRA_DESCRIPTORS: tuple[SettingDescriptor, ...] = (
    SettingDescriptor("STARTUP_POWER_MIN", "Startup Power Min", "number", 1, 0x04, min_value=0, max_value=255),
    SettingDescriptor("STARTUP_POWER_MAX", "Startup Power Max", "number", 1, 0x07, min_value=0, max_value=255),
    SettingDescriptor(
        "PWM_FREQUENCY",
        "PWM Frequency",
        "enum",
        1,
        0x0A,
        _enum_options((24, "24kHz"), (48, "48kHz"), (96, "96kHz"), (0, "Dynamic")),
    ),
    SettingDescriptor("BRAKING_STRENGTH", "Braking Strength", "number", 1, 0x10, group="brake", min_value=0, max_value=255),
    SettingDescriptor(
        "POWER_RATING",
        "Power Rating",
        "enum",
        1,
        0x29,
        _enum_options((1, "1S"), (2, "2S+")),
        "safety",
    ),
    SettingDescriptor("FORCE_EDT_ARM", "Force EDT Arm", "bool", 1, 0x2A, group="safety"),
    SettingDescriptor(
        "THRESHOLD_48to24",
        "48→24 Threshold",
        "number",
        1,
        0x2B,
        group="advanced",
        min_value=0,
        max_value=255,
        visible_if=_visible_when_dynamic_pwm,
    ),
    SettingDescriptor(
        "THRESHOLD_96to48",
        "96→48 Threshold",
        "number",
        1,
        0x2C,
        group="advanced",
        min_value=0,
        max_value=255,
        visible_if=_visible_when_dynamic_pwm,
    ),
    SettingDescriptor(
        "PPM_CENTER_THROTTLE",
        "PPM Center Throttle",
        "number",
        1,
        0x21,
        group="individual",
        min_value=0,
        max_value=255,
        visible_if=_visible_when_3d,
    ),
    SettingDescriptor("STARTUP_MELODY", "Startup Melody", "bytes", 128, 0x70, group="advanced", editable=False),
    SettingDescriptor("STARTUP_MELODY_WAIT_MS", "Melody Wait (ms)", "number", 2, 0xF0, group="advanced", min_value=0, max_value=65535),
)


def _read_bytes(data: bytes, start_address: int, offset: int, size: int) -> bytes | None:
    local_start = offset - start_address
    local_end = local_start + size
    if local_start < 0 or local_end > len(data):
        return None
    return data[local_start:local_end]


def _decode_value(descriptor: SettingDescriptor, raw: bytes) -> int | str | bytes:
    if descriptor.field_type == "string":
        return raw.decode("ascii", errors="replace").rstrip("\x00 ")
    if descriptor.field_type == "bytes":
        return bytes(raw)
    if descriptor.field_type == "bool":
        return int(raw[0])
    if descriptor.size == 1:
        return int(raw[0])
    if descriptor.size == 2:
        return (int(raw[0]) << 8) | int(raw[1])
    return raw


def _format_value(descriptor: SettingDescriptor, value: int | str | bytes) -> str:
    if isinstance(value, str):
        return value or "<empty>"
    if isinstance(value, bytes):
        non_zero = sum(1 for b in value if b != 0)
        return f"<{len(value)} bytes, {non_zero} non-zero>"
    if descriptor.field_type == "bool":
        return "Enabled" if value else "Disabled"
    if descriptor.options:
        for option in descriptor.options:
            if option.value == value:
                return option.label
    return str(value)


def _encode_scalar(descriptor: ParsedSetting, value: int | str | bytes) -> bytes:
    if descriptor.field_type == "string":
        text = str(value)
        encoded = text.encode("ascii", errors="replace")[: descriptor.size]
        return encoded.ljust(descriptor.size, b" ")
    if descriptor.field_type in {"bool", "enum", "number"}:
        int_value = int(value)
        if descriptor.size == 1:
            return bytes([int_value & 0xFF])
        if descriptor.size == 2:
            return bytes([(int_value >> 8) & 0xFF, int_value & 0xFF])
    if isinstance(value, bytes):
        return value[: descriptor.size].ljust(descriptor.size, b"\x00")
    raise ValueError(f"Cannot encode field {descriptor.name} of type {descriptor.field_type}")


def _sanitize_edits(decoded: DecodedSettings, edits: dict[str, int | str | bytes]) -> dict[str, int | str | bytes]:
    sanitized = dict(edits)
    if decoded.family == "Bluejay":
        try:
            pwm_frequency = int(sanitized.get("PWM_FREQUENCY", 24))
        except (TypeError, ValueError):
            pwm_frequency = 24

        if pwm_frequency != 0:
            sanitized.pop("THRESHOLD_96to48", None)
            sanitized.pop("THRESHOLD_48to24", None)
        else:
            low = sanitized.get("THRESHOLD_96to48")
            high = sanitized.get("THRESHOLD_48to24")
            if low is not None and high is not None:
                low_int = int(low)
                high_int = int(high)
                if low_int > high_int:
                    sanitized["THRESHOLD_96to48"] = high_int
    return sanitized


def validate_setting_edits(decoded: DecodedSettings, edits: dict[str, int | str | bytes]) -> list[str]:
    errors: list[str] = []
    field_map = {field.name: field for field in decoded.fields}
    merged = get_editable_field_values(decoded)
    merged.update(edits)

    for name, value in merged.items():
        field = field_map.get(name)
        if field is None or not field.editable:
            continue
        if field.min_value is not None or field.max_value is not None:
            try:
                int_value = int(value)
            except (TypeError, ValueError):
                errors.append(f"{field.label}: expected integer value")
                continue
            if field.min_value is not None and int_value < field.min_value:
                errors.append(f"{field.label}: must be >= {field.min_value}")
            if field.max_value is not None and int_value > field.max_value:
                errors.append(f"{field.label}: must be <= {field.max_value}")

    if decoded.family == "Bluejay":
        try:
            pwm_frequency = int(merged.get("PWM_FREQUENCY", 24))
        except (TypeError, ValueError):
            pwm_frequency = 24
        if pwm_frequency == 0:
            low = int(merged.get("THRESHOLD_96to48", 0))
            high = int(merged.get("THRESHOLD_48to24", 0))
            if low > high:
                errors.append("Dynamic PWM thresholds require 96→48 <= 48→24")

    return errors


def get_visible_fields(decoded: DecodedSettings, edits: dict[str, int | str | bytes] | None = None) -> tuple[ParsedSetting, ...]:
    merged = get_editable_field_values(decoded)
    if edits:
        merged.update(edits)

    visible: list[ParsedSetting] = []
    for field in decoded.fields:
        if field.editable and field.name in merged:
            descriptor_visible = True
            if field.visible_if is not None:
                descriptor_visible = field.visible_if(merged)
            if not descriptor_visible:
                continue
        visible.append(field)
    return tuple(visible)


def _detect_family(layout_revision: int | None, firmware_name: str) -> str:
    if "bluejay" in firmware_name.lower() or (layout_revision is not None and layout_revision >= 200):
        return "Bluejay"
    if layout_revision in {32, 33}:
        return "BLHeli_S"
    return "Unknown"


def decode_settings_payload(data: bytes, start_address: int = 0) -> DecodedSettings:
    """Decode a raw EEPROM/settings chunk into a lightweight structured model."""

    if not isinstance(data, bytes):
        data = bytes(data)

    provisional_name = ""
    name_raw = _read_bytes(data, start_address, 0x60, 16)
    if name_raw is not None:
        provisional_name = name_raw.decode("ascii", errors="replace").strip()

    layout_revision_raw = _read_bytes(data, start_address, 0x02, 1)
    layout_revision = int(layout_revision_raw[0]) if layout_revision_raw is not None else None
    family = _detect_family(layout_revision, provisional_name)

    descriptors = list(CORE_DESCRIPTORS)
    if family == "Bluejay":
        descriptors.extend(BLUEJAY_EXTRA_DESCRIPTORS)

    parsed_fields: list[ParsedSetting] = []
    layout_name = ""
    mcu_name = ""
    firmware_name = provisional_name

    for descriptor in descriptors:
        raw = _read_bytes(data, start_address, descriptor.offset, descriptor.size)
        if raw is None:
            continue
        value = _decode_value(descriptor, raw)
        display = _format_value(descriptor, value)
        parsed_fields.append(
            ParsedSetting(
                name=descriptor.name,
                label=descriptor.label,
                field_type=descriptor.field_type,
                raw_value=value,
                display_value=display,
                group=descriptor.group,
                offset=descriptor.offset,
                size=descriptor.size,
                editable=descriptor.editable,
                options=descriptor.options,
                min_value=descriptor.min_value,
                max_value=descriptor.max_value,
                visible_if=descriptor.visible_if,
            )
        )
        if descriptor.name == "LAYOUT" and isinstance(value, str):
            layout_name = value
        elif descriptor.name == "MCU" and isinstance(value, str):
            mcu_name = value
        elif descriptor.name == "NAME" and isinstance(value, str):
            firmware_name = value

    return DecodedSettings(
        family=family,
        layout_revision=layout_revision,
        firmware_name=firmware_name,
        layout_name=layout_name,
        mcu_name=mcu_name,
        start_address=start_address,
        byte_count=len(data),
        source_data=bytes(data),
        fields=tuple(parsed_fields),
    )


def build_settings_payload(decoded: DecodedSettings, edits: dict[str, int | str | bytes]) -> bytes:
    """Apply editable field overrides onto the currently loaded EEPROM payload."""

    edits = _sanitize_edits(decoded, edits)
    errors = validate_setting_edits(decoded, edits)
    if errors:
        raise ValueError("; ".join(errors))

    payload = bytearray(decoded.source_data)
    field_map = {field.name: field for field in decoded.fields}

    for name, value in edits.items():
        field = field_map.get(name)
        if field is None or not field.editable:
            continue
        local_offset = field.offset - decoded.start_address
        if local_offset < 0 or local_offset + field.size > len(payload):
            continue
        encoded = _encode_scalar(field, value)
        payload[local_offset:local_offset + field.size] = encoded

    return bytes(payload)


def get_editable_field_values(decoded: DecodedSettings) -> dict[str, int | str | bytes]:
    """Return the current editable values from a decoded settings payload."""

    return {field.name: field.raw_value for field in decoded.fields if field.editable}
