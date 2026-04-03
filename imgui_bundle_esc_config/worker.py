"""Worker/controller foundation for the ImGui ESC configurator.

Phase 1 focuses on transport ownership, serial port enumeration, and clean
command/event boundaries. Higher-level MSP and 4-way operations will build on
this queue-based skeleton.
"""

from __future__ import annotations

from dataclasses import dataclass
import queue
import threading
import time
from time import perf_counter
from typing import Any, Callable

from MSP import (
    FOURWAY_ACK,
    FOURWAY_CMDS,
    FOURWAY_FC_SYNC,
    FourWayClient,
    MSPClient,
    SerialPortDescriptor,
    SerialTransport,
    build_fourway_frame,
    build_msp_frame,
    crc16_xmodem,
    list_serial_ports,
)

from .firmware_catalog import FirmwareCatalogClient, FirmwareCatalogSnapshot, FirmwareRelease, describe_release_compatibility, load_firmware_file
from .settings_decoder import DecodedSettings, decode_settings_payload

MSP_SET_PASSTHROUGH = 245
MSP_SET_MOTOR = 214
MSP_API_VERSION = 1
MSP_FC_VARIANT = 2
MSP_FC_VERSION = 3
MSP_BOARD_INFO = 4
MSP_BUILD_INFO = 5
MSP_MOTOR = 104
MSP_STATUS = 101
MSP_UID = 160
MSP_FEATURE_CONFIG = 36
MSP_BATTERY_STATE = 130
MSP_RC = 105
MSP_ANALOG = 110
PROTOCOL_MODE_MSP = "msp"
PROTOCOL_MODE_OPTIMIZED_TANG9K = "optimized_tang9k"

MSP_COMMAND_NAMES: dict[int, str] = {
    MSP_API_VERSION: "MSP_API_VERSION",
    MSP_FC_VARIANT: "MSP_FC_VARIANT",
    MSP_FC_VERSION: "MSP_FC_VERSION",
    MSP_BOARD_INFO: "MSP_BOARD_INFO",
    MSP_BUILD_INFO: "MSP_BUILD_INFO",
    MSP_FEATURE_CONFIG: "MSP_FEATURE_CONFIG",
    MSP_MOTOR: "MSP_MOTOR",
    MSP_RC: "MSP_RC",
    MSP_ANALOG: "MSP_ANALOG",
    MSP_STATUS: "MSP_STATUS",
    MSP_BATTERY_STATE: "MSP_BATTERY_STATE",
    MSP_UID: "MSP_UID",
    MSP_SET_PASSTHROUGH: "MSP_SET_PASSTHROUGH",
    MSP_SET_MOTOR: "MSP_SET_MOTOR",
}


@dataclass(frozen=True)
class CommandRefreshPorts:
    """Request serial port enumeration."""


@dataclass(frozen=True)
class CommandConnect:
    """Request a transport connection."""

    port: str
    baudrate: int = 115200
    timeout: float = 0.2
    protocol_mode: str = "msp"


@dataclass(frozen=True)
class CommandDisconnect:
    """Request transport shutdown."""

    reason: str = "Disconnected"


@dataclass(frozen=True)
class CommandShutdown:
    """Request worker termination."""


@dataclass(frozen=True)
class CommandEnterPassthrough:
    """Request MSP passthrough entry for the selected motor."""

    motor_index: int = 0


@dataclass(frozen=True)
class CommandExitPassthrough:
    """Request passthrough exit and 4-way reset behavior."""


@dataclass(frozen=True)
class CommandScanEscs:
    """Request ESC scan while entering/refreshing passthrough state."""

    motor_index: int = 0


@dataclass(frozen=True)
class CommandSetMotorSpeed:
    """Request DSHOT speed write via MSP_SET_MOTOR for a single motor."""

    motor_index: int = 0
    speed: int = 0


@dataclass(frozen=True)
class CommandReadFourWayIdentity:
    """Request 4-way interface identity/version reads."""


@dataclass(frozen=True)
class CommandReadSettings:
    """Request EEPROM/settings bytes from the active ESC."""

    length: int = 128
    address: int = 0
    motor_index: int = 0


@dataclass(frozen=True)
class CommandRefreshFirmwareCatalog:
    """Request firmware catalog refresh."""


@dataclass(frozen=True)
class CommandDownloadFirmware:
    """Request a remote firmware image download for the selected release."""

    release: FirmwareRelease
    pwm_khz: int = 48


@dataclass(frozen=True)
class CommandWriteSettings:
    """Request EEPROM/settings write to the active ESC."""

    data: bytes
    address: int = 0
    verify_readback: bool = True


@dataclass(frozen=True)
class CommandFlashEsc:
    """Request local firmware flash + verify for the active ESC."""

    file_path: str
    family: str
    display_name: str = ""
    verify_readback: bool = True
    allow_incompatible: bool = False


@dataclass(frozen=True)
class CommandFlashAllEscs:
    """Flash the same firmware to all ESCs in sequence, reading settings for each first."""

    file_path: str
    family: str
    motor_count: int
    display_name: str = ""
    verify_readback: bool = True
    settings_read_length: int = 255
    settings_address: int = 0


@dataclass(frozen=True)
class CommandCancelOperation:
    """Request cancellation of the current long-running flash or download operation."""


@dataclass(frozen=True)
class EventOperationCancelled:
    """Emitted when a flash or download operation is cancelled by the user."""

    operation: str  # "flash" | "download" | "flash_all"


@dataclass(frozen=True)
class EventPortsUpdated:
    """Serial ports enumerated by the worker."""

    ports: list[SerialPortDescriptor]


@dataclass(frozen=True)
class EventConnected:
    """Transport connected successfully."""

    port: str
    baudrate: int
    protocol_mode: str = "msp"


@dataclass(frozen=True)
class EventDisconnected:
    """Transport disconnected or closed."""

    reason: str


@dataclass(frozen=True)
class EventError:
    """Recoverable worker error."""

    message: str


@dataclass(frozen=True)
class EventLog:
    """Log message emitted by the worker."""

    level: str
    message: str
    source: str = "worker"


@dataclass(frozen=True)
class EventProtocolTrace:
    """Detailed MSP / 4-way protocol trace line for debug UIs."""

    channel: str
    message: str


@dataclass(frozen=True)
class EventPassthroughState:
    """Current passthrough state reported by the worker."""

    active: bool
    motor_index: int
    esc_count: int


@dataclass(frozen=True)
class EventEscScanResult:
    """ESC scan result from a passthrough command flow."""

    esc_count: int
    motor_index: int


@dataclass(frozen=True)
class EventFourWayIdentity:
    """4-way identity information returned by the worker."""

    interface_name: str
    protocol_version: int
    interface_version: str


