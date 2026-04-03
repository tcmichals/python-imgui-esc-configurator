import sys
import os
import unittest

# Add current dir to path to find MSP
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))

from MSP.stream_protocol import build_stream_frame, parse_stream_frame, STREAM_SYNC, STREAM_VERSION

class TestStreamProtocol(unittest.TestCase):
    def test_basic_framing(self):
        payload = b"\x01\x02\x03\x04"
        channel = 0x05
        seq = 0x1234
        
        framed = build_stream_frame(payload, channel, seq)
        
        # [Sync] [Ver] [Flags] [Chan] [SeqH] [SeqL] [LenH] [LenL] [Payload...] [CRCH] [CRCL]
        self.assertEqual(framed[0], STREAM_SYNC)
        self.assertEqual(framed[1], STREAM_VERSION)
        self.assertEqual(framed[3], channel)
        self.assertEqual(framed[4], 0x12)
        self.assertEqual(framed[5], 0x34)
        self.assertEqual(framed[7], 4) # len
        self.assertEqual(framed[8:12], payload)
        
        decoded = parse_stream_frame(framed)
        self.assertEqual(decoded.channel, channel)
        self.assertEqual(decoded.seq, seq)
        self.assertEqual(decoded.payload, payload)
        self.assertTrue(decoded.crc_ok)

    def test_invalid_sync(self):
        payload = b"test"
        framed = bytearray(build_stream_frame(payload, 1, 1))
        framed[0] = 0x00 # Corrupt sync
        
        with self.assertRaises(ValueError):
            parse_stream_frame(bytes(framed))

    def test_bad_crc(self):
        payload = b"test"
        framed = bytearray(build_stream_frame(payload, 1, 1))
        framed[-1] = (framed[-1] + 1) & 0xFF # Corrupt CRC
        
        decoded = parse_stream_frame(bytes(framed))
        self.assertFalse(decoded.crc_ok)

if __name__ == "__main__":
    unittest.main()
