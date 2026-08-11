# Copyright (C) 2026 Tim Michals
# SPDX-License-Identifier: GPL-3.0-or-later
"""
AbstractX ASP PCIe-like TLP Protocol & Transport Driver (comm_proto/asp_tlp.py)
--------------------------------------------------------------------------------
Replaces legacy FCSP protocol in python-imgui-esc-configurator.
Operates exclusively over 64-byte fixed-size AbstractX TLPs (asp-tlp-64b)
using SPI / Dual-SPI memory-mapped register BAR accesses.
"""

from __future__ import annotations
import struct
from dataclasses import dataclass
from typing import Optional, Tuple

# -----------------------------------------------------------------------------
# PCIe TLP Header Types & Channels
# -----------------------------------------------------------------------------
TLP_HDR_MEM_RD = 0x00  # Host Memory Read Request
TLP_HDR_MEM_WR = 0x01  # Host Memory Write Request
TLP_HDR_CPLD   = 0x0A  # Completion with Data Response

TLP_CHAN_CTRL            = 0x01  # Wishbone Register Access Channel
TLP_CHAN_TELEMETRY       = 0x02  # Zero-CPU IMU Stream Channel
TLP_CHAN_ESC_PASSTHROUGH = 0x05  # 1-Wire ESC Software UART Channel

# SPI Command Bytes
SPI_CMD_WRITE_BURST = 0xA1  # 0xA1: 64-Byte Write Burst
SPI_CMD_READ_BURST  = 0xA2  # 0xA2: 64-Byte Read Burst
SPI_CMD_READ_STATUS = 0xA0  # 0xA0: Query Status

# -----------------------------------------------------------------------------
# Wishbone BAR Register Addresses (0x40000000..0x40000600)
# -----------------------------------------------------------------------------
REG_SYS_ID_REV    = 0x40000000  # Expects 0xABF10164 (Device: 0xABF1, Rev: 0x01, Arch: 0x64)
REG_SYS_VENDOR_ID = 0x40000004  # Expects 0x19981ACC (Subsys: 0x1998, Vendor: 0x1ACC)
REG_SYS_SCRATCH   = 0x40000008  # R/W Host Loopback Scratchpad (Default: 0xCAFEBABE)
REG_SYS_LED_CTRL  = 0x4000000C  # R/W Onboard LEDs 2..6 (Bits 1..5)
REG_SYS_TIME_LOW  = 0x40000010  # RO Master Timestamp Nanoseconds [31:0]
REG_SYS_TIME_HIGH = 0x40000014  # RO Atomic Shadow Timestamp Nanoseconds [63:32]

REG_MOTOR_CTRL    = 0x40000200  # Motor Protocol (00=DShot600, 01=DShot300, 10=DShot150, 11=PWM)
REG_MOTOR_CH1     = 0x40000204  # Motor Ch 1 Throttle (0..2047 / 1000..2000 us)
REG_MOTOR_CH2     = 0x40000208  # Motor Ch 2 Throttle
REG_MOTOR_CH3     = 0x4000020C  # Motor Ch 3 Throttle
REG_MOTOR_CH4     = 0x40000210  # Motor Ch 4 Throttle

REG_PWM_DEC_CTRL  = 0x40000300  # [31:16]=ID (0x0001), [15:8]=NUM_CH (4), [7:0]=Ready Flags
REG_PWM_DEC_CH1   = 0x40000304  # RC Channel 1 Measured Pulse Width in us
REG_PWM_DEC_CH2   = 0x40000308  # RC Channel 2 Measured Pulse Width in us
REG_PWM_DEC_CH3   = 0x4000030C  # RC Channel 3 Measured Pulse Width in us
REG_PWM_DEC_CH4   = 0x40000310  # RC Channel 4 Measured Pulse Width in us

REG_NEO_CTRL      = 0x40000600  # Bit 0 = Enable, Bits 7..0 = Num LEDs
REG_NEO_LED0      = 0x40000604  # Color 24-bit 0x00RRGGBB

# -----------------------------------------------------------------------------
# TLP Frame Representation
# -----------------------------------------------------------------------------
@dataclass(frozen=True)
class AspTlpPacket:
    pkt_type: int
    channel: int
    addr: int
    payload: bytes

    @property
    def is_valid_device(self) -> bool:
        return self.addr == REG_SYS_ID_REV and len(self.payload) >= 4 and struct.unpack('>I', self.payload[:4])[0] == 0xABF10164


def build_tlp64(pkt_type: int, channel: int, addr: int, data_payload: bytes = b"") -> bytes:
    """Builds a 64-byte fixed size AbstractX TLP packet."""
    header = struct.pack('>BBHI', pkt_type & 0xFF, channel & 0xFF, 0x0000, addr & 0xFFFFFFFF)
    payload = (data_payload or b"").ljust(56, b'\x00')[:56]
    return header + payload


