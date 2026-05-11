"""Asyncio FCSP protocol implementation with multiplexing support."""

from __future__ import annotations

import asyncio
import struct
from typing import Dict, Tuple
from .fcsp import (
    SYNC_BYTE,
    HEADER_SIZE,
    CRC_SIZE,
    HEADER_NO_SYNC_STRUCT,
    FcspFrame,
    decode_frame,
    encode_frame,
)

class AsyncFcspClient:
    """Asyncio FCSP request/response client with built-in multiplexer."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self.reader = reader
        self.writer = writer
        self._seq = 0
        self._pending_responses: Dict[Tuple[int, int], asyncio.Future[FcspFrame]] = {}

    def next_seq(self) -> int:
        seq = self._seq & 0xFFFF
        self._seq = (self._seq + 1) & 0xFFFF
        return seq

    async def send_frame(
        self,
        channel: int,
        payload: bytes = b"",
        *,
        flags: int = 0,
        expect_response: bool = True,
        timeout: float = 1.0,
    ) -> FcspFrame | None:
        seq = self.next_seq()
        frame_bytes = encode_frame(channel, seq, payload, flags=flags)
        
        future = None
        if expect_response:
            future = asyncio.get_running_loop().create_future()
            self._pending_responses[(channel, seq)] = future

        self.writer.write(frame_bytes)
        await self.writer.drain()

        if not expect_response:
            return None

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            # Cleanup on timeout
            self._pending_responses.pop((channel, seq), None)
            raise TimeoutError(f"timeout waiting for FCSP response on channel 0x{channel:02X} seq={seq}")
        finally:
            self._pending_responses.pop((channel, seq), None)

    def dispatch_frame(self, frame: FcspFrame) -> bool:
        """Dispatch a frame to a pending solicitor. Returns True if handled."""
        key = (frame.channel, frame.seq)
        future = self._pending_responses.get(key)
        if future and not future.done():
            future.set_result(frame)
            return True
        return False

    async def read_frame(self) -> FcspFrame:
        """Read a single frame from the transport. 
        Note: In multiplexed mode, this should be called by a single background task.
        """
        # 1. Sync to header
        while True:
            byte = await self.reader.read(1)
            if not byte:
                raise EOFError("Serial connection closed while waiting for FCSP sync")
            if byte[0] == SYNC_BYTE:
                break

        # 2. Read header
        header_no_sync = await self.reader.readexactly(HEADER_SIZE - 1)
        version, flags, channel, seq, payload_len = HEADER_NO_SYNC_STRUCT.unpack(header_no_sync)
        
        # 3. Read payload and CRC
        body_len = payload_len + CRC_SIZE
        body = await self.reader.readexactly(body_len)
        
        full_frame = bytes([SYNC_BYTE]) + header_no_sync + body
        return decode_frame(full_frame)