@dataclass(frozen=True)
class EventSettingsLoaded:
    """Raw EEPROM/settings payload from 4-way read."""

    data: bytes
    address: int
    motor_index: int = 0


@dataclass(frozen=True)
class EventSettingsWritten:
    """Result metadata for a settings write operation."""

    address: int
    size: int
    verified: bool


@dataclass(frozen=True)
class EventFirmwareCatalogLoaded:
    """Firmware catalog snapshot loaded by the worker."""

    snapshot: FirmwareCatalogSnapshot
    from_cache: bool = False


@dataclass(frozen=True)
class EventFirmwareDownloaded:
    """Firmware image downloaded and cached for flashing."""

    file_path: str
    image_name: str
    family: str
    source: str
    byte_count: int


@dataclass(frozen=True)
class EventProgress:
    """Long-running operation progress update."""

    operation: str
    stage: str
    current: int
    total: int
    message: str = ""


@dataclass(frozen=True)
class EventMotorCount:
    """Motor count reported by the FC via MSP."""

    count: int


@dataclass(frozen=True)
class EventMspStats:
    """MSP transport health stats for UI status display."""

    total: int
    errors: int
    success_percent: float
    error_percent: float
    messages_per_second: float


@dataclass(frozen=True)
class EventFirmwareFlashed:
    """Final flash result metadata."""

    byte_count: int
    verified: bool
    display_name: str
    family: str
    motor_index: int


@dataclass(frozen=True)
class EventAllEscsFlashed:
    """Batch flash summary — emitted when CommandFlashAllEscs completes."""

    total_attempted: int
    total_succeeded: int
    motor_indices: tuple[int, ...]


