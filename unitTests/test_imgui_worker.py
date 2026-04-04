"""Tests for the ImGui app worker/controller foundation."""

from __future__ import annotations

import tempfile
import time
from pathlib import Path

from MSP import FOURWAY_CMDS
from MSP import SerialPortDescriptor
from comm_proto.fcsp import (
    FCSP_CAP_TLV_DSHOT_MOTOR_COUNT,
    FCSP_CAP_TLV_FEATURE_FLAGS,
    FCSP_CAP_TLV_PROFILE_STRING,
    FCSP_CAP_TLV_SUPPORTED_OPS,
    FCSP_CAP_TLV_SUPPORTED_SPACES,
    FCSP_HELLO_TLV_ENDPOINT_NAME,
    FCSP_HELLO_TLV_ENDPOINT_ROLE,
    FCSP_HELLO_TLV_PROTOCOL_STRING,
    FcspChannel,
    FcspControlOp,
    FcspEndpointRole,
    FcspResult,
    FcspTlv,
    build_get_caps_response_payload,
    build_hello_response_payload,
    build_control_payload,
    decode_frame,
    encode_frame as encode_fcsp_frame,
    encode_tlvs,
    parse_control_payload,
)
from comm_proto.tang9k_stream import Tang9kChannel, Tang9kLogEvent, Tang9kLogLevel, Tang9kLogSource, encode_fc_log_event, encode_frame
from imgui_bundle_esc_config import APP_VERSION
from imgui_bundle_esc_config.app_state import create_app_state
from imgui_bundle_esc_config.firmware_catalog import FirmwareCatalogSnapshot, FirmwareImage, FirmwareRelease
from imgui_bundle_esc_config.worker import (
    CommandGetFcspLinkStatus,
    CommandConnect,
    CommandDownloadFirmware,
    CommandDisconnect,
    CommandEnterPassthrough,
    CommandExitPassthrough,
    CommandFlashEsc,
    CommandRefreshFirmwareCatalog,
    CommandReadFourWayIdentity,
    CommandReadSettings,
    CommandSetMotorSpeed,
    CommandWriteSettings,
    CommandRefreshPorts,
    CommandScanEscs,
    EventConnected,
    EventDisconnected,
    EventError,
    EventEscScanResult,
    EventFcspCapabilities,
    EventFcspLinkStatus,
    EventFirmwareCatalogLoaded,
    EventFirmwareDownloaded,
    EventFirmwareFlashed,
    EventFourWayIdentity,
    EventLog,
    EventMotorCount,
    EventPassthroughState,
    EventPortsUpdated,
    EventProgress,
    EventProtocolTrace,
    EventSettingsLoaded,
    EventSettingsWritten,
    WorkerController,
)


MOTOR_PAYLOAD_4 = b"\x00\x00\x00\x00\x00\x00\x00\x00"
MOTOR_PAYLOAD_16 = b"\x00" * 32


class FakeTransport:
    def __init__(self, port: str, baudrate: int, timeout: float) -> None:
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeFcspTransport(FakeTransport):
    def __init__(self, port: str, baudrate: int, timeout: float, *, read_script: bytes) -> None:
        super().__init__(port, baudrate, timeout)
        self._read_buf = bytearray(read_script)
        self.writes: list[bytes] = []

    def write(self, data: bytes) -> None:
        self.writes.append(bytes(data))

    def read(self, size: int) -> bytes:
        if size <= 0 or not self._read_buf:
            return b""
        count = min(size, len(self._read_buf))
        out = bytes(self._read_buf[:count])
        del self._read_buf[:count]
        return out


def make_fcsp_control_response(op: FcspControlOp, *, result: int = int(FcspResult.OK), data: bytes = b"", seq: int = 1) -> bytes:
    return encode_fcsp_frame(
        FcspChannel.CONTROL,
        seq=seq,
        payload=build_control_payload(op, bytes([result & 0xFF]) + bytes(data)),
    )


def make_fcsp_control_frame(op: FcspControlOp, data: bytes, *, seq: int = 1) -> bytes:
    return encode_fcsp_frame(
        FcspChannel.CONTROL,
        seq=seq,
        payload=build_control_payload(op, bytes(data)),
    )


class _FakeFrame:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload


class _FakeMspResponse:
    def __init__(self, payload: bytes) -> None:
        self.frame = _FakeFrame(payload)


class FakeMspClient:
    def __init__(self, responses: list[bytes] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[tuple[int, bytes]] = []

    def send_msp(self, command: int, payload: bytes, **kwargs):
        self.calls.append((command, payload))
        if self.responses:
            return _FakeMspResponse(self.responses.pop(0))
        return _FakeMspResponse(b"\x00")


class _FakeFourWayResponse:
    def __init__(self, params: bytes, *, ack: int = 0) -> None:
        self.command = 0
        self.address = 0
        self.params = params
        self.ack = ack
        self.crc_ok = True


class FakeFourWayClient:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.send_calls: list[tuple[int, int, bytes]] = []
        self._eeprom_memory: dict[int, bytes] = {}
        self._flash_memory: dict[int, bytes] = {}
        self.force_mismatch_readback = False

    def get_version(self):
        self.calls.append("get_version")
        return _FakeFourWayResponse(bytes([108]))

    def get_name(self):
        self.calls.append("get_name")
        return _FakeFourWayResponse(b"Pico4way\x00")

    def send(self, command: int, *args, **kwargs):
        address = int(kwargs.get("address", 0))
        params = bytes(kwargs.get("params", b""))
        self.send_calls.append((command, address, params))
        self.calls.append(f"send:{command}")
        if command == FOURWAY_CMDS["read_eeprom"]:
            request_len = params[0] if params else 0
            if request_len == 0:
                request_len = 256
            if self.force_mismatch_readback:
                return _FakeFourWayResponse(bytes([0xFF] * request_len))
            stored = self._eeprom_memory.get(address)
            if stored is not None:
                return _FakeFourWayResponse(stored[:request_len])
            return _FakeFourWayResponse(bytes(range(request_len)))
        if command == FOURWAY_CMDS["write_eeprom"]:
            self._eeprom_memory[address] = params
            return _FakeFourWayResponse(b"")
        if command == FOURWAY_CMDS["init_flash"]:
            return _FakeFourWayResponse(b"")
        if command == FOURWAY_CMDS["page_erase"]:
            self._flash_memory[address] = b""
            return _FakeFourWayResponse(b"")
        if command == FOURWAY_CMDS["write"]:
            self._flash_memory[address] = params
            return _FakeFourWayResponse(b"")
        if command == FOURWAY_CMDS["read"]:
            request_len = params[0] if params else 0
            if request_len == 0:
                request_len = 256
            stored = self._flash_memory.get(address, b"")
            return _FakeFourWayResponse(stored[:request_len].ljust(request_len, b"\xFF"))
        if command == FOURWAY_CMDS["reset"]:
            return _FakeFourWayResponse(b"")
        return _FakeFourWayResponse(bytes([200, 6]))


def make_settings_payload(*, family: str = "BLHeli_S") -> bytes:
    if family == "Bluejay":
        payload = bytearray([0x00] * 0xFF)
        payload[0x02] = 200
        payload[0x60:0x60 + len(b"Bluejay")] = b"Bluejay"
    else:
        payload = bytearray([0x00] * 0x70)
        payload[0x02] = 32
        payload[0x60:0x60 + len(b"BLHeli_S")] = b"BLHeli_S"
    payload[0x40:0x40 + len(b"TEST_LAYOUT")] = b"TEST_LAYOUT"
    payload[0x50:0x50 + len(b"EFM8BB2")] = b"EFM8BB2"
    return bytes(payload)


class FakeFirmwareCatalogClient:
    def __init__(self, *, last_refresh_used_cache: bool = False) -> None:
        self.last_refresh_used_cache = last_refresh_used_cache

    def refresh_catalog(self) -> FirmwareCatalogSnapshot:
        return FirmwareCatalogSnapshot(
            refreshed_at="2026-03-22T00:00:00+00:00",
            releases_by_source={
                "Bluejay": (
                    FirmwareRelease(
                        source="Bluejay",
                        family="Bluejay",
                        key="v0.21.0",
                        name="0.21.0",
                        download_url_template="https://example.invalid/bluejay/",
                        assets=(("TEST_LAYOUT_48_v0.21.0.hex", "https://example.invalid/TEST_LAYOUT_48_v0.21.0.hex"),),
                    ),
                ),
                "BLHeli_S": (
                    FirmwareRelease(
                        source="BLHeli_S",
                        family="BLHeli_S",
                        key="16.7",
                        name="16.7",
                        download_url_template="https://example.invalid/blheli/",
                    ),
                ),
            },
            layouts_by_source={},
        )

    def download_release_image(self, release: FirmwareRelease, *, layout_name: str, pwm_khz: int | None = None):
        file_name = f"{layout_name}_{release.key}.hex"
        file_path = Path(tempfile.gettempdir()) / file_name
        file_path.write_bytes(b"\x01\x02\x03\x04")
        return FirmwareImage(
            source=release.source,
            family=release.family,
            name=file_name,
            data=b"\x01\x02\x03\x04",
            origin="downloaded",
            start_address=0,
            path=str(file_path),
        )


def wait_for_event(controller: WorkerController, event_type: type, timeout: float = 1.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        for event in controller.poll_events():
            if isinstance(event, event_type):
                return event
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for {event_type.__name__}")


def drain_events(controller: WorkerController, event_type: type, timeout: float = 0.3) -> list:
    """Collect all events of a given type that arrive within timeout."""
    deadline = time.time() + timeout
    collected = []
    while time.time() < deadline:
        for event in controller.poll_events():
            if isinstance(event, event_type):
                collected.append(event)
        time.sleep(0.01)
    return collected

def wait_for_passthrough_state(controller: WorkerController, *, active: bool, timeout: float = 1.0) -> EventPassthroughState:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for event in controller.poll_events():
            if isinstance(event, EventPassthroughState) and event.active is active:
                return event
        time.sleep(0.01)
    raise AssertionError(f"Timed out waiting for EventPassthroughState(active={active})")


def test_worker_refreshes_ports() -> None:
    ports = [
        SerialPortDescriptor(device="/dev/ttyUSB0", description="Bridge A", hwid="usb-a"),
        SerialPortDescriptor(device="/dev/ttyUSB1", description="Bridge B", hwid="usb-b"),
    ]
    controller = WorkerController(port_enumerator=lambda: ports)

    controller.start()
    try:
        controller.enqueue(CommandRefreshPorts())
        event = wait_for_event(controller, EventPortsUpdated)
        assert event.ports == ports
    finally:
        controller.stop()


def test_worker_connects_and_disconnects() -> None:
    created: list[FakeTransport] = []

    def factory(port: str, baudrate: int, timeout: float) -> FakeTransport:
        transport = FakeTransport(port=port, baudrate=baudrate, timeout=timeout)
        created.append(transport)
        return transport

    controller = WorkerController(port_enumerator=lambda: [], transport_factory=factory)

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", baudrate=230400, timeout=0.5))
        connected = wait_for_event(controller, EventConnected)
        assert connected.port == "/dev/ttyUSB0"
        assert connected.baudrate == 230400
        assert created[0].closed is False

        controller.enqueue(CommandDisconnect(reason="User requested disconnect"))
        disconnected = wait_for_event(controller, EventDisconnected)
        assert disconnected.reason == "User requested disconnect"
        assert created[0].closed is True
    finally:
        controller.stop()


def test_worker_connect_uses_optimized_protocol_mode() -> None:
    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))

        connected = wait_for_event(controller, EventConnected)
        assert connected.protocol_mode == "optimized_tang9k"
    finally:
        controller.stop()


