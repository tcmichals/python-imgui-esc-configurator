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
