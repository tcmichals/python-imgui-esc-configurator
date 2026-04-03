from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import struct

from MSP.fourway import crc16_xmodem


SYNC_BYTE = 0xA5
PROTOCOL_VERSION = 1
MAX_PAYLOAD_ABSOLUTE = 0xFFFF
HEADER_NO_SYNC_STRUCT = struct.Struct(">BBBHH")
HEADER_SIZE = 1 + HEADER_NO_SYNC_STRUCT.size
CRC_SIZE = 2


class FcspChannel(IntEnum):
    CONTROL = 0x01
    TELEMETRY = 0x02
    FC_LOG = 0x03
    DEBUG_TRACE = 0x04
    ESC_SERIAL = 0x05


class FcspFlag(IntEnum):
    ACK_REQUEST = 0x01
    ACK_RESPONSE = 0x02
    ERROR = 0x04


class FcspControlOp(IntEnum):
    PT_ENTER = 0x01
    PT_EXIT = 0x02
    ESC_SCAN = 0x03
    SET_MOTOR_SPEED = 0x04
    GET_LINK_STATUS = 0x05
    PING = 0x06
    READ_BLOCK = 0x10
    WRITE_BLOCK = 0x11
    GET_CAPS = 0x12
    HELLO = 0x13


class FcspResult(IntEnum):
    OK = 0x00
    INVALID_ARGUMENT = 0x01
    BUSY = 0x02
    NOT_READY = 0x03
    NOT_SUPPORTED = 0x04
    CRC_OR_FRAME_ERROR = 0x05
    INTERNAL_ERROR = 0x06


class FcspEndpointRole(IntEnum):
    OFFLOADER = 0x01
    FLIGHT_CONTROLLER = 0x02
    SIM = 0x03


class FcspAddressSpace(IntEnum):
    FC_REG = 0x01
    ESC_EEPROM = 0x02
    FLASH = 0x03
    TELEMETRY_SNAPSHOT = 0x04
    PWM_IO = 0x10
    DSHOT_IO = 0x11
    LED_IO = 0x12
    NEO_IO = 0x13


@dataclass(frozen=True)
class FcspFrame:
    version: int
    flags: int
    channel: int
    seq: int
    payload: bytes
    crc: int


@dataclass(frozen=True)
class FcspTlv:
    tlv_type: int
    value: bytes


FCSP_HELLO_TLV_ENDPOINT_ROLE = 0x01
FCSP_HELLO_TLV_ENDPOINT_NAME = 0x02
FCSP_HELLO_TLV_PROTOCOL_STRING = 0x03
FCSP_HELLO_TLV_PROFILE_STRING = 0x04
FCSP_HELLO_TLV_INSTANCE_ID = 0x05
FCSP_HELLO_TLV_UPTIME_MS = 0x06

FCSP_CAP_TLV_SUPPORTED_OPS = 0x01
FCSP_CAP_TLV_SUPPORTED_SPACES = 0x02
FCSP_CAP_TLV_MAX_READ_BLOCK_LEN = 0x03
FCSP_CAP_TLV_MAX_WRITE_BLOCK_LEN = 0x04
FCSP_CAP_TLV_PROFILE_STRING = 0x05
FCSP_CAP_TLV_FEATURE_FLAGS = 0x06
FCSP_CAP_TLV_PWM_CHANNEL_COUNT = 0x10
FCSP_CAP_TLV_DSHOT_MOTOR_COUNT = 0x11
FCSP_CAP_TLV_LED_COUNT = 0x12
FCSP_CAP_TLV_NEOPIXEL_COUNT = 0x13
FCSP_CAP_TLV_SUPPORTED_IO_SPACES = 0x14

_U16_STRUCT = struct.Struct(">H")
_U32_STRUCT = struct.Struct(">I")


@dataclass(frozen=True)
class FcspHelloSummary:
    endpoint_role: int | None
    endpoint_name: str
    protocol_string: str
    profile_string: str
    instance_id: int | None
    uptime_ms: int | None
    entries: tuple[FcspTlv, ...]


@dataclass(frozen=True)
class FcspCapabilitySummary:
    supported_ops_bitmap: bytes | None
    supported_spaces_bitmap: bytes | None
    max_read_block_length: int | None
    max_write_block_length: int | None
    profile_string: str
    feature_flags: int | None
    pwm_channel_count: int | None
    dshot_motor_count: int | None
    led_count: int | None
    neopixel_count: int | None
    supported_io_spaces_bitmap: bytes | None
    entries: tuple[FcspTlv, ...]


