import serial
import time
import sys
from MSP import build_msp_frame

def test_sim_pty(port):
    print(f"[TEST] Connecting to Simulation PTY: {port}")
    try:
        ser = serial.Serial(port, 115200, timeout=1.0)
    except Exception as e:
        print(f"[TEST] Failed to open PTY: {e}")
        return

    # 1. Create a standard MSP_API_VERSION (1) request
    # Since we are testing the 'stream_framer' which expects 0xA5 framing,
    # we need to wrap the MSP packet in our Stream Protocol.
    
    payload = b"" # No payload for API_VERSION
    msp_packet = build_msp_frame(1, payload)
    
    # Wrap in 0xA5 Stream Packet: [0xA5] [Len LSB] [Len MSB] [Chan] [Seq] [Payload...] [CRC LSB] [CRC MSB]
    # For this test, we'll just send raw bytes to see if the SYNC logic works.
    
    print(f"[TEST] Sending raw MSP packet: {msp_packet.hex().upper()}")
    ser.write(msp_packet)
    ser.flush()
    
    time.sleep(0.5)
    print("[TEST] Done. Check Simulation console for 'RTL' messages.")
    ser.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_framer_sim.py /dev/pts/X")
    else:
        test_sim_pty(sys.argv[1])
