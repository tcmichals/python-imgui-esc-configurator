"""Asyncio 4-way client implementation."""

from __future__ import annotations

import asyncio
from .fourway import (
    FOURWAY_FC_SYNC,
    FourWayResponse,
    build_fourway_frame,
    parse_fourway_response_frame,
)

class AsyncFourWayClient:
    """Asyncio 4-way request/response client."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer

    async def send(
        self,
        command: int,
        address: int = 0,
        params: bytes = b"",
        timeout: float = 2.0,
    ) -> FourWayResponse:
        request = build_fourway_frame(command, address=address, params=params)
        self.writer.write(request)
        await self.writer.drain()
        
        try:
            return await asyncio.wait_for(self.read_response(), timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"timeout waiting for 4-way response to command 0x{command:02X}")

    async def read_response(self) -> FourWayResponse:
        # 1. Sync to header
        while True:
            byte = await self.reader.read(1)
            if not byte:
                raise EOFError("Serial connection closed while waiting for 4-way sync")
            if byte[0] == FOURWAY_FC_SYNC:
                break

        # 2. Read header (command, address_h, address_l, param_len)
        header = await self.reader.readexactly(4)
        param_len_field = header[3]
        param_len = param_len_field if param_len_field != 0 else 256

        # 3. Read params, ack, and checksum
        # params: param_len, ack: 1, checksum: 2
        body_len = param_len + 1 + 2
        body = await self.reader.readexactly(body_len)
        
        full_frame = bytes([FOURWAY_FC_SYNC]) + header + body
        return parse_fourway_response_frame(full_frame)
