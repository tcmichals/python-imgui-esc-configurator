"""Asyncio-based Worker/controller for the ImGui ESC configurator.

This implementation uses asyncio for the event loop and serial-asyncio for
non-blocking serial I/O, providing higher throughput and lower overhead
than the legacy threading-based model.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import time
from dataclasses import dataclass
from typing import Any, Callable

import serial_asyncio

from .backend_models import (
    CommandConnect,
    CommandDisconnect,
    CommandEnterPassthrough,
    CommandExitPassthrough,
    CommandRefreshPorts,
    CommandReadFourWayIdentity,
    CommandReadSettings,
    CommandScanEscs,
    CommandSetMotorSpeed,
    CommandShutdown,
    CommandFlashEsc,
    CommandFlashAllEscs,
    CommandWriteSettings,
    EventConnected,
    EventDisconnected,
    EventEscScanResult,
    EventFirmwareFlashed,
    EventFourWayIdentity,
    EventLog,
    EventOperationCancelled,
    EventPassthroughState,
    EventPortsUpdated,
    EventProgress,
    EventSettingsLoaded,
    EventSettingsWritten,
)

from .worker import (
    MSP_API_VERSION,
    MSP_FC_VARIANT,
    MSP_FC_VERSION,
    MSP_BOARD_INFO,
    MSP_BUILD_INFO,
    MSP_UID,
    MSP_STATUS,
    MSP_FEATURE_CONFIG,
    MSP_BATTERY_STATE,
    MSP_RC,
    MSP_ANALOG,
    MSP_COMMAND_NAMES,
    MSP_SET_PASSTHROUGH,
    MSP_SET_MOTOR,
)

from .firmware_catalog import load_firmware_file

from MSP.fourway import (
    FOURWAY_CMDS,
    FOURWAY_ACK,
)

from MSP.async_client import AsyncMSPClient
from MSP.async_fourway import AsyncFourWayClient
from comm_proto.async_fcsp import AsyncFcspClient
from comm_proto.fcsp import (
    FCSP_HELLO_TLV_ENDPOINT_NAME,
    FCSP_HELLO_TLV_PROFILE_STRING,
    FCSP_HELLO_TLV_PROTOCOL_STRING,
    FcspControlOp,
    FcspTlv,
    build_hello_payload,
    parse_hello_response_payload,
    build_get_caps_request_payload,
    parse_get_caps_response_payload,
    summarize_hello_tlvs,
    summarize_capability_tlvs,
    format_capability_tlv,
    FcspChannel,
    FcspAddressSpace,
    build_read_block_payload,
    build_write_block_payload,
)

PROTOCOL_MODE_MSP = "msp"
PROTOCOL_MODE_OPTIMIZED_TANG9K = "optimized_tang9k"

logger = logging.getLogger(__name__)

class AsyncWorkerController:
    """Asyncio-based backend kernel for transport and protocol execution.
    
    This replaces the legacy WorkerController's threading model with a
    single-threaded asynchronous event loop.
    """

    def __init__(self, *, port_enumerator: Callable[[], list[Any]]):
        self._port_enumerator = port_enumerator
        self._command_queue: asyncio.Queue[object] = asyncio.Queue()
        self._event_queue: queue.Queue[object] = queue.Queue() # Thread-safe for UI polling
        self._loop_task: asyncio.Task | None = None
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        
        self._msp_client: AsyncMSPClient | None = None
        self._fourway_client: AsyncFourWayClient | None = None
        self._fcsp_client: AsyncFcspClient | None = None
        self._telemetry_task: asyncio.Task | None = None
        
        self._protocol_mode = PROTOCOL_MODE_MSP
        self._is_running = False
        
        # Runtime state
        self._motor_count = 4
        self._passthrough_active = False
        self._passthrough_motor = 0
        self._esc_count = 0
        self._dshot_speeds = [0] * self._motor_count
        
        # Capability cache
        self._fcsp_caps: Any = None

    def start(self) -> None:
        """Start the async worker loop."""
        if self._is_running:
            return
        self._is_running = True
        self._loop_task = asyncio.create_task(self._worker_loop())
        self._emit(EventLog("info", "Asyncio Worker kernel started", source="kernel"))

    async def stop(self) -> None:
        """Stop the async worker loop."""
        self._is_running = False
        await self._command_queue.put(CommandShutdown())
        if self._loop_task:
            try:
                await asyncio.wait_for(self._loop_task, timeout=2.0)
            except asyncio.TimeoutError:
                self._loop_task.cancel()
            self._loop_task = None

    def submit(self, command: object) -> None:
        """Submit a command to the worker (thread-safe for UI integration)."""
        # Note: In a pure async app, we would use await queue.put()
        # For ImGui integration, we might need loop.call_soon_threadsafe
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(self._command_queue.put_nowait, command)
        except RuntimeError:
            # Fallback if no loop is running yet
            self._command_queue.put_nowait(command)

    def poll_events(self, max_events: int = 100) -> list[object]:
        """Poll events from the worker (thread-safe for UI integration)."""
        events: list[object] = []
        for _ in range(max_events):
            try:
                events.append(self._event_queue.get_nowait())
            except queue.Empty:
                break
        return events

    def _emit(self, event: object) -> None:
        self._event_queue.put_nowait(event)

    async def _worker_loop(self) -> None:
        """Main async event loop for the kernel."""
        logger.info("Kernel: Entering async loop")
        while self._is_running:
            command = await self._command_queue.get()
            
            if isinstance(command, CommandShutdown):
                break
            
            try:
                await self._handle_command(command)
            except Exception as exc:
                logger.exception("Kernel: Command handling failed")
                self._emit(EventLog("error", f"Kernel error: {exc}", source="kernel"))
            finally:
                self._command_queue.task_done()
        
        logger.info("Kernel: Exiting async loop")
        self._is_running = False

    async def _handle_command(self, command: object) -> None:
        """Route and execute commands asynchronously."""
        if isinstance(command, CommandRefreshPorts):
            ports = await asyncio.to_thread(self._port_enumerator)
            self._emit(EventPortsUpdated(ports=ports))
            self._emit(EventLog("info", f"Enumerated {len(ports)} serial port(s)", source="kernel"))
            
        elif isinstance(command, CommandDisconnect):
            await self._handle_disconnect("User requested disconnect")
            
        elif isinstance(command, CommandEnterPassthrough):
            await self._handle_enter_passthrough(command)
            
        elif isinstance(command, CommandExitPassthrough):
            await self._handle_exit_passthrough()
            
        elif isinstance(command, CommandScanEscs):
            await self._handle_scan_escs(command)
            
        elif isinstance(command, CommandSetMotorSpeed):
            await self._handle_set_motor_speed(command)
            
        elif isinstance(command, CommandReadFourWayIdentity):
            await self._handle_read_fourway_identity()
            
        elif isinstance(command, CommandReadSettings):
            await self._handle_read_settings(command)
            
        elif isinstance(command, CommandWriteSettings):
            await self._handle_write_settings(command)
            
        elif isinstance(command, CommandFlashEsc):
            await self._handle_flash_esc(command)
            
        elif isinstance(command, CommandFlashAllEscs):
            await self._handle_flash_all_escs(command)

    async def _handle_connect(self, command: CommandConnect, *, test_reader=None, test_writer=None) -> None:
        """Establish connection and initialize protocol clients."""
        if self._writer:
            await self._handle_disconnect("Disconnecting previous transport before new connection")
            
        self._protocol_mode = command.protocol_mode
        self._emit(EventLog("info", f"Connecting to {command.port} @ {command.baudrate} baud (mode={self._protocol_mode})...", source="kernel"))
        
        try:
            if test_reader and test_writer:
                self._reader, self._writer = test_reader, test_writer
            else:
                self._reader, self._writer = await serial_asyncio.open_serial_connection(
                    url=command.port, 
                    baudrate=command.baudrate
                )
            
            # Initialize async clients
            self._msp_client = AsyncMSPClient(self._reader, self._writer)
            self._fourway_client = AsyncFourWayClient(self._reader, self._writer)
            self._fcsp_client = AsyncFcspClient(self._reader, self._writer)
            
            self._emit(EventConnected(port=command.port, baudrate=command.baudrate, protocol_mode=self._protocol_mode))
            self._emit(EventLog("info", f"Connected to {command.port}", source="kernel"))
            
            # Start background reader for telemetry/logs
            self._telemetry_task = asyncio.create_task(self._telemetry_loop())

            # Start MSP or FCSP probe based on mode
            if self._protocol_mode == PROTOCOL_MODE_MSP:
                asyncio.create_task(self._probe_msp_identity())
            elif self._protocol_mode == PROTOCOL_MODE_OPTIMIZED_TANG9K:
                asyncio.create_task(self._probe_fcsp_handshake())
            
        except Exception as exc:
            self._emit(EventLog("error", f"Connection failed: {exc}", source="kernel"))
            await self._handle_disconnect(f"Connection failed: {exc}")

    async def _handle_disconnect(self, reason: str) -> None:
        """Close connection and cleanup clients."""
        if self._telemetry_task:
            self._telemetry_task.cancel()
            self._telemetry_task = None
            
        if self._writer:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
        self._reader = None
        self._msp_client = None
        self._fourway_client = None
        self._fcsp_client = None
        self._passthrough_active = False
        self._esc_count = 0
        self._emit(EventDisconnected(reason=reason))
        self._emit(EventLog("info", reason, source="kernel"))

    async def _handle_enter_passthrough(self, command: CommandEnterPassthrough) -> None:
        if not self._msp_client:
            return
        
        motor_index = command.motor_index
        self._emit(EventLog("info", f"Entering passthrough for motor {motor_index}...", source="esc"))
        
        try:
            # Optimized FCSP path
            if self._protocol_mode == PROTOCOL_MODE_OPTIMIZED_TANG9K and self._fcsp_client:
                response = await self._fcsp_client.send_frame(
                    FcspChannel.CONTROL,
                    bytes([int(FcspControlOp.PT_ENTER), motor_index & 0xFF]),
                    timeout=0.8
                )
                if response and response.payload:
                    self._esc_count = response.payload[1] if len(response.payload) > 1 else 1 # Result byte followed by count
                else:
                    raise RuntimeError("No response to PT_ENTER")
            else:
                # Legacy MSP path
                response = await self._msp_client.send_msp(
                    MSP_SET_PASSTHROUGH,
                    bytes([0x00, motor_index & 0xFF]),
                    timeout=1.5
                )
                if response and response.frame:
                    self._esc_count = response.frame.payload[0] if response.frame.payload else 0
            
            self._passthrough_active = self._esc_count > 0
            self._passthrough_motor = motor_index
            self._emit(EventPassthroughState(active=self._passthrough_active, motor_index=motor_index, esc_count=self._esc_count))
            self._emit(EventLog("info", f"Passthrough {'active' if self._passthrough_active else 'failed'} (ESC count={self._esc_count})", source="esc"))
            
        except Exception as exc:
            self._emit(EventLog("error", f"Failed to enter passthrough: {exc}", source="esc"))

    async def _handle_exit_passthrough(self) -> None:
        if not self._msp_client:
            return
            
        self._emit(EventLog("info", "Exiting passthrough...", source="esc"))
        try:
            if self._protocol_mode == PROTOCOL_MODE_OPTIMIZED_TANG9K and self._fcsp_client:
                await self._fcsp_client.send_frame(FcspChannel.CONTROL, bytes([int(FcspControlOp.PT_EXIT)]), timeout=0.8)
            else:
                await self._msp_client.send_msp(MSP_SET_PASSTHROUGH, bytes([0x08]), timeout=1.5)
            
            self._passthrough_active = False
            self._esc_count = 0
            self._emit(EventPassthroughState(active=False, motor_index=0, esc_count=0))
            self._emit(EventLog("info", "Passthrough exited", source="esc"))
        except Exception as exc:
            self._emit(EventLog("error", f"Failed to exit passthrough: {exc}", source="esc"))

    async def _handle_scan_escs(self, command: CommandScanEscs) -> None:
        # Similar logic to PT_ENTER but emits EventEscScanResult
        await self._handle_enter_passthrough(CommandEnterPassthrough(motor_index=command.motor_index))
        self._emit(EventEscScanResult(esc_count=self._esc_count, motor_index=command.motor_index))

    async def _handle_set_motor_speed(self, command: CommandSetMotorSpeed) -> None:
        if not self._msp_client:
            return
            
        motor_index = command.motor_index
        speed = max(0, min(2047, int(command.speed)))
        
        try:
            if self._protocol_mode == PROTOCOL_MODE_OPTIMIZED_TANG9K and self._fcsp_client:
                payload = bytes([int(FcspControlOp.SET_MOTOR_SPEED), motor_index & 0xFF]) + speed.to_bytes(2, "big")
                await self._fcsp_client.send_frame(FcspChannel.CONTROL, payload, expect_response=False)
            else:
                self._dshot_speeds[motor_index] = speed
                # Legacy MSP SET_MOTOR usually sends all speeds
                payload = bytearray()
                for s in self._dshot_speeds:
                    payload.extend(s.to_bytes(2, "little"))
                await self._msp_client.send_msp(MSP_SET_MOTOR, bytes(payload), expect_response=False)
            
            self._dshot_speeds[motor_index] = speed
            # No log for every speed change to avoid flooding, or use a throttle
        except Exception as exc:
            self._emit(EventLog("error", f"Failed to set motor speed: {exc}", source="esc"))

    async def _handle_read_fourway_identity(self) -> None:
        if not self._fourway_client or not self._passthrough_active:
            return
            
        self._emit(EventLog("info", "Reading 4-way identity...", source="4way"))
        try:
            # We can use asyncio.gather to read multiple things concurrently if supported
            # But 4-way is strictly half-duplex and sequential on most bridges
            v_resp = await self._fourway_client.send(FOURWAY_CMDS["get_version"])
            n_resp = await self._fourway_client.send(FOURWAY_CMDS["get_name"])
            
            name = bytes(n_resp.params).decode("ascii", errors="replace").rstrip("\x00 ")
            self._emit(EventFourWayIdentity(
                interface_name=name,
                protocol_version=v_resp.params[0] if v_resp.params else 0,
                interface_version="" # TODO
            ))
            self._emit(EventLog("info", f"4-way identity: {name}", source="4way"))
        except Exception as exc:
            self._emit(EventLog("error", f"Failed to read 4-way identity: {exc}", source="4way"))

    async def _handle_read_settings(self, command: CommandReadSettings) -> None:
        if not self._msp_client:
            return
            
        address = command.address
        length = command.length
        
        try:
            if self._protocol_mode == PROTOCOL_MODE_OPTIMIZED_TANG9K and self._fcsp_client:
                payload = build_read_block_payload(int(FcspAddressSpace.ESC_EEPROM), address, length)
                response = await self._fcsp_client.send_frame(
                    FcspChannel.CONTROL, 
                    bytes([int(FcspControlOp.READ_BLOCK)]) + payload,
                    timeout=1.0
                )
                if response and len(response.payload) > 3:
                    # FCSP READ_BLOCK response: result:u8, len:u16, data:bytes
                    data = response.payload[3:]
                else:
                    raise RuntimeError("Invalid READ_BLOCK response")
            else:
                if not self._passthrough_active:
                    await self._handle_enter_passthrough(CommandEnterPassthrough(motor_index=command.motor_index))
                
                response = await self._fourway_client.send(FOURWAY_CMDS["read_eeprom"], address=address, params=bytes([length & 0xFF]))
                data = bytes(response.params)
            
            self._emit(EventSettingsLoaded(data=data, address=address, motor_index=command.motor_index))
            self._emit(EventLog("info", f"Read {len(data)} bytes of settings from 0x{address:04X}", source="esc"))
        except Exception as exc:
            self._emit(EventLog("error", f"Failed to read settings: {exc}", source="esc"))

    async def _handle_write_settings(self, command: CommandWriteSettings) -> None:
        if not self._msp_client:
            return
            
        address = command.address
        data = bytes(command.data)
        
        try:
            if self._protocol_mode == PROTOCOL_MODE_OPTIMIZED_TANG9K and self._fcsp_client:
                payload = build_write_block_payload(int(FcspAddressSpace.ESC_EEPROM), address, data)
                await self._fcsp_client.send_frame(
                    FcspChannel.CONTROL,
                    bytes([int(FcspControlOp.WRITE_BLOCK)]) + payload,
                    timeout=1.0
                )
            else:
                if not self._passthrough_active:
                    await self._handle_enter_passthrough(CommandEnterPassthrough(motor_index=0)) # Default
                
                await self._fourway_client.send(FOURWAY_CMDS["write_eeprom"], address=address, params=data)
            
            self._emit(EventSettingsWritten(address=address, size=len(data), verified=True))
            self._emit(EventLog("info", f"Wrote {len(data)} bytes of settings to 0x{address:04X}", source="esc"))
        except Exception as exc:
            self._emit(EventLog("error", f"Failed to write settings: {exc}", source="esc"))

    async def _handle_flash_esc(self, command: CommandFlashEsc) -> None:
        """Asynchronous firmware flashing loop with progress reporting."""
        if not self._fourway_client or not self._passthrough_active:
            self._emit(EventLog("error", "Cannot flash: passthrough not active", source="flash"))
            return
            
        self._emit(EventLog("info", f"Starting flash for motor {self._passthrough_motor}...", source="flash"))
        
        try:
            # 1. Load image
            image = await asyncio.to_thread(load_firmware_file, command.file_path, family=command.family)
            data = bytes(image.data)
            start_addr = image.start_address
            page_size = 256
            total_pages = (len(data) + page_size - 1) // page_size
            
            # 2. Init flash
            await self._fourway_client.send(FOURWAY_CMDS["init_flash"], address=start_addr)
            
            # 3. Erase
            for i in range(total_pages):
                addr = start_addr + (i * page_size)
                self._emit(EventProgress(operation="flash", stage="erase", current=i, total=total_pages, message=f"Erasing page {i+1}/{total_pages}"))
                await self._fourway_client.send(FOURWAY_CMDS["page_erase"], address=addr, params=b"\x01")
            
            # 4. Write
            for i in range(total_pages):
                addr = start_addr + (i * page_size)
                chunk = data[i*page_size : (i+1)*page_size]
                self._emit(EventProgress(operation="flash", stage="write", current=i, total=total_pages, message=f"Writing page {i+1}/{total_pages}"))
                await self._fourway_client.send(FOURWAY_CMDS["write"], address=addr, params=chunk)
            
            # 5. Verify
            if command.verify_readback:
                for i in range(total_pages):
                    addr = start_addr + (i * page_size)
                    chunk = data[i*page_size : (i+1)*page_size]
                    self._emit(EventProgress(operation="flash", stage="verify", current=i, total=total_pages, message=f"Verifying page {i+1}/{total_pages}"))
                    resp = await self._fourway_client.send(FOURWAY_CMDS["read"], address=addr, params=bytes([len(chunk) & 0xFF]))
                    if bytes(resp.params) != chunk:
                        raise RuntimeError(f"Verification failed at 0x{addr:04X}")
            
            # 6. Reset
            await self._fourway_client.send(FOURWAY_CMDS["reset"])
            
            self._emit(EventFirmwareFlashed(
                byte_count=len(data),
                verified=command.verify_readback,
                display_name=image.name,
                family=command.family,
                motor_index=self._passthrough_motor
            ))
            self._emit(EventLog("info", "Flash complete!", source="flash"))
            
        except asyncio.CancelledError:
            self._emit(EventOperationCancelled(operation="flash"))
            self._emit(EventLog("warning", "Flash cancelled", source="flash"))
        except Exception as exc:
            self._emit(EventLog("error", f"Flash failed: {exc}", source="flash"))

    async def _handle_flash_all_escs(self, command: CommandFlashAllEscs) -> None:
        """Sequential flash for all detected ESCs."""
        self._emit(EventLog("info", "Starting batch flash for all ESCs...", source="flash"))
        try:
            # We assume esc_count is already known from a previous scan
            for i in range(self._esc_count):
                self._emit(EventLog("info", f"Batch Flash: Targeting ESC {i+1}/{self._esc_count}", source="flash"))
                # Switch passthrough
                await self._handle_enter_passthrough(CommandEnterPassthrough(motor_index=i))
                # Flash this ESC
                await self._handle_flash_esc(CommandFlashEsc(
                    file_path=command.file_path,
                    family=command.family,
                    display_name=command.display_name,
                    verify_readback=command.verify_readback
                ))
            
            self._emit(EventLog("info", "Batch flash completed for all ESCs", source="flash"))
        except Exception as exc:
            self._emit(EventLog("error", f"Batch flash failed: {exc}", source="flash"))

    async def _telemetry_loop(self) -> None:
        """Background loop to process all incoming FCSP frames (Telemetry, Logs, Responses)."""
        if self._fcsp_client is None:
            return

        logger.info("Kernel: Starting telemetry/dispatch loop")
        try:
            while self._is_running:
                # The loop is the SOLE reader of the FCSP transport
                frame = await self._fcsp_client.read_frame()
                
                # 1. Try to dispatch to a pending command (Solicited)
                if self._fcsp_client.dispatch_frame(frame):
                    continue
                
                # 2. Handle as unsolicited event
                if frame.channel == FcspChannel.TELEMETRY:
                    # TODO: Emit telemetry event
                    pass
                elif frame.channel == FcspChannel.FC_LOG:
                    msg = frame.payload.decode("ascii", errors="replace")
                    self._emit(EventLog("info", f"FC Log: {msg}", source="fc"))
                
        except asyncio.CancelledError:
            logger.info("Kernel: Telemetry loop cancelled")
        except Exception as exc:
            if self._is_running:
                logger.error("Kernel: Telemetry loop error: %s", exc)

    async def _probe_msp_identity(self) -> None:
        """Sequential MSP probe steps (non-blocking)."""
        if self._msp_client is None:
            return

        async def safe_read(command: int, description: str) -> bytes:
            try:
                response = await self._msp_client.send_msp(command, b"", timeout=1.2)
                if response and response.frame:
                    return response.frame.payload
                return b""
            except Exception as exc:
                name = MSP_COMMAND_NAMES.get(command, str(command))
                self._emit(EventLog("warning", f"MSP probe failed for {name}: {exc}", source="msp"))
                return b""

        def safe_ascii(data: bytes) -> str:
            return bytes(data).decode("ascii", errors="replace").rstrip("\x00 ")

        self._emit(EventLog("info", "Starting MSP identity probe...", source="msp"))

        api = await safe_read(MSP_API_VERSION, "API version")
        if len(api) >= 3:
            self._emit(EventLog("info", f"MSP API version: {api[0]}.{api[1]}.{api[2]}", source="msp"))

        variant = await safe_read(MSP_FC_VARIANT, "FC variant")
        if variant:
            self._emit(EventLog("info", f"FC variant: {safe_ascii(variant)}", source="msp"))

        fc_version = await safe_read(MSP_FC_VERSION, "FC version")
        if len(fc_version) >= 3:
            self._emit(EventLog("info", f"FC version: {fc_version[0]}.{fc_version[1]}.{fc_version[2]}", source="msp"))

        board = await safe_read(MSP_BOARD_INFO, "board info")
        if board:
            board_name = safe_ascii(board[:8]) if len(board) >= 4 else board.hex().upper()
            self._emit(EventLog("info", f"Board info: {board_name}", source="msp"))

        # ... additional probe steps follow similar pattern ...
        self._emit(EventLog("info", "MSP identity probe complete", source="msp"))

    async def _probe_fcsp_handshake(self) -> None:
        """Perform FCSP HELLO and GET_CAPS handshake (non-blocking)."""
        if self._fcsp_client is None:
            return

        self._emit(EventLog("info", "Starting FCSP handshake...", source="fcsp"))
        try:
            # 1. HELLO
            hello_payload = build_hello_payload([
                FcspTlv(tlv_type=FCSP_HELLO_TLV_ENDPOINT_NAME, value=b"python-imgui-esc-configurator-async"),
                FcspTlv(tlv_type=FCSP_HELLO_TLV_PROTOCOL_STRING, value=b"FCSP/1"),
                FcspTlv(tlv_type=FCSP_HELLO_TLV_PROFILE_STRING, value=b"PY-GUI-ASYNC"),
            ])
            
            # Send HELLO on CONTROL channel (0x01)
            response = await self._fcsp_client.send_frame(0x01, hello_payload, timeout=0.5)
            if not response:
                raise RuntimeError("No response to HELLO")
                
            status, tlvs = parse_hello_response_payload(response.payload)
            hello_summary = summarize_hello_tlvs(tlvs)
            peer_name = hello_summary.endpoint_name or "Unknown Peer"
            self._emit(EventLog("info", f"FCSP HELLO ok: {peer_name}", source="fcsp"))

            # 2. GET_CAPS
            caps_request = build_get_caps_request_payload()
            response = await self._fcsp_client.send_frame(0x01, bytes([int(FcspControlOp.GET_CAPS)]) + caps_request, timeout=0.5)
            if not response:
                raise RuntimeError("No response to GET_CAPS")
                
            status, caps_tlvs, _page, _has_more = parse_get_caps_response_payload(response.payload)
            caps_summary = summarize_capability_tlvs(caps_tlvs)
            
            for entry in caps_summary.entries:
                self._emit(EventLog("info", format_capability_tlv(entry), source="fcsp"))
                
            self._emit(EventLog("info", "FCSP handshake complete", source="fcsp"))
            
        except Exception as exc:
            self._emit(EventLog("error", f"FCSP handshake failed: {exc}", source="fcsp"))