def encode_frame(channel: int, seq: int, payload: bytes = b"", *, flags: int = 0, version: int = PROTOCOL_VERSION) -> bytes:
    payload = payload or b""
    if len(payload) > MAX_PAYLOAD_ABSOLUTE:
        raise ValueError(f"payload too large: {len(payload)} > {MAX_PAYLOAD_ABSOLUTE}")
    header_no_sync = HEADER_NO_SYNC_STRUCT.pack(
        version & 0xFF,
        flags & 0xFF,
        channel & 0xFF,
        seq & 0xFFFF,
        len(payload) & 0xFFFF,
    )
    crc = crc16_xmodem(header_no_sync + payload)
    return bytes([SYNC_BYTE]) + header_no_sync + payload + crc.to_bytes(2, "big")


def decode_frame(frame: bytes) -> FcspFrame:
    if len(frame) < HEADER_SIZE + CRC_SIZE:
        raise ValueError("frame too short")
    if frame[0] != SYNC_BYTE:
        raise ValueError("invalid sync byte")

    version, flags, channel, seq, payload_len = HEADER_NO_SYNC_STRUCT.unpack(frame[1:HEADER_SIZE])
    expected_len = HEADER_SIZE + payload_len + CRC_SIZE
    if len(frame) != expected_len:
        raise ValueError("frame length mismatch")

    payload = frame[HEADER_SIZE:HEADER_SIZE + payload_len]
    checksum = int.from_bytes(frame[-2:], "big")
    calculated = crc16_xmodem(frame[1:-2])
    if checksum != calculated:
        raise ValueError(f"crc mismatch: recv=0x{checksum:04X} calc=0x{calculated:04X}")

    return FcspFrame(version=version, flags=flags, channel=channel, seq=seq, payload=payload, crc=checksum)


def build_control_payload(op_id: int, data: bytes = b"") -> bytes:
    return bytes([op_id & 0xFF]) + (data or b"")


def parse_control_payload(payload: bytes) -> tuple[int, bytes]:
    if not payload:
        raise ValueError("control payload empty")
    return payload[0], payload[1:]


def _pack_len_prefixed_blob(data: bytes) -> bytes:
    blob = bytes(data)
    if len(blob) > 0xFFFF:
        raise ValueError("blob too large for u16 length prefix")
    return _U16_STRUCT.pack(len(blob)) + blob


def _unpack_len_prefixed_blob(data: bytes) -> tuple[bytes, bytes]:
    if len(data) < 2:
        raise ValueError("missing u16 length prefix")
    blob_len = _U16_STRUCT.unpack(data[:2])[0]
    end = 2 + blob_len
    if len(data) < end:
        raise ValueError("truncated length-prefixed blob")
    return bytes(data[2:end]), bytes(data[end:])


def encode_tlvs(entries: list[FcspTlv]) -> bytes:
    out = bytearray()
    for entry in entries:
        value = bytes(entry.value)
        if len(value) > 255:
            raise ValueError("tlv value too large")
        out.extend((entry.tlv_type & 0xFF, len(value) & 0xFF))
        out.extend(value)
    return bytes(out)


def decode_tlvs(data: bytes) -> list[FcspTlv]:
    pos = 0
    tlvs: list[FcspTlv] = []
    while pos < len(data):
        if pos + 2 > len(data):
            raise ValueError("truncated tlv header")
        tlv_type = data[pos]
        tlv_len = data[pos + 1]
        pos += 2
        if pos + tlv_len > len(data):
            raise ValueError("truncated tlv value")
        tlvs.append(FcspTlv(tlv_type=tlv_type, value=bytes(data[pos:pos + tlv_len])))
        pos += tlv_len
    return tlvs


