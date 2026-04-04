from __future__ import annotations

from MSP import SerialPortDescriptor

from imgui_bundle_esc_config.backend_models import (
    CommandConnect,
    CommandDisconnect,
    CommandRefreshPorts,
    EventConnected,
    EventDisconnected,
    EventLog,
    EventPortsUpdated,
)
from imgui_bundle_esc_config.headless_cli import run_headless_frontend


class FakeController:
    def __init__(self, events: list[object]) -> None:
        self._events = list(events)
        self.enqueued: list[object] = []
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def enqueue(self, command: object) -> None:
        self.enqueued.append(command)

    def poll_events(self, max_events: int = 100) -> list[object]:
        batch = self._events[:max_events]
        self._events = self._events[max_events:]
        return batch


def test_headless_ports_lists_detected_ports() -> None:
    fake = FakeController(
        events=[
            EventPortsUpdated(
                ports=[
                    SerialPortDescriptor(device="/dev/ttyUSB0", description="Bridge A", hwid="abc"),
                    SerialPortDescriptor(device="/dev/ttyUSB1", description="Bridge B", hwid="def"),
                ]
            )
        ]
    )
    lines: list[str] = []

    code = run_headless_frontend(
        ["ports", "--timeout", "0.2"],
        controller_factory=lambda: fake,
        output=lines.append,
    )

    assert code == 0
    assert fake.started is True
    assert fake.stopped is True
    assert any(isinstance(cmd, CommandRefreshPorts) for cmd in fake.enqueued)
    assert any("Detected 2 port(s)" in line for line in lines)
    assert any("/dev/ttyUSB0" in line for line in lines)


def test_headless_connect_success_and_disconnect() -> None:
    fake = FakeController(
        events=[
            EventConnected(port="/dev/ttyUSB0", baudrate=230400, protocol_mode="msp"),
            EventDisconnected(reason="Headless frontend disconnect"),
        ]
    )
    lines: list[str] = []

    code = run_headless_frontend(
        [
            "connect",
            "--port",
            "/dev/ttyUSB0",
            "--baudrate",
            "230400",
            "--protocol",
            "msp",
            "--disconnect-after",
            "0.01",
            "--timeout",
            "0.3",
        ],
        controller_factory=lambda: fake,
        output=lines.append,
    )

    assert code == 0
    assert isinstance(fake.enqueued[0], CommandConnect)
    assert isinstance(fake.enqueued[1], CommandDisconnect)
    assert any("Connected:" in line for line in lines)
    assert any("Disconnected:" in line for line in lines)


def test_headless_connect_timeout_returns_error_code() -> None:
    fake = FakeController(events=[])
    lines: list[str] = []

    code = run_headless_frontend(
        ["connect", "--port", "/dev/ttyUSB0", "--timeout", "0.05"],
        controller_factory=lambda: fake,
        output=lines.append,
    )

    assert code == 2
    assert any("timed out waiting for connection result" in line for line in lines)


def test_headless_monitor_streams_events_and_logs() -> None:
    fake = FakeController(
        events=[
            EventLog(level="info", source="worker", message="Worker thread started"),
            EventPortsUpdated(
                ports=[SerialPortDescriptor(device="/dev/ttyUSB0", description="Bridge A", hwid="abc")]
            ),
        ]
    )
    lines: list[str] = []

    code = run_headless_frontend(
        ["monitor", "--duration", "0.05"],
        controller_factory=lambda: fake,
        output=lines.append,
    )

    assert code == 0
    assert any("Monitoring backend events" in line for line in lines)
    assert any("[LOG/INFO]" in line for line in lines)
    assert any("ports_updated count=1" in line for line in lines)
    assert any("Monitoring complete:" in line for line in lines)


def test_headless_monitor_can_request_port_refresh() -> None:
    fake = FakeController(events=[])
    lines: list[str] = []

    code = run_headless_frontend(
        ["monitor", "--duration", "0.05", "--refresh-ports"],
        controller_factory=lambda: fake,
        output=lines.append,
    )

    assert code == 0
    assert any(isinstance(cmd, CommandRefreshPorts) for cmd in fake.enqueued)