def test_worker_connect_accepts_optimized_alias_mode() -> None:
    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized"))
        connected = wait_for_event(controller, EventConnected)
        assert connected.protocol_mode == "optimized_tang9k"
    finally:
        controller.stop()


def test_worker_connect_accepts_tang20k_alias_mode() -> None:
    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang20k"))
        connected = wait_for_event(controller, EventConnected)
        assert connected.protocol_mode == "optimized_tang9k"
    finally:
        controller.stop()


def test_worker_connect_optimized_mode_probes_fcsp_hello_and_caps() -> None:
    hello_response = encode_fcsp_frame(
        FcspChannel.CONTROL,
        seq=100,
        payload=build_control_payload(
            FcspControlOp.HELLO,
            build_hello_response_payload(
                0,
                [
                    FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_ROLE, value=bytes([FcspEndpointRole.OFFLOADER])),
                    FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"offloader"),
                    FcspTlv(tlv_type=FCSP_HELLO_TLV_PROTOCOL_STRING, value=b"FCSP/1"),
                ],
            ),
        ),
    )
    caps_tlvs = encode_tlvs([
        FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x00\x04"),
        FcspTlv(tlv_type=FCSP_CAP_TLV_PROFILE_STRING, value=b"SERV8-50-SPIPROD"),
        FcspTlv(tlv_type=FCSP_CAP_TLV_FEATURE_FLAGS, value=b"\x00\x00\x00\x01"),
    ])
    caps_response = encode_fcsp_frame(
        FcspChannel.CONTROL,
        seq=101,
        payload=build_control_payload(
            FcspControlOp.GET_CAPS,
            build_get_caps_response_payload(
                0,
                [
                    FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x00\x04"),
                    FcspTlv(tlv_type=FCSP_CAP_TLV_PROFILE_STRING, value=b"SERV8-50-SPIPROD"),
                    FcspTlv(tlv_type=FCSP_CAP_TLV_FEATURE_FLAGS, value=b"\x00\x00\x00\x01"),
                ],
            ),
        ),
    )
    scripted_read = hello_response + caps_response

    created: list[FakeFcspTransport] = []

    def factory(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        transport = FakeFcspTransport(port, baudrate, timeout, read_script=scripted_read)
        created.append(transport)
        return transport

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=factory,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        connected = wait_for_event(controller, EventConnected)
        assert connected.protocol_mode == "optimized_tang9k"

        collected_events: list[object] = []
        deadline = time.time() + 1.2
        caps_event = None
        while time.time() < deadline and caps_event is None:
            batch = controller.poll_events(max_events=100)
            if batch:
                collected_events.extend(batch)
                for event in batch:
                    if isinstance(event, EventFcspCapabilities):
                        caps_event = event
                        break
            time.sleep(0.01)

        assert caps_event is not None
        assert caps_event.peer_name == "offloader"
        assert caps_event.esc_count == 4
        assert caps_event.feature_flags == 1
        assert len(caps_event.tlvs) == 3

        logs = [event for event in collected_events if isinstance(event, EventLog)]
        logs.extend(drain_events(controller, EventLog, timeout=0.4))
        assert any("FCSP HELLO ok" in event.message for event in logs)
        assert any("FCSP GET_CAPS ok" in event.message for event in logs)

        assert created
        writes = created[0].writes
        assert len(writes) >= 2

        req1 = decode_frame(writes[0])
        req2 = decode_frame(writes[1])
        op1, _ = parse_control_payload(req1.payload)
        op2, _ = parse_control_payload(req2.payload)
        assert op1 == FcspControlOp.HELLO
        assert op2 == FcspControlOp.GET_CAPS
    finally:
        controller.stop()


def test_worker_connect_optimized_mode_fcsp_probe_failure_keeps_connected() -> None:
    # Invalid response: channel FC_LOG instead of CONTROL -> FCSP probe should warn and continue.
    bad_response = encode_fcsp_frame(
        FcspChannel.FC_LOG,
        seq=7,
        payload=b"log",
    )

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeFcspTransport(p, b, t, read_script=bad_response),
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        connected = wait_for_event(controller, EventConnected)
        assert connected.protocol_mode == "optimized_tang9k"

        logs = drain_events(controller, EventLog, timeout=1.0)
        assert any("FCSP handshake probe failed" in event.message for event in logs)
    finally:
        controller.stop()


def test_worker_optimized_fcsp_enter_passthrough_and_scan_use_native_control() -> None:
    read_script = b"".join(
        [
            make_fcsp_control_frame(
                FcspControlOp.HELLO,
                build_hello_response_payload(
                    FcspResult.OK,
                    [
                        FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC"),
                        FcspTlv(tlv_type=FCSP_HELLO_TLV_PROTOCOL_STRING, value=b"FCSP/1"),
                    ],
                ),
                seq=1,
            ),
            make_fcsp_control_frame(
                FcspControlOp.GET_CAPS,
                build_get_caps_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04")],
                ),
                seq=2,
            ),
            make_fcsp_control_response(FcspControlOp.PT_ENTER, data=b"\x04", seq=3),
            make_fcsp_control_response(FcspControlOp.ESC_SCAN, data=b"\x04", seq=4),
        ]
    )

    created: list[FakeFcspTransport] = []
    msp = FakeMspClient()

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        transport = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(transport)
        return transport

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _transport: msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=2))
        pt = wait_for_passthrough_state(controller, active=True)
        assert pt.active is True
        assert pt.motor_index == 2
        assert pt.esc_count == 4

        controller.enqueue(CommandScanEscs(motor_index=2))
        scan = wait_for_event(controller, EventEscScanResult)
        assert scan.motor_index == 2
        assert scan.esc_count == 4

        assert msp.calls == []
        assert created
        writes = created[0].writes
        assert len(writes) >= 4

        op1, body1 = parse_control_payload(decode_frame(writes[0]).payload)
        op2, body2 = parse_control_payload(decode_frame(writes[1]).payload)
        op3, body3 = parse_control_payload(decode_frame(writes[2]).payload)
        op4, body4 = parse_control_payload(decode_frame(writes[3]).payload)
        assert (op1, op2, op3, op4) == (
            FcspControlOp.HELLO,
            FcspControlOp.GET_CAPS,
            FcspControlOp.PT_ENTER,
            FcspControlOp.ESC_SCAN,
        )
        assert body1
        assert body2 == b""
        assert body3 == bytes([0x02])
        assert body4 == bytes([0x02])
    finally:
        controller.stop()


