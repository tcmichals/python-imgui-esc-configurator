"""Asyncio MSP client implementation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from .protocol import MSP_HEADER_IN, MspFrame, build_msp_frame, parse_msp_frame

@dataclass(frozen=True)
class AsyncMspResponse:
    """Result wrapper for async MSP responses."""

    frame: MspFrame
    raw_frame: bytes

class AsyncMSPClient:
    """Asyncio MSP request/response client."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer

    async def send_msp(
        self,
        command: int,
        payload: bytes = b"",
        *,
        expect_response: bool = True,
        timeout: float = 1.0,
    ) -> Optional[AsyncMspResponse]:
        raw_frame = build_msp_frame(command, payload)
        self.writer.write(raw_frame)
        await self.writer.drain()
        
        if not expect_response:
            return None
            
        try:
            response_frame = await asyncio.wait_for(self.read_response(), timeout=timeout)
            return AsyncMspResponse(frame=response_frame, raw_frame=raw_frame)
        except asyncio.TimeoutError:
            raise TimeoutError(f"timeout waiting for MSP response to command {command}")

    async def read_response(self) -> MspFrame:
        # 1. Sync to header
        buffer = b""
        while True:
            byte = await self.reader.read(1)
            if not byte:
                raise EOFError("Serial connection closed while waiting for MSP header")
            buffer += byte
            if buffer.endswith(MSP_HEADER_IN):
                break
            if len(buffer) > 64:
                buffer = buffer[-64:]

        # 2. Read size and command
        header_remaining = await self.reader.readexactly(2)
        size = header_remaining[0]
        command = header_remaining[1]

        # 3. Read payload and checksum
        body_len = size + 1
        body = await self.reader.readexactly(body_len)
        
        full_frame = MSP_HEADER_IN + header_remaining + body
        return parse_msp_frame(full_frame)
