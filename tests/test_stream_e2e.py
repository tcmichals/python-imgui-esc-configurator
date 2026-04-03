import socket
import sys
import os
import time

# Add current dir to path to find MSP
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))

from MSP import build_msp_frame, build_stream_frame, parse_stream_frame, parse_msp_frame

def test_e2e_sim():
    host = "localhost"
    port = 4445
    
    # MSP_API_VERSION = 1
    msp_payload = build_msp_frame(1)
    # Stream it on Channel 0x01
    stream_packet = build_stream_frame(msp_payload, 0x01, 42)
    
    print(f"Connecting to {host}:{port}...")
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((host, port))
        
        print(f"Sending framed MSP: {stream_packet.hex().upper()}")
        s.sendall(stream_packet)
        
        # Wait for response
        s.settimeout(2.0)
        data = s.recv(1024)
        if not data:
            print("No data received!")
            return
            
        print(f"Received raw: {data.hex().upper()}")
        
        # Note: The simulation sends back RAW MSP or framed?
        # The SERV firmware usually just writes to UART0. 
        # The SimBridge captures UART0.
        
        # If it's raw MSP, we should find $M>
        if b"$M>" in data:
            idx = data.find(b"$M>")
            msp_resp = parse_msp_frame(data[idx:])
            print(f"Decoded MSP Response: CMD={msp_resp.command} Payload={msp_resp.payload.hex()}")
        else:
            print("Could not find MSP header in response")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        s.close()

if __name__ == "__main__":
    test_e2e_sim()