def parse_tlp64(raw_64b: bytes) -> AspTlpPacket:
    """Parses a 64-byte raw TLP vector into an AspTlpPacket."""
    if len(raw_64b) != 64:
        raise ValueError(f"Invalid TLP packet size: {len(raw_64b)} (expected 64 bytes)")
    pkt_type, channel, _, addr = struct.unpack('>BBHI', raw_64b[:8])
    return AspTlpPacket(pkt_type=pkt_type, channel=channel, addr=addr, payload=raw_64b[8:])


# -----------------------------------------------------------------------------
# ASP Transport Driver
# -----------------------------------------------------------------------------
class AspTransportDriver:
    def __init__(self, spidev_path: Optional[str] = None, mock: bool = False, use_dual_spi: bool = False):
        self.mock = mock
        self.use_dual_spi = use_dual_spi
        self.spidev_path = spidev_path or "/dev/spidev0.0"
        self.mock_regs = {
            REG_SYS_ID_REV:    0xABF10164,
            REG_SYS_VENDOR_ID: 0x19981ACC,
            REG_SYS_SCRATCH:   0xCAFEBABE,
            REG_SYS_LED_CTRL:  0x0000003E,
            REG_PWM_DEC_CTRL:  0x0001040F,
            REG_PWM_DEC_CH1:   0x000005DC,  # 1500 us
            REG_PWM_DEC_CH2:   0x000003E8,  # 1000 us
            REG_PWM_DEC_CH3:   0x000007D0,  # 2000 us
            REG_PWM_DEC_CH4:   0x000005DC,  # 1500 us
        }
        self.spi = None

        if not mock:
            try:
                import spidev
                self.spi = spidev.SpiDev()
                bus, dev = map(int, self.spidev_path.replace('/dev/spidev', '').split('.'))
                self.spi.open(bus, dev)
                self.spi.max_speed_hz = 25000000  # 25 MHz
                
                SPI_TX_DUAL = getattr(spidev, 'SPI_TX_DUAL', 0x100)
                SPI_RX_DUAL = getattr(spidev, 'SPI_RX_DUAL', 0x400)
                dt_mode = self.spi.mode
                is_dt_dual = bool(dt_mode & (SPI_TX_DUAL | SPI_RX_DUAL))

                if use_dual_spi or is_dt_dual:
                    try:
                        self.spi.mode = dt_mode | SPI_TX_DUAL | SPI_RX_DUAL
                    except Exception:
                        self.spi.mode = 0
                else:
                    self.spi.mode = 0
            except Exception as e:
                self.mock = True

    def reg_write32(self, addr: int, val_32: int) -> bool:
        if self.mock:
            self.mock_regs[addr] = val_32 & 0xFFFFFFFF
            return True

        tx_tlp = build_tlp64(TLP_HDR_MEM_WR, TLP_CHAN_CTRL, addr, struct.pack('>I', val_32 & 0xFFFFFFFF))
        cmd_frame = [SPI_CMD_WRITE_BURST] + list(tx_tlp)
        self.spi.xfer2(cmd_frame)
        return True

    def reg_read32(self, addr: int) -> int:
        if self.mock:
            return self.mock_regs.get(addr, 0x00000000)

        tx_tlp = build_tlp64(TLP_HDR_MEM_RD, TLP_CHAN_CTRL, addr)
        cmd_frame = [SPI_CMD_READ_BURST] + list(tx_tlp) + [0]*64
        rx = self.spi.xfer2(cmd_frame)
        rx_tlp = bytes(rx[65:129])
        pkt = parse_tlp64(rx_tlp)
        val = struct.unpack('>I', pkt.payload[:4])[0]
        return val

    def get_timestamp_ns(self) -> int:
        low = self.reg_read32(REG_SYS_TIME_LOW)
        high = self.reg_read32(REG_SYS_TIME_HIGH)
        return (high << 32) | low

    def set_motor_throttle(self, ch: int, val: int) -> bool:
        return self.reg_write32(REG_MOTOR_CH1 + ((ch - 1) * 4), val)

    def get_rc_channel_us(self, ch: int) -> int:
        raw = self.reg_read32(REG_PWM_DEC_CH1 + ((ch - 1) * 4))
        return raw & 0xFFFF

    def set_neopixel_rgb(self, r: int, g: int, b: int) -> bool:
        rgb = ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF)
        self.reg_write32(REG_NEO_CTRL, 0x00000101)
        return self.reg_write32(REG_NEO_LED0, rgb)