def test_worker_optimized_fcsp_exit_passthrough_uses_native_control() -> None:
    read_script = b"".join(
        [
            make_fcsp_control_frame(
                FcspControlOp.HELLO,
                build_hello_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
                ),
                seq=1,
            ),
            make_fcsp_control_frame(
                FcspControlOp.GET_CAPS,
                build_get_caps_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04")],
                ),
                seq=2,
            ),
            make_fcsp_control_response(FcspControlOp.PT_ENTER, data=b"\x02", seq=3),
            make_fcsp_control_response(FcspControlOp.PT_EXIT, data=b"", seq=4),
        ]
    )

    created: list[FakeFcspTransport] = []
    msp = FakeMspClient()

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        transport = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(transport)
        return transport

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _transport: msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        entered = wait_for_passthrough_state(controller, active=True)
        assert entered.active is True

        controller.enqueue(CommandExitPassthrough())
        exited = wait_for_passthrough_state(controller, active=False)
        assert exited.active is False
        assert exited.esc_count == 0

        assert msp.calls == []
        assert created
        writes = created[0].writes
        assert len(writes) >= 4
        op4, body4 = parse_control_payload(decode_frame(writes[3]).payload)
        assert op4 == FcspControlOp.PT_EXIT
        assert body4 == b""
    finally:
        controller.stop()


def test_worker_optimized_fcsp_set_motor_speed_uses_native_control() -> None:
    read_script = b"".join(
        [
            make_fcsp_control_frame(
                FcspControlOp.HELLO,
                build_hello_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
                ),
                seq=1,
            ),
            make_fcsp_control_frame(
                FcspControlOp.GET_CAPS,
                build_get_caps_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04")],
                ),
                seq=2,
            ),
            make_fcsp_control_response(FcspControlOp.SET_MOTOR_SPEED, data=b"", seq=3),
        ]
    )

    created: list[FakeFcspTransport] = []
    msp = FakeMspClient()

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        transport = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(transport)
        return transport

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _transport: msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandSetMotorSpeed(motor_index=2, speed=321))
        time.sleep(0.05)

        assert msp.calls == []
        assert created
        writes = created[0].writes
        assert len(writes) >= 3

        op3, body3 = parse_control_payload(decode_frame(writes[2]).payload)
        assert op3 == FcspControlOp.SET_MOTOR_SPEED
        assert body3 == bytes([0x02, 0x01, 0x41])
    finally:
        controller.stop()


def test_worker_optimized_fcsp_get_link_status_uses_native_control() -> None:
    # GET_LINK_STATUS body: flags:u16, rx_drops:u16, crc_err:u16
    read_script = b"".join(
        [
            make_fcsp_control_frame(
                FcspControlOp.HELLO,
                build_hello_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
                ),
                seq=1,
            ),
            make_fcsp_control_frame(
                FcspControlOp.GET_CAPS,
                build_get_caps_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04")],
                ),
                seq=2,
            ),
            make_fcsp_control_response(FcspControlOp.GET_LINK_STATUS, data=b"\x00\x03\x00\x05\x00\x02", seq=3),
        ]
    )

    created: list[FakeFcspTransport] = []
    msp = FakeMspClient()

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        transport = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(transport)
        return transport

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _transport: msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandGetFcspLinkStatus())
        link = wait_for_event(controller, EventFcspLinkStatus)
        assert link.flags == 0x0003
        assert link.rx_drops == 5
        assert link.crc_err == 2

        assert msp.calls == []
        assert created
        writes = created[0].writes
        assert len(writes) >= 3
        op3, body3 = parse_control_payload(decode_frame(writes[2]).payload)
        assert op3 == FcspControlOp.GET_LINK_STATUS
        assert body3 == b""
    finally:
        controller.stop()


def test_worker_optimized_fcsp_set_motor_speed_falls_back_when_op_not_advertised() -> None:
    read_script = b"".join(
        [
            make_fcsp_control_frame(
                FcspControlOp.HELLO,
                build_hello_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
                ),
                seq=1,
            ),
            make_fcsp_control_frame(
                FcspControlOp.GET_CAPS,
                build_get_caps_response_payload(
                    FcspResult.OK,
                    [
                        FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04"),
                        FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_OPS, value=b"\x00"),
                    ],
                ),
                seq=2,
            ),
            make_fcsp_control_response(FcspControlOp.PT_ENTER, data=b"\x02", seq=3),
        ]
    )

    created: list[FakeFcspTransport] = []
    msp = FakeMspClient()

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        transport = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(transport)
        return transport

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _transport: msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandSetMotorSpeed(motor_index=1, speed=250))
        time.sleep(0.08)

        assert msp.calls
        assert msp.calls[-1][0] == 214

        assert created
        writes = created[0].writes
        assert len(writes) >= 2
        ops = [parse_control_payload(decode_frame(raw).payload)[0] for raw in writes]
        assert FcspControlOp.HELLO in ops
        assert FcspControlOp.GET_CAPS in ops
        assert FcspControlOp.SET_MOTOR_SPEED not in ops

        logs = drain_events(controller, EventLog, timeout=0.4)
        assert any("SET_MOTOR_SPEED not advertised" in event.message for event in logs)
    finally:
        controller.stop()


def test_worker_optimized_fcsp_enter_passthrough_falls_back_when_op_not_advertised() -> None:
    read_script = b"".join(
        [
            make_fcsp_control_frame(
                FcspControlOp.HELLO,
                build_hello_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
                ),
                seq=1,
            ),
            make_fcsp_control_frame(
                FcspControlOp.GET_CAPS,
                build_get_caps_response_payload(
                    FcspResult.OK,
                    [
                        FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04"),
                        FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_OPS, value=b"\x00"),
                    ],
                ),
                seq=2,
            ),
        ]
    )

    created: list[FakeFcspTransport] = []
    msp = FakeMspClient(responses=[b"\x03"])

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        transport = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(transport)
        return transport

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _transport: msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=1))
        pt = wait_for_passthrough_state(controller, active=True)
        assert pt.motor_index == 1
        assert pt.esc_count == 3

        passthrough_calls = [(cmd, payload) for cmd, payload in msp.calls if cmd == 245]
        assert passthrough_calls
        assert passthrough_calls[-1][1] == bytes([0x00, 0x01])

        assert created
        writes = created[0].writes
        ops = [parse_control_payload(decode_frame(raw).payload)[0] for raw in writes]
        assert FcspControlOp.HELLO in ops
        assert FcspControlOp.GET_CAPS in ops
        assert FcspControlOp.PT_ENTER not in ops
    finally:
        controller.stop()


def test_worker_optimized_fcsp_get_link_status_warns_when_op_not_advertised() -> None:
    read_script = b"".join(
        [
            make_fcsp_control_frame(
                FcspControlOp.HELLO,
                build_hello_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
                ),
                seq=1,
            ),
            make_fcsp_control_frame(
                FcspControlOp.GET_CAPS,
                build_get_caps_response_payload(
                    FcspResult.OK,
                    [
                        FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04"),
                        FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_OPS, value=b"\x00"),
                    ],
                ),
                seq=2,
            ),
        ]
    )

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeFcspTransport(p, b, t, read_script=read_script),
        msp_client_factory=lambda _transport: FakeMspClient(),
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandGetFcspLinkStatus())
        logs = drain_events(controller, EventLog, timeout=0.8)
        assert any("GET_LINK_STATUS not advertised" in event.message for event in logs)
    finally:
        controller.stop()


def test_worker_get_fcsp_link_status_warns_when_fcsp_inactive() -> None:
    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=lambda _transport: FakeMspClient(),
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="msp"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandGetFcspLinkStatus())
        logs = drain_events(controller, EventLog, timeout=0.6)
        assert any("FCSP link status unavailable" in event.message for event in logs)
    finally:
        controller.stop()


def test_worker_optimized_fcsp_read_settings_uses_read_block() -> None:
    payload = bytes(range(16))
    read_script = b"".join(
        [
            make_fcsp_control_frame(
                FcspControlOp.HELLO,
                build_hello_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
                ),
                seq=1,
            ),
            make_fcsp_control_frame(
                FcspControlOp.GET_CAPS,
                build_get_caps_response_payload(
                    FcspResult.OK,
                    [
                        FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04"),
                        FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_OPS, value=b"\xFF\xFF\xFF"),
                        FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_SPACES, value=b"\xFF"),
                    ],
                ),
                seq=2,
            ),
            make_fcsp_control_response(FcspControlOp.READ_BLOCK, data=b"\x00\x10" + payload, seq=3),
        ]
    )

    created: list[FakeFcspTransport] = []
    msp = FakeMspClient()

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        transport = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(transport)
        return transport

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _transport: msp,
        fourway_client_factory=lambda _transport: FakeFourWayClient(),
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandReadSettings(length=16, address=0x0010, motor_index=2))
        settings = wait_for_event(controller, EventSettingsLoaded)
        assert settings.address == 0x0010
        assert settings.data == payload
        assert settings.motor_index == 2

        assert msp.calls == []
        assert created
        writes = created[0].writes
        assert len(writes) >= 3
        op3, body3 = parse_control_payload(decode_frame(writes[2]).payload)
        assert op3 == FcspControlOp.READ_BLOCK
        assert body3[0] == 0x02  # ESC_EEPROM
        assert body3[1:5] == b"\x00\x00\x00\x10"
        assert body3[5:7] == b"\x00\x10"
    finally:
        controller.stop()


