"""Reusable serial transport plus MSP and 4-way client helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

import serial
from serial.tools import list_ports

from .fourway import FOURWAY_CMDS, FOURWAY_FC_SYNC, FourWayResponse, build_fourway_frame, parse_fourway_response_frame
from .protocol import MSP_HEADER_IN, MspFrame, build_msp_frame, parse_msp_frame


@dataclass(frozen=True)
class SerialPortDescriptor:
    """Lightweight serial port description for UI and scripts."""

    device: str
    description: str
    hwid: str


@dataclass(frozen=True)
class MspResponse:
    """Result wrapper for MSP responses."""

    frame: MspFrame
    raw_frame: bytes


class SerialTransport:
    """Thin wrapper around pyserial for shared app/script usage."""

    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 0.1):
        self._serial = serial.Serial(port, baudrate, timeout=timeout)
        time.sleep(0.05)

    @property
    def serial(self) -> serial.Serial:
        return self._serial

    def write(self, data: bytes) -> None:
        self._serial.write(data)
        self._serial.flush()

    def read(self, size: int) -> bytes:
        return self._serial.read(size)

    def close(self) -> None:
        self._serial.close()

    def is_open(self) -> bool:
        return self._serial.is_open

class FramedSerialTransport:
    """Wraps a SerialTransport with high-speed 0xA5 Stream Protocol framing."""

    def __init__(self, transport: SerialTransport):
        self._transport = transport
        self._seq = 0
        self._channel = 0x01 # Default to CONTROL
        self._last_raw_packet = b""
        
        # Stress testing / corruption state
        self.inject_crc_error = False
        self.inject_sync_error = False
        self.inject_truncated = False
        self.inject_fuzz = False

    @property
    def transport(self) -> SerialTransport:
        return self._transport

    def set_channel(self, chan: int) -> None:
        self._channel = chan & 0xFF

    def write(self, payload: bytes) -> None:
        """Wrap payload in 0xA5 Stream Frame and write to transport."""
        from .stream_protocol import STREAM_SYNC, STREAM_VERSION
        from .fourway import crc16_xmodem
        
        seq = self._seq
        self._seq = (self._seq + 1) & 0xFFFF
        
        sync = STREAM_SYNC
        version = STREAM_VERSION
        chan = self._channel
        flags = 0x00
        
        if self.inject_sync_error:
            sync = 0xEE # Wrong sync
            self.inject_sync_error = False
            
        payload_len = len(payload)
        header = bytes([
            version,
            flags,
            chan,
            (seq >> 8) & 0xFF,
            seq & 0xFF,
            (payload_len >> 8) & 0xFF,
            payload_len & 0xFF,
        ])
        body = header + payload
        
        if self.inject_fuzz:
            body = bytes([b ^ 0xFF for b in body])
            self.inject_fuzz = False

        crc = crc16_xmodem(body)
        if self.inject_crc_error:
            crc = (crc + 1) & 0xFFFF # Incorrect CRC
            self.inject_crc_error = False
            
        frame = bytes([sync]) + body + bytes([(crc >> 8) & 0xFF, crc & 0xFF])
        
        if self.inject_truncated:
            frame = frame[:len(frame)//2] # Send only half
            self.inject_truncated = False

        self._last_raw_packet = frame
        self._transport.write(frame)

    def read(self, size: int) -> bytes:
        return self._transport.read(size)

    def close(self) -> None:
        self._transport.close()

    def is_open(self) -> bool:
        return self._transport.is_open()


class MSPClient:
    """Reusable MSP request/response client."""

    def __init__(self, transport: SerialTransport):
        self.transport = transport

    def send_msp(
        self,
        command: int,
        payload: bytes = b"",
        *,
        expect_response: bool = True,
        timeout: float = 1.0,
    ) -> Optional[MspResponse]:
        raw_frame = build_msp_frame(command, payload)
        self.transport.write(raw_frame)
        if not expect_response:
            return None
        response_frame = self.read_response(timeout=timeout)
        return MspResponse(frame=response_frame, raw_frame=raw_frame)

    def read_response(self, timeout: float = 1.0) -> MspFrame:
        start = time.time()
        buffer = b""
        while time.time() - start < timeout:
            byte = self.transport.read(1)
            if not byte:
                continue
            buffer += byte
            if buffer.endswith(MSP_HEADER_IN):
                break
            if len(buffer) > 64:
                buffer = buffer[-64:]
        else:
            raise TimeoutError("timeout waiting for MSP response header")

        size_bytes = self.transport.read(1)
        command_bytes = self.transport.read(1)
        if len(size_bytes) != 1 or len(command_bytes) != 1:
            raise TimeoutError("truncated MSP response header")

        size = size_bytes[0]
        payload = self.transport.read(size)
        checksum = self.transport.read(1)
        if len(payload) != size or len(checksum) != 1:
            raise TimeoutError("truncated MSP response payload")

        full_frame = MSP_HEADER_IN + size_bytes + command_bytes + payload + checksum
        return parse_msp_frame(full_frame)


class FourWayClient:
    """Reusable 4-way client built on top of the serial transport."""

    def __init__(self, transport: SerialTransport):
        self.transport = transport

    def send(self, command: int, address: int = 0, params: bytes = b"", timeout: float = 2.0) -> FourWayResponse:
        request = build_fourway_frame(command, address=address, params=params)
        self.transport.write(request)
        return self.read_response(timeout=timeout)

    def read_response(self, timeout: float = 2.0) -> FourWayResponse:
        start = time.time()
        first = b""
        while time.time() - start < timeout:
            byte = self.transport.read(1)
            if not byte:
                continue
            if byte[0] == FOURWAY_FC_SYNC:
                first = byte
                break
        if not first:
            raise TimeoutError("timeout waiting for 4-way response sync")

        header = self.transport.read(4)
        if len(header) != 4:
            raise TimeoutError("truncated 4-way response header")

        param_len_field = header[3]
        param_len = param_len_field if param_len_field != 0 else 256
        params = self.transport.read(param_len)
        ack = self.transport.read(1)
        checksum = self.transport.read(2)
        if len(params) != param_len or len(ack) != 1 or len(checksum) != 2:
            raise TimeoutError("truncated 4-way response payload")

        full_frame = first + header + params + ack + checksum
        return parse_fourway_response_frame(full_frame)

    def test_alive(self) -> FourWayResponse:
        return self.send(FOURWAY_CMDS["test_alive"])

    def get_version(self) -> FourWayResponse:
        return self.send(FOURWAY_CMDS["get_version"])

    def get_name(self) -> FourWayResponse:
        return self.send(FOURWAY_CMDS["get_name"])

    def exit_4way(self) -> FourWayResponse:
        return self.send(FOURWAY_CMDS["exit"])

    def init_flash(self, esc_num: int = 0) -> FourWayResponse:
        return self.send(FOURWAY_CMDS["init_flash"], params=bytes([esc_num & 0x03]), timeout=10.0)

    def read_flash(self, address: int, length: int) -> FourWayResponse:
        return self.send(FOURWAY_CMDS["read"], address=address, params=bytes([length & 0xFF]))


def list_serial_ports() -> list[SerialPortDescriptor]:
    """Enumerate available serial ports for UI and scripts."""
    ports = []
    for port in list_ports.comports():
        ports.append(
            SerialPortDescriptor(
                device=port.device,
                description=port.description or "",
                hwid=port.hwid or "",
            )
        )
    return ports