def summarize_hello_tlvs(entries: list[FcspTlv]) -> FcspHelloSummary:
    endpoint_role: int | None = None
    endpoint_name = ""
    protocol_string = ""
    profile_string = ""
    instance_id: int | None = None
    uptime_ms: int | None = None

    for entry in entries:
        value = bytes(entry.value)
        if entry.tlv_type == FCSP_HELLO_TLV_ENDPOINT_ROLE and value:
            endpoint_role = int(value[0])
        elif entry.tlv_type == FCSP_HELLO_TLV_ENDPOINT_NAME:
            endpoint_name = value.decode("utf-8", errors="replace")
        elif entry.tlv_type == FCSP_HELLO_TLV_PROTOCOL_STRING:
            protocol_string = value.decode("utf-8", errors="replace")
        elif entry.tlv_type == FCSP_HELLO_TLV_PROFILE_STRING:
            profile_string = value.decode("utf-8", errors="replace")
        elif entry.tlv_type == FCSP_HELLO_TLV_INSTANCE_ID and value:
            instance_id = int.from_bytes(value, "big")
        elif entry.tlv_type == FCSP_HELLO_TLV_UPTIME_MS and value:
            uptime_ms = int.from_bytes(value, "big")

    return FcspHelloSummary(
        endpoint_role=endpoint_role,
        endpoint_name=endpoint_name,
        protocol_string=protocol_string,
        profile_string=profile_string,
        instance_id=instance_id,
        uptime_ms=uptime_ms,
        entries=tuple(entries),
    )


def summarize_capability_tlvs(entries: list[FcspTlv]) -> FcspCapabilitySummary:
    supported_ops_bitmap: bytes | None = None
    supported_spaces_bitmap: bytes | None = None
    max_read_block_length: int | None = None
    max_write_block_length: int | None = None
    profile_string = ""
    feature_flags: int | None = None
    pwm_channel_count: int | None = None
    dshot_motor_count: int | None = None
    led_count: int | None = None
    neopixel_count: int | None = None
    supported_io_spaces_bitmap: bytes | None = None
    for entry in entries:
        value = bytes(entry.value)
        if entry.tlv_type == FCSP_CAP_TLV_SUPPORTED_OPS:
            supported_ops_bitmap = value
        elif entry.tlv_type == FCSP_CAP_TLV_SUPPORTED_SPACES:
            supported_spaces_bitmap = value
        elif entry.tlv_type == FCSP_CAP_TLV_MAX_READ_BLOCK_LEN and value:
            max_read_block_length = int.from_bytes(value, "big")
        elif entry.tlv_type == FCSP_CAP_TLV_MAX_WRITE_BLOCK_LEN and value:
            max_write_block_length = int.from_bytes(value, "big")
        elif entry.tlv_type == FCSP_CAP_TLV_PROFILE_STRING:
            profile_string = value.decode("utf-8", errors="replace")
        elif entry.tlv_type == FCSP_CAP_TLV_FEATURE_FLAGS and entry.value:
            feature_flags = int.from_bytes(value, "big")
        elif entry.tlv_type == FCSP_CAP_TLV_PWM_CHANNEL_COUNT and value:
            pwm_channel_count = int.from_bytes(value, "big")
        elif entry.tlv_type == FCSP_CAP_TLV_DSHOT_MOTOR_COUNT and value:
            dshot_motor_count = int.from_bytes(value, "big")
        elif entry.tlv_type == FCSP_CAP_TLV_LED_COUNT and value:
            led_count = int.from_bytes(value, "big")
        elif entry.tlv_type == FCSP_CAP_TLV_NEOPIXEL_COUNT and value:
            neopixel_count = int.from_bytes(value, "big")
        elif entry.tlv_type == FCSP_CAP_TLV_SUPPORTED_IO_SPACES:
            supported_io_spaces_bitmap = value
    return FcspCapabilitySummary(
        supported_ops_bitmap=supported_ops_bitmap,
        supported_spaces_bitmap=supported_spaces_bitmap,
        max_read_block_length=max_read_block_length,
        max_write_block_length=max_write_block_length,
        profile_string=profile_string,
        feature_flags=feature_flags,
        pwm_channel_count=pwm_channel_count,
        dshot_motor_count=dshot_motor_count,
        led_count=led_count,
        neopixel_count=neopixel_count,
        supported_io_spaces_bitmap=supported_io_spaces_bitmap,
        entries=tuple(entries),
    )


def build_hello_payload(entries: list[FcspTlv]) -> bytes:
    return _pack_len_prefixed_blob(encode_tlvs(entries))


def parse_hello_payload(data: bytes) -> list[FcspTlv]:
    tlv_blob, rest = _unpack_len_prefixed_blob(data)
    if rest:
        raise ValueError("unexpected trailing bytes after HELLO payload")
    return decode_tlvs(tlv_blob)


