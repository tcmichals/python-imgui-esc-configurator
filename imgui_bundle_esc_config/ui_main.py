"""ImGui rendering helpers for the ESC configurator shell."""

from __future__ import annotations

from collections import defaultdict
import re
from pathlib import Path

import imgui_bundle
from imgui_bundle import has_submodule, imgui

im_file_dialog = getattr(imgui_bundle, "im_file_dialog", None) if has_submodule("im_file_dialog") else None

from . import APP_VERSION
from .app_state import AppState
from .diagnostics_export import export_diagnostics_bundle
from .runtime_logging import get_runtime_log_path
from .settings_decoder import build_settings_payload, get_visible_fields, validate_setting_edits
from .worker import (
    CommandCancelOperation,
    CommandConnect,
    CommandDownloadFirmware,
    CommandDisconnect,
    CommandEnterPassthrough,
    CommandExitPassthrough,
    CommandFlashEsc,
    CommandFlashAllEscs,
    CommandGetFcspLinkStatus,
    CommandRefreshFirmwareCatalog,
    CommandReadSettings,
    CommandSetMotorSpeed,
    CommandWriteSettings,
    CommandRefreshPorts,
    WorkerController,
)


DSHOT_UI_MIN = 1000
DSHOT_UI_MAX = 2000
FIRMWARE_FILE_DIALOG_KEY = "FirmwareFileOpenDialog"


def _parse_hex_bytes(raw: str) -> bytes:
    text = raw.strip()
    if not text:
        raise ValueError("Enter one or more hex bytes (e.g. '01 02 A0')")

    compact = re.sub(r"[^0-9A-Fa-f]", "", text)
    if len(compact) == 0:
        raise ValueError("No hex digits found")
    if len(compact) % 2 != 0:
        raise ValueError("Hex input must contain an even number of digits")

    data = bytes.fromhex(compact)
    if len(data) > 256:
        raise ValueError("At most 256 bytes can be written in one operation")
    return data