class WorkerController:
    """Queue-based worker that owns transport lifecycle outside the UI thread."""

    def __init__(
        self,
        *,
        port_enumerator: Callable[[], list[SerialPortDescriptor]] = list_serial_ports,
        transport_factory: Callable[[str, int, float], SerialTransport] = SerialTransport,
        msp_client_factory: Callable[[SerialTransport], Any] = MSPClient,
        fourway_client_factory: Callable[[SerialTransport], Any] = FourWayClient,
        firmware_catalog_client: FirmwareCatalogClient | None = None,
        msp_probe_on_connect: bool = False,
        esc_stabilization_delay_s: float = 0.0,
    ) -> None:
        self._port_enumerator = port_enumerator
        self._transport_factory = transport_factory
        self._msp_client_factory = msp_client_factory
        self._fourway_client_factory = fourway_client_factory
        self._firmware_catalog_client = firmware_catalog_client or FirmwareCatalogClient()
        self._msp_probe_on_connect = msp_probe_on_connect
        self._esc_stabilization_delay_s = float(esc_stabilization_delay_s)
        self._command_queue: queue.Queue[object] = queue.Queue()
        self._event_queue: queue.Queue[object] = queue.Queue()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._transport: SerialTransport | None = None
        self._msp_client: Any | None = None
        self._fourway_client: Any | None = None
        self._passthrough_active = False
        self._passthrough_motor = 0
        self._esc_count = 0
        self._protocol_mode = PROTOCOL_MODE_MSP
        self._motor_count = 4
        self._dshot_speeds = [0, 0, 0, 0]
        self._msp_total = 0
        self._msp_errors = 0
        self._msp_started_at = perf_counter()
        self._last_decoded_settings: DecodedSettings | None = None
        self._last_settings_motor: int | None = None
        self._cancel_requested = threading.Event()

    def _emit_msp_stats(self) -> None:
        elapsed = max(0.001, perf_counter() - self._msp_started_at)
        total = int(self._msp_total)
        errors = int(self._msp_errors)
        success = max(0, total - errors)
        success_percent = (100.0 * success / total) if total > 0 else 100.0
        error_percent = (100.0 * errors / total) if total > 0 else 0.0
        messages_per_second = float(total) / elapsed
        self._emit(
            EventMspStats(
                total=total,
                errors=errors,
                success_percent=success_percent,
                error_percent=error_percent,
                messages_per_second=messages_per_second,
            )
        )

    def _emit_progress(self, operation: str, stage: str, current: int, total: int, message: str = "") -> None:
        safe_total = max(1, int(total))
        safe_current = max(0, min(int(current), safe_total))
        self._emit(
            EventProgress(
                operation=operation,
                stage=stage,
                current=safe_current,
                total=safe_total,
                message=message,
            )
        )

    def _build_motor_payload(self, speeds: list[int]) -> bytes:
        payload = bytearray()
        for value in speeds:
            payload.append(value & 0xFF)
            payload.append((value >> 8) & 0xFF)
        return bytes(payload)

    def _set_motor_count(self, count: int) -> None:
        safe_count = max(1, min(16, int(count)))
        if safe_count == self._motor_count:
            return
        old_speeds = list(self._dshot_speeds)
        self._motor_count = safe_count
        self._dshot_speeds = (old_speeds + [0] * safe_count)[:safe_count]
        self._emit(EventMotorCount(count=self._motor_count))

    def _query_motor_count_from_msp(self) -> None:
        if self._msp_client is None:
            return
        try:
            response = self._send_msp_logged(
                MSP_MOTOR,
                b"",
                expect_response=True,
                timeout=1.0,
                description="read motor count",
            )
            payload = bytes(getattr(getattr(response, "frame", None), "payload", b""))
            if len(payload) >= 2:
                count = len(payload) // 2
                self._set_motor_count(count)
                self._emit(EventLog("info", f"FC reported motor count: {self._motor_count}", source="msp"))
            else:
                self._emit(EventMotorCount(count=self._motor_count))
        except Exception as exc:
            self._emit(EventMotorCount(count=self._motor_count))
            self._emit(EventLog("warning", f"Motor count probe failed, using default {self._motor_count}: {exc}", source="msp"))

    def _safe_ascii(self, data: bytes) -> str:
        return bytes(data).decode("ascii", errors="replace").rstrip("\x00 ")

    def _probe_msp_identity(self) -> None:
        if self._msp_client is None:
            return

        def read_payload(command: int, description: str) -> bytes:
            response = self._send_msp_logged(
                command,
                b"",
                expect_response=True,
                timeout=1.2,
                description=description,
            )
            return bytes(getattr(getattr(response, "frame", None), "payload", b""))

        def safe_read_payload(command: int, description: str) -> bytes:
            try:
                return read_payload(command, description)
            except Exception as exc:  # pragma: no cover - backend dependent
                command_name = MSP_COMMAND_NAMES.get(command, str(command))
                self._emit(EventLog("warning", f"MSP probe step failed for {command_name}: {exc}", source="msp"))
                return b""

        api = safe_read_payload(MSP_API_VERSION, "read API version")
        if len(api) >= 3:
            self._emit(EventLog("info", f"MSP API version: {api[0]}.{api[1]}.{api[2]}", source="msp"))

        variant = safe_read_payload(MSP_FC_VARIANT, "read FC variant")
        if variant:
            self._emit(EventLog("info", f"FC variant: {self._safe_ascii(variant)}", source="msp"))

        fc_version = safe_read_payload(MSP_FC_VERSION, "read FC version")
        if len(fc_version) >= 3:
            self._emit(EventLog("info", f"FC version: {fc_version[0]}.{fc_version[1]}.{fc_version[2]}", source="msp"))

        board = safe_read_payload(MSP_BOARD_INFO, "read board info")
        if board:
            board_name = self._safe_ascii(board[:8]) if len(board) >= 4 else self._format_bytes(board)
            self._emit(EventLog("info", f"Board info: {board_name}", source="msp"))

        build = safe_read_payload(MSP_BUILD_INFO, "read build info")
        if build:
            self._emit(EventLog("info", f"Build info: {self._safe_ascii(build)}", source="msp"))

        uid = safe_read_payload(MSP_UID, "read UID")
        if uid:
            self._emit(EventLog("info", f"UID: {uid.hex().upper()}", source="msp"))

        status = safe_read_payload(MSP_STATUS, "read status")
        if status:
            self._emit(EventLog("info", f"Status payload: {self._format_bytes(status)}", source="msp"))

        feature_config = safe_read_payload(MSP_FEATURE_CONFIG, "read feature config")
        if feature_config:
            self._emit(EventLog("info", f"Feature config payload: {self._format_bytes(feature_config)}", source="msp"))

        battery = safe_read_payload(MSP_BATTERY_STATE, "read battery state")
        if battery:
            self._emit(EventLog("info", f"Battery state payload: {self._format_bytes(battery)}", source="msp"))

        rc = safe_read_payload(MSP_RC, "read rc channels")
        if rc:
            self._emit(EventLog("info", f"RC payload: {self._format_bytes(rc)}", source="msp"))

        analog = safe_read_payload(MSP_ANALOG, "read analog")
        if analog:
            self._emit(EventLog("info", f"Analog payload: {self._format_bytes(analog)}", source="msp"))

    def _trace_protocol(self, channel: str, message: str) -> None:
        self._emit(EventProtocolTrace(channel=channel, message=message))

    def _format_bytes(self, data: bytes, limit: int = 48) -> str:
        if not data:
            return "<empty>"
        shown = data[:limit].hex(" ").upper()
        if len(data) > limit:
            return f"{shown} … ({len(data)} bytes)"
        return shown

    def _fourway_cmd_name(self, command: int) -> str:
        for name, value in FOURWAY_CMDS.items():
            if value == command:
                return name
        return f"0x{command:02X}"

    def _build_fourway_response_frame(self, command: int, address: int, params: bytes, ack: int) -> bytes:
        param_bytes = bytes(params)
        if len(param_bytes) > 256:
            raise ValueError("4-way response params must be <= 256 bytes")
        param_len = len(param_bytes) if len(param_bytes) < 256 else 0
        body = bytes(
            [
                FOURWAY_FC_SYNC,
                command & 0xFF,
                (address >> 8) & 0xFF,
                address & 0xFF,
                param_len,
            ]
        ) + param_bytes + bytes([ack & 0xFF])
        crc = crc16_xmodem(body)
        return body + bytes([(crc >> 8) & 0xFF, crc & 0xFF])

    def _send_msp_logged(
        self,
        command: int,
        payload: bytes = b"",
        *,
        expect_response: bool = True,
        timeout: float = 1.0,
        description: str = "",
    ) -> Any:
        command_name = MSP_COMMAND_NAMES.get(command, "MSP_UNKNOWN")
        request_frame = build_msp_frame(command, payload)
        desc = f" ({description})" if description else ""
        self._trace_protocol(
            "MSP",
            (
                f"MSP -> {command_name}({command}){desc}: "
                f"{request_frame.hex(' ').upper()}"
            ),
        )
        self._msp_total += 1
        try:
            response = self._msp_client.send_msp(  # type: ignore[union-attr]
                command,
                payload,
                expect_response=expect_response,
                timeout=timeout,
            )
        except Exception:
            self._msp_errors += 1
            self._emit_msp_stats()
            raise
        self._emit_msp_stats()
        if response is None:
            self._trace_protocol("MSP", f"MSP <= {command_name}({command}): <no response expected>")
            return None

        frame = response.frame
        response_command = int(getattr(frame, "command", command))
        response_payload = bytes(getattr(frame, "payload", b""))
        response_frame = build_msp_frame(response_command, response_payload, header=b"$M>")
        response_command_name = MSP_COMMAND_NAMES.get(response_command, "MSP_UNKNOWN")
        self._trace_protocol(
            "MSP",
            (
                f"MSP <= {response_command_name}({response_command}): "
                f"{response_frame.hex(' ').upper()}"
            ),
        )
        return response

    def _send_fourway_logged(
        self,
        command: int,
        *,
        address: int = 0,
        params: bytes = b"",
        timeout: float = 2.0,
        description: str = "",
    ) -> Any:
        name = self._fourway_cmd_name(command)
        desc = f" ({description})" if description else ""
        request_frame = build_fourway_frame(command, address=address, params=params)
        self._trace_protocol(
            "4WAY",
            f"4WAY -> {name}(0x{command:02X}){desc}: {request_frame.hex(' ').upper()}",
        )
        response = self._fourway_client.send(  # type: ignore[union-attr]
            command,
            address=address,
            params=params,
            timeout=timeout,
        )
        response_command = int(getattr(response, "command", command))
        response_address = int(getattr(response, "address", address))
        response_params = bytes(getattr(response, "params", b""))
        response_ack = int(getattr(response, "ack", 0))
        response_crc_ok = bool(getattr(response, "crc_ok", False))
        response_frame = self._build_fourway_response_frame(
            command=response_command,
            address=response_address,
            params=response_params,
            ack=response_ack,
        )
        ack_name = FOURWAY_ACK.get(response_ack, f"UNKNOWN(0x{response_ack:02X})")
        self._trace_protocol(
            "4WAY",
            (
                f"4WAY <= {name}(0x{response_command:02X}): {response_frame.hex(' ').upper()} "
                f"ack={ack_name} crc_ok={response_crc_ok}"
            ),
        )
        return response

    def _ensure_fourway_ok(self, response: Any, operation: str) -> None:
        ack = int(getattr(response, "ack", 0))
        if ack != 0:
            ack_name = FOURWAY_ACK.get(ack, f"UNKNOWN(0x{ack:02X})")
            raise RuntimeError(f"{operation} failed with ACK {ack_name}")

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker_loop, name="esc-config-worker", daemon=True)
        self._thread.start()
        self._emit(EventLog("info", "Worker thread started"))

    def stop(self, timeout: float = 1.0) -> None:
        if self._thread is None:
            return
        self.enqueue(CommandShutdown())
        self._thread.join(timeout=timeout)
        self._thread = None
        self._stop_event.set()

    def enqueue(self, command: object) -> None:
        self._command_queue.put(command)

    def poll_events(self, max_events: int = 100) -> list[object]:
        events: list[object] = []
        for _ in range(max_events):
            try:
                events.append(self._event_queue.get_nowait())
            except queue.Empty:
                break
        return events

    def _emit(self, event: object) -> None:
        self._event_queue.put(event)

    def _disconnect_transport(self, reason: str) -> None:
        transport = self._transport
        if transport is not None:
            try:
                transport.close()
            finally:
                self._transport = None
        self._msp_client = None
        self._fourway_client = None
        self._passthrough_active = False
        self._passthrough_motor = 0
        self._esc_count = 0
        self._protocol_mode = PROTOCOL_MODE_MSP
        self._motor_count = 4
        self._dshot_speeds = [0, 0, 0, 0]
        self._last_decoded_settings = None
        self._last_settings_motor = None
        self._msp_total = 0
        self._msp_errors = 0
        self._msp_started_at = perf_counter()
        self._emit(EventPassthroughState(active=False, motor_index=0, esc_count=0))
        self._emit(EventMotorCount(count=self._motor_count))
        self._emit_msp_stats()
        self._emit(EventDisconnected(reason=reason))
        self._emit(EventLog("info", reason))

    def _handle_refresh_ports(self) -> None:
        ports = self._port_enumerator()
        self._emit(EventPortsUpdated(ports=ports))
        self._emit(EventLog("info", f"Enumerated {len(ports)} serial port(s)"))

    def _handle_connect(self, command: CommandConnect) -> None:
        if self._transport is not None:
            self._disconnect_transport("Disconnected previous transport")

        try:
            self._transport = self._transport_factory(command.port, command.baudrate, command.timeout)
            self._msp_client = self._msp_client_factory(self._transport)
            self._fourway_client = self._fourway_client_factory(self._transport)
        except Exception as exc:  # pragma: no cover - exact backend errors are environment-specific
            message = f"Failed to connect to {command.port}: {exc}"
            self._emit(EventError(message=message))
            self._emit(EventLog("error", message))
            self._transport = None
            self._msp_client = None
            self._fourway_client = None
            return

        protocol_mode = (
            PROTOCOL_MODE_OPTIMIZED_TANG9K
            if command.protocol_mode in {
                "optimized",
                "tang20k",
                "optimized_tang20k",
                "optimized_tangnano20k",
                PROTOCOL_MODE_OPTIMIZED_TANG9K,
            }
            else PROTOCOL_MODE_MSP
        )
        self._protocol_mode = protocol_mode
        protocol_label = "Optimized protocol" if protocol_mode == PROTOCOL_MODE_OPTIMIZED_TANG9K else "MSP protocol"
        self._msp_total = 0
        self._msp_errors = 0
        self._msp_started_at = perf_counter()

        self._emit(
            EventConnected(
                port=command.port,
                baudrate=command.baudrate,
                protocol_mode=protocol_mode,
            )
        )
        self._emit_msp_stats()
        self._emit(EventMotorCount(count=self._motor_count))
        self._dshot_speeds = [0] * self._motor_count
        self._query_motor_count_from_msp()
        self._emit(EventPassthroughState(active=False, motor_index=0, esc_count=0))
        self._emit(
            EventLog(
                "info",
                f"Connected to {command.port} @ {command.baudrate} ({protocol_label})",
            )
        )
        if protocol_mode == PROTOCOL_MODE_OPTIMIZED_TANG9K:
            self._emit(
                EventLog(
                    "info",
                    "Optimized protocol selected (Tang9K SERV+PIO path); MSP fallback remains active until Tang9K transport is wired.",
                    source="tang9k",
                )
            )
        if self._msp_probe_on_connect:
            self._probe_msp_identity()

    def _emit_passthrough_state(self) -> None:
        self._emit(
            EventPassthroughState(
                active=self._passthrough_active,
                motor_index=self._passthrough_motor,
                esc_count=self._esc_count,
            )
        )

    def _is_transport_fatal(self, exc: BaseException) -> bool:
        """Return True if an exception represents an unrecoverable serial/IO loss."""
        exc_type_name = type(exc).__name__.lower()
        # serial.SerialException, OSError, BrokenPipeError etc.
        is_io_type = isinstance(exc, (OSError, EOFError)) or "serial" in exc_type_name or "port" in exc_type_name
        msg = str(exc).lower()
        fatal_phrases = ("device disconnected", "i/o error", "input/output error", "port is closed", "broken pipe",
                         "no such file", "device not found", "access is denied", "the device has no data")
        return is_io_type or any(p in msg for p in fatal_phrases)

    def _require_msp_client(self) -> bool:
        if self._msp_client is not None:
            return True
        message = "Not connected: connect to a serial target first"
        self._emit(EventError(message=message))
        self._emit(EventLog("warning", message))
        return False

    def _extract_esc_count(self, response: Any) -> int:
        payload = getattr(getattr(response, "frame", None), "payload", b"")
        if not payload:
            return 0
        return int(payload[0])

    def _extract_first_param(self, response: Any) -> int:
        params = getattr(response, "params", b"")
        if not params:
            return 0
        return int(params[0])

    def _decode_ascii_params(self, response: Any) -> str:
        params = getattr(response, "params", b"")
        if not params:
            return ""
        return bytes(params).decode("ascii", errors="replace").rstrip("\x00")

    def _require_passthrough(self) -> bool:
        if self._passthrough_active:
            return True
        message = "Passthrough is not active; enter passthrough before 4-way identity read"
        self._emit(EventError(message=message))
        self._emit(EventLog("warning", message))
        return False

    def _handle_enter_passthrough(self, command: CommandEnterPassthrough) -> None:
        if not self._require_msp_client():
            return
        motor_index = command.motor_index
        if not (0 <= motor_index < self._motor_count):
            message = f"Invalid motor index {motor_index}; expected 0..{self._motor_count - 1}"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return

        transition_start = perf_counter()
        response = self._send_msp_logged(
            MSP_SET_PASSTHROUGH,
            bytes([0x00, motor_index & 0xFF]),
            expect_response=True,
            timeout=1.5,
            description=f"enter passthrough motor={motor_index}",
        )
        transition_ms = (perf_counter() - transition_start) * 1000.0
        esc_count = self._extract_esc_count(response)
        self._passthrough_active = esc_count > 0
        self._passthrough_motor = motor_index
        self._esc_count = esc_count
        if self._passthrough_active:
            self._dshot_speeds = [0, 0, 0, 0]
            self._last_decoded_settings = None
            self._last_settings_motor = None
        self._emit_passthrough_state()
        if self._passthrough_active:
            self._emit(EventLog("info", f"Passthrough active on motor {motor_index}; ESC count={esc_count}"))
            self._emit(
                EventLog(
                    "info",
                    (
                        f"ESC transition timing: switched to ESC serial on motor {motor_index} "
                        f"in {transition_ms:.1f} ms (ESC count={esc_count})"
                    ),
                    source="esc",
                )
            )
        else:
            self._emit(EventError(message="Passthrough did not activate (ESC count=0)"))
            self._emit(
                EventLog(
                    "warning",
                    (
                        f"ESC transition timing: serial handoff attempt on motor {motor_index} "
                        f"did not activate in {transition_ms:.1f} ms"
                    ),
                    source="esc",
                )
            )

    def _handle_exit_passthrough(self) -> None:
        if not self._require_msp_client():
            return
        transition_start = perf_counter()
        self._send_msp_logged(
            MSP_SET_PASSTHROUGH,
            bytes([0x08]),
            expect_response=True,
            timeout=1.5,
            description="exit passthrough",
        )
        transition_ms = (perf_counter() - transition_start) * 1000.0
        self._passthrough_active = False
        self._esc_count = 0
        self._dshot_speeds = [0, 0, 0, 0]
        self._last_decoded_settings = None
        self._last_settings_motor = None
        self._emit_passthrough_state()
        self._emit(EventLog("info", "Passthrough exit requested"))
        self._emit(
            EventLog(
                "info",
                f"ESC transition timing: switched from ESC serial back to DSHOT in {transition_ms:.1f} ms",
                source="esc",
            )
        )

    def _handle_scan_escs(self, command: CommandScanEscs) -> None:
        if not self._require_msp_client():
            return
        motor_index = command.motor_index
        if not (0 <= motor_index < self._motor_count):
            message = f"Invalid motor index {motor_index}; expected 0..{self._motor_count - 1}"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return

        response = self._send_msp_logged(
            MSP_SET_PASSTHROUGH,
            bytes([0x00, motor_index & 0xFF]),
            expect_response=True,
            timeout=1.5,
            description=f"scan escs motor={motor_index}",
        )
        esc_count = self._extract_esc_count(response)
        self._passthrough_active = esc_count > 0
        self._passthrough_motor = motor_index
        self._esc_count = esc_count
        self._emit_passthrough_state()
        self._emit(EventEscScanResult(esc_count=esc_count, motor_index=motor_index))
        self._emit(EventLog("info", f"ESC scan complete on motor {motor_index}: count={esc_count}"))

    def _handle_set_motor_speed(self, command: CommandSetMotorSpeed) -> None:
        if not self._require_msp_client():
            return
        motor_index = int(command.motor_index)
        if not (0 <= motor_index < self._motor_count):
            message = f"Invalid motor index {motor_index}; expected 0..{self._motor_count - 1}"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return

        speed = max(0, min(2047, int(command.speed)))
        if self._passthrough_active:
            self._emit(
                EventLog(
                    "warning",
                    "Cannot set DSHOT speed while passthrough is active; exit passthrough first.",
                    source="esc",
                )
            )
            return

        self._dshot_speeds[motor_index] = speed
        payload = self._build_motor_payload(self._dshot_speeds)
        self._send_msp_logged(
            MSP_SET_MOTOR,
            payload,
            expect_response=False,
            timeout=0.3,
            description=f"set motor {motor_index} speed={speed}",
        )
        self._emit(EventLog("info", f"DSHOT speed set: motor {motor_index} -> {speed}", source="esc"))

    def _handle_read_fourway_identity(self) -> None:
        if not self._require_msp_client():
            return
        if not self._require_passthrough():
            return
        if self._fourway_client is None:
            message = "4-way client not initialized"
            self._emit(EventError(message=message))
            self._emit(EventLog("error", message))
            return

        req_get_version = build_fourway_frame(FOURWAY_CMDS["get_version"], address=0, params=b"")
        self._trace_protocol(
            "4WAY",
            f"4WAY -> get_version(0x31) (read protocol version): {req_get_version.hex(' ').upper()}",
        )
        protocol_resp = self._fourway_client.get_version()
        protocol_resp_frame = self._build_fourway_response_frame(
            command=FOURWAY_CMDS["get_version"],
            address=0,
            params=bytes(getattr(protocol_resp, "params", b"")),
            ack=int(getattr(protocol_resp, "ack", 0)),
        )
        self._trace_protocol(
            "4WAY",
            (
                f"4WAY <= get_version(0x31): {protocol_resp_frame.hex(' ').upper()} "
                f"ack={FOURWAY_ACK.get(int(getattr(protocol_resp, 'ack', 0)), f'UNKNOWN(0x{int(getattr(protocol_resp, 'ack', 0)):02X}')} "
                f"crc_ok={bool(getattr(protocol_resp, 'crc_ok', False))}"
            ),
        )

        req_get_name = build_fourway_frame(FOURWAY_CMDS["get_name"], address=0, params=b"")
        self._trace_protocol(
            "4WAY",
            f"4WAY -> get_name(0x32) (read interface name): {req_get_name.hex(' ').upper()}",
        )
        name_resp = self._fourway_client.get_name()
        name_resp_frame = self._build_fourway_response_frame(
            command=FOURWAY_CMDS["get_name"],
            address=0,
            params=bytes(getattr(name_resp, "params", b"")),
            ack=int(getattr(name_resp, "ack", 0)),
        )
        self._trace_protocol(
            "4WAY",
            (
                f"4WAY <= get_name(0x32): {name_resp_frame.hex(' ').upper()} "
                f"ack={FOURWAY_ACK.get(int(getattr(name_resp, 'ack', 0)), f'UNKNOWN(0x{int(getattr(name_resp, 'ack', 0)):02X}')} "
                f"crc_ok={bool(getattr(name_resp, 'crc_ok', False))}"
            ),
        )

        if_version_resp = self._send_fourway_logged(
            FOURWAY_CMDS["get_if_version"],
            description="read interface version",
        )

        protocol_version = self._extract_first_param(protocol_resp)
        interface_name = self._decode_ascii_params(name_resp)
        if_version_params = getattr(if_version_resp, "params", b"")
        if len(if_version_params) >= 2:
            interface_version = f"{int(if_version_params[0])}.{int(if_version_params[1])}"
        elif len(if_version_params) == 1:
            interface_version = str(int(if_version_params[0]))
        else:
            interface_version = ""

        self._emit(
            EventFourWayIdentity(
                interface_name=interface_name,
                protocol_version=protocol_version,
                interface_version=interface_version,
            )
        )
        self._emit(
            EventLog(
                "info",
                f"4-way identity read: name='{interface_name}' protocol={protocol_version} interface={interface_version}",
            )
        )

    def _handle_read_settings(self, command: CommandReadSettings) -> None:
        if not self._require_msp_client():
            return

        auto_entered = False
        if not self._passthrough_active:
            motor_index = int(command.motor_index)
            if not (0 <= motor_index < self._motor_count):
                message = f"Invalid motor index {motor_index}; expected 0..{self._motor_count - 1}"
                self._emit(EventError(message=message))
                self._emit(EventLog("warning", message))
                return
            self._handle_enter_passthrough(CommandEnterPassthrough(motor_index=motor_index))
            auto_entered = True

        if not self._require_passthrough():
            return
        if self._fourway_client is None:
            message = "4-way client not initialized"
            self._emit(EventError(message=message))
            self._emit(EventLog("error", message))
            return

        if auto_entered:
            self._emit(EventLog("info", f"Auto-entered passthrough on motor {self._passthrough_motor} before reading settings"))
            if self._esc_stabilization_delay_s > 0.0:
                self._emit(EventLog(
                    "info",
                    f"ESC stabilization delay: waiting {self._esc_stabilization_delay_s * 1000:.0f} ms before reading settings",
                    source="esc",
                ))
                time.sleep(self._esc_stabilization_delay_s)
            try:
                self._handle_read_fourway_identity()
            except Exception as exc:
                self._emit(EventLog("warning", f"4-way identity bootstrap failed before settings read: {exc}", source="4way"))

        length = max(1, min(255, int(command.length)))
        address = max(0, int(command.address))
        response = self._send_fourway_logged(
            FOURWAY_CMDS["read_eeprom"],
            address=address,
            params=bytes([length & 0xFF]),
            description="read settings",
        )
        params = bytes(getattr(response, "params", b""))
        self._last_decoded_settings = decode_settings_payload(params, start_address=address)
        self._last_settings_motor = self._passthrough_motor
        self._emit(EventSettingsLoaded(data=params, address=address, motor_index=self._passthrough_motor))
        self._emit(EventLog("info", f"Read settings: {len(params)} byte(s) @ 0x{address:04X}"))

    def _handle_write_settings(self, command: CommandWriteSettings) -> None:
        if not self._require_msp_client():
            return
        if not self._require_passthrough():
            return
        if self._fourway_client is None:
            message = "4-way client not initialized"
            self._emit(EventError(message=message))
            self._emit(EventLog("error", message))
            return

        address = max(0, int(command.address))
        data = bytes(command.data)
        if len(data) < 1 or len(data) > 256:
            message = f"Invalid settings write length {len(data)}; expected 1..256"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return

        self._send_fourway_logged(
            FOURWAY_CMDS["write_eeprom"],
            address=address,
            params=data,
            description="write settings",
        )

        verified = False
        readback = b""
        if command.verify_readback:
            read_len_param = 0 if len(data) == 256 else len(data)
            readback_response = self._send_fourway_logged(
                FOURWAY_CMDS["read_eeprom"],
                address=address,
                params=bytes([read_len_param & 0xFF]),
                description="verify settings readback",
            )
            readback = bytes(getattr(readback_response, "params", b""))
            verified = readback == data
            if not verified:
                message = (
                    f"Settings verification failed @ 0x{address:04X}: "
                    f"wrote {len(data)} byte(s), read back {len(readback)} byte(s)"
                )
                self._emit(EventError(message=message))
                self._emit(EventLog("error", message))
                return

        self._emit(EventSettingsWritten(address=address, size=len(data), verified=verified))
        if readback:
            self._last_decoded_settings = decode_settings_payload(readback, start_address=address)
            self._last_settings_motor = self._passthrough_motor
            self._emit(EventSettingsLoaded(data=readback, address=address, motor_index=self._passthrough_motor))
        self._emit(
            EventLog(
                "info",
                f"Wrote settings: {len(data)} byte(s) @ 0x{address:04X}"
                + (" (verified)" if verified else ""),
            )
        )

    def _handle_flash_esc(self, command: CommandFlashEsc) -> None:
        if not self._require_msp_client():
            return
        if not self._require_passthrough():
            return
        if self._fourway_client is None:
            message = "4-way client not initialized"
            self._emit(EventError(message=message))
            self._emit(EventLog("error", message))
            return

        if self._last_decoded_settings is None:
            message = "Read settings before flashing so compatibility can be checked"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return
        if self._last_settings_motor != self._passthrough_motor:
            message = (
                f"Settings are stale for active ESC {self._passthrough_motor}; "
                f"read settings again before flashing"
            )
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return

        esc_family = (self._last_decoded_settings.family or "").strip()
        requested_family = (command.family or esc_family).strip()
        if not esc_family or esc_family == "Unknown":
            message = "ESC family is unknown; read settings from a recognized BLHeli_S or Bluejay target before flashing"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return
        if requested_family and requested_family != esc_family and not command.allow_incompatible:
            message = f"Firmware family mismatch: target is {esc_family}, requested image is {requested_family}"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return

        file_path = command.file_path.strip()
        if not file_path:
            message = "Select a local firmware file before flashing"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return

        image = load_firmware_file(file_path, family=requested_family or esc_family)
        display_name = command.display_name.strip() or image.name
        data = bytes(image.data)
        start_address = max(0, int(image.start_address))
        page_size = 256
        total_pages = max(1, (len(data) + page_size - 1) // page_size)

        self._emit_progress("flash", "load", 1, 1, f"Loaded {display_name} ({len(data)} byte(s))")
        self._emit(
            EventLog(
                "info",
                f"Starting firmware flash: {display_name} -> motor {self._passthrough_motor} ({esc_family}, {len(data)} byte(s))",
                source="flash",
            )
        )

        init_response = self._send_fourway_logged(
            FOURWAY_CMDS["init_flash"],
            address=start_address,
            params=b"\x00",
            description="flash init",
        )
        self._ensure_fourway_ok(init_response, "flash init")

        for page_index, offset in enumerate(range(0, len(data), page_size), start=1):
            if self._cancel_requested.is_set():
                self._emit(EventOperationCancelled(operation="flash"))
                self._emit(EventLog("info", "Flash cancelled by user", source="flash"))
                return
            absolute_address = start_address + offset
            self._emit_progress("flash", "erase", page_index - 1, total_pages, f"Erasing page {page_index}/{total_pages}")
            erase_response = self._send_fourway_logged(
                FOURWAY_CMDS["page_erase"],
                address=absolute_address,
                params=b"\x01",
                description=f"erase page {page_index}/{total_pages}",
            )
            self._ensure_fourway_ok(erase_response, f"erase page {page_index}")
            self._emit_progress("flash", "erase", page_index, total_pages, f"Erased page {page_index}/{total_pages}")

        for page_index, offset in enumerate(range(0, len(data), page_size), start=1):
            if self._cancel_requested.is_set():
                self._emit(EventOperationCancelled(operation="flash"))
                self._emit(EventLog("info", "Flash cancelled by user", source="flash"))
                return
            chunk = data[offset:offset + page_size]
            absolute_address = start_address + offset
            self._emit_progress("flash", "write", page_index - 1, total_pages, f"Writing block {page_index}/{total_pages}")
            write_response = self._send_fourway_logged(
                FOURWAY_CMDS["write"],
                address=absolute_address,
                params=chunk,
                description=f"write block {page_index}/{total_pages}",
            )
            self._ensure_fourway_ok(write_response, f"write block {page_index}")
            self._emit_progress("flash", "write", page_index, total_pages, f"Wrote block {page_index}/{total_pages}")

        verified = False
        if command.verify_readback:
            for page_index, offset in enumerate(range(0, len(data), page_size), start=1):
                if self._cancel_requested.is_set():
                    self._emit(EventOperationCancelled(operation="flash"))
                    self._emit(EventLog("info", "Flash verify cancelled by user", source="flash"))
                    return
                chunk = data[offset:offset + page_size]
                absolute_address = start_address + offset
                read_len_param = 0 if len(chunk) == 256 else len(chunk)
                self._emit_progress("flash", "verify", page_index - 1, total_pages, f"Verifying block {page_index}/{total_pages}")
                verify_response = self._send_fourway_logged(
                    FOURWAY_CMDS["read"],
                    address=absolute_address,
                    params=bytes([read_len_param & 0xFF]),
                    description=f"verify block {page_index}/{total_pages}",
                )
                self._ensure_fourway_ok(verify_response, f"verify block {page_index}")
                readback = bytes(getattr(verify_response, "params", b""))[: len(chunk)]
                if readback != chunk:
                    raise RuntimeError(
                        f"Flash verification failed at 0x{absolute_address:04X}: expected {len(chunk)} byte(s)"
                    )
                self._emit_progress("flash", "verify", page_index, total_pages, f"Verified block {page_index}/{total_pages}")
            verified = True

        reset_response = self._send_fourway_logged(
            FOURWAY_CMDS["reset"],
            address=0,
            params=b"\x00",
            description="reset after flash",
        )
        self._ensure_fourway_ok(reset_response, "device reset")
        self._emit_progress("flash", "complete", 1, 1, f"Flash complete: {display_name}")
        self._emit(
            EventFirmwareFlashed(
                byte_count=len(data),
                verified=verified,
                display_name=display_name,
                family=esc_family,
                motor_index=self._passthrough_motor,
            )
        )
        self._emit(
            EventLog(
                "info",
                f"Firmware flash complete: {display_name} ({len(data)} byte(s))" + (" (verified)" if verified else ""),
                source="flash",
            )
        )

    def _handle_flash_all_escs(self, command: CommandFlashAllEscs) -> None:
        if not self._require_msp_client():
            return

        motor_count = max(1, int(command.motor_count))
        succeeded: list[int] = []
        failed: list[int] = []

        for motor_index in range(motor_count):
            self._emit(
                EventLog("info", f"Batch flash: starting ESC {motor_index + 1}/{motor_count}", source="flash")
            )
            self._emit_progress(
                "flash_all", "start", motor_index, motor_count,
                f"Flash {motor_index + 1}/{motor_count}: entering passthrough"
            )

            try:
                self._handle_enter_passthrough(CommandEnterPassthrough(motor_index=motor_index))
                if not self._passthrough_active or self._passthrough_motor != motor_index:
                    raise RuntimeError(f"Passthrough did not activate for motor {motor_index}")

                self._handle_read_settings(
                    CommandReadSettings(
                        length=command.settings_read_length,
                        address=command.settings_address,
                        motor_index=motor_index,
                    )
                )

                display_name = command.display_name or command.file_path.rstrip("/").split("/")[-1]
                self._handle_flash_esc(
                    CommandFlashEsc(
                        file_path=command.file_path,
                        family=command.family,
                        display_name=f"{display_name} [ESC {motor_index + 1}]",
                        verify_readback=command.verify_readback,
                    )
                )
                succeeded.append(motor_index)
                self._emit(
                    EventLog("info", f"Batch flash: ESC {motor_index + 1} succeeded", source="flash")
                )

            except Exception as exc:
                failed.append(motor_index)
                message = f"Batch flash: ESC {motor_index + 1} failed: {exc}"
                self._emit(EventError(message=message))
                self._emit(EventLog("error", message, source="flash"))

        summary = f"Batch flash complete: {len(succeeded)}/{motor_count} succeeded"
        if failed:
            summary += f" (failed ESCs: {[m + 1 for m in failed]})"
        self._emit_progress("flash_all", "complete", motor_count, motor_count, summary)
        self._emit(
            EventAllEscsFlashed(
                total_attempted=motor_count,
                total_succeeded=len(succeeded),
                motor_indices=tuple(succeeded),
            )
        )
        self._emit(EventLog("info", summary, source="flash"))

    def _handle_refresh_firmware_catalog(self) -> None:
        snapshot = self._firmware_catalog_client.refresh_catalog()
        self._emit(
            EventFirmwareCatalogLoaded(
                snapshot=snapshot,
                from_cache=bool(getattr(self._firmware_catalog_client, "last_refresh_used_cache", False)),
            )
        )
        total_releases = sum(len(releases) for releases in snapshot.releases_by_source.values())
        self._emit(EventLog("info", f"Firmware catalog refreshed: {total_releases} release entries"))

    def _handle_download_firmware(self, command: CommandDownloadFirmware) -> None:
        if self._last_decoded_settings is None:
            message = "Read settings before downloading firmware so the target layout can be resolved"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return
        if self._last_settings_motor != self._passthrough_motor:
            message = (
                f"Settings are stale for active ESC {self._passthrough_motor}; "
                f"read settings again before downloading firmware"
            )
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return

        release = command.release
        target_family = (self._last_decoded_settings.family or "").strip()
        if target_family and target_family != "Unknown" and release.family != target_family:
            message = f"Firmware family mismatch: target is {target_family}, selected release is {release.family}"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return

        layout_name = self._last_decoded_settings.layout_name
        if not layout_name:
            message = "Target ESC layout is unknown; read settings from a recognized ESC before downloading firmware"
            self._emit(EventError(message=message))
            self._emit(EventLog("warning", message))
            return

        compatibility = describe_release_compatibility(
            release,
            esc_family=target_family,
            layout_name=layout_name,
            pwm_khz=command.pwm_khz,
        )
        if not compatibility.compatible:
            self._emit(EventError(message=compatibility.reason))
            self._emit(EventLog("warning", compatibility.reason))
            return

        self._emit_progress("download", "start", 0, 1, f"Downloading {release.name} for {layout_name}")
        image = self._firmware_catalog_client.download_release_image(
            release,
            layout_name=layout_name,
            pwm_khz=command.pwm_khz,
        )
        self._emit_progress("download", "complete", 1, 1, f"Downloaded {image.name}")
        self._emit(
            EventFirmwareDownloaded(
                file_path=image.path,
                image_name=image.name,
                family=image.family,
                source=image.source,
                byte_count=len(image.data),
            )
        )
        self._emit(
            EventLog(
                "info",
                f"Firmware downloaded: {image.name} ({len(image.data)} byte(s)) -> {image.path}",
                source="firmware",
            )
        )

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                command = self._command_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            if isinstance(command, CommandRefreshPorts):
                self._handle_refresh_ports()
                continue

            if isinstance(command, CommandConnect):
                self._handle_connect(command)
                continue

            if isinstance(command, CommandDisconnect):
                self._disconnect_transport(command.reason)
                continue

            if isinstance(command, CommandEnterPassthrough):
                try:
                    self._handle_enter_passthrough(command)
                except Exception as exc:
                    msg = f"Passthrough entry failed: {exc}"
                    self._emit(EventError(message=msg))
                    self._emit(EventLog("error", msg))
                    if self._is_transport_fatal(exc):
                        self._disconnect_transport(f"Transport lost during passthrough entry: {exc}")
                continue

            if isinstance(command, CommandExitPassthrough):
                try:
                    self._handle_exit_passthrough()
                except Exception as exc:
                    msg = f"Passthrough exit failed: {exc}"
                    self._emit(EventError(message=msg))
                    self._emit(EventLog("error", msg))
                    if self._is_transport_fatal(exc):
                        self._disconnect_transport(f"Transport lost during passthrough exit: {exc}")
                continue

            if isinstance(command, CommandScanEscs):
                try:
                    self._handle_scan_escs(command)
                except Exception as exc:
                    msg = f"ESC scan failed: {exc}"
                    self._emit(EventError(message=msg))
                    self._emit(EventLog("error", msg))
                    if self._is_transport_fatal(exc):
                        self._disconnect_transport(f"Transport lost during ESC scan: {exc}")
                continue

            if isinstance(command, CommandSetMotorSpeed):
                try:
                    self._handle_set_motor_speed(command)
                except Exception as exc:
                    msg = f"DSHOT speed set failed: {exc}"
                    self._emit(EventError(message=msg))
                    self._emit(EventLog("error", msg))
                    if self._is_transport_fatal(exc):
                        self._disconnect_transport(f"Transport lost during motor speed set: {exc}")
                continue

            if isinstance(command, CommandReadFourWayIdentity):
                try:
                    self._handle_read_fourway_identity()
                except Exception as exc:
                    msg = f"4-way identity read failed: {exc}"
                    self._emit(EventError(message=msg))
                    self._emit(EventLog("error", msg))
                    if self._is_transport_fatal(exc):
                        self._disconnect_transport(f"Transport lost during 4-way identity read: {exc}")
                continue

            if isinstance(command, CommandReadSettings):
                try:
                    self._handle_read_settings(command)
                except Exception as exc:
                    msg = f"Settings read failed: {exc}"
                    self._emit(EventError(message=msg))
                    self._emit(EventLog("error", msg))
                    if self._is_transport_fatal(exc):
                        self._disconnect_transport(f"Transport lost during settings read: {exc}")
                continue

            if isinstance(command, CommandRefreshFirmwareCatalog):
                try:
                    self._handle_refresh_firmware_catalog()
                except Exception as exc:
                    self._emit(EventError(message=f"Firmware catalog refresh failed: {exc}"))
                    self._emit(EventLog("error", f"Firmware catalog refresh failed: {exc}"))
                continue

            if isinstance(command, CommandDownloadFirmware):
                try:
                    self._cancel_requested.clear()
                    self._handle_download_firmware(command)
                except Exception as exc:
                    msg = f"Firmware download failed: {exc}"
                    self._emit(EventError(message=msg))
                    self._emit(EventLog("error", msg))
                    if self._is_transport_fatal(exc):
                        self._disconnect_transport(f"Transport lost during firmware download: {exc}")
                continue

            if isinstance(command, CommandFlashEsc):
                try:
                    self._cancel_requested.clear()
                    self._handle_flash_esc(command)
                except Exception as exc:
                    msg = f"Firmware flash failed: {exc}"
                    self._emit(EventError(message=msg))
                    self._emit(EventLog("error", msg))
                    if self._is_transport_fatal(exc):
                        self._disconnect_transport(f"Transport lost during firmware flash: {exc}")
                continue

            if isinstance(command, CommandFlashAllEscs):
                try:
                    self._cancel_requested.clear()
                    self._handle_flash_all_escs(command)
                except Exception as exc:
                    msg = f"Batch firmware flash failed: {exc}"
                    self._emit(EventError(message=msg))
                    self._emit(EventLog("error", msg))
                    if self._is_transport_fatal(exc):
                        self._disconnect_transport(f"Transport lost during batch flash: {exc}")
                continue

            if isinstance(command, CommandCancelOperation):
                self._cancel_requested.set()
                self._emit(EventLog("info", "Cancel requested by user", source="worker"))
                continue

            if isinstance(command, CommandWriteSettings):
                try:
                    self._handle_write_settings(command)
                except Exception as exc:
                    msg = f"Settings write failed: {exc}"
                    self._emit(EventError(message=msg))
                    self._emit(EventLog("error", msg))
                    if self._is_transport_fatal(exc):
                        self._disconnect_transport(f"Transport lost during settings write: {exc}")
                continue

            if isinstance(command, CommandShutdown):
                if self._transport is not None:
                    self._disconnect_transport("Worker shutdown")
                self._emit(EventLog("info", "Worker thread stopping"))
                self._stop_event.set()
                break

            self._emit(EventError(message=f"Unhandled command type: {type(command).__name__}"))
            self._emit(EventLog("warning", f"Unhandled command type: {type(command).__name__}"))