def test_worker_optimized_fcsp_write_settings_uses_write_block_and_verify_read_block() -> None:
    write_payload = bytes([0xAA, 0x55, 0x10, 0x20])
    read_script = b"".join(
        [
            make_fcsp_control_frame(
                FcspControlOp.HELLO,
                build_hello_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
                ),
                seq=1,
            ),
            make_fcsp_control_frame(
                FcspControlOp.GET_CAPS,
                build_get_caps_response_payload(
                    FcspResult.OK,
                    [
                        FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04"),
                        FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_OPS, value=b"\xFF\xFF\xFF"),
                        FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_SPACES, value=b"\xFF"),
                    ],
                ),
                seq=2,
            ),
            make_fcsp_control_response(FcspControlOp.WRITE_BLOCK, data=b"\x00\x04", seq=3),
            make_fcsp_control_response(FcspControlOp.READ_BLOCK, data=b"\x00\x04" + write_payload, seq=4),
        ]
    )

    created: list[FakeFcspTransport] = []
    msp = FakeMspClient()

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        transport = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(transport)
        return transport

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _transport: msp,
        fourway_client_factory=lambda _transport: FakeFourWayClient(),
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandWriteSettings(address=0x0020, data=write_payload, verify_readback=True))
        write_event = wait_for_event(controller, EventSettingsWritten)
        assert write_event.address == 0x0020
        assert write_event.size == len(write_payload)
        assert write_event.verified is True

        assert msp.calls == []
        assert created
        writes = created[0].writes
        assert len(writes) >= 4
        op3, body3 = parse_control_payload(decode_frame(writes[3 - 1]).payload)
        op4, body4 = parse_control_payload(decode_frame(writes[4 - 1]).payload)
        assert op3 == FcspControlOp.WRITE_BLOCK
        assert op4 == FcspControlOp.READ_BLOCK
        assert body3[0] == 0x02  # ESC_EEPROM
        assert body3[1:5] == b"\x00\x00\x00\x20"
        assert body3[5:7] == b"\x00\x04"
        assert body3[7:] == write_payload
        assert body4[0] == 0x02
        assert body4[1:5] == b"\x00\x00\x00\x20"
        assert body4[5:7] == b"\x00\x04"
    finally:
        controller.stop()


def test_worker_optimized_fcsp_read_settings_falls_back_when_space_not_advertised() -> None:
    read_script = b"".join(
        [
            make_fcsp_control_frame(
                FcspControlOp.HELLO,
                build_hello_response_payload(
                    FcspResult.OK,
                    [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
                ),
                seq=1,
            ),
            make_fcsp_control_frame(
                FcspControlOp.GET_CAPS,
                build_get_caps_response_payload(
                    FcspResult.OK,
                    [
                        FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04"),
                        FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_OPS, value=b"\xFF\xFF\xFF"),
                        FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_SPACES, value=b"\x00"),
                    ],
                ),
                seq=2,
            ),
            make_fcsp_control_response(FcspControlOp.PT_ENTER, data=b"\x02", seq=3),
        ]
    )

    created: list[FakeFcspTransport] = []
    msp = FakeMspClient()
    fourway = FakeFourWayClient()

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        transport = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(transport)
        return transport

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _transport: msp,
        fourway_client_factory=lambda _transport: fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandReadSettings(length=8, address=0x0000, motor_index=1))
        settings = wait_for_event(controller, EventSettingsLoaded)
        assert len(settings.data) == 8

        assert msp.calls == []

        assert created
        ops = [parse_control_payload(decode_frame(raw).payload)[0] for raw in created[0].writes]
        assert FcspControlOp.PT_ENTER in ops
        assert FcspControlOp.READ_BLOCK not in ops
        assert any(call[0] == FOURWAY_CMDS["read_eeprom"] for call in fourway.send_calls)
    finally:
        controller.stop()


def test_worker_enter_passthrough_and_scan() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x04", b"\x04"])

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=2))
        pt = wait_for_event(controller, EventPassthroughState)
        assert pt.active is True
        assert pt.motor_index == 2
        assert pt.esc_count == 4

        controller.enqueue(CommandScanEscs(motor_index=2))
        scan = wait_for_event(controller, EventEscScanResult)
        assert scan.motor_index == 2
        assert scan.esc_count == 4

        passthrough_calls = [(cmd, payload) for cmd, payload in msp.calls if cmd == 245]
        assert len(passthrough_calls) >= 2
        assert passthrough_calls[0][1] == bytes([0x00, 0x02])
        assert passthrough_calls[1][1] == bytes([0x00, 0x02])
    finally:
        controller.stop()


def test_worker_exit_passthrough() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02", b"\x00"])

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)

        controller.enqueue(CommandExitPassthrough())
        pt = wait_for_event(controller, EventPassthroughState)
        assert pt.active is False
        assert pt.esc_count == 0

        assert msp.calls[-1][0] == 245
        assert msp.calls[-1][1] == bytes([0x08])
    finally:
        controller.stop()


def test_worker_read_fourway_identity() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)

        controller.enqueue(CommandReadFourWayIdentity())
        identity = wait_for_event(controller, EventFourWayIdentity)
        assert identity.interface_name == "Pico4way"
        assert identity.protocol_version == 108
        assert identity.interface_version == "200.6"

        assert fourway.calls[0] == "get_version"
        assert fourway.calls[1] == "get_name"
        assert fourway.send_calls[0][0] == FOURWAY_CMDS["get_if_version"]
    finally:
        controller.stop()


def test_worker_set_motor_speed_sends_msp_set_motor_payload() -> None:
    msp = FakeMspClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandSetMotorSpeed(motor_index=2, speed=321))
        time.sleep(0.05)

        assert msp.calls
        cmd, payload = msp.calls[-1]
        assert cmd == 214
        assert len(payload) == 8
        # motor index 2 => third motor in payload
        m3 = payload[4] | (payload[5] << 8)
        assert m3 == 321
        assert payload[0:4] == b"\x00\x00\x00\x00"
        assert payload[6:8] == b"\x00\x00"
    finally:
        controller.stop()


def test_worker_set_motor_speed_preserves_other_motor_values() -> None:
    msp = FakeMspClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandSetMotorSpeed(motor_index=0, speed=111))
        time.sleep(0.02)
        controller.enqueue(CommandSetMotorSpeed(motor_index=2, speed=333))
        time.sleep(0.05)

        cmd, payload = msp.calls[-1]
        assert cmd == 214
        m1 = payload[0] | (payload[1] << 8)
        m2 = payload[2] | (payload[3] << 8)
        m3 = payload[4] | (payload[5] << 8)
        m4 = payload[6] | (payload[7] << 8)
        assert (m1, m2, m3, m4) == (111, 0, 333, 0)
    finally:
        controller.stop()


def test_worker_set_motor_speed_resets_after_reconnect() -> None:
    msp = FakeMspClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)
        controller.enqueue(CommandSetMotorSpeed(motor_index=0, speed=500))
        time.sleep(0.02)

        controller.enqueue(CommandDisconnect(reason="reset"))
        _ = wait_for_event(controller, EventDisconnected)

        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)
        controller.enqueue(CommandSetMotorSpeed(motor_index=1, speed=250))
        time.sleep(0.05)

        cmd, payload = msp.calls[-1]
        assert cmd == 214
        m1 = payload[0] | (payload[1] << 8)
        m2 = payload[2] | (payload[3] << 8)
        m3 = payload[4] | (payload[5] << 8)
        m4 = payload[6] | (payload[7] << 8)
        assert (m1, m2, m3, m4) == (0, 250, 0, 0)
    finally:
        controller.stop()


def test_worker_set_motor_speed_blocked_while_passthrough_active() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x01"])

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)

        before = len(msp.calls)
        controller.enqueue(CommandSetMotorSpeed(motor_index=0, speed=250))
        time.sleep(0.05)

        assert len(msp.calls) == before
    finally:
        controller.stop()


def test_worker_set_motor_speed_clamps_high_value() -> None:
    msp = FakeMspClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandSetMotorSpeed(motor_index=1, speed=9999))
        time.sleep(0.05)

        cmd, payload = msp.calls[-1]
        assert cmd == 214
        m2 = payload[2] | (payload[3] << 8)
        assert m2 == 2047
    finally:
        controller.stop()


def test_worker_set_motor_speed_rejects_invalid_motor_index() -> None:
    msp = FakeMspClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        before = len(msp.calls)
        controller.enqueue(CommandSetMotorSpeed(motor_index=9, speed=100))
        err = wait_for_event(controller, EventError)

        assert "Invalid motor index" in err.message
        assert len(msp.calls) == before
    finally:
        controller.stop()


def test_worker_read_settings() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)

        controller.enqueue(CommandReadSettings(length=16, address=0))
        settings = wait_for_event(controller, EventSettingsLoaded)
        assert settings.address == 0
        assert len(settings.data) == 16
        assert settings.data[0] == 0
        assert settings.data[-1] == 15

        cmd, addr, params = fourway.send_calls[-1]
        assert cmd == FOURWAY_CMDS["read_eeprom"]
        assert addr == 0
        assert params == bytes([16])
    finally:
        controller.stop()


