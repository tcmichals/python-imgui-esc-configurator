from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import struct

from MSP.fourway import crc16_xmodem


SYNC_BYTE = 0xA5
PROTOCOL_VERSION = 1
MAX_PAYLOAD_RECOMMENDED = 192
MAX_PAYLOAD_ABSOLUTE = 0xFFFF
HEADER_NO_SYNC_STRUCT = struct.Struct(">BBBHH")
HEADER_SIZE = 1 + HEADER_NO_SYNC_STRUCT.size
CRC_SIZE = 2


class Tang9kChannel(IntEnum):
    CONTROL = 0x01
    TELEMETRY = 0x02
    FC_LOG = 0x03
    DEBUG_TRACE = 0x04


class Tang9kLogLevel(IntEnum):
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3


class Tang9kLogSource(IntEnum):
    FC = 0
    ESC = 1
    MSP = 2
    SYSTEM = 3


@dataclass(frozen=True)
class Tang9kFrame:
    version: int
    flags: int
    channel: int
    seq: int
    payload: bytes
    crc: int


@dataclass(frozen=True)
class Tang9kLogEvent:
    level: int
    source: int
    uptime_ms: int
    message: str


def encode_frame(
    channel: int,
    seq: int,
    payload: bytes = b"",
    *,
    flags: int = 0,
    version: int = PROTOCOL_VERSION,
) -> bytes:
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


def decode_frame(frame: bytes) -> Tang9kFrame:
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
        raise ValueError(
            f"crc mismatch: recv=0x{checksum:04X} calc=0x{calculated:04X}"
        )

    return Tang9kFrame(
        version=version,
        flags=flags,
        channel=channel,
        seq=seq,
        payload=payload,
        crc=checksum,
    )


def encode_fc_log_event(event: Tang9kLogEvent) -> bytes:
    message_bytes = event.message.encode("utf-8")
    return struct.pack(">BBI", event.level & 0xFF, event.source & 0xFF, event.uptime_ms & 0xFFFFFFFF) + message_bytes


def decode_fc_log_event(payload: bytes) -> Tang9kLogEvent:
    if len(payload) < 6:
        raise ValueError("fc log payload too short")
    level, source, uptime_ms = struct.unpack(">BBI", payload[:6])
    message = payload[6:].decode("utf-8", errors="replace")
    return Tang9kLogEvent(
        level=level,
        source=source,
        uptime_ms=uptime_ms,
        message=message,
    )


def format_fc_log_event(event: Tang9kLogEvent) -> str:
    try:
        level_name = Tang9kLogLevel(event.level).name
    except ValueError:
        level_name = f"L{event.level}"
    try:
        source_name = Tang9kLogSource(event.source).name
    except ValueError:
        source_name = f"S{event.source}"
    return f"TANG9K {source_name}/{level_name} +{event.uptime_ms}ms {event.message}"


def format_frame_trace(direction: str, frame_bytes: bytes) -> str:
    frame = decode_frame(frame_bytes)
    channel_name = Tang9kChannel(frame.channel).name if frame.channel in Tang9kChannel._value2member_map_ else f"0x{frame.channel:02X}"
    return (
        f"TANG9K {direction} CH={channel_name}(0x{frame.channel:02X}) "
        f"SEQ={frame.seq} LEN={len(frame.payload)} FLAGS=0x{frame.flags:02X}: "
        f"{frame_bytes.hex(' ').upper()}"
    )


class Tang9kStreamParser:
    def __init__(self, *, max_payload: int = MAX_PAYLOAD_RECOMMENDED):
        self._buf = bytearray()
        self._max_payload = max_payload

    def feed(self, data: bytes) -> list[Tang9kFrame]:
        if data:
            self._buf.extend(data)

        frames: list[Tang9kFrame] = []
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