def build_hello_response_payload(result: int, entries: list[FcspTlv]) -> bytes:
    return bytes([result & 0xFF]) + _pack_len_prefixed_blob(encode_tlvs(entries))


def parse_hello_response_payload(data: bytes) -> tuple[int, list[FcspTlv]]:
    if not data:
        raise ValueError("HELLO response payload empty")
    tlv_blob, rest = _unpack_len_prefixed_blob(data[1:])
    if rest:
        raise ValueError("unexpected trailing bytes after HELLO response")
    return int(data[0]), decode_tlvs(tlv_blob)


def build_get_caps_request_payload(page: int | None = None, max_len: int | None = None) -> bytes:
    if page is None and max_len is None:
        return b""
    safe_page = 0 if page is None else int(page)
    safe_max_len = MAX_PAYLOAD_ABSOLUTE if max_len is None else int(max_len)
    if not (0 <= safe_page <= 0xFF):
        raise ValueError("GET_CAPS page must fit in u8")
    if not (0 <= safe_max_len <= 0xFFFF):
        raise ValueError("GET_CAPS max_len must fit in u16")
    return bytes([safe_page & 0xFF]) + _U16_STRUCT.pack(safe_max_len)


def parse_get_caps_request_payload(data: bytes) -> tuple[int, int]:
    if not data:
        return 0, MAX_PAYLOAD_ABSOLUTE
    if len(data) != 3:
        raise ValueError("GET_CAPS request must be empty or page:u8 + max_len:u16")
    return int(data[0]), _U16_STRUCT.unpack(data[1:3])[0]


def build_get_caps_response_payload(result: int, entries: list[FcspTlv], *, page: int | None = None, has_more: bool | None = None) -> bytes:
    tlv_blob = encode_tlvs(entries)
    if page is None and has_more is None:
        return bytes([result & 0xFF]) + _pack_len_prefixed_blob(tlv_blob)
    safe_page = 0 if page is None else int(page)
    safe_has_more = 1 if has_more else 0
    if not (0 <= safe_page <= 0xFF):
        raise ValueError("GET_CAPS response page must fit in u8")
    return bytes([result & 0xFF, safe_page & 0xFF, safe_has_more & 0xFF]) + _pack_len_prefixed_blob(tlv_blob)


def parse_get_caps_response_payload(data: bytes) -> tuple[int, list[FcspTlv], int | None, bool | None]:
    if not data:
        raise ValueError("GET_CAPS response payload empty")
    result = int(data[0])
    body = bytes(data[1:])
    if len(body) >= 4:
        paged_len = _U16_STRUCT.unpack(body[2:4])[0]
        if len(body) == 4 + paged_len:
            return result, decode_tlvs(body[4:]), int(body[0]), bool(body[1])
    tlv_blob, rest = _unpack_len_prefixed_blob(body)
    if rest:
        raise ValueError("unexpected trailing bytes after GET_CAPS response")
    return result, decode_tlvs(tlv_blob), None, None


def build_read_block_payload(space: int, address: int, length: int) -> bytes:
    safe_space = int(space)
    safe_address = int(address)
    safe_length = int(length)
    if not (0 <= safe_space <= 0xFF):
        raise ValueError("READ_BLOCK space must fit in u8")
    if not (0 <= safe_address <= 0xFFFFFFFF):
        raise ValueError("READ_BLOCK address must fit in u32")
    if not (0 <= safe_length <= 0xFFFF):
        raise ValueError("READ_BLOCK length must fit in u16")
    return bytes([safe_space & 0xFF]) + _U32_STRUCT.pack(safe_address) + _U16_STRUCT.pack(safe_length)


def parse_read_block_payload(data: bytes) -> tuple[int, int, int]:
    if len(data) != 7:
        raise ValueError("READ_BLOCK payload must be space:u8 + address:u32 + len:u16")
    return int(data[0]), _U32_STRUCT.unpack(data[1:5])[0], _U16_STRUCT.unpack(data[5:7])[0]


def build_write_block_payload(space: int, address: int, data: bytes) -> bytes:
    payload = bytes(data)
    return build_read_block_payload(space, address, len(payload)) + payload


