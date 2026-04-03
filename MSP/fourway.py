"""Pure BLHeli 4-way framing helpers shared by apps, scripts, and tests."""

from __future__ import annotations

from dataclasses import dataclass

FOURWAY_PC_SYNC = 0x2F
FOURWAY_FC_SYNC = 0x2E

FOURWAY_CMDS = {
    "test_alive": 0x30,
    "get_version": 0x31,
    "get_name": 0x32,
    "get_if_version": 0x33,
    "exit": 0x34,
    "reset": 0x35,
    "init_flash": 0x37,
    "erase_all": 0x38,
    "page_erase": 0x39,
    "read": 0x3A,
    "write": 0x3B,
    "read_eeprom": 0x3D,
    "write_eeprom": 0x3E,
    "set_mode": 0x3F,
}

FOURWAY_ACK = {
    0x00: "OK",
    0x01: "UNKNOWN_ERROR",
    0x02: "INVALID_CMD",
    0x03: "INVALID_CRC",
    0x04: "VERIFY_ERROR",
    0x05: "D_INVALID_CMD",
    0x06: "D_CMD_FAILED",
    0x07: "D_UNKNOWN_ERROR",
    0x08: "INVALID_CHANNEL",
    0x09: "INVALID_PARAM",
    0x0F: "GENERAL_ERROR",
}


@dataclass(frozen=True)
class FourWayResponse:
    """Decoded 4-way response frame."""

    command: int
    address: int
    params: bytes
    ack: int
    checksum: int
    crc_ok: bool

    @property
    def ack_str(self) -> str:
        return FOURWAY_ACK.get(self.ack, f"UNKNOWN(0x{self.ack:02X})")


def crc16_xmodem(data: bytes) -> int:
    """Return CRC16 XMODEM for a byte sequence."""
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
        crc &= 0xFFFF
    return crc


def build_fourway_frame(command: int, address: int = 0, params: bytes = b"") -> bytes:
    """Build a full 4-way request frame."""
    if len(params) == 0:
        params = b"\x00"
    if len(params) > 256:
        raise ValueError("4-way params must be <= 256 bytes")

    param_len = len(params) if len(params) < 256 else 0
    body = bytes(
        [
            FOURWAY_PC_SYNC,
            command & 0xFF,
            (address >> 8) & 0xFF,
            address & 0xFF,
            param_len,
        ]
    ) + params
    checksum = crc16_xmodem(body)
    return body + bytes([(checksum >> 8) & 0xFF, checksum & 0xFF])


def parse_fourway_response_frame(frame: bytes) -> FourWayResponse:
    """Parse a complete 4-way response frame and validate its CRC."""
    if len(frame) < 8:
        raise ValueError("frame too short for 4-way response")
    if frame[0] != FOURWAY_FC_SYNC:
        raise ValueError("invalid 4-way response sync")

    command = frame[1]
    address = (frame[2] << 8) | frame[3]
    param_len_field = frame[4]
    param_len = param_len_field if param_len_field != 0 else 256
    expected_len = 5 + param_len + 1 + 2
    if len(frame) != expected_len:
        raise ValueError("4-way response length mismatch")

    params = frame[5:5 + param_len]
    ack = frame[5 + param_len]
    checksum = (frame[-2] << 8) | frame[-1]
    calc = crc16_xmodem(frame[:-2])

    return FourWayResponse(
        command=command,
        address=address,
        params=params,
        ack=ack,
        checksum=checksum,
        crc_ok=checksum == calc,
    )
