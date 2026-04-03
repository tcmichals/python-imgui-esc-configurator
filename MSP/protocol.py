"""Pure MSP v1 framing helpers shared by scripts, apps, and tests."""

from __future__ import annotations

from dataclasses import dataclass

MSP_HEADER_OUT = b"$M<"
MSP_HEADER_IN = b"$M>"
MSP_HEADER_ERR = b"$M!"
_VALID_HEADERS = {MSP_HEADER_OUT, MSP_HEADER_IN, MSP_HEADER_ERR}


@dataclass(frozen=True)
class MspFrame:
    """Decoded MSP v1 frame."""

    header: bytes
    command: int
    payload: bytes
    checksum: int

    @property
    def size(self) -> int:
        return len(self.payload)

    @property
    def is_error(self) -> bool:
        return self.header == MSP_HEADER_ERR

    @property
    def is_response(self) -> bool:
        return self.header == MSP_HEADER_IN

    @property
    def is_request(self) -> bool:
        return self.header == MSP_HEADER_OUT


def calc_checksum(buf: bytes) -> int:
    """Return the MSP v1 XOR checksum."""
    checksum = 0
    for byte in buf:
        checksum ^= byte
    return checksum


def hexdump(data: bytes) -> str:
    """Format bytes as upper-case hex pairs separated by spaces."""
    return " ".join(f"{byte:02X}" for byte in data)


def build_msp_frame(command: int, payload: bytes = b"", header: bytes = MSP_HEADER_OUT) -> bytes:
    """Build a complete MSP v1 frame."""
    if header not in _VALID_HEADERS:
        raise ValueError("invalid MSP header")
    if len(payload) > 255:
        raise ValueError("MSP v1 payload must be <= 255 bytes")

    size = len(payload)
    frame_without_checksum = header + bytes([size, command & 0xFF]) + payload
    checksum = calc_checksum(frame_without_checksum[3:])
    return frame_without_checksum + bytes([checksum])


def parse_msp_frame(frame: bytes) -> MspFrame:
    """Parse a complete MSP v1 frame and validate its checksum."""
    if len(frame) < 6:
        raise ValueError("frame too short for MSP v1")

    header = frame[:3]
    if header not in _VALID_HEADERS:
        raise ValueError("invalid MSP header")

    size = frame[3]
    expected_len = 3 + 1 + 1 + size + 1
    if len(frame) != expected_len:
        raise ValueError("frame length mismatch")

    command = frame[4]
    payload = frame[5:5 + size]
    checksum = frame[-1]
    calculated = calc_checksum(frame[3:-1])
    if checksum != calculated:
        raise ValueError("checksum mismatch")

    return MspFrame(header=header, command=command, payload=payload, checksum=checksum)