def _ellipsize(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    if max_chars <= 1:
        return "…"
    return text[: max_chars - 1] + "…"


def _status_metrics_text(
    *,
    msp_success_percent: float,
    msp_error_percent: float,
    msp_messages_per_second: float,
    motor_count: int,
    compact: bool,
) -> str:
    if compact:
        return (
            f"MSP {msp_success_percent:.0f}% | "
            f"Err {msp_error_percent:.0f}% | "
            f"{msp_messages_per_second:.1f}/s | "
            f"M{motor_count} | "
            f"v{APP_VERSION}"
        )
    return (
        f"MSP: {msp_success_percent:.0f}%  "
        f"Err: {msp_error_percent:.0f}%  "
        f"Rate: {msp_messages_per_second:.1f}/s  "
        f"Motors: {motor_count}  "
        f"v{APP_VERSION}"
    )


def drain_worker_events(state: AppState, controller: WorkerController) -> None:
    """Apply any worker-generated events to the UI state."""

    for event in controller.poll_events(max_events=100):
        state.apply_event(event)


def _render_step_heading(title: str, color: tuple[float, float, float, float]) -> None:
    imgui.text_colored(color, title)
    imgui.separator()


def render_connection_panel(state: AppState, controller: WorkerController) -> None:
    imgui.text("Protocol")
    selected_mode = 1 if state.connection_protocol_mode == "optimized_tang9k" else 0
    if imgui.radio_button("MSP protocol", selected_mode == 0):
        state.connection_protocol_mode = "msp"
    imgui.same_line()
    if imgui.radio_button("Optimized protocol", selected_mode == 1):
        state.connection_protocol_mode = "optimized_tang9k"

    imgui.separator()

    if imgui.button("Refresh Ports"):
        controller.enqueue(CommandRefreshPorts())

    imgui.same_line()
    button_label = "Disconnect" if state.connected else "Connect"
    if imgui.button(button_label):
        if state.connected:
            controller.enqueue(CommandDisconnect())
        else:
            port = state.selected_port()
            if port:
                controller.enqueue(
                    CommandConnect(
                        port=port,
                        baudrate=state.connection.baud_rate,
                        protocol_mode=state.connection_protocol_mode,
                    )
                )
            else:
                state.append_log("warning", "Select or enter a serial port before connecting")

    available_labels = [
        f"{port.device} — {port.description}" if port.description else port.device
        for port in state.available_ports
    ]
    preview = available_labels[state.selected_port_index] if available_labels else "<no ports detected>"
    if imgui.begin_combo("Detected Ports", preview):
        for index, label in enumerate(available_labels):
            clicked, _selected = imgui.selectable(label, index == state.selected_port_index)
            if clicked:
                state.selected_port_index = index
                state.connection.manual_port = ""
        imgui.end_combo()

    changed_port, manual_port = imgui.input_text("Manual Port Override", state.connection.manual_port, 256)
    if changed_port:
        state.connection.manual_port = manual_port

    changed_baud, baud_rate = imgui.input_int("Baud Rate", state.connection.baud_rate)
    if changed_baud:
        state.connection.baud_rate = max(baud_rate, 1)

    state_label = "Connected" if state.connected else "Disconnected"
    state_color = (0.45, 0.95, 0.55, 1.0) if state.connected else (0.95, 0.85, 0.45, 1.0)
    imgui.text_colored(state_color, state_label)
    imgui.same_line()
    imgui.text(f"Port: {state.selected_port() or '<none>'}")
    imgui.same_line()
    imgui.text(f"Detected: {len(state.available_ports)}")
    imgui.same_line()
    imgui.text(f"Baud: {state.connection.baud_rate}")

    if state.connection_protocol_mode == "optimized_tang9k":
        imgui.separator()
        imgui.text("FCSP Link")
        imgui.text(f"Peer: {state.fcsp_connected_peer or '<probing / unavailable>'}")
        esc_count_text = str(state.fcsp_cap_esc_count) if state.fcsp_cap_esc_count is not None else "<n/a>"
        flags_text = f"0x{state.fcsp_cap_feature_flags:X}" if state.fcsp_cap_feature_flags is not None else "<n/a>"
        imgui.same_line()
        imgui.text(f"ESC Count: {esc_count_text}")
        imgui.same_line()
        imgui.text(f"Flags: {flags_text}")
        support_get_link = (
            "yes" if state.fcsp_supports_get_link_status is True else
            "no" if state.fcsp_supports_get_link_status is False else
            "<unknown>"
        )
        support_read_block = (
            "yes" if state.fcsp_supports_read_block is True else
            "no" if state.fcsp_supports_read_block is False else
            "<unknown>"
        )
        support_write_block = (
            "yes" if state.fcsp_supports_write_block is True else
            "no" if state.fcsp_supports_write_block is False else
            "<unknown>"
        )
        support_esc_eeprom = (
            "yes" if state.fcsp_supports_esc_eeprom_space is True else
            "no" if state.fcsp_supports_esc_eeprom_space is False else
            "<unknown>"
        )
        imgui.text(
            f"Support: GET_LINK_STATUS={support_get_link} READ_BLOCK={support_read_block} "
            f"WRITE_BLOCK={support_write_block} ESC_EEPROM={support_esc_eeprom}"
        )
        link_flags_text = f"0x{state.fcsp_link_flags:04X}" if state.fcsp_link_flags is not None else "<n/a>"
        link_drops_text = str(state.fcsp_link_rx_drops) if state.fcsp_link_rx_drops is not None else "<n/a>"
        link_crc_text = str(state.fcsp_link_crc_err) if state.fcsp_link_crc_err is not None else "<n/a>"
        imgui.text(f"Link: flags={link_flags_text} drops={link_drops_text} crc={link_crc_text}")
        can_refresh_link = state.connected and state.fcsp_supports_get_link_status is not False
        if not can_refresh_link:
            imgui.begin_disabled()
        if imgui.small_button("Refresh FCSP Link Status"):
            controller.enqueue(CommandGetFcspLinkStatus())
        if not can_refresh_link:
            imgui.end_disabled()
        for description in state.fcsp_cap_descriptions[:8]:
            imgui.bullet_text(description)

    if state.last_error:
        imgui.separator()
        imgui.text_colored((1.0, 0.4, 0.4, 1.0), f"Last error: {state.last_error}")
        imgui.same_line()
        if imgui.small_button("Dismiss##error"):
            state.last_error = ""


def render_log_panel(state: AppState) -> None:
    imgui.text("Recent Logs")
    imgui.separator()
    for entry in state.logs[-12:]:
        imgui.text_wrapped(f"[{entry.timestamp}] {entry.source}/{entry.level}: {entry.message}")


def _begin_themed_window(
    title: str,
    *,
    first_pos: tuple[float, float],
    first_size: tuple[float, float],
    title_bg: tuple[float, float, float, float],
    title_bg_active: tuple[float, float, float, float],
    title_bg_collapsed: tuple[float, float, float, float],
) -> None:
    imgui.set_next_window_pos(first_pos, imgui.Cond_.first_use_ever)
    imgui.set_next_window_size(first_size, imgui.Cond_.first_use_ever)
    imgui.push_style_color(imgui.Col_.title_bg, title_bg)
    imgui.push_style_color(imgui.Col_.title_bg_active, title_bg_active)
    imgui.push_style_color(imgui.Col_.title_bg_collapsed, title_bg_collapsed)
    imgui.begin(title)


def _end_themed_window() -> None:
    imgui.end()
    imgui.pop_style_color(3)


def render_log_window(state: AppState) -> None:
    _begin_themed_window(
        "ESC Configurator Logs",
        first_pos=(950, 20),
        first_size=(520, 320),
        title_bg=(0.22, 0.18, 0.06, 1.0),
        title_bg_active=(0.78, 0.53, 0.12, 1.0),
        title_bg_collapsed=(0.18, 0.14, 0.05, 1.0),
    )
    imgui.text("Worker and UI log messages")
    imgui.text_wrapped(f"File: {get_runtime_log_path()}")
    imgui.separator()

    if imgui.button("Clear Log View"):
        state.logs.clear()

    imgui.same_line()
    imgui.text(f"Entries: {len(state.logs)}")

    changed_log_search, new_log_search = imgui.input_text("Filter##log_search", state.log_search, 128)
    if changed_log_search:
        state.log_search = new_log_search

    imgui.separator()
    display_logs = state.filtered_logs()

    child_size = (0.0, 0.0)
    child_visible = imgui.begin_child("log_messages", child_size, True)
    if child_visible:
        for entry in display_logs:
            prefix = f"[{entry.timestamp}] {entry.source}/{entry.level}: "
            if entry.level == "ERROR":
                imgui.text_colored((1.0, 0.4, 0.4, 1.0), prefix + entry.message)
            elif entry.level == "WARNING":
                imgui.text_colored((1.0, 0.8, 0.3, 1.0), prefix + entry.message)
            else:
                imgui.text_wrapped(prefix + entry.message)
        if display_logs:
            imgui.set_scroll_here_y(1.0)
    imgui.end_child()

    _end_themed_window()


def render_protocol_window(state: AppState) -> None:
    if not state.show_protocol_window:
        return

    _begin_themed_window(
        "ESC Protocol Trace",
        first_pos=(950, 360),
        first_size=(620, 420),
        title_bg=(0.06, 0.18, 0.24, 1.0),
        title_bg_active=(0.09, 0.52, 0.68, 1.0),
        title_bg_collapsed=(0.05, 0.13, 0.18, 1.0),
    )
    imgui.text("Detailed MSP and BLHeli 4-way traffic")
    imgui.separator()

    if imgui.button("Clear Protocol Trace"):
        state.protocol_traces.clear()

    imgui.same_line()
    imgui.text(f"Entries: {len(state.protocol_traces)}")

    imgui.separator()
    child_visible = imgui.begin_child("protocol_trace_messages", (0.0, 0.0), True)
    if child_visible:
        for entry in state.protocol_traces:
            if entry.channel == "MSP":
                color = (0.75, 0.85, 1.0, 1.0)
            elif entry.channel == "4WAY":
                color = (0.8, 1.0, 0.8, 1.0)
            elif entry.channel == "TANG9K":
                color = (1.0, 0.85, 0.6, 1.0)
            else:
                color = (0.9, 0.9, 0.9, 1.0)
            imgui.text_colored(color, f"[{entry.timestamp}] {entry.channel}")
            imgui.same_line()
            imgui.text_wrapped(entry.message)
        if state.protocol_traces:
            imgui.set_scroll_here_y(1.0)
    imgui.end_child()

    _end_themed_window()


def render_imgui_debug_windows(state: AppState) -> None:
    if state.show_imgui_metrics_window and hasattr(imgui, "show_metrics_window"):
        imgui.show_metrics_window()
    if state.show_imgui_debug_log_window and hasattr(imgui, "show_debug_log_window"):
        imgui.show_debug_log_window()


def render_status_bar(state: AppState) -> None:
    imgui.separator()
    content_width = float(imgui.get_content_region_avail()[0])
    compact = content_width < 760.0
    status_chars = 42 if compact else 120
    port_chars = 28 if compact else 80

    # Row 1: connection status row
    if state.connected:
        conn_color = (0.45, 0.95, 0.55, 1.0)
        conn_dot = "\u25cf"  # filled circle
    else:
        conn_color = (0.95, 0.55, 0.35, 1.0)
        conn_dot = "\u25cb"  # empty circle
    imgui.text_colored(conn_color, conn_dot)
    imgui.same_line()
    display_status = _ellipsize(state.status_text, status_chars)
    imgui.text(f"Status: {display_status}")
    if display_status != state.status_text and imgui.is_item_hovered():
        imgui.set_tooltip(state.status_text)

    if state.connected_port:
        if compact:
            display_port = _ellipsize(state.connected_port, port_chars)
            imgui.text(f"Port: {display_port}")
        else:
            imgui.same_line()
            display_port = _ellipsize(state.connected_port, port_chars)
            imgui.text(f"| Port: {display_port}")
        if display_port != state.connected_port and imgui.is_item_hovered():
            imgui.set_tooltip(state.connected_port)

    if not compact:
        imgui.same_line()
    if state.passthrough_active:
        mode_color = (0.8, 1.0, 0.55, 1.0)
        mode_label = "ESC Serial"
    else:
        mode_color = (0.65, 0.85, 1.0, 1.0)
        mode_label = "MSP"
    mode_prefix = "Mode: " if compact else "| Mode: "
    imgui.text_colored(mode_color, f"{mode_prefix}{mode_label}")

    # Row 2: metrics row
    motor_count = max(1, min(16, int(state.motor_count)))
    metrics = _status_metrics_text(
        msp_success_percent=state.msp_success_percent,
        msp_error_percent=state.msp_error_percent,
        msp_messages_per_second=state.msp_messages_per_second,
        motor_count=motor_count,
        compact=compact,
    )
    imgui.text(_ellipsize(metrics, 120 if not compact else 70))


def render_passthrough_panel(state: AppState, controller: WorkerController) -> None:
    imgui.text("ESC Link")

    motor_count = max(1, min(16, int(state.motor_count)))
    if state.selected_motor_index >= motor_count:
        state.selected_motor_index = motor_count - 1

    if motor_count > 1:
        preview = f"ESC {state.selected_motor_index + 1} of {motor_count}"
        if imgui.begin_combo("Target ESC for Read Settings", preview):
            for esc_index in range(motor_count):
                clicked, _selected = imgui.selectable(
                    f"ESC {esc_index + 1}",
                    esc_index == state.selected_motor_index,
                )
                if clicked:
                    state.selected_motor_index = esc_index
            imgui.end_combo()
    else:
        state.selected_motor_index = 0
        imgui.text("Target ESC for Read Settings: ESC 1")

    imgui.text_disabled("Used when Read Settings auto-enters passthrough.")

    read_settings_enabled = state.connected
    if not read_settings_enabled:
        imgui.begin_disabled()
    if imgui.button("Read Settings"):
        controller.enqueue(
            CommandReadSettings(
                length=state.settings_rw_length,
                address=state.settings_rw_address,
                motor_index=state.selected_motor_index,
            )
        )
    if not read_settings_enabled:
        imgui.end_disabled()

    if state.passthrough_active:
        imgui.same_line()
        if imgui.button("Exit Passthrough"):
            controller.enqueue(CommandExitPassthrough())

    if not state.passthrough_active:
        imgui.separator()
        imgui.text("DSHOT Speed")

        if len(state.dshot_speed_values) != motor_count:
            resized_values = [max(DSHOT_UI_MIN, min(DSHOT_UI_MAX, int(value))) for value in state.dshot_speed_values[:motor_count]]
            if len(resized_values) < motor_count:
                resized_values.extend([DSHOT_UI_MIN] * (motor_count - len(resized_values)))
            state.dshot_speed_values = resized_values

        imgui.text("Safety")
        if imgui.radio_button("SAFE", not state.dshot_safety_armed):
            state.dshot_safety_armed = False
        imgui.same_line()
        if imgui.radio_button("ARMED", state.dshot_safety_armed):
            state.dshot_safety_armed = True

        if not state.dshot_safety_armed:
            imgui.text_colored((1.0, 0.8, 0.35, 1.0), "Safety is SAFE. Arm to apply slider changes.")
        else:
            imgui.text_wrapped("Use individual motor sliders for fine tuning.")

        dshot_enabled = state.connected and state.dshot_safety_armed

        for motor_index in range(motor_count):
            current_speed = int(state.dshot_speed_values[motor_index])
            changed, speed_value = imgui.slider_int(
                f"Motor {motor_index + 1} Speed##dshot_slider_{motor_index}",
                current_speed,
                DSHOT_UI_MIN,
                DSHOT_UI_MAX,
            )
            if changed:
                clamped = max(DSHOT_UI_MIN, min(DSHOT_UI_MAX, int(speed_value)))
                state.dshot_speed_values[motor_index] = clamped
                if dshot_enabled:
                    controller.enqueue(
                        CommandSetMotorSpeed(
                            motor_index=motor_index,
                            speed=clamped,
                        )
                    )

    imgui.separator()
    active_text = "YES" if state.passthrough_active else "NO"
    imgui.text(f"Passthrough Active: {active_text}")
    imgui.same_line()
    imgui.text(f"Motor: {state.passthrough_motor}")
    imgui.same_line()
    imgui.text(f"ESCs: {state.detected_esc_count}")
    imgui.same_line()
    imgui.text(f"FC Motors: {motor_count}")
    imgui.text(f"4-way: {state.fourway_interface_name or '<n/a>'}")
    imgui.same_line()
    imgui.text(f"Protocol: {state.fourway_protocol_version}")
    imgui.same_line()
    imgui.text(f"Version: {state.fourway_interface_version or '<n/a>'}")


def render_settings_panel(state: AppState, controller: WorkerController) -> None:
    imgui.text("Settings")

    identity_enabled = state.connected and state.passthrough_active

    changed_rw_address, rw_address = imgui.input_int("Settings Address", state.settings_rw_address)
    if changed_rw_address:
        state.settings_rw_address = max(rw_address, 0)

    changed_rw_length, rw_length = imgui.input_int("Settings Read Length", state.settings_rw_length)
    if changed_rw_length:
        state.settings_rw_length = min(max(rw_length, 1), 255)

    if not identity_enabled:
        imgui.begin_disabled()
    if imgui.button("Read Settings"):
        controller.enqueue(
            CommandReadSettings(
                length=state.settings_rw_length,
                address=state.settings_rw_address,
            )
        )
    if not identity_enabled:
        imgui.end_disabled()

    imgui.text(f"Address: 0x{state.settings_address:04X}")
    imgui.same_line()
    imgui.text(f"Size: {state.settings_size}")
    imgui.same_line()
    imgui.text(f"Last Write: {state.settings_last_write_size}")
    imgui.same_line()
    imgui.text(f"Verified: {'YES' if state.settings_last_write_verified else 'NO'}")
    imgui.text_wrapped(f"Settings Preview: {state.settings_hex_preview or '<n/a>'}")

    decoded = state.decoded_settings
    if decoded is not None:
        validation_errors = validate_setting_edits(decoded, state.settings_edit_values)
        visible_fields = get_visible_fields(decoded, state.settings_edit_values)

        imgui.separator()
        imgui.text("Decoded Settings")
        imgui.text(f"Family: {decoded.family}")
        imgui.same_line()
        imgui.text(f"Firmware: {decoded.firmware_name or '<unknown>'}")
        imgui.same_line()
        imgui.text(f"Layout: {decoded.layout_name or '<unknown>'}")
        imgui.text(f"MCU: {decoded.mcu_name or '<unknown>'}")
        imgui.same_line()
        imgui.text(f"Revision: {decoded.layout_revision if decoded.layout_revision is not None else '<n/a>'}")
        imgui.same_line()
        imgui.text(f"Visible: {len(visible_fields)} / {len(decoded.fields)}")
        imgui.same_line()
        imgui.text(f"Dirty: {'YES' if state.settings_dirty() else 'NO'}")
        if validation_errors:
            imgui.text_colored((1.0, 0.4, 0.4, 1.0), f"Validation Errors: {len(validation_errors)}")
            for error in validation_errors:
                imgui.text_wrapped(f"- {error}")

        if validation_errors or not state.settings_dirty():
            imgui.begin_disabled()
        if imgui.button("Write Decoded Settings"):
            try:
                payload = build_settings_payload(decoded, state.settings_edit_values)
                controller.enqueue(
                    CommandWriteSettings(
                        address=decoded.start_address,
                        data=payload,
                        verify_readback=True,
                    )
                )
            except ValueError as exc:
                state.last_error = str(exc)
                state.append_log("warning", str(exc))
        if validation_errors or not state.settings_dirty():
            imgui.end_disabled()

        _SETTINGS_GROUP_ORDER = [
            "general", "individual", "beacon", "safety", "brake", "advanced", "identity",
        ]
        by_group: dict[str, list] = defaultdict(list)
        for _f in visible_fields:
            by_group[_f.group or "general"].append(_f)
        # any group not in the canonical order goes at the end
        all_groups = list(_SETTINGS_GROUP_ORDER)
        for _g in by_group:
            if _g not in all_groups:
                all_groups.append(_g)

        def _render_settings_field_row(field, state: AppState) -> None:  # noqa: ANN001
            imgui.table_next_row()
            imgui.table_set_column_index(0)
            imgui.text_unformatted(field.name)
            imgui.table_set_column_index(1)
            imgui.text_unformatted(field.label)
            imgui.table_set_column_index(2)
            imgui.text_unformatted(field.field_type)
            imgui.table_set_column_index(3)
            if not field.editable:
                imgui.text_wrapped(field.display_value)
                return
            current_value = state.settings_edit_values.get(field.name, field.raw_value)
            if field.field_type == "bool":
                changed, value = imgui.checkbox(f"##{field.name}", bool(int(current_value)))
                if changed:
                    state.settings_edit_values[field.name] = 1 if value else 0
            elif field.field_type == "enum" and field.options:
                selected_index = 0
                for _idx, _opt in enumerate(field.options):
                    if _opt.value == int(current_value):
                        selected_index = _idx
                        break
                preview = field.options[selected_index].label
                if imgui.begin_combo(f"##{field.name}", preview):
                    for _idx, _opt in enumerate(field.options):
                        clicked, _ = imgui.selectable(_opt.label, _idx == selected_index)
                        if clicked:
                            state.settings_edit_values[field.name] = _opt.value
                    imgui.end_combo()
            elif field.field_type == "number":
                changed, value = imgui.input_int(f"##{field.name}", int(current_value))
                if changed:
                    max_value = (1 << (field.size * 8)) - 1
                    state.settings_edit_values[field.name] = min(max(value, 0), max_value)
            else:
                imgui.text_wrapped(field.display_value)

        for _group_name in all_groups:
            _group_fields = by_group.get(_group_name, [])
            if not _group_fields:
                continue
            _header_label = _group_name.replace("_", " ").title()
            if imgui.collapsing_header(
                f"{_header_label} ({len(_group_fields)})##group_{_group_name}",
                imgui.TreeNodeFlags_.default_open,
            ):
                if imgui.begin_table(f"settings_{_group_name}", 4):
                    imgui.table_setup_column("Field")
                    imgui.table_setup_column("Label")
                    imgui.table_setup_column("Type")
                    imgui.table_setup_column("Value / Editor")
                    imgui.table_headers_row()
                    for _field in _group_fields:
                        _render_settings_field_row(_field, state)
                    imgui.end_table()

    if imgui.collapsing_header("Advanced Raw EEPROM"):
        changed_write_hex, write_hex = imgui.input_text(
            "Settings Write Bytes (hex)",
            state.settings_write_hex_input,
            1024,
        )
        if changed_write_hex:
            state.settings_write_hex_input = write_hex

        if not identity_enabled:
            imgui.begin_disabled()
        if imgui.button("Write Raw EEPROM Bytes"):
            try:
                write_bytes = _parse_hex_bytes(state.settings_write_hex_input)
                controller.enqueue(
                    CommandWriteSettings(
                        address=state.settings_rw_address,
                        data=write_bytes,
                        verify_readback=True,
                    )
                )
            except ValueError as exc:
                state.last_error = str(exc)
                state.append_log("warning", str(exc))
        if not identity_enabled:
            imgui.end_disabled()


def render_firmware_panel(state: AppState, controller: WorkerController) -> None:
    imgui.text("Firmware")

    if imgui.button("Refresh Firmware Catalog"):
        controller.enqueue(CommandRefreshFirmwareCatalog())

    catalog = state.firmware_catalog
    if catalog is None:
        imgui.text("No firmware catalog loaded.")
        return

    imgui.same_line()
    imgui.text(state.firmware_catalog_source_label())
    if state.show_firmware_catalog_stale_warning(threshold_hours=24.0):
        imgui.same_line()
        imgui.text_colored((1.0, 0.7, 0.3, 1.0), "⚠ stale cache")
        imgui.same_line()
        if imgui.small_button("Refresh now##stale_cache_refresh"):
            controller.enqueue(CommandRefreshFirmwareCatalog())
        if imgui.is_item_hovered():
            imgui.set_tooltip(state.firmware_catalog_stale_warning_text(threshold_hours=24.0))
    imgui.text(f"Catalog Refreshed: {catalog.refreshed_at}")

    sources = state.firmware_sources()
    preview_source = state.selected_firmware_source or (sources[0] if sources else "<none>")
    if imgui.begin_combo("Firmware Source", preview_source):
        for source in sources:
            clicked, _ = imgui.selectable(source, source == preview_source)
            if clicked:
                state.select_firmware_source(source)
        imgui.end_combo()

    # Search / filter box
    changed_search, new_search = imgui.input_text("Search releases##fw_search", state.firmware_release_search, 128)
    if changed_search:
        state.firmware_release_search = new_search

    releases = state.filtered_firmware_releases()
    selected_release = state.selected_firmware_release()
    selected_preview = selected_release.name if selected_release is not None else "<none>"
    if imgui.begin_combo("Release", selected_preview):
        for release in releases:
            clicked, _ = imgui.selectable(release.name, selected_release is not None and release.key == selected_release.key)
            if clicked:
                state.selected_firmware_release_key = release.key
        imgui.end_combo()

    imgui.separator()
    if state.decoded_settings is not None:
        imgui.text(f"Target Family: {state.target_firmware_family() or '<unknown>'}")
        imgui.same_line()
        imgui.text(f"Target Layout: {state.target_layout_name() or '<unknown>'}")
    if imgui.begin_table("firmware_release_table", 5):
        imgui.table_setup_column("Name")
        imgui.table_setup_column("Key")
        imgui.table_setup_column("Published")
        imgui.table_setup_column("Flags")
        imgui.table_setup_column("Compatibility")
        imgui.table_headers_row()

        for release in releases:
            compatibility = state.firmware_release_compatibility(release) if state.decoded_settings is not None else None
            imgui.table_next_row()
            imgui.table_set_column_index(0)
            imgui.text_unformatted(release.name)
            imgui.table_set_column_index(1)
            imgui.text_unformatted(release.key)
            imgui.table_set_column_index(2)
            imgui.text_unformatted(release.published_at or "<n/a>")
            imgui.table_set_column_index(3)
            flags = []
            if release.prerelease:
                flags.append("prerelease")
            if selected_release is not None and release.key == selected_release.key:
                flags.append("selected")
            imgui.text_unformatted(", ".join(flags) if flags else "-")
            imgui.table_set_column_index(4)
            if compatibility is None:
                imgui.text_unformatted("pending target info")
            elif compatibility.compatible:
                imgui.text_colored((0.45, 0.95, 0.55, 1.0), compatibility.reason)
            else:
                imgui.text_colored((1.0, 0.55, 0.35, 1.0), compatibility.reason)

        imgui.end_table()

    if selected_release is not None:
        selected_compatibility = state.firmware_release_compatibility(selected_release) if state.decoded_settings is not None else None
        imgui.separator()
        imgui.text("Selected Release Details")
        imgui.text(f"Family: {selected_release.family}")
        imgui.text(f"Key: {selected_release.key}")
        imgui.text_wrapped(f"Download URL Template: {selected_release.download_url_template}")
        imgui.text_wrapped(f"Release URL: {selected_release.release_url or '<n/a>'}")
        if selected_compatibility is not None:
            color = (0.45, 0.95, 0.55, 1.0) if selected_compatibility.compatible else (1.0, 0.55, 0.35, 1.0)
            imgui.text_colored(color, f"Compatibility: {selected_compatibility.reason}")

    imgui.separator()
    imgui.text("Download from Web")
    target_layout = state.decoded_settings.layout_name if state.decoded_settings is not None else ""
    target_family = state.decoded_settings.family if state.decoded_settings is not None else ""
    active_esc = int(state.passthrough_motor)
    settings_esc = int(state.settings_loaded_motor)
    settings_match_active = state.decoded_settings is not None and settings_esc == active_esc
    imgui.text(f"Active ESC: {active_esc + 1}")
    imgui.same_line()
    settings_label = str(settings_esc + 1) if settings_esc >= 0 else "<none>"
    imgui.text(f"Settings from ESC: {settings_label}")
    if state.decoded_settings is not None and not settings_match_active:
        imgui.text_colored((1.0, 0.6, 0.35, 1.0), "Settings do not match active ESC. Re-read settings before firmware operations.")
        if imgui.button("Read Settings for Active ESC"):
            controller.enqueue(
                CommandReadSettings(
                    length=state.settings_rw_length,
                    address=state.settings_rw_address,
                    motor_index=active_esc,
                )
            )
    imgui.text(f"Target Layout: {target_layout or '<read settings first>'}")
    if selected_release is not None and selected_release.family == "Bluejay":
        pwm_options = [24, 48, 96]
        current_pwm = state.firmware_remote_pwm_khz if state.firmware_remote_pwm_khz in pwm_options else 48
        if imgui.begin_combo("Bluejay PWM Variant", f"{current_pwm} kHz"):
            for pwm in pwm_options:
                clicked, _ = imgui.selectable(f"{pwm} kHz", pwm == current_pwm)
                if clicked:
                    state.firmware_remote_pwm_khz = pwm
            imgui.end_combo()

    download_compatible = (
        selected_release is not None
        and state.decoded_settings is not None
        and settings_match_active
        and bool(target_layout)
        and state.firmware_release_compatibility(selected_release).compatible
        and not state.firmware_download_active
    )
    if not download_compatible:
        imgui.begin_disabled()
    if imgui.button("Download Selected Release") and selected_release is not None:
        controller.enqueue(
            CommandDownloadFirmware(
                release=selected_release,
                pwm_khz=state.firmware_remote_pwm_khz,
            )
        )
    if not download_compatible:
        imgui.end_disabled()
    if state.firmware_download_active:
        imgui.same_line()
        if imgui.button("Cancel##cancel_download"):
            controller.enqueue(CommandCancelOperation())
    if state.firmware_download_message:
        imgui.same_line()
        imgui.text_wrapped(state.firmware_download_message)

    imgui.separator()
    imgui.text("Local Firmware Flash")
    changed_local_path, local_path = imgui.input_text("Firmware File Path", state.firmware_local_file_path, 1024)
    if changed_local_path:
        state.firmware_local_file_path = local_path

    imgui.same_line()
    if im_file_dialog is not None:
        if imgui.button("Browse…"):
            starting_dir = ""
            current_path = state.firmware_local_file_path.strip()
            if current_path:
                path = Path(current_path)
                if path.is_dir():
                    starting_dir = str(path)
                elif path.parent.exists():
                    starting_dir = str(path.parent)
            im_file_dialog.FileDialog.instance().open(
                FIRMWARE_FILE_DIALOG_KEY,
                "Select firmware file",
                "Firmware (*.hex*.bin*.elf).hex,.bin,.elf,.*",
                False,
                starting_dir,
            )

        if im_file_dialog.FileDialog.instance().is_done(FIRMWARE_FILE_DIALOG_KEY):
            if im_file_dialog.FileDialog.instance().has_result():
                state.firmware_local_file_path = im_file_dialog.FileDialog.instance().get_result().path()
            im_file_dialog.FileDialog.instance().close()
    else:
        imgui.begin_disabled()
        imgui.button("Browse…")
        imgui.end_disabled()
        if imgui.is_item_hovered():
            imgui.set_tooltip("File picker is unavailable in this build of imgui_bundle")

    family_options = ["BLHeli_S", "Bluejay"]
    current_family = state.firmware_local_family or (selected_release.family if selected_release is not None else "BLHeli_S")
    if current_family not in family_options:
        current_family = family_options[0]
    if imgui.begin_combo("Local Firmware Family", current_family):
        for family in family_options:
            clicked, _ = imgui.selectable(family, family == current_family)
            if clicked:
                state.firmware_local_family = family
        imgui.end_combo()
    if not state.firmware_local_family:
        state.firmware_local_family = current_family

    target_family = state.decoded_settings.family if state.decoded_settings is not None else "<read settings first>"
    selected_family = state.selected_firmware_family() or "<unset>"
    compatibility_ok = state.decoded_settings is not None and target_family == selected_family
    compatibility_color = (0.45, 0.95, 0.55, 1.0) if compatibility_ok else (1.0, 0.55, 0.35, 1.0)
    compatibility_text = "compatible" if compatibility_ok else "not compatible yet"
    imgui.text(f"Target ESC Family: {target_family}")
    imgui.same_line()
    imgui.text(f"Selected Image Family: {selected_family}")
    imgui.text_colored(compatibility_color, f"Compatibility: {compatibility_text}")
    imgui.text_disabled("Web downloads populate the local flash path automatically, matching the web-style release selection flow.")

    changed_confirm, confirm_value = imgui.checkbox(
        "I confirm this will erase and reflash the active ESC",
        state.firmware_flash_confirmed,
    )
    if changed_confirm:
        state.firmware_flash_confirmed = confirm_value

    flash_enabled = (
        state.connected
        and state.passthrough_active
        and state.decoded_settings is not None
        and settings_match_active
        and bool(state.firmware_local_file_path.strip())
        and compatibility_ok
        and state.firmware_flash_confirmed
        and not state.firmware_flash_active
    )
    if not flash_enabled:
        imgui.begin_disabled()
    if imgui.button("Flash Local Firmware"):
        controller.enqueue(
            CommandFlashEsc(
                file_path=state.firmware_local_file_path.strip(),
                family=state.selected_firmware_family(),
                display_name=state.firmware_local_file_path.strip().split("/")[-1],
                verify_readback=True,
            )
        )
    if not flash_enabled:
        imgui.end_disabled()

    if state.firmware_flash_stage:
        imgui.same_line()
        imgui.text(f"Stage: {state.firmware_flash_stage}")
        if state.firmware_flash_active:
            imgui.same_line()
            if imgui.button("Cancel##cancel_flash"):
                controller.enqueue(CommandCancelOperation())
        fraction = 0.0
        if state.firmware_flash_total > 0:
            fraction = max(0.0, min(1.0, float(state.firmware_flash_current) / float(state.firmware_flash_total)))
        imgui.progress_bar(fraction, (-1.0, 0.0), state.firmware_flash_message or "Firmware flash progress")

    if state.firmware_last_flash_name:
        imgui.text(
            f"Last Flash: {state.firmware_last_flash_name} — {state.firmware_last_flash_size} byte(s)"
            + (" (verified)" if state.firmware_last_flash_verified else "")
        )

    imgui.separator()
    motor_count = max(1, min(16, int(state.motor_count)))
    imgui.text(f"Flash All ESCs  ({motor_count} motor(s) detected)")
    imgui.text_disabled("Reads settings then flashes each ESC in turn with the same firmware file.")
    flash_all_enabled = (
        state.connected
        and bool(state.firmware_local_file_path.strip())
        and compatibility_ok
        and state.firmware_flash_confirmed
        and not state.firmware_flash_active
        and not state.flash_all_active
    )
    if not flash_all_enabled:
        imgui.begin_disabled()
    if imgui.button(f"Flash All {motor_count} ESCs"):
        controller.enqueue(
            CommandFlashAllEscs(
                file_path=state.firmware_local_file_path.strip(),
                family=state.selected_firmware_family(),
                motor_count=motor_count,
                display_name=state.firmware_local_file_path.strip().split("/")[-1],
                verify_readback=True,
                settings_read_length=state.settings_rw_length,
                settings_address=state.settings_rw_address,
            )
        )
    if not flash_all_enabled:
        imgui.end_disabled()

    if state.flash_all_active or state.flash_all_message:
        imgui.same_line()
        imgui.text_wrapped(state.flash_all_message or "Batch flash in progress…")
    if state.flash_all_active:
        imgui.same_line()
        if imgui.button("Cancel Batch##cancel_flash_all"):
            controller.enqueue(CommandCancelOperation())
    if state.flash_all_total > 0 and not state.flash_all_active:
        result_color = (0.45, 0.95, 0.55, 1.0) if state.flash_all_succeeded == state.flash_all_total else (1.0, 0.7, 0.3, 1.0)
        imgui.text_colored(result_color, f"Last batch: {state.flash_all_succeeded}/{state.flash_all_total} succeeded")


def render_diagnostics_panel(state: AppState) -> None:
    imgui.text("Diagnostics")
    changed_protocol, value_protocol = imgui.checkbox("Show Protocol Trace Window", state.show_protocol_window)
    if changed_protocol:
        state.show_protocol_window = value_protocol
    changed_metrics, value_metrics = imgui.checkbox("Show ImGui Metrics Window", state.show_imgui_metrics_window)
    if changed_metrics:
        state.show_imgui_metrics_window = value_metrics
    changed_debug_log, value_debug_log = imgui.checkbox("Show ImGui Debug Log Window", state.show_imgui_debug_log_window)
    if changed_debug_log:
        state.show_imgui_debug_log_window = value_debug_log

    if imgui.button("Export Diagnostics Bundle"):
        try:
            bundle_dir = export_diagnostics_bundle(state)
            state.diagnostics_last_export_path = str(bundle_dir)
            state.append_log("info", f"Diagnostics bundle exported: {bundle_dir}", source="diag")
            state.status_text = f"Diagnostics exported: {bundle_dir.name}"
        except Exception as exc:
            message = f"Diagnostics export failed: {exc}"
            state.append_log("error", message, source="diag")
            state.last_error = message
            state.status_text = message

    imgui.text_wrapped(f"Python Log File: {get_runtime_log_path()}")
    if state.diagnostics_last_export_path:
        imgui.text_wrapped(f"Last Diagnostics Export: {state.diagnostics_last_export_path}")
    imgui.text(f"Visible UI Log Entries: {len(state.logs)}")
    imgui.text(f"Visible Protocol Trace Entries: {len(state.protocol_traces)}")

    if state.connection_protocol_mode == "optimized_tang9k":
        imgui.separator()
        imgui.text("FCSP Capability Snapshot")
        imgui.text(f"Peer: {state.fcsp_connected_peer or '<unknown>'}")
        imgui.text(
            "Capabilities: "
            f"{len(state.fcsp_cap_descriptions)} entry(ies), "
            f"ESCs={state.fcsp_cap_esc_count if state.fcsp_cap_esc_count is not None else '<n/a>'}, "
            f"Flags={f'0x{state.fcsp_cap_feature_flags:X}' if state.fcsp_cap_feature_flags is not None else '<n/a>'}"
        )
        imgui.text(
            "Link: "
            f"flags={f'0x{state.fcsp_link_flags:04X}' if state.fcsp_link_flags is not None else '<n/a>'} "
            f"drops={state.fcsp_link_rx_drops if state.fcsp_link_rx_drops is not None else '<n/a>'} "
            f"crc={state.fcsp_link_crc_err if state.fcsp_link_crc_err is not None else '<n/a>'}"
        )


def render_main_window(state: AppState, controller: WorkerController) -> None:
    _begin_themed_window(
        "ESC Configurator (ImGui Bundle)",
        first_pos=(20, 20),
        first_size=(900, 760),
        title_bg=(0.11, 0.12, 0.18, 1.0),
        title_bg_active=(0.26, 0.32, 0.52, 1.0),
        title_bg_collapsed=(0.08, 0.09, 0.14, 1.0),
    )
    imgui.text("Desktop ESC Configurator")
    imgui.same_line()
    imgui.text_colored((0.70, 0.80, 1.00, 1.0), f"v{APP_VERSION}")
    imgui.text_wrapped(f"Next: {state.recommended_next_step()}")
    imgui.separator()

    _render_step_heading("1. Connect", (0.90, 0.90, 0.30, 1.0))
    render_connection_panel(state, controller)

    if state.connected:
        _render_step_heading("2. ESC Link", (0.80, 1.00, 0.40, 1.0))
        render_passthrough_panel(state, controller)

    if state.connected and state.passthrough_active:
        _render_step_heading("3. Settings", (0.60, 0.95, 1.00, 1.0))
        render_settings_panel(state, controller)

    if state.connected and state.passthrough_active and state.detected_esc_count > 0:
        _render_step_heading("4. Firmware", (1.00, 0.85, 0.50, 1.0))
        render_firmware_panel(state, controller)

    if imgui.collapsing_header("Diagnostics / Advanced"):
        render_diagnostics_panel(state)

    render_status_bar(state)
    _end_themed_window()
    render_log_window(state)
    render_protocol_window(state)
    render_imgui_debug_windows(state)