def parse_write_block_payload(data: bytes) -> tuple[int, int, bytes]:
    if len(data) < 7:
        raise ValueError("WRITE_BLOCK payload too short")
    space, address, length = parse_read_block_payload(data[:7])
    block = bytes(data[7:])
    if len(block) != length:
        raise ValueError("WRITE_BLOCK payload length mismatch")
    return space, address, block


def format_capability_tlv(entry: FcspTlv) -> str:
    label = {
        FCSP_CAP_TLV_SUPPORTED_OPS: "Supported ops bitmap",
        FCSP_CAP_TLV_SUPPORTED_SPACES: "Supported spaces bitmap",
        FCSP_CAP_TLV_MAX_READ_BLOCK_LEN: "Max read block length",
        FCSP_CAP_TLV_MAX_WRITE_BLOCK_LEN: "Max write block length",
        FCSP_CAP_TLV_PROFILE_STRING: "Profile string",
        FCSP_CAP_TLV_FEATURE_FLAGS: "Feature flags",
        FCSP_CAP_TLV_PWM_CHANNEL_COUNT: "PWM channel count",
        FCSP_CAP_TLV_DSHOT_MOTOR_COUNT: "DSHOT motor count",
        FCSP_CAP_TLV_LED_COUNT: "LED count",
        FCSP_CAP_TLV_NEOPIXEL_COUNT: "NeoPixel count",
        FCSP_CAP_TLV_SUPPORTED_IO_SPACES: "Supported IO spaces bitmap",
    }.get(entry.tlv_type, f"TLV 0x{entry.tlv_type:02X}")

    value = bytes(entry.value)
    if not value:
        return f"{label}: <empty>"
    if entry.tlv_type in {
        FCSP_CAP_TLV_MAX_READ_BLOCK_LEN,
        FCSP_CAP_TLV_MAX_WRITE_BLOCK_LEN,
        FCSP_CAP_TLV_PWM_CHANNEL_COUNT,
        FCSP_CAP_TLV_DSHOT_MOTOR_COUNT,
        FCSP_CAP_TLV_LED_COUNT,
        FCSP_CAP_TLV_NEOPIXEL_COUNT,
    }:
        return f"{label}: {int.from_bytes(value, 'big')}"
    if entry.tlv_type == FCSP_CAP_TLV_FEATURE_FLAGS:
        numeric = int.from_bytes(value, "big")
        return f"{label}: 0x{numeric:0{max(2, len(value) * 2)}X}"
    if entry.tlv_type in {FCSP_CAP_TLV_SUPPORTED_OPS, FCSP_CAP_TLV_SUPPORTED_SPACES, FCSP_CAP_TLV_SUPPORTED_IO_SPACES}:
        return f"{label}: {value.hex(' ').upper()}"
    if all(32 <= byte < 127 for byte in value):
        return f"{label}: {value.decode('ascii', errors='replace')}"
    if len(value) <= 4:
        numeric = int.from_bytes(value, "big")
        return f"{label}: 0x{numeric:0{max(2, len(value) * 2)}X} ({numeric})"
    return f"{label}: {value.hex(' ').upper()}"


class FcspStreamParser:
    def __init__(self, *, max_payload: int = MAX_PAYLOAD_ABSOLUTE):
        self._buf = bytearray()
        self._max_payload = max_payload

    def feed(self, data: bytes) -> list[FcspFrame]:
        if data:
            self._buf.extend(data)

        frames: list[FcspFrame] = []
        while True:
            if not self._buf:
                return frames

            sync_index = self._buf.find(SYNC_BYTE)
            if sync_index < 0:
                self._buf.clear()
                return frames
            if sync_index > 0:
                del self._buf[:sync_index]

            if len(self._buf) < HEADER_SIZE + CRC_SIZE:
                return frames

            version, flags, channel, seq, payload_len = HEADER_NO_SYNC_STRUCT.unpack(self._buf[1:HEADER_SIZE])
            _ = (version, flags, channel, seq)
            if payload_len > self._max_payload:
                del self._buf[0]
                continue

            frame_len = HEADER_SIZE + payload_len + CRC_SIZE
            if len(self._buf) < frame_len:
                return frames

            candidate = bytes(self._buf[:frame_len])
            try:
                frame = decode_frame(candidate)
            except ValueError:
                del self._buf[0]
                continue

            frames.append(frame)
            del self._buf[:frame_len]
