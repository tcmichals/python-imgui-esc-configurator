#!/usr/bin/env python3
"""
Motor test script - continuously sends DSHOT commands via MSP
Use arrow keys or q/w/e/r to control motors in real-time.
Press Ctrl+C to stop.

SAFETY FEATURES:
- SPACE = stop sending immediately
- ESC = stop and exit
- Max throttle capped at 500 (safe test range)
- Motors start at 0
"""

import argparse
import serial
import time
import sys
import termios
import tty
import select

MSP_HEADER = b"$M<"
MSP_SET_MOTOR = 214

# SAFETY: Maximum throttle for testing (2047 is full throttle)
MAX_THROTTLE = 500

def calc_checksum(buf: bytes) -> int:
    cs = 0
    for b in buf:
        cs ^= b
    return cs

def build_motor_frame(m1, m2, m3, m4):
    """Build MSP_SET_MOTOR frame with 4 motor values (16-bit little-endian)"""
    payload = bytes([
        m1 & 0xFF, (m1 >> 8) & 0xFF,
        m2 & 0xFF, (m2 >> 8) & 0xFF,
        m3 & 0xFF, (m3 >> 8) & 0xFF,
        m4 & 0xFF, (m4 >> 8) & 0xFF,
    ])
    frame = MSP_HEADER + bytes([len(payload), MSP_SET_MOTOR]) + payload
    cs = calc_checksum(frame[3:])
    return frame + bytes([cs])

class MotorController:
    def __init__(self, port, baud=115200, max_throttle=500, interval=0.0005):
        self.ser = serial.Serial(port, baud, timeout=0.01)
        self.motors = [0, 0, 0, 0]  # Throttle values for each motor
        self.max_throttle = max_throttle
        self.running = True
        self.last_send = 0
        self.send_interval = interval
        
    def set_motor(self, idx, value):
        """Set motor throttle (0-max_throttle)"""
        self.motors[idx] = max(0, min(self.max_throttle, value))
        
    def send_motors(self):
        """Send current motor values to ESC"""
        frame = build_motor_frame(*self.motors)
        self.ser.write(frame)
        self.ser.flush()
        # Drain response (if any)
        self.ser.read(64)
        
    def stop_all(self):
        """Emergency stop"""
        self.motors = [0, 0, 0, 0]
        self.send_motors()

def get_key_nonblocking():
    """Get key press without blocking, returns None if no key pressed"""
    if select.select([sys.stdin], [], [], 0)[0]:
        return sys.stdin.read(1)
    return None

def main():
    parser = argparse.ArgumentParser(description="Motor test with continuous DSHOT")
    parser.add_argument("--port", default="/dev/ttyUSB1", help="Serial port")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate")
    parser.add_argument("--max-throttle", type=int, default=MAX_THROTTLE, help=f"Max throttle (default {MAX_THROTTLE})")
    parser.add_argument("--interval", type=float, default=0.0005, help="Send interval in seconds (default 0.0005 = 0.5ms = 2kHz)")
    args = parser.parse_args()
    
    max_thr = args.max_throttle
    rate_hz = 1.0 / args.interval
    
    print(f"Motor Test - {args.port} @ {args.baud}")
    print()
    print("=== SAFETY ===")
    print(f"  Max throttle: {max_thr}")
    print(f"  Send rate:    {rate_hz:.0f}Hz ({args.interval*1000:.1f}ms)")
    print("  SPACE = STOP SENDING")
    print()
    print("Controls:")
    print("  q/a - Motor 1 up/down")
    print("  w/s - Motor 2 up/down")
    print("  e/d - Motor 3 up/down")
    print("  r/f - Motor 4 up/down")
    print("  SPACE - STOP SENDING")
    print("  ESC or x - Stop and Exit")
    print()
    print("Throttle step: 50 per keypress")
    print()
    print("*** REMOVE PROPELLERS BEFORE TESTING ***")
    print()
    
    ctrl = MotorController(args.port, args.baud, max_throttle=max_thr, interval=args.interval)
    
    print("Ready. Press keys to control motors...")
    print()
    
    # Save terminal settings
    old_settings = termios.tcgetattr(sys.stdin)
    
    try:
        # Set terminal to raw mode for non-blocking key input
        tty.setcbreak(sys.stdin.fileno())
        
        while ctrl.running:
            now = time.time()
            
            # Check for key press
            key = get_key_nonblocking()
            if key:
                step = 50
                if key == 'q': ctrl.set_motor(0, ctrl.motors[0] + step)
                elif key == 'a': ctrl.set_motor(0, ctrl.motors[0] - step)
                elif key == 'w': ctrl.set_motor(1, ctrl.motors[1] + step)
                elif key == 's': ctrl.set_motor(1, ctrl.motors[1] - step)
                elif key == 'e': ctrl.set_motor(2, ctrl.motors[2] + step)
                elif key == 'd': ctrl.set_motor(2, ctrl.motors[2] - step)
                elif key == 'r': ctrl.set_motor(3, ctrl.motors[3] + step)
                elif key == 'f': ctrl.set_motor(3, ctrl.motors[3] - step)
                elif key == ' ':  # STOP SENDING
                    print("\n*** STOPPED SENDING ***")
                    ctrl.running = False
                    continue
                elif key == '\x1b' or key == 'x':  # ESC or x
                    ctrl.running = False
                    continue
                
                # Print motor values
                print(f"\rM1:{ctrl.motors[0]:4d} M2:{ctrl.motors[1]:4d} M3:{ctrl.motors[2]:4d} M4:{ctrl.motors[3]:4d}  ", end='', flush=True)
            
            # Send motor values at fixed interval
            if now - ctrl.last_send >= ctrl.send_interval:
                ctrl.send_motors()
                ctrl.last_send = now
            
    except KeyboardInterrupt:
        print("\n\nCtrl+C - Stopping...")
    finally:
        # Restore terminal settings
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        print("\nStopped sending. Exiting.")

if __name__ == "__main__":
    main()
