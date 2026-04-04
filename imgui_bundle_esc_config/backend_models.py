"""Shared backend command/event models for reusable frontends and tests."""

from __future__ import annotations

from dataclasses import dataclass

from MSP import SerialPortDescriptor
from comm_proto.fcsp import FcspTlv

from .firmware_catalog import FirmwareCatalogSnapshot, FirmwareRelease


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
class CommandGetFcspLinkStatus:
    """Request FCSP GET_LINK_STATUS for optimized-mode diagnostics."""


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
class CommandReadBlock:
    """Request a generic FCSP READ_BLOCK for any address space (no MSP fallback)."""

    space: int
    address: int
    length: int


@dataclass(frozen=True)
class CommandWriteBlock:
    """Request a generic FCSP WRITE_BLOCK for any address space (no MSP fallback)."""

    space: int
    data: bytes
    address: int = 0
    verify_readback: bool = False


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
class EventFcspCapabilities:
    """Decoded FCSP handshake and capability information for optimized mode."""

    peer_name: str
    esc_count: int | None
    feature_flags: int | None
    tlvs: tuple[FcspTlv, ...] = ()


@dataclass(frozen=True)
class EventFcspLinkStatus:
    """Latest FCSP link health counters from GET_LINK_STATUS."""

    flags: int
    rx_drops: int
    crc_err: int


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


@dataclass(frozen=True)
class EventBlockRead:
    """Raw block data returned by a FCSP READ_BLOCK for any address space."""

    space: int
    address: int
    data: bytes


@dataclass(frozen=True)
class EventBlockWritten:
    """Result metadata for a FCSP WRITE_BLOCK for any address space."""

    space: int
    address: int
    size: int
    verified: bool
