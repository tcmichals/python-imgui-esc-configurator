"""Simple headless frontend that exercises the shared backend contract.

This module is intentionally small and educational: it demonstrates how a
non-ImGui frontend can drive the same command/event worker boundary.
"""

from __future__ import annotations

import argparse
import time
from typing import Callable

from .backend_models import (
    CommandConnect,
    CommandDisconnect,
    CommandRefreshPorts,
    EventConnected,
    EventDisconnected,
    EventError,
    EventLog,
    EventPortsUpdated,
)
from .worker import WorkerController


def _wait_for_event(
    controller: WorkerController,
    event_types: tuple[type, ...],
    timeout_s: float,
    *,
    on_log: Callable[[str], None] | None = None,
) -> object | None:
    deadline = time.time() + max(0.01, float(timeout_s))
    while time.time() < deadline:
        for event in controller.poll_events(max_events=1):
            if isinstance(event, EventLog) and on_log is not None:
                on_log(f"[{event.level.upper()}] {event.source}: {event.message}")
            if isinstance(event, event_types):
                return event
        time.sleep(0.01)
    return None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m imgui_bundle_esc_config.headless_cli",
        description="Simple headless frontend for the ESC worker backend.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print worker log events while waiting")

    sub = parser.add_subparsers(dest="command", required=True)

    ports = sub.add_parser("ports", help="Enumerate serial ports via backend worker")
    ports.add_argument("--timeout", type=float, default=1.0, help="Seconds to wait for EventPortsUpdated")

    connect = sub.add_parser("connect", help="Connect to a serial port using backend worker")
    connect.add_argument("--port", required=True, help="Serial device path (e.g. /dev/ttyUSB0)")
    connect.add_argument("--baudrate", type=int, default=115200, help="Baud rate")
    connect.add_argument("--protocol", default="msp", help="Protocol mode (msp or optimized_tang9k)")
    connect.add_argument("--timeout", type=float, default=1.5, help="Seconds to wait for connection result")
    connect.add_argument(
        "--disconnect-after",
        type=float,
        default=0.0,
        help="Optional seconds to wait before issuing disconnect after successful connect",
    )

    monitor = sub.add_parser("monitor", help="Stream backend events/logs for classroom/demo use")
    monitor.add_argument("--duration", type=float, default=1.0, help="Seconds to stream events")
    monitor.add_argument(
        "--refresh-ports",
        action="store_true",
        help="Request a serial port refresh before streaming",
    )

    return parser


def run_headless_frontend(
    argv: list[str] | None = None,
    *,
    controller_factory: Callable[[], WorkerController] = WorkerController,
    output: Callable[[str], None] = print,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    controller = controller_factory()
    controller.start()

    def log_line(message: str) -> None:
        if args.verbose:
            output(message)

    try:
        if args.command == "ports":
            controller.enqueue(CommandRefreshPorts())
            event = _wait_for_event(controller, (EventPortsUpdated, EventError), args.timeout, on_log=log_line)
            if isinstance(event, EventError):
                output(f"ERROR: {event.message}")
                return 2
            if not isinstance(event, EventPortsUpdated):
                output("ERROR: timed out waiting for serial port enumeration")
                return 2
            if not event.ports:
                output("No serial ports detected")
                return 0
            output(f"Detected {len(event.ports)} port(s):")
            for port in event.ports:
                desc = f" — {port.description}" if getattr(port, "description", "") else ""
                output(f"- {port.device}{desc}")
            return 0

        if args.command == "connect":
            controller.enqueue(
                CommandConnect(
                    port=args.port,
                    baudrate=max(1, int(args.baudrate)),
                    protocol_mode=str(args.protocol),
                )
            )
            event = _wait_for_event(
                controller,
                (EventConnected, EventError, EventDisconnected),
                args.timeout,
                on_log=log_line,
            )
            if isinstance(event, EventConnected):
                output(
                    f"Connected: port={event.port} baud={event.baudrate} protocol={event.protocol_mode}"
                )
                if float(args.disconnect_after) > 0:
                    time.sleep(float(args.disconnect_after))
                    controller.enqueue(CommandDisconnect(reason="Headless frontend disconnect"))
                    disc = _wait_for_event(
                        controller,
                        (EventDisconnected, EventError),
                        max(0.25, args.timeout),
                        on_log=log_line,
                    )
                    if isinstance(disc, EventDisconnected):
                        output(f"Disconnected: {disc.reason}")
                        return 0
                    if isinstance(disc, EventError):
                        output(f"ERROR: {disc.message}")
                        return 2
                    output("ERROR: timed out waiting for disconnect confirmation")
                    return 2
                return 0
            if isinstance(event, EventError):
                output(f"ERROR: {event.message}")
                return 2
            if isinstance(event, EventDisconnected):
                output(f"Disconnected: {event.reason}")
                return 2
            output("ERROR: timed out waiting for connection result")
            return 2

        if args.command == "monitor":
            duration = max(0.05, float(args.duration))
            if args.refresh_ports:
                controller.enqueue(CommandRefreshPorts())

            output(f"Monitoring backend events for {duration:.2f}s...")
            deadline = time.time() + duration
            seen = 0
            while time.time() < deadline:
                batch = controller.poll_events(max_events=1)
                if not batch:
                    time.sleep(0.01)
                    continue
                for event in batch:
                    seen += 1
                    if isinstance(event, EventLog):
                        output(f"[LOG/{event.level.upper()}] {event.source}: {event.message}")
                    elif isinstance(event, EventPortsUpdated):
                        output(f"[EVENT] ports_updated count={len(event.ports)}")
                    elif isinstance(event, EventConnected):
                        output(f"[EVENT] connected port={event.port} baud={event.baudrate} protocol={event.protocol_mode}")
                    elif isinstance(event, EventDisconnected):
                        output(f"[EVENT] disconnected reason={event.reason}")
                    elif isinstance(event, EventError):
                        output(f"[EVENT] error message={event.message}")
                    else:
                        output(f"[EVENT] {type(event).__name__}")

            output(f"Monitoring complete: {seen} event(s)")
            return 0

        output(f"ERROR: unknown command {args.command}")
        return 2
    finally:
        controller.stop()


def main() -> None:
    raise SystemExit(run_headless_frontend())


if __name__ == "__main__":
    main()