def test_worker_read_settings_auto_enters_passthrough_and_bootstraps_identity() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandReadSettings(length=16, address=0, motor_index=1))
        settings = wait_for_event(controller, EventSettingsLoaded)

        assert settings.address == 0
        assert len(settings.data) == 16
        assert any(call == "get_version" for call in fourway.calls)
        assert any(call == "get_name" for call in fourway.calls)
        assert any(call[0] == FOURWAY_CMDS["get_if_version"] for call in fourway.send_calls)
        assert any(call[0] == FOURWAY_CMDS["read_eeprom"] for call in fourway.send_calls)
    finally:
        controller.stop()


def test_worker_esc_stabilization_delay_is_applied_and_logged() -> None:
    """When esc_stabilization_delay_s > 0, a delay is inserted on auto-enter and an info log is emitted."""
    import time as _time_mod
    from imgui_bundle_esc_config.worker import EventLog

    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
        esc_stabilization_delay_s=0.05,  # small but measurable delay for test
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        t0 = _time_mod.perf_counter()
        controller.enqueue(CommandReadSettings(length=16, address=0, motor_index=0))

        # Collect ALL events until we see EventSettingsLoaded
        all_events: list = []
        deadline = _time_mod.time() + 3.0
        settings_ev = None
        while _time_mod.time() < deadline and settings_ev is None:
            for ev in controller.poll_events():
                all_events.append(ev)
                if isinstance(ev, EventSettingsLoaded):
                    settings_ev = ev
            _time_mod.sleep(0.005)

        elapsed = _time_mod.perf_counter() - t0
        assert settings_ev is not None, "EventSettingsLoaded was not emitted"
        # at least the delay was applied (50ms); allow generous margin for CI
        assert elapsed >= 0.04

        # an info log about the stabilization delay must have been emitted
        assert any(
            "stabilization" in getattr(ev, "message", "").lower()
            for ev in all_events
            if isinstance(ev, EventLog)
        ), "Expected stabilization delay log message"
    finally:
        controller.stop()


def test_worker_write_settings_with_readback_verification() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)

        payload = bytes([0xAA, 0x55, 0x10, 0x20])
        controller.enqueue(CommandWriteSettings(address=0x0010, data=payload, verify_readback=True))

        write_event = wait_for_event(controller, EventSettingsWritten)
        assert write_event.address == 0x0010
        assert write_event.size == len(payload)
        assert write_event.verified is True

        write_call = fourway.send_calls[-2]
        assert write_call[0] == FOURWAY_CMDS["write_eeprom"]
        assert write_call[1] == 0x0010
        assert write_call[2] == payload

        read_call = fourway.send_calls[-1]
        assert read_call[0] == FOURWAY_CMDS["read_eeprom"]
        assert read_call[1] == 0x0010
        assert read_call[2] == bytes([len(payload)])
    finally:
        controller.stop()


def test_worker_write_settings_verification_failure_emits_error() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()
    fourway.force_mismatch_readback = True

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)

        controller.enqueue(CommandWriteSettings(address=0x0000, data=bytes([0x01, 0x02]), verify_readback=True))
        err = wait_for_event(controller, EventError)
        assert "verification failed" in err.message.lower()
    finally:
        controller.stop()


def test_worker_flash_local_firmware_runs_erase_write_verify_pipeline() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()
    fourway._eeprom_memory[0] = make_settings_payload(family="BLHeli_S")

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
        handle.write(bytes(range(64)))
        firmware_path = handle.name

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)

        controller.enqueue(CommandReadSettings(length=128, address=0))
        _ = wait_for_event(controller, EventSettingsLoaded)

        controller.enqueue(CommandFlashEsc(file_path=firmware_path, family="BLHeli_S", display_name="test.bin"))
        flashed = wait_for_event(controller, EventFirmwareFlashed)
        assert flashed.byte_count == 64
        assert flashed.verified is True
        assert flashed.display_name == "test.bin"

        progress_events: list[EventProgress] = []
        deadline = time.time() + 1.0
        while time.time() < deadline:
            batch = controller.poll_events(max_events=100)
            for event in batch:
                if isinstance(event, EventProgress):
                    progress_events.append(event)
            if any(event.stage == "complete" for event in progress_events):
                break
            time.sleep(0.01)

        assert any(call[0] == FOURWAY_CMDS["init_flash"] for call in fourway.send_calls)
        assert any(call[0] == FOURWAY_CMDS["page_erase"] for call in fourway.send_calls)
        assert any(call[0] == FOURWAY_CMDS["write"] for call in fourway.send_calls)
        assert any(call[0] == FOURWAY_CMDS["read"] for call in fourway.send_calls)
        assert any(call[0] == FOURWAY_CMDS["reset"] for call in fourway.send_calls)
    finally:
        controller.stop()


def test_worker_flash_rejects_family_mismatch() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()
    fourway._eeprom_memory[0] = make_settings_payload(family="Bluejay")

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
        handle.write(b"\xAA\x55\x01\x02")
        firmware_path = handle.name

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)

        controller.enqueue(CommandReadSettings(length=255, address=0))
        _ = wait_for_event(controller, EventSettingsLoaded)

        controller.enqueue(CommandFlashEsc(file_path=firmware_path, family="BLHeli_S", display_name="wrong.bin"))
        err = wait_for_event(controller, EventError)
        assert "family mismatch" in err.message.lower()
    finally:
        controller.stop()


def test_worker_flash_rejects_stale_settings_after_switching_esc() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02", b"\x02"])
    fourway = FakeFourWayClient()
    fourway._eeprom_memory[0] = make_settings_payload(family="BLHeli_S")

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
        handle.write(b"\x11\x22\x33\x44")
        firmware_path = handle.name

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)
        controller.enqueue(CommandReadSettings(length=128, address=0))
        _ = wait_for_event(controller, EventSettingsLoaded)

        controller.enqueue(CommandEnterPassthrough(motor_index=1))
        _ = wait_for_event(controller, EventPassthroughState)

        controller.enqueue(CommandFlashEsc(file_path=firmware_path, family="BLHeli_S"))
        err = wait_for_event(controller, EventError)
        assert "read settings before flashing" in err.message.lower()
    finally:
        controller.stop()


def test_worker_download_rejects_stale_settings_after_switching_esc() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02", b"\x02"])
    fourway = FakeFourWayClient()
    fourway._eeprom_memory[0] = make_settings_payload(family="Bluejay")
    firmware_client = FakeFirmwareCatalogClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
        firmware_catalog_client=firmware_client,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)
        controller.enqueue(CommandReadSettings(length=255, address=0))
        _ = wait_for_event(controller, EventSettingsLoaded)

        controller.enqueue(CommandEnterPassthrough(motor_index=1))
        _ = wait_for_event(controller, EventPassthroughState)

        release = firmware_client.refresh_catalog().releases_by_source["Bluejay"][0]
        controller.enqueue(CommandDownloadFirmware(release=release, pwm_khz=48))
        err = wait_for_event(controller, EventError)
        assert "read settings before downloading firmware" in err.message.lower()
    finally:
        controller.stop()


def test_worker_refreshes_firmware_catalog() -> None:
    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        firmware_catalog_client=FakeFirmwareCatalogClient(),
    )

    controller.start()
    try:
        controller.enqueue(CommandRefreshFirmwareCatalog())
        event = wait_for_event(controller, EventFirmwareCatalogLoaded)
        assert set(event.snapshot.releases_by_source.keys()) == {"Bluejay", "BLHeli_S"}
        assert event.snapshot.releases_by_source["Bluejay"][0].key == "v0.21.0"
        assert event.snapshot.releases_by_source["BLHeli_S"][0].name == "16.7"
        assert event.from_cache is False
    finally:
        controller.stop()


def test_worker_refreshes_firmware_catalog_marks_cached_origin() -> None:
    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        firmware_catalog_client=FakeFirmwareCatalogClient(last_refresh_used_cache=True),
    )

    controller.start()
    try:
        controller.enqueue(CommandRefreshFirmwareCatalog())
        event = wait_for_event(controller, EventFirmwareCatalogLoaded)
        assert event.from_cache is True
    finally:
        controller.stop()


def test_worker_downloads_selected_firmware_release() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()
    fourway._eeprom_memory[0] = make_settings_payload(family="Bluejay")
    firmware_client = FakeFirmwareCatalogClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
        firmware_catalog_client=firmware_client,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)

        controller.enqueue(CommandReadSettings(length=255, address=0))
        _ = wait_for_event(controller, EventSettingsLoaded)

        release = firmware_client.refresh_catalog().releases_by_source["Bluejay"][0]
        controller.enqueue(CommandDownloadFirmware(release=release, pwm_khz=48))
        downloaded = wait_for_event(controller, EventFirmwareDownloaded)

        assert downloaded.family == "Bluejay"
        assert downloaded.image_name.endswith(".hex")
        assert downloaded.byte_count == 4
        assert downloaded.file_path
    finally:
        controller.stop()


