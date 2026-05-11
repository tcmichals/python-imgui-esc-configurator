"""Benchmark script to compare Synchronous vs Asynchronous Kernel performance."""

import asyncio
import time
import logging
import sys
import os
import threading
from typing import Callable, Any

# Ensure we can import from the root directory
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

class AsyncMockStream:
    def __init__(self, latency=0.001):
        self.latency = latency
        self._closed = False

    async def read(self, n=-1):
        await asyncio.sleep(self.latency)
        return b"\x00" * (n if n > 0 else 1)

    async def readexactly(self, n):
        await asyncio.sleep(self.latency)
        return b"\x00" * n

    def write(self, data):
        pass

    async def drain(self):
        await asyncio.sleep(self.latency)

    def close(self):
        self._closed = True

    async def wait_closed(self):
        pass

# Mock serial_asyncio if not present
try:
    import serial_asyncio
except ImportError:
    class MockSerialAsyncio:
        @staticmethod
        async def open_serial_connection(**kwargs):
            return AsyncMockStream(), AsyncMockStream()
    sys.modules["serial_asyncio"] = MockSerialAsyncio

# Import legacy components
from imgui_bundle_esc_config.worker import WorkerController, CommandConnect, CommandRefreshPorts
from MSP.serial_client import SerialPortDescriptor

# Import new async components
from imgui_bundle_esc_config.async_worker import AsyncWorkerController

# Configure logging
logging.basicConfig(level=logging.WARNING)

class SyncMockTransport:
    def __init__(self, port, baudrate, timeout):
        self.closed = False
        self.latency = 0.001
        
    def write(self, data: bytes):
        time.sleep(self.latency)
        
    def read(self, size: int) -> bytes:
        time.sleep(self.latency)
        return b"\x00" * size
        
    def close(self):
        self.closed = True
    
    def is_open(self):
        return not self.closed

def run_sync_telemetry_test(iterations=100):
    print(f"Starting Sync Telemetry Benchmark...")
    
    ports = [SerialPortDescriptor(device="COM1", description="Fake", hwid="123")]
    controller = WorkerController(
        port_enumerator=lambda: ports,
        transport_factory=lambda p, b, t: SyncMockTransport(p, b, t)
    )
    
    controller.start()
    controller.enqueue(CommandConnect(port="COM1", baudrate=115200))
    time.sleep(0.1) # Wait for connect
    
    start_time = time.perf_counter()
    
    # In legacy, we can't easily run telemetry in background without modifying the worker.
    # But we can simulate the worker being busy with 100 commands.
    for _ in range(iterations):
        controller.enqueue(CommandRefreshPorts())
        # The legacy worker processes these one by one in its thread.
        # We'll just wait for the last one to be processed by checking a dummy event or just sleeping.
        time.sleep(0.005) 
        
    end_time = time.perf_counter()
    controller.stop()
    return end_time - start_time

async def run_async_telemetry_test(iterations=100):
    print(f"Starting Async Telemetry Benchmark...")
    
    ports = [SerialPortDescriptor(device="COM1", description="Fake", hwid="123")]
    controller = AsyncWorkerController(port_enumerator=lambda: ports)
    
    controller.start()
    controller.submit(CommandConnect(port="COM1", baudrate=115200))
    await asyncio.sleep(0.1)
    
    start_time = time.perf_counter()
    
    # In async, we can have a background "telemetry" task running in the same loop
    async def telemetry_task():
        for _ in range(iterations * 10):
            await asyncio.sleep(0.0001) # Simulate high-rate background noise
            
    t_task = asyncio.create_task(telemetry_task())
    
    for _ in range(iterations):
        controller.submit(CommandRefreshPorts())
        await asyncio.sleep(0.005)
        
    await t_task
    end_time = time.perf_counter()
    await controller.stop()
    return end_time - start_time

if __name__ == "__main__":
    sync_time = run_sync_telemetry_test()
    async_time = asyncio.run(run_async_telemetry_test())
    
    print("\nResults (Heavy Workload):")
    print(f"Sync: {sync_time:.4f}s")
    print(f"Async: {async_time:.4f}s")
    if sync_time > 0:
        print(f"Improvement: {((sync_time - async_time) / sync_time) * 100:.2f}%")
