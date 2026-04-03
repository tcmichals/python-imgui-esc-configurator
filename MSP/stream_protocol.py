"""Tang9K Stream Protocol framing helpers (v1).

Used for high-speed serial communication with the SERV RISC-V SoC on Tang Nano 20K.
"""

from __future__ import annotations
from dataclasses import dataclass
from .fourway import crc16_xmodem

STREAM_SYNC = 0xA5
STREAM_VERSION = 1

# Channels
STREAM_CHAN_CONTROL = 0x01   # MSP commands
STREAM_CHAN_TELEMETRY = 0x02 # High-rate telemetry
STREAM_CHAN_LOG = 0x03       # FC logs
STREAM_CHAN_DEBUG = 0x04     # Debug traces
STREAM_CHAN_ESC_SERIAL = 0x05 # ESC Passthrough / 4-Way

@dataclass(frozen=True)
class StreamFrame:
    """Decoded Tang9K Stream Protocol frame."""
    version: int
    flags: int
    channel: int
    seq: int
    payload: bytes
    crc: int
    crc_ok: bool

    def to_bytes(self) -> bytes:
        """Serialize the frame to bytes."""
        # Frame = [sync] [version] [flags] [channel] [seq_msb] [seq_lsb] [len_msb] [len_lsb] [payload...] [crc_msb] [crc_lsb]
        payload_len = len(self.payload)
        header = bytes([
            STREAM_VERSION,
            self.flags & 0xFF,
            self.channel & 0xFF,
            (self.seq >> 8) & 0xFF,
            self.seq & 0xFF,
            (payload_len >> 8) & 0xFF,
            payload_len & 0xFF,
        ])
        body = header + self.payload
        crc = crc16_xmodem(body)
        return bytes([STREAM_SYNC]) + body + bytes([(crc >> 8) & 0xFF, crc & 0xFF])

def build_stream_frame(payload: bytes, channel: int, seq: int, version: int = STREAM_VERSION, flags: int = 0) -> bytes:
    """Build a complete framed packet for the Tang9K Stream Protocol."""
    payload_len = len(payload)
    # Body excludes sync byte for CRC
    body = bytes([
        version & 0xFF,
        flags & 0xFF,
        channel & 0xFF,
        (seq >> 8) & 0xFF,
        seq & 0xFF,
        (payload_len >> 8) & 0xFF,
        payload_len & 0xFF,
    ]) + payload
    crc = crc16_xmodem(body)
    return bytes([STREAM_SYNC]) + body + bytes([(crc >> 8) & 0xFF, crc & 0xFF])

def parse_stream_frame(data: bytes) -> StreamFrame:
    """Parse a single framed packet. Expects data to START with the sync byte."""
    if len(data) < 11: # 1 sync + 7 header + 2 crc + min 1 payload (or 0)
        raise ValueError("Frame too short")
    
    if data[0] != STREAM_SYNC:
        raise ValueError(f"Invalid sync byte: 0x{data[0]:02X}")
    
    version = data[1]
    flags = data[2]
    channel = data[3]
    seq = (data[4] << 8) | data[5]
    payload_len = (data[6] << 8) | data[7]
    
    total_expected = 1 + 7 + payload_len + 2
    if len(data) < total_expected:
        raise ValueError(f"Incomplete frame: expected {total_expected}, got {len(data)}")
    
    payload = data[8:8+payload_len]
    packet_crc = (data[8+payload_len] << 8) | data[9+payload_len]
    
    # CRC is over version..payload
    calc_crc = crc16_xmodem(data[1:8+payload_len])
    
    return StreamFrame(
        version=version,
        flags=flags,
        channel=channel,
        seq=seq,
        payload=payload,
        crc=packet_crc,
        crc_ok=(packet_crc == calc_crc)
    )