def test_worker_emits_protocol_trace_for_settings_read() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    def make_fourway(_transport: FakeTransport) -> FakeFourWayClient:
        return fourway

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_event(controller, EventPassthroughState)

        controller.enqueue(CommandReadSettings(length=8, address=0x0010))
        collected_events: list[object] = []
        deadline = time.time() + 1.0
        settings_loaded = False
        while time.time() < deadline and not settings_loaded:
            for event in controller.poll_events(max_events=50):
                collected_events.append(event)
                if isinstance(event, EventSettingsLoaded):
                    settings_loaded = True
            time.sleep(0.01)

        assert settings_loaded is True
        traces = [event for event in collected_events if isinstance(event, EventProtocolTrace)]
        assert any(event.channel == "4WAY" and "read settings" in event.message for event in traces)
        assert any(event.channel == "4WAY" and "ack=OK" in event.message for event in traces)
    finally:
        controller.stop()


def test_app_state_records_protocol_trace_entries() -> None:
    state = create_app_state()

    state.apply_event(EventProtocolTrace(channel="MSP", message="TX cmd=245 len=2"))
    state.apply_event(EventProtocolTrace(channel="4WAY", message="RX read_eeprom ack=OK"))

    assert len(state.protocol_traces) == 2
    assert state.protocol_traces[0].channel == "MSP"
    assert "cmd=245" in state.protocol_traces[0].message
    assert state.protocol_traces[1].channel == "4WAY"
    assert "ack=OK" in state.protocol_traces[1].message


def test_app_state_connected_status_is_protocol_agnostic() -> None:
    state = create_app_state()

    state.connection_protocol_mode = "optimized_tang9k"
    state.apply_event(EventConnected(port="/dev/ttyUSB0", baudrate=115200, protocol_mode="msp"))
    assert state.status_text == "Connected to /dev/ttyUSB0 @ 115200"
    assert state.connection_protocol_mode == "optimized_tang9k"

    state.apply_event(EventDisconnected(reason="bye"))
    state.apply_event(EventConnected(port="/dev/ttyUSB0", baudrate=115200, protocol_mode="optimized_tang9k"))
    assert state.status_text == "Connected to /dev/ttyUSB0 @ 115200"


def test_app_state_records_fcsp_capabilities_for_optimized_mode() -> None:
    state = create_app_state()

    state.apply_event(
        EventFcspCapabilities(
            peer_name="offloader",
            esc_count=4,
            feature_flags=1,
            tlvs=(
                FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x00\x04"),
                FcspTlv(tlv_type=FCSP_CAP_TLV_FEATURE_FLAGS, value=b"\x00\x00\x00\x01"),
            ),
        )
    )

    assert state.fcsp_connected_peer == "offloader"
    assert state.fcsp_cap_esc_count == 4
    assert state.fcsp_cap_feature_flags == 1
    assert any("DSHOT motor count: 4" in entry for entry in state.fcsp_cap_descriptions)
    assert any("Feature flags: 0x00000001" in entry for entry in state.fcsp_cap_descriptions)


def test_app_state_decodes_fcsp_supported_op_and_space_flags() -> None:
    state = create_app_state()

    state.apply_event(
        EventFcspCapabilities(
            peer_name="offloader",
            esc_count=4,
            feature_flags=1,
            tlvs=(
                FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_OPS, value=b"\xFF\xFF\xFF"),
                FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_SPACES, value=b"\x3C\x00\x03"),
                FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x00\x04"),
            ),
        )
    )

    assert state.fcsp_supported_ops_bitmap_hex == "FF FF FF"
    assert state.fcsp_supported_spaces_bitmap_hex == "3C 00 03"
    assert state.fcsp_supports_get_link_status is True
    assert state.fcsp_supports_read_block is True
    assert state.fcsp_supports_write_block is True
    assert state.fcsp_supports_esc_eeprom_space is True
    assert state.fcsp_supports_flash_space is True
    assert state.fcsp_supports_pwm_io_space is True
    assert state.fcsp_supports_dshot_io_space is True


def test_app_state_records_fcsp_link_status() -> None:
    state = create_app_state()

    state.apply_event(EventFcspLinkStatus(flags=0x0003, rx_drops=5, crc_err=2))

    assert state.fcsp_link_flags == 0x0003
    assert state.fcsp_link_rx_drops == 5
    assert state.fcsp_link_crc_err == 2
    assert "flags=0x0003" in state.status_text


def test_worker_connect_msp_probe_logs_identity_fields() -> None:
    probe_payloads = [
        bytes([1, 46, 0]),
        b"BTFL",
        bytes([4, 5, 6]),
        b"PICO2BD1",
        b"Mar 22 2026 12:34:56",
        bytes.fromhex("00112233445566778899AABB"),
        bytes([0x10, 0x00, 0x20, 0x00]),
        bytes([0x00, 0x00, 0x00, 0x00]),
        bytes([0x00] * 9),
        bytes([0x10, 0x11] * 18),
        bytes([0x33, 0x44, 0x55, 0x66, 0x77]),
    ]
    msp = FakeMspClient(responses=probe_payloads)

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        msp_probe_on_connect=True,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        collected: list[object] = []
        deadline = time.time() + 1.0
        connected_seen = False
        while time.time() < deadline:
            batch = controller.poll_events(max_events=200)
            if batch:
                collected.extend(batch)
                connected_seen = connected_seen or any(isinstance(event, EventConnected) for event in batch)
                msp_count = sum(
                    1
                    for event in collected
                    if isinstance(event, EventLog) and getattr(event, "source", "") == "msp"
                )
                if connected_seen and msp_count >= 6:
                    break
            time.sleep(0.01)

        events = collected
        msp_logs = [
            event.message
            for event in events
            if isinstance(event, EventLog) and getattr(event, "source", "") == "msp"
        ]

        assert any("MSP API version" in message for message in msp_logs)
        assert any("FC variant" in message for message in msp_logs)
        assert any("FC version" in message for message in msp_logs)
        assert any("Board info" in message for message in msp_logs)
        assert any("Build info" in message for message in msp_logs)
        assert any("UID" in message for message in msp_logs)
        assert any("Status payload" in message for message in msp_logs)
        assert any("Feature config payload" in message for message in msp_logs)
        assert any("Battery state payload" in message for message in msp_logs)
        assert any("RC payload" in message for message in msp_logs)
        assert any("Analog payload" in message for message in msp_logs)
    finally:
        controller.stop()


def test_app_version_constant_exported() -> None:
    assert isinstance(APP_VERSION, str)
    assert APP_VERSION


def test_worker_reports_dynamic_motor_count_from_msp_motor_reply() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_16])

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        events: list[object] = []
        deadline = time.time() + 1.0
        connected_seen = False
        motor_count_seen = False
        while time.time() < deadline and not (connected_seen and motor_count_seen):
            batch = controller.poll_events(max_events=100)
            if batch:
                events.extend(batch)
                connected_seen = connected_seen or any(isinstance(event, EventConnected) for event in batch)
                motor_count_seen = motor_count_seen or any(
                    isinstance(event, EventMotorCount) and event.count == 16 for event in batch
                )
            time.sleep(0.01)

        assert connected_seen is True
        assert any(isinstance(event, EventMotorCount) and event.count == 16 for event in events)

        controller.enqueue(CommandSetMotorSpeed(motor_index=15, speed=777))
        time.sleep(0.05)

        cmd, payload = msp.calls[-1]
        assert cmd == 214
        assert len(payload) == 32
        m16 = payload[30] | (payload[31] << 8)
        assert m16 == 777
    finally:
        controller.stop()


def test_worker_protocol_trace_contains_named_msp_request_reply() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, bytes([1, 46, 0])])

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        msp_probe_on_connect=True,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        traces: list[EventProtocolTrace] = []
        deadline = time.time() + 1.0
        connected_seen = False
        while time.time() < deadline:
            batch = controller.poll_events(max_events=100)
            connected_seen = connected_seen or any(isinstance(event, EventConnected) for event in batch)
            for event in batch:
                if isinstance(event, EventProtocolTrace):
                    traces.append(event)
            if connected_seen and any("MSP -> MSP_API_VERSION(1)" in trace.message for trace in traces) and any(
                "MSP <= MSP_API_VERSION(1)" in trace.message for trace in traces
            ):
                break
            time.sleep(0.01)

        assert any("MSP -> MSP_API_VERSION(1)" in trace.message for trace in traces)
        assert any("MSP <= MSP_API_VERSION(1)" in trace.message for trace in traces)
    finally:
        controller.stop()


def test_worker_emits_esc_transition_timing_log_on_passthrough_entry() -> None:
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x04"])

    def make_msp(_transport: FakeTransport) -> FakeMspClient:
        return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=1))

        collected: list[object] = []
        deadline = time.time() + 1.0
        passthrough_seen = False
        while time.time() < deadline and not passthrough_seen:
            batch = controller.poll_events(max_events=100)
            if batch:
                collected.extend(batch)
                passthrough_seen = any(isinstance(event, EventPassthroughState) for event in batch)
            time.sleep(0.01)

        assert passthrough_seen is True
        esc_logs = [
            event.message
            for event in collected
            if isinstance(event, EventLog) and getattr(event, "source", "") == "esc"
        ]
        assert any("switched to ESC serial" in message for message in esc_logs)
        assert any("ms" in message for message in esc_logs)
    finally:
        controller.stop()


