#!/usr/bin/env python3
"""
serialMSP.py

Send MSP (MultiWii Serial Protocol) commands and arbitrary raw bytes (e.g. BLHeli_S frames)
over a serial port to exercise/test hardware (FPGA, ESCs, etc.).

Usage examples:
  python3 serialMSP.py --port /dev/ttyUSB0 --baud 115200 msp --cmd 105 --payload 01ff
  python3 serialMSP.py --port /dev/ttyUSB0 raw --data 0A0B0C
  python3 serialMSP.py --port /dev/ttyUSB0 listen

Note: BLHeli/BLHeli_S ESCs commonly use inverted UART levels and 1-wire half-duplex interfaces;
this script writes normal TTL-level bytes. Hardware adapter or FPGA wiring must handle inversion
and direction switching.

Requires: pyserial (pip install pyserial)
"""

import argparse
import datetime
import os
import sys
import time

if __package__ in {None, ""}:
    PYTHON_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if PYTHON_ROOT not in sys.path:
        sys.path.insert(0, PYTHON_ROOT)
    from MSP import FOURWAY_CMDS, FourWayClient, MSPClient, SerialTransport, hexdump
else:
    from . import FOURWAY_CMDS, FourWayClient, MSPClient, SerialTransport, hexdump


def parse_hex_bytes(s: str) -> bytes:
    s2 = s.replace("0x", "").replace(" ", "").replace(",", "")
    if len(s2) % 2 == 1:
        s2 = "0" + s2
    return bytes.fromhex(s2)


def open_serial(port: str, baud: int, timeout: float = 0.1) -> SerialTransport:
    try:
        return SerialTransport(port, baudrate=baud, timeout=timeout)
    except Exception as e:
        print(f"Failed to open serial port {port}: {e}")
        sys.exit(2)


