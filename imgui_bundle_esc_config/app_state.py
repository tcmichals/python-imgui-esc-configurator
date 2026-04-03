"""UI-facing state models for the ImGui ESC configurator."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re

from MSP import SerialPortDescriptor
from comm_proto.tang9k_stream import (
    Tang9kChannel,
    decode_fc_log_event,
    decode_frame,
    format_fc_log_event,
    format_frame_trace,
)

from .firmware_catalog import FirmwareCatalogSnapshot, FirmwareRelease, describe_release_compatibility
from .runtime_logging import log_protocol_trace, log_ui_message
from .settings_decoder import DecodedSettings, decode_settings_payload, get_editable_field_values

from .worker import (
    EventFourWayIdentity,
    EventEscScanResult,
    EventFirmwareCatalogLoaded,
    EventConnected,
    EventDisconnected,
    EventError,
    EventAllEscsFlashed,
    EventFirmwareDownloaded,
    EventFirmwareFlashed,
    EventLog,
    EventMspStats,
    EventMotorCount,
    EventOperationCancelled,
    EventPassthroughState,
    EventPortsUpdated,
    EventProgress,
    EventProtocolTrace,
    EventSettingsLoaded,
    EventSettingsWritten,
)


DSHOT_UI_MIN = 1000
DSHOT_UI_MAX = 2000


@dataclass
class LogEntry:
    """A single UI-visible log entry."""

    timestamp: str
    level: str
    source: str
    message: str


@dataclass
class ProtocolTraceEntry:
    """A single protocol trace entry for MSP / 4-way debug windows."""

    timestamp: str
    channel: str
    message: str


@dataclass
class ConnectionSettings:
    """User-editable connection settings for the worker."""

    manual_port: str = ""
    baud_rate: int = 115200


@dataclass
class AppState:
    """Root UI state consumed by rendering code."""

    connection: ConnectionSettings = field(default_factory=ConnectionSettings)
    available_ports: list[SerialPortDescriptor] = field(default_factory=list)
    selected_port_index: int = 0
    connected: bool = False
    connected_port: str = ""
    connection_protocol_mode: str = "msp"
    motor_count: int = 4
    selected_motor_index: int = 0
    dshot_speed_values: list[int] = field(default_factory=lambda: [DSHOT_UI_MIN, DSHOT_UI_MIN, DSHOT_UI_MIN, DSHOT_UI_MIN])
    dshot_safety_armed: bool = False
    passthrough_active: bool = False
    passthrough_motor: int = 0
    detected_esc_count: int = 0
    fourway_interface_name: str = ""
    fourway_protocol_version: int = 0
    fourway_interface_version: str = ""
    settings_rw_address: int = 0
    settings_rw_length: int = 128
    settings_write_hex_input: str = ""
    settings_address: int = 0
    settings_size: int = 0
    settings_loaded_motor: int = -1
    settings_last_write_size: int = 0
    settings_last_write_verified: bool = False
    settings_hex_preview: str = ""
    decoded_settings: DecodedSettings | None = None
    settings_edit_values: dict[str, int | str | bytes] = field(default_factory=dict)
    firmware_catalog: FirmwareCatalogSnapshot | None = None
    firmware_catalog_from_cache: bool = False
    firmware_release_search: str = ""
    selected_firmware_source: str = ""
    selected_firmware_release_key: str = ""
    firmware_local_file_path: str = ""
    firmware_local_family: str = ""
    firmware_remote_pwm_khz: int = 48
    firmware_download_active: bool = False
    firmware_download_message: str = ""
    firmware_flash_confirmed: bool = False
    firmware_flash_active: bool = False
    firmware_flash_stage: str = ""
    firmware_flash_current: int = 0
    firmware_flash_total: int = 1
    firmware_flash_message: str = ""
    firmware_last_flash_size: int = 0
    firmware_last_flash_verified: bool = False
    firmware_last_flash_name: str = ""
    flash_all_active: bool = False
    flash_all_total: int = 0
    flash_all_succeeded: int = 0
    flash_all_message: str = ""
    show_protocol_window: bool = True
    show_imgui_metrics_window: bool = False
    show_imgui_debug_log_window: bool = False
    tang9k_decode_hex_input: str = ""
    tang9k_decode_last: str = ""
    diagnostics_last_export_path: str = ""
    last_error: str = ""
    status_text: str = "Idle"
    msp_total: int = 0
    msp_errors: int = 0
    msp_success_percent: float = 100.0
    msp_error_percent: float = 0.0
    msp_messages_per_second: float = 0.0
    log_search: str = ""
    logs: list[LogEntry] = field(default_factory=list)
    protocol_traces: list[ProtocolTraceEntry] = field(default_factory=list)

    def append_log(self, level: str, message: str, source: str = "ui") -> None:
        normalized_source = (source or "ui").upper()
        log_ui_message(level, message, source=source or "ui")
        self.logs.append(
            LogEntry(
                timestamp=datetime.now().strftime("%H:%M:%S"),
                level=level.upper(),
                source=normalized_source,
                message=message,
            )
        )
        self.logs = self.logs[-200:]

    def filtered_logs(self) -> list[LogEntry]:
        query = self.log_search.strip().lower()
        if not query:
            return list(self.logs)
        return [
            entry
            for entry in self.logs
            if query in entry.message.lower() or query in entry.source.lower()
        ]

    def selected_port(self) -> str:
        manual_port = self.connection.manual_port.strip()
        if manual_port:
            return manual_port
        if 0 <= self.selected_port_index < len(self.available_ports):
            return self.available_ports[self.selected_port_index].device
        return ""

    def append_protocol_trace(self, channel: str, message: str) -> None:
        log_protocol_trace(channel, message)
        self.protocol_traces.append(
            ProtocolTraceEntry(
                timestamp=datetime.now().strftime("%H:%M:%S"),
                channel=channel,
                message=message,
            )
        )
        self.protocol_traces = self.protocol_traces[-400:]

    def decode_tang9k_hex_frame(self, raw_hex: str, *, direction: str = "<=") -> bool:
        text = (raw_hex or "").strip()
        if not text:
            self.tang9k_decode_last = "Tang9K decode failed: empty input"
            self.append_log("warning", self.tang9k_decode_last, source="ui")
            return False

        compact = re.sub(r"[^0-9A-Fa-f]", "", text)
        if len(compact) == 0:
            self.tang9k_decode_last = "Tang9K decode failed: no hex digits found"
            self.append_log("warning", self.tang9k_decode_last, source="ui")
            return False
        if len(compact) % 2 != 0:
            self.tang9k_decode_last = "Tang9K decode failed: hex input must be even-length"
            self.append_log("warning", self.tang9k_decode_last, source="ui")
            return False

        try:
            frame_bytes = bytes.fromhex(compact)
            frame = decode_frame(frame_bytes)
            trace_line = format_frame_trace(direction, frame_bytes)
            self.append_protocol_trace("TANG9K", trace_line)

            if frame.channel == Tang9kChannel.FC_LOG:
                event = decode_fc_log_event(frame.payload)
                self.append_log("info", format_fc_log_event(event), source="fc")

            self.tang9k_decode_last = (
                f"Decoded Tang9K frame: channel=0x{frame.channel:02X} seq={frame.seq} payload={len(frame.payload)}"
            )
            self.append_log("info", self.tang9k_decode_last, source="ui")
            return True
        except Exception as exc:
            self.tang9k_decode_last = f"Tang9K decode failed: {exc}"
            self.append_log("warning", self.tang9k_decode_last, source="ui")
            return False

    def settings_dirty(self) -> bool:
        decoded = self.decoded_settings
        if decoded is None:
            return False
        return self.settings_edit_values != get_editable_field_values(decoded)

    def firmware_sources(self) -> list[str]:
        if self.firmware_catalog is None:
            return []
        return sorted(self.firmware_catalog.releases_by_source.keys())

    def target_firmware_family(self) -> str:
        if self.decoded_settings is None:
            return ""
        return self.decoded_settings.family

    def target_layout_name(self) -> str:
        if self.decoded_settings is None:
            return ""
        return self.decoded_settings.layout_name

    def firmware_release_compatibility(self, release: FirmwareRelease):
        return describe_release_compatibility(
            release,
            esc_family=self.target_firmware_family(),
            layout_name=self.target_layout_name(),
            pwm_khz=self.firmware_remote_pwm_khz,
        )

    def select_firmware_source(self, source: str) -> None:
        self.selected_firmware_source = source
        releases = self.firmware_catalog.releases_by_source.get(source, ()) if self.firmware_catalog is not None else ()
        self.selected_firmware_release_key = releases[0].key if releases else ""

    def visible_firmware_releases(self) -> tuple[FirmwareRelease, ...]:
        if self.firmware_catalog is None:
            return ()
        source = self.selected_firmware_source
        if not source:
            sources = self.firmware_sources()
            source = sources[0] if sources else ""
        releases = self.firmware_catalog.releases_by_source.get(source, ())
        if self.decoded_settings is None:
            return releases
        compatible = tuple(release for release in releases if self.firmware_release_compatibility(release).compatible)
        return compatible if compatible else ()

    def filtered_firmware_releases(self) -> tuple[FirmwareRelease, ...]:
        releases = self.visible_firmware_releases()
        query = self.firmware_release_search.strip().lower()
        if not query:
            return releases
        return tuple(
            release
            for release in releases
            if query in release.name.lower() or query in release.key.lower()
        )

    def firmware_catalog_total_releases(self) -> int:
        if self.firmware_catalog is None:
            return 0
        return sum(len(releases) for releases in self.firmware_catalog.releases_by_source.values())

    def firmware_catalog_source_label(self) -> str:
        if self.firmware_catalog is None:
            return ""
        total = self.firmware_catalog_total_releases()
        if not self.firmware_catalog_from_cache:
            return f"Releases: {total}"
        age_label = self.firmware_catalog_cache_age_label()
        if age_label:
            return f"Releases: {total} (cached, age {age_label})"
        return f"Releases: {total} (cached)"

    def firmware_catalog_refreshed_at_datetime(self) -> datetime | None:
        if self.firmware_catalog is None:
            return None
        raw = (self.firmware_catalog.refreshed_at or "").strip()
        if not raw:
            return None
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def firmware_catalog_cache_age_seconds(self) -> float | None:
        if not self.firmware_catalog_from_cache:
            return None
        refreshed_at = self.firmware_catalog_refreshed_at_datetime()
        if refreshed_at is None:
            return None
        now = datetime.now(timezone.utc)
        age_seconds = (now - refreshed_at).total_seconds()
        return max(0.0, age_seconds)

    def firmware_catalog_cache_age_label(self) -> str:
        age_seconds = self.firmware_catalog_cache_age_seconds()
        if age_seconds is None:
            return ""
        total_minutes = int(age_seconds // 60)
        days = total_minutes // (60 * 24)
        hours = (total_minutes % (60 * 24)) // 60
        minutes = total_minutes % 60
        if days > 0:
            return f"{days}d {hours}h"
        if hours > 0:
            return f"{hours}h {minutes}m"
        return f"{minutes}m"

    def firmware_catalog_cache_is_stale(self, *, threshold_hours: float = 24.0) -> bool:
        age_seconds = self.firmware_catalog_cache_age_seconds()
        if age_seconds is None:
            return False
        return age_seconds >= max(0.0, float(threshold_hours)) * 3600.0

    def show_firmware_catalog_stale_warning(self, *, threshold_hours: float = 24.0) -> bool:
        if not self.firmware_catalog_from_cache:
            return False
        return self.firmware_catalog_cache_is_stale(threshold_hours=threshold_hours)

    def firmware_catalog_stale_warning_text(self, *, threshold_hours: float = 24.0) -> str:
        if not self.show_firmware_catalog_stale_warning(threshold_hours=threshold_hours):
            return ""
        threshold_text = int(max(1.0, float(threshold_hours)))
        return f"Cached firmware catalog is older than {threshold_text}h. Refresh when online for latest releases."

    def selected_firmware_release(self) -> FirmwareRelease | None:
        releases = self.visible_firmware_releases()
        for release in releases:
            if release.key == self.selected_firmware_release_key:
                return release
        return releases[0] if releases else None

    def selected_firmware_family(self) -> str:
        if self.firmware_local_family:
            return self.firmware_local_family
        release = self.selected_firmware_release()
        if release is not None:
            return release.family
        return ""

    def recommended_next_step(self) -> str:
        if not self.connected:
            return "Connect to the bridge using a detected port or manual port override."
        if not self.passthrough_active:
            return "Choose the target motor and enter passthrough to talk to the ESC."
        if self.detected_esc_count <= 0:
            return "Scan for ESCs to confirm the active target before reading settings."
        if self.decoded_settings is None:
            return "Read settings to load the structured editor for the active ESC."
        if self.firmware_catalog is None:
            return "Refresh the firmware catalog if you want to compare available firmware versions."
        return "Review settings or browse firmware releases for the selected ESC family."

    def _resize_dshot_speed_values(self, target_count: int) -> None:
        safe_count = max(1, min(16, int(target_count)))
        current = [max(DSHOT_UI_MIN, min(DSHOT_UI_MAX, int(value))) for value in self.dshot_speed_values]
        if len(current) < safe_count:
            current.extend([DSHOT_UI_MIN] * (safe_count - len(current)))
        elif len(current) > safe_count:
            current = current[:safe_count]
        self.dshot_speed_values = current

    def apply_event(self, event: object) -> None:
        if isinstance(event, EventPortsUpdated):
            self.available_ports = list(event.ports)
            if self.selected_port_index >= len(self.available_ports):
                self.selected_port_index = 0
            self.status_text = f"Detected {len(self.available_ports)} serial port(s)"
            return

        if isinstance(event, EventConnected):
            self.connected = True
            self.connected_port = event.port
            self._resize_dshot_speed_values(self.motor_count)
            self.dshot_safety_armed = False
            self.last_error = ""
            self.status_text = f"Connected to {event.port} @ {event.baudrate}"
            return

        if isinstance(event, EventDisconnected):
            self.connected = False
            self.connected_port = ""
            self.motor_count = 4
            self.selected_motor_index = 0
            self.dshot_speed_values = [DSHOT_UI_MIN, DSHOT_UI_MIN, DSHOT_UI_MIN, DSHOT_UI_MIN]
            self.dshot_safety_armed = False
            self.passthrough_active = False
            self.detected_esc_count = 0
            self.fourway_interface_name = ""
            self.fourway_protocol_version = 0
            self.fourway_interface_version = ""
            self.settings_rw_address = 0
            self.settings_rw_length = 128
            self.settings_write_hex_input = ""
            self.settings_address = 0
            self.settings_size = 0
            self.settings_loaded_motor = -1
            self.settings_last_write_size = 0
            self.settings_last_write_verified = False
            self.settings_hex_preview = ""
            self.decoded_settings = None
            self.settings_edit_values = {}
            self.firmware_download_active = False
            self.firmware_download_message = ""
            self.firmware_flash_confirmed = False
            self.firmware_flash_active = False
            self.firmware_flash_stage = ""
            self.firmware_flash_current = 0
            self.firmware_flash_total = 1
            self.firmware_flash_message = ""
            self.firmware_last_flash_size = 0
            self.firmware_last_flash_verified = False
            self.firmware_last_flash_name = ""
            self.flash_all_active = False
            self.flash_all_total = 0
            self.flash_all_succeeded = 0
            self.flash_all_message = ""
            self.diagnostics_last_export_path = ""
            self.msp_total = 0
            self.msp_errors = 0
            self.msp_success_percent = 100.0
            self.msp_error_percent = 0.0
            self.msp_messages_per_second = 0.0
            self.status_text = event.reason
            return

        if isinstance(event, EventMspStats):
            self.msp_total = int(event.total)
            self.msp_errors = int(event.errors)
            self.msp_success_percent = float(event.success_percent)
            self.msp_error_percent = float(event.error_percent)
            self.msp_messages_per_second = float(event.messages_per_second)
            return

        if isinstance(event, EventMotorCount):
            self.motor_count = max(1, int(event.count))
            if self.selected_motor_index >= self.motor_count:
                self.selected_motor_index = self.motor_count - 1
            self._resize_dshot_speed_values(self.motor_count)
            self.status_text = f"FC reported motor count: {self.motor_count}"
            return

        if isinstance(event, EventProtocolTrace):
            self.append_protocol_trace(event.channel, event.message)
            return

        if isinstance(event, EventFirmwareCatalogLoaded):
            self.firmware_catalog = event.snapshot
            self.firmware_catalog_from_cache = event.from_cache
            if not self.selected_firmware_source or self.selected_firmware_source not in event.snapshot.releases_by_source:
                sources = sorted(event.snapshot.releases_by_source.keys())
                self.selected_firmware_source = sources[0] if sources else ""
            # If settings are already loaded, align source to the target ESC family
            target_family = self.target_firmware_family()
            if target_family and target_family in event.snapshot.releases_by_source:
                self.selected_firmware_source = target_family
            releases = event.snapshot.releases_by_source.get(self.selected_firmware_source, ())
            if not self.selected_firmware_release_key or not any(
                release.key == self.selected_firmware_release_key for release in releases
            ):
                self.selected_firmware_release_key = releases[0].key if releases else ""
            # Align release key to a compatible entry when settings are loaded
            filtered_releases = self.visible_firmware_releases()
            if filtered_releases and not any(r.key == self.selected_firmware_release_key for r in filtered_releases):
                self.selected_firmware_release_key = filtered_releases[0].key
            total = sum(len(releases) for releases in event.snapshot.releases_by_source.values())
            self.status_text = f"Firmware catalog refreshed: {total} release(s)"
            return

        if isinstance(event, EventFirmwareDownloaded):
            self.firmware_download_active = False
            self.firmware_download_message = f"Downloaded {event.image_name}"
            self.firmware_local_file_path = event.file_path
            self.firmware_local_family = event.family
            self.firmware_flash_confirmed = False
            self.status_text = f"Firmware downloaded: {event.image_name}"
            return

        if isinstance(event, EventProgress):
            if event.operation == "download":
                self.firmware_download_active = event.stage not in {"complete", "failed"}
                self.firmware_download_message = event.message
                self.status_text = event.message or f"Download {event.stage}: {event.current}/{event.total}"
                return
            if event.operation == "flash":
                self.firmware_flash_stage = event.stage
                self.firmware_flash_current = int(event.current)
                self.firmware_flash_total = max(1, int(event.total))
                self.firmware_flash_message = event.message
                self.firmware_flash_active = event.stage not in {"complete", "failed"}
                self.status_text = event.message or f"Flash {event.stage}: {event.current}/{event.total}"
            if event.operation == "flash_all":
                self.flash_all_active = event.stage not in {"complete", "failed"}
                self.flash_all_message = event.message
                self.status_text = event.message or f"Batch flash {event.stage}: {event.current}/{event.total}"
            return

        if isinstance(event, EventFirmwareFlashed):
            self.firmware_flash_active = False
            self.firmware_last_flash_size = int(event.byte_count)
            self.firmware_last_flash_verified = bool(event.verified)
            self.firmware_last_flash_name = event.display_name
            self.firmware_flash_stage = "complete"
            self.firmware_flash_current = 1
            self.firmware_flash_total = 1
            self.firmware_flash_message = f"Flash complete: {event.display_name}"
            self.status_text = self.firmware_flash_message
            return

        if isinstance(event, EventAllEscsFlashed):
            self.flash_all_active = False
            self.flash_all_total = int(event.total_attempted)
            self.flash_all_succeeded = int(event.total_succeeded)
            self.flash_all_message = (
                f"Batch flash: {event.total_succeeded}/{event.total_attempted} succeeded"
            )
            self.status_text = self.flash_all_message
            return

        if isinstance(event, EventPassthroughState):
            self.passthrough_active = event.active
            self.passthrough_motor = event.motor_index
            self.detected_esc_count = event.esc_count
            if event.active:
                self.status_text = f"Passthrough active (motor {event.motor_index}, ESCs={event.esc_count})"
            else:
                self.status_text = "Passthrough inactive"
            return

        if isinstance(event, EventEscScanResult):
            self.detected_esc_count = event.esc_count
            self.status_text = f"ESC scan complete: {event.esc_count} detected"
            return

        if isinstance(event, EventFourWayIdentity):
            self.fourway_interface_name = event.interface_name
            self.fourway_protocol_version = event.protocol_version
            self.fourway_interface_version = event.interface_version
            self.status_text = "4-way identity read complete"
            return

        if isinstance(event, EventSettingsLoaded):
            self.settings_address = event.address
            self.settings_size = len(event.data)
            self.settings_loaded_motor = int(getattr(event, "motor_index", self.passthrough_motor))
            preview = event.data[:32]
            self.settings_hex_preview = preview.hex(" ").upper()
            self.decoded_settings = decode_settings_payload(event.data, start_address=event.address)
            self.settings_edit_values = get_editable_field_values(self.decoded_settings)
            if self.firmware_catalog is not None:
                target_family = self.target_firmware_family()
                if target_family and target_family in self.firmware_catalog.releases_by_source:
                    self.selected_firmware_source = target_family
                filtered_releases = self.visible_firmware_releases()
                if filtered_releases and not any(release.key == self.selected_firmware_release_key for release in filtered_releases):
                    self.selected_firmware_release_key = filtered_releases[0].key
            self.status_text = f"Settings read complete: {len(event.data)} byte(s)"
            return

        if isinstance(event, EventSettingsWritten):
            self.settings_last_write_size = event.size
            self.settings_last_write_verified = event.verified
            verify_tag = " (verified)" if event.verified else ""
            self.status_text = f"Settings write complete: {event.size} byte(s){verify_tag}"
            return

        if isinstance(event, EventError):
            self.last_error = event.message
            if self.firmware_flash_active:
                self.firmware_flash_active = False
                self.firmware_flash_stage = "failed"
                self.firmware_flash_message = event.message
            if self.firmware_download_active:
                self.firmware_download_active = False
                self.firmware_download_message = f"Download failed: {event.message}"
            if self.flash_all_active:
                self.flash_all_active = False
                self.flash_all_message = f"Batch flash failed: {event.message}"
            self.status_text = event.message
            return

        if isinstance(event, EventOperationCancelled):
            if event.operation in {"flash", "flash_all"}:
                self.firmware_flash_active = False
                self.firmware_flash_stage = "cancelled"
                self.firmware_flash_message = "Cancelled by user"
            if event.operation == "flash_all":
                self.flash_all_active = False
                self.flash_all_message = "Batch flash cancelled by user"
            if event.operation == "download":
                self.firmware_download_active = False
                self.firmware_download_message = "Download cancelled by user"
            self.status_text = f"Operation cancelled ({event.operation})"
            return

        if isinstance(event, EventLog):
            self.append_log(event.level, event.message, source=event.source)


def create_app_state() -> AppState:
    """Construct the initial application state."""

    state = AppState()
    state.append_log("info", "Application initialized", source="app")
    return state