def test_app_state_decodes_tang9k_fc_log_frame_into_trace_and_log() -> None:
    state = create_app_state()
    payload = encode_fc_log_event(
        Tang9kLogEvent(
            level=Tang9kLogLevel.INFO,
            source=Tang9kLogSource.FC,
            uptime_ms=321,
            message="scheduler tick",
        )
    )
    frame = encode_frame(Tang9kChannel.FC_LOG, seq=11, payload=payload)

    ok = state.decode_tang9k_hex_frame(frame.hex(" "))

    assert ok is True
    assert any(entry.channel == "TANG9K" for entry in state.protocol_traces)
    assert any("scheduler tick" in entry.message for entry in state.logs)
    assert "Decoded Tang9K frame" in state.tang9k_decode_last


def test_app_state_tang9k_decode_invalid_hex_reports_warning() -> None:
    state = create_app_state()

    ok = state.decode_tang9k_hex_frame("A5 01 0")

    assert ok is False
    assert "failed" in state.tang9k_decode_last.lower()
    assert any(entry.level == "WARNING" and "Tang9K decode failed" in entry.message for entry in state.logs)


def test_app_state_resizes_dshot_speed_values_with_motor_count() -> None:
    state = create_app_state()
    state.dshot_speed_values = [1000, 1200, 1300, 1400]

    state.apply_event(EventMotorCount(count=8))
    assert state.motor_count == 8
    assert state.dshot_speed_values[:4] == [1000, 1200, 1300, 1400]
    assert state.dshot_speed_values[4:] == [1000, 1000, 1000, 1000]

    state.apply_event(EventMotorCount(count=2))
    assert state.motor_count == 2
    assert state.dshot_speed_values == [1000, 1200]


def test_app_state_motor_count_event_updates_status_and_bounds() -> None:
    state = create_app_state()
    state.selected_motor_index = 9

    state.apply_event(EventMotorCount(count=8))

    assert state.motor_count == 8
    assert state.selected_motor_index == 7
    assert state.status_text == "FC reported motor count: 8"


def test_app_state_tracks_settings_loaded_motor_index() -> None:
    state = create_app_state()
    state.apply_event(EventSettingsLoaded(data=make_settings_payload(family="BLHeli_S"), address=0, motor_index=3))

    assert state.settings_loaded_motor == 3


def test_app_state_filters_releases_to_target_compatible_family_and_layout() -> None:
    state = create_app_state()
    firmware_client = FakeFirmwareCatalogClient()
    snapshot = firmware_client.refresh_catalog()
    bluejay_release = FirmwareRelease(
        source="Bluejay",
        family="Bluejay",
        key="v0.21.0",
        name="0.21.0",
        download_url_template="https://example.invalid/bluejay/",
        assets=(("TEST_LAYOUT_48_v0.21.0.hex", "https://example.invalid/TEST_LAYOUT_48_v0.21.0.hex"),),
    )
    incompatible_bluejay = FirmwareRelease(
        source="Bluejay",
        family="Bluejay",
        key="v0.20.0",
        name="0.20.0",
        download_url_template="https://example.invalid/bluejay/",
        assets=(("OTHER_LAYOUT_48_v0.20.0.hex", "https://example.invalid/OTHER_LAYOUT_48_v0.20.0.hex"),),
    )
    state.apply_event(
        EventFirmwareCatalogLoaded(
            snapshot=FirmwareCatalogSnapshot(
                refreshed_at=snapshot.refreshed_at,
                releases_by_source={
                    "Bluejay": (incompatible_bluejay, bluejay_release),
                    "BLHeli_S": snapshot.releases_by_source["BLHeli_S"],
                },
                layouts_by_source={},
            )
        )
    )

    state.apply_event(EventSettingsLoaded(data=make_settings_payload(family="Bluejay"), address=0))

    assert state.selected_firmware_source == "Bluejay"
    releases = state.visible_firmware_releases()
    assert [release.key for release in releases] == ["v0.21.0"]
    assert state.selected_firmware_release_key == "v0.21.0"


# ---------------------------------------------------------------------------
# Batch flash: CommandFlashAllEscs
# ---------------------------------------------------------------------------

def test_worker_flash_all_escs_flashes_each_motor_in_sequence() -> None:
    msp = FakeMspClient(responses=[
        MOTOR_PAYLOAD_4,   # connect motor count probe
        b"\x02",           # enter passthrough motor 0
        b"\x02",           # enter passthrough motor 1
    ])
    fourway = FakeFourWayClient()
    fourway._eeprom_memory[0] = make_settings_payload(family="BLHeli_S")

    def make_msp(_t): return msp
    def make_fourway(_t): return fourway

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
        handle.write(bytes(range(64)))
        firmware_path = handle.name

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        from imgui_bundle_esc_config.worker import CommandFlashAllEscs, EventAllEscsFlashed
        controller.enqueue(CommandFlashAllEscs(
            file_path=firmware_path,
            family="BLHeli_S",
            motor_count=2,
            display_name="test.bin",
            verify_readback=True,
            settings_read_length=128,
            settings_address=0,
        ))

        result = wait_for_event(controller, EventAllEscsFlashed, timeout=5.0)
        assert result.total_attempted == 2
        assert result.total_succeeded == 2
        assert set(result.motor_indices) == {0, 1}

        # Verify both ESC passthrough switches happened
        pt_calls = [payload for cmd, payload in msp.calls if cmd == 245 and len(payload) == 2 and payload[0] == 0x00]
        assert any(p == bytes([0x00, 0x00]) for p in pt_calls), "Should have entered passthrough for motor 0"
        assert any(p == bytes([0x00, 0x01]) for p in pt_calls), "Should have entered passthrough for motor 1"
    finally:
        controller.stop()


def test_worker_flash_all_escs_partial_failure_reports_succeeded_count() -> None:
    """If one ESC fails, the rest are still attempted and the result reflects partial success."""
    msp = FakeMspClient(responses=[
        MOTOR_PAYLOAD_4,  # connect
        b"\x00",          # passthrough for motor 0 → ESC count = 0 → fails
        b"\x02",          # passthrough for motor 1 → succeeds
    ])
    fourway = FakeFourWayClient()
    fourway._eeprom_memory[0] = make_settings_payload(family="BLHeli_S")

    def make_msp(_t): return msp
    def make_fourway(_t): return fourway

    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as handle:
        handle.write(bytes(range(32)))
        firmware_path = handle.name

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=make_fourway,
    )

    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        from imgui_bundle_esc_config.worker import CommandFlashAllEscs, EventAllEscsFlashed
        controller.enqueue(CommandFlashAllEscs(
            file_path=firmware_path,
            family="BLHeli_S",
            motor_count=2,
            settings_read_length=128,
            settings_address=0,
        ))

        result = wait_for_event(controller, EventAllEscsFlashed, timeout=5.0)
        assert result.total_attempted == 2
        assert result.total_succeeded == 1
        assert 1 in result.motor_indices
    finally:
        controller.stop()


def test_worker_cancel_operation_sets_cancel_flag_and_emits_log() -> None:
    """CommandCancelOperation must set the cancel flag and emit an info log."""
    from imgui_bundle_esc_config.worker import CommandCancelOperation, EventLog

    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4])
    def make_msp(_t): return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=lambda _t: FakeFourWayClient(),
    )
    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandCancelOperation())

        # The cancel produces an info log within a short window
        import time as _t2
        deadline = _t2.time() + 1.0
        log_events = []
        while _t2.time() < deadline:
            for ev in controller.poll_events():
                if isinstance(ev, EventLog):
                    log_events.append(ev)
            _t2.sleep(0.01)

        assert any("cancel" in ev.message.lower() for ev in log_events), \
            f"Expected cancel log, got: {[ev.message for ev in log_events]}"
    finally:
        controller.stop()


def test_worker_transport_fatal_ioerror_auto_disconnects() -> None:
    """An OSError during an MSP command must trigger an automatic EventDisconnected."""
    from imgui_bundle_esc_config.worker import EventDisconnected

    class FakeMspClientRaisesIO(FakeMspClient):
        def send_msp(self, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
            raise OSError("i/o error: device disconnected")

    msp = FakeMspClientRaisesIO(responses=[])

    def make_msp(_t): return msp

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=make_msp,
        fourway_client_factory=lambda _t: FakeFourWayClient(),
    )
    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        # Trigger any command that uses _send_msp_logged
        from imgui_bundle_esc_config.worker import CommandEnterPassthrough
        controller.enqueue(CommandEnterPassthrough(motor_index=0))

        disconnected = wait_for_event(controller, EventDisconnected, timeout=3.0)
        assert disconnected is not None
        assert "transport" in disconnected.reason.lower() or "disconnected" in disconnected.reason.lower()
    finally:
        controller.stop()


def test_worker_is_transport_fatal_recognises_ioerror() -> None:
    """_is_transport_fatal must return True for OSError and False for ValueError."""
    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=lambda _t: FakeMspClient(responses=[]),
        fourway_client_factory=lambda _t: FakeFourWayClient(),
    )
    assert controller._is_transport_fatal(OSError("device disconnected")) is True
    assert controller._is_transport_fatal(OSError("i/o error")) is True
    assert controller._is_transport_fatal(ValueError("bad value")) is False
    assert controller._is_transport_fatal(RuntimeError("timeout")) is False


# ---------------------------------------------------------------------------
# MSP fallback path regression — must pass while FCSP-native paths are added
# ---------------------------------------------------------------------------