def main():
    p = argparse.ArgumentParser(description="Send MSP and raw serial frames")
    p.add_argument("--port", required=True, help="Serial device, e.g. /dev/ttyUSB0")
    p.add_argument("--baud", type=int, default=115200)
    p.add_argument("--dump", action="store_true", help="Hex dump TX/RX frames")
    sub = p.add_subparsers(dest="mode")

    msp = sub.add_parser("msp", help="Send an MSP command")
    msp.add_argument("--cmd", type=int, required=True, help="MSP command id (decimal)")
    msp.add_argument("--payload", default="", help="Payload bytes as hex (e.g. 0102ff)")
    msp.add_argument("--no-response", action="store_true", help="Don't wait for an MSP response")

    raw = sub.add_parser("raw", help="Send raw bytes (useful for BLHeli frames)")
    raw.add_argument("--data", required=True, help="Hex bytes to send, e.g. 0A0B0C")
    raw.add_argument("--repeat", type=int, default=1, help="Repeat count")
    raw.add_argument("--read-after", type=float, default=0.05, help="Time (s) to wait and read response after write")

    blheli = sub.add_parser("blheli", help="Send BLHeli-style raw bytes (convenience wrapper)")
    blheli.add_argument("--data", required=True, help="Hex bytes for BLHeli frame, e.g. 0A0B0C")
    blheli.add_argument("--repeat", type=int, default=1, help="Repeat count")
    blheli.add_argument("--read-after", type=float, default=0.02, help="Wait time after write to read response")

    set_mux = sub.add_parser("set_mux", help="Set UART mux selection via MSP id 245")
    set_mux.add_argument("--mux-sel", type=int, choices=[0,1], default=0, help="Mux select (0 or 1)")
    set_mux.add_argument("--mux-ch", type=int, choices=[0,1,2,3], default=0, help="Mux channel (0..3)")
    set_mux.add_argument("--msp-mode", type=int, choices=[0,1], default=0, help="MSP mode (0 or 1)")
    set_mux.add_argument("--clear", action="store_true", help="Send clear (zero-length) payload for MSP 245")

    listen = sub.add_parser("listen", help="Listen and print bytes/lines from serial")
    listen.add_argument("--hex", action="store_true", help="Print bytes as hex")

    fourway = sub.add_parser("fourway", help="Send 4-way interface commands (after MSP passthrough)")
    fourway.add_argument("--cmd", choices=list(FOURWAY_CMDS.keys()),
                         help="Single 4way command to send")
    fourway.add_argument("--cmds", nargs='+', choices=list(FOURWAY_CMDS.keys()),
                         help="Multiple 4way commands to send in sequence")
    fourway.add_argument("--esc", type=int, default=0, choices=[0,1,2,3],
                         help="ESC number (for init_flash)")
    fourway.add_argument("--address", type=lambda x: int(x, 0), default=0,
                         help="Address (for read/write commands)")
    fourway.add_argument("--length", type=int, default=128,
                         help="Length (for read commands)")
    fourway.add_argument("--passthrough", action="store_true",
                         help="Send MSP_SET_PASSTHROUGH (245) first to enter 4way mode")
    fourway.add_argument("--delay", type=float, default=0.1,
                         help="Delay in seconds between commands (default: 0.1)")

    args = p.parse_args()
    if args.mode is None:
        p.print_help()
        sys.exit(1)

    transport = open_serial(args.port, args.baud)

    if args.mode == "msp":
        payload = parse_hex_bytes(args.payload) if args.payload else b""
        client = MSPClient(transport)
        response = None
        raw_tx = None
        try:
            response = client.send_msp(args.cmd, payload, expect_response=not args.no_response)
            raw_tx = response.raw_frame if response else None
        except TimeoutError as exc:
            print(f"MSP timeout: {exc}")
        if raw_tx is not None:
            print(f"Sent MSP cmd={args.cmd} size={len(payload)}")
            if args.dump:
                print("TX:", hexdump(raw_tx))
        else:
            print(f"Sent MSP cmd={args.cmd} size={len(payload)}")
        if response:
            frame = response.frame
            print(
                f"Recv MSP cmd={frame.command} size={frame.size} cs=0x{frame.checksum:02x} valid=True"
            )
            print("RX:", hexdump(frame.header + bytes([frame.size, frame.command]) + frame.payload + bytes([frame.checksum])))
            print("Payload:", frame.payload.hex())
    elif args.mode == "raw":
        data = parse_hex_bytes(args.data)
        for i in range(args.repeat):
            transport.write(data)
            print(f"Wrote {len(data)} bytes: {data.hex()}")
            if args.dump:
                print("TX:", hexdump(data))
            # optional read-after to capture response
            if getattr(args, 'read_after', 0) and args.read_after > 0:
                time.sleep(args.read_after)
                rx = transport.read(256)
                if rx:
                    print(datetime.datetime.now().isoformat(), "RX:", hexdump(rx))
            time.sleep(0.01)
    elif args.mode == "blheli":
        data = parse_hex_bytes(args.data)
        for i in range(args.repeat):
            transport.write(data)
            print(f"Wrote BLHeli {len(data)} bytes: {data.hex()}")
            if args.dump:
                print("TX:", hexdump(data))
            time.sleep(args.read_after)
            rx = transport.read(256)
            if rx:
                print(datetime.datetime.now().isoformat(), "RX:", hexdump(rx))
    elif args.mode == "set_mux":
        # Build and send MSP id 245 to control UART muxing
        client = MSPClient(transport)
        if args.clear:
            payload = b""
            print("Sending MSP 245 clear (zero-length payload)")
        else:
            val = (args.msp_mode << 3) | (args.mux_ch << 1) | (args.mux_sel)
            payload = bytes([val & 0xFF])
            print(f"Sending MSP 245 set_mux mux_sel={args.mux_sel} mux_ch={args.mux_ch} msp_mode={args.msp_mode} val=0x{val:02x}")
        try:
            resp = client.send_msp(245, payload, expect_response=True)
        except TimeoutError as exc:
            print(f"MSP timeout: {exc}")
            resp = None
        if args.dump:
            print("Payload TX:", hexdump(payload))
        if resp:
            print("Response payload:", resp.frame.payload.hex())
    elif args.mode == "fourway":
        # Enter 4way mode first if requested
        if args.passthrough:
            print("Entering 4way mode via MSP_SET_PASSTHROUGH...")
            client = MSPClient(transport)
            try:
                resp = client.send_msp(245, b"", expect_response=True)
            except TimeoutError:
                resp = None
            if resp and resp.frame.payload:
                print(f"4way mode active, {resp.frame.payload[0]} ESCs reported")
            elif resp:
                print("4way mode active")
            else:
                print("Failed to enter 4way mode")
                transport.close()
                sys.exit(1)
        
        fw = FourWayClient(transport)
        
        # Build command list from --cmd or --cmds
        if args.cmds:
            cmd_list = args.cmds
        elif args.cmd:
            cmd_list = [args.cmd]
        else:
            print("Error: must specify --cmd or --cmds")
            transport.close()
            sys.exit(1)
        
        for idx, cmd in enumerate(cmd_list):
            if idx > 0:
                time.sleep(args.delay)
            print(f"\n--- Command {idx+1}/{len(cmd_list)}: {cmd} ---")
            resp = None
            
            if cmd == 'test_alive':
                resp = fw.test_alive()
            elif cmd == 'get_version':
                resp = fw.get_version()
            elif cmd == 'get_name':
                resp = fw.get_name()
                if resp.params:
                    name = resp.params.decode('ascii', errors='replace').rstrip('\x00')
                    print(f"Interface name: {name}")
            elif cmd == 'get_if_version':
                resp = fw.send(FOURWAY_CMDS['get_if_version'])
            elif cmd == 'exit':
                resp = fw.exit_4way()
                print("Exited 4way mode")
            elif cmd == 'init_flash':
                print(f"Initializing ESC {args.esc} for flashing...")
                resp = fw.init_flash(args.esc)
                if resp.ack == 0:
                    print(f"ESC {args.esc} bootloader active, signature: {resp.params.hex()}")
                else:
                    print(f"ESC {args.esc} init failed")
            elif cmd == 'read':
                resp = fw.read_flash(args.address, args.length)
            elif cmd == 'reset':
                resp = fw.send(FOURWAY_CMDS['reset'], params=bytes([args.esc & 0x03]))
            else:
                # Generic send
                resp = fw.send(FOURWAY_CMDS[cmd])

            if resp is not None:
                print(
                    f"4way RX: cmd=0x{resp.command:02X} addr=0x{resp.address:04X} ack={resp.ack_str} params={resp.params.hex()}"
                )
                print(f"  CRC: recv=0x{resp.checksum:04X} ok={resp.crc_ok}")
    elif args.mode == "listen":
        print(f"Listening on {args.port} @ {args.baud} baud. Ctrl-C to exit.")
        try:
            while True:
                b = transport.read(1)
                if not b:
                    continue
                if args.hex:
                    print(datetime.datetime.now().isoformat(), "RX:", b.hex(), end=" ", flush=True)
                else:
                    # try to print human text, fall back to hex for non-printables
                    if 32 <= b[0] <= 126 or b in b"\n\r\t":
                        sys.stdout.buffer.write(b)
                        sys.stdout.flush()
                    else:
                        print(datetime.datetime.now().isoformat(), "RX:", b.hex(), end=" ", flush=True)
        except KeyboardInterrupt:
            print("\nStopped listening")
    transport.close()


if __name__ == "__main__":
    main()