def test_worker_msp_mode_read_settings_uses_fourway_never_fcsp() -> None:
    """In plain MSP mode (no FCSP), CommandReadSettings must use the 4-way wire path.
    No FCSP frames should be written to the transport."""
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=lambda _t: msp,
        fourway_client_factory=lambda _t: fourway,
    )
    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))  # default protocol_mode="msp"
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_passthrough_state(controller, active=True)

        controller.enqueue(CommandReadSettings(length=32, address=0))
        settings = wait_for_event(controller, EventSettingsLoaded)

        assert len(settings.data) == 32
        # MSP_SET_PASSTHROUGH = 245 must have been called, not FCSP
        assert any(cmd == 245 for cmd, _ in msp.calls)
        # FourWay read_eeprom must have been called
        fourway_reads = [c for c, _, _ in fourway.send_calls if c == FOURWAY_CMDS["read_eeprom"]]
        assert fourway_reads
    finally:
        controller.stop()


def test_worker_msp_mode_write_settings_uses_fourway_never_fcsp() -> None:
    """In plain MSP mode, CommandWriteSettings must use the 4-way path; FCSP is not used."""
    msp = FakeMspClient(responses=[MOTOR_PAYLOAD_4, b"\x02"])
    fourway = FakeFourWayClient()

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeTransport(p, b, t),
        msp_client_factory=lambda _t: msp,
        fourway_client_factory=lambda _t: fourway,
    )
    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandEnterPassthrough(motor_index=0))
        _ = wait_for_passthrough_state(controller, active=True)

        controller.enqueue(CommandWriteSettings(data=bytes(range(16)), address=0, verify_readback=True))
        written = wait_for_event(controller, EventSettingsWritten)

        assert written.size == 16
        # 4-way write_eeprom must have been called
        fourway_writes = [c for c, _, _ in fourway.send_calls if c == FOURWAY_CMDS["write_eeprom"]]
        assert fourway_writes
    finally:
        controller.stop()


# ---------------------------------------------------------------------------
# Generic FCSP block I/O — READ_BLOCK / WRITE_BLOCK for dynamic spaces
# ---------------------------------------------------------------------------

def _make_fcsp_handshake_script(extra_responses: list[bytes] = ()) -> bytes:
    """Return a scripted read buffer containing a minimal HELLO+GET_CAPS exchange
    followed by any caller-provided response frames.  No SUPPORTED_OPS or
    SUPPORTED_SPACES TLVs are included so all ops/spaces are treated as
    available (bitmap is None → advertised by default).
    """
    hello_frame = make_fcsp_control_frame(
        FcspControlOp.HELLO,
        build_hello_response_payload(
            FcspResult.OK,
            [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
        ),
        seq=1,
    )
    caps_frame = make_fcsp_control_frame(
        FcspControlOp.GET_CAPS,
        build_get_caps_response_payload(
            FcspResult.OK,
            [FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04")],
        ),
        seq=2,
    )
    return b"".join([hello_frame, caps_frame] + list(extra_responses))


def _make_read_block_response(block: bytes, *, seq: int = 3) -> bytes:
    """Build a make_fcsp_control_response-style READ_BLOCK success frame."""
    length_prefix = len(block).to_bytes(2, "big")
    return make_fcsp_control_response(FcspControlOp.READ_BLOCK, data=length_prefix + block, seq=seq)


def _make_write_block_response(byte_count: int, *, seq: int = 3) -> bytes:
    """Build a WRITE_BLOCK success response frame."""
    return make_fcsp_control_response(FcspControlOp.WRITE_BLOCK, data=byte_count.to_bytes(2, "big"), seq=seq)


def test_worker_fcsp_read_block_dshot_io_space_emits_event_block_read() -> None:
    """CommandReadBlock for DSHOT_IO (0x11) emits EventBlockRead with the returned data."""
    from comm_proto.fcsp import FcspAddressSpace
    from imgui_bundle_esc_config.worker import CommandReadBlock, EventBlockRead

    block_payload = bytes([0x01, 0x02, 0x03, 0x04])
    read_script = _make_fcsp_handshake_script([_make_read_block_response(block_payload)])

    created: list[FakeFcspTransport] = []

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        t = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(t)
        return t

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _t: FakeMspClient(),
    )
    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandReadBlock(space=int(FcspAddressSpace.DSHOT_IO), address=0, length=4))
        event = wait_for_event(controller, EventBlockRead)

        assert event.space == int(FcspAddressSpace.DSHOT_IO)
        assert event.address == 0
        assert event.data == block_payload

        # Verify the correct FCSP frame was sent on the wire
        assert created
        ops = [parse_control_payload(decode_frame(raw).payload)[0] for raw in created[0].writes]
        assert FcspControlOp.READ_BLOCK in ops
    finally:
        controller.stop()


def test_worker_fcsp_write_block_pwm_io_space_emits_event_block_written() -> None:
    """CommandWriteBlock for PWM_IO (0x10) emits EventBlockWritten."""
    from comm_proto.fcsp import FcspAddressSpace
    from imgui_bundle_esc_config.worker import CommandWriteBlock, EventBlockWritten

    payload = bytes([0xAA, 0xBB, 0xCC])
    read_script = _make_fcsp_handshake_script([_make_write_block_response(len(payload))])

    created: list[FakeFcspTransport] = []

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        t = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(t)
        return t

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _t: FakeMspClient(),
    )
    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandWriteBlock(space=int(FcspAddressSpace.PWM_IO), data=payload, address=0))
        event = wait_for_event(controller, EventBlockWritten)

        assert event.space == int(FcspAddressSpace.PWM_IO)
        assert event.address == 0
        assert event.size == len(payload)
        assert event.verified is False

        assert created
        ops = [parse_control_payload(decode_frame(raw).payload)[0] for raw in created[0].writes]
        assert FcspControlOp.WRITE_BLOCK in ops
    finally:
        controller.stop()


def test_worker_fcsp_write_block_with_verify_readback_succeeds() -> None:
    """CommandWriteBlock with verify_readback=True performs READ_BLOCK confirm and sets verified=True."""
    from comm_proto.fcsp import FcspAddressSpace
    from imgui_bundle_esc_config.worker import CommandWriteBlock, EventBlockWritten

    payload = bytes([0x11, 0x22, 0x33, 0x44])
    write_resp = _make_write_block_response(len(payload), seq=3)
    read_resp = _make_read_block_response(payload, seq=4)
    read_script = _make_fcsp_handshake_script([write_resp, read_resp])

    created: list[FakeFcspTransport] = []

    def make_transport(port: str, baudrate: int, timeout: float) -> FakeFcspTransport:
        t = FakeFcspTransport(port, baudrate, timeout, read_script=read_script)
        created.append(t)
        return t

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=make_transport,
        msp_client_factory=lambda _t: FakeMspClient(),
    )
    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(
            CommandWriteBlock(space=int(FcspAddressSpace.DSHOT_IO), data=payload, address=0x10, verify_readback=True)
        )
        event = wait_for_event(controller, EventBlockWritten)

        assert event.verified is True
        assert event.size == len(payload)
        assert event.address == 0x10

        assert created
        ops = [parse_control_payload(decode_frame(raw).payload)[0] for raw in created[0].writes]
        assert FcspControlOp.WRITE_BLOCK in ops
        assert ops.count(FcspControlOp.READ_BLOCK) >= 1
    finally:
        controller.stop()


def test_worker_fcsp_read_block_emits_error_when_space_not_advertised() -> None:
    """CommandReadBlock is rejected with EventError when the target space is absent from capabilities."""
    from comm_proto.fcsp import FcspAddressSpace, FCSP_CAP_TLV_SUPPORTED_SPACES
    from imgui_bundle_esc_config.worker import CommandReadBlock

    # Bitmap: 3 bytes all zero — space 0x11 (DSHOT_IO) is NOT set.
    hello_frame = make_fcsp_control_frame(
        FcspControlOp.HELLO,
        build_hello_response_payload(
            FcspResult.OK,
            [FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"Tang9k FC")],
        ),
        seq=1,
    )
    caps_frame = make_fcsp_control_frame(
        FcspControlOp.GET_CAPS,
        build_get_caps_response_payload(
            FcspResult.OK,
            [
                FcspTlv(tlv_type=FCSP_CAP_TLV_DSHOT_MOTOR_COUNT, value=b"\x04"),
                FcspTlv(tlv_type=FCSP_CAP_TLV_SUPPORTED_SPACES, value=b"\x00\x00\x00"),
            ],
        ),
        seq=2,
    )
    read_script = hello_frame + caps_frame

    controller = WorkerController(
        port_enumerator=lambda: [],
        transport_factory=lambda p, b, t: FakeFcspTransport(p, b, t, read_script=read_script),
        msp_client_factory=lambda _t: FakeMspClient(),
    )
    controller.start()
    try:
        controller.enqueue(CommandConnect(port="/dev/ttyUSB0", protocol_mode="optimized_tang9k"))
        _ = wait_for_event(controller, EventConnected)

        controller.enqueue(CommandReadBlock(space=int(FcspAddressSpace.DSHOT_IO), address=0, length=8))
        error = wait_for_event(controller, EventError)

        assert "0x11" in error.message or "not available" in error.message
    finally:
        controller.stop()
