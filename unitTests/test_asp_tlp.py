# Copyright (C) 2026 Tim Michals
# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from comm_proto.asp_tlp import (
    AspTlpPacket,
    AspTransportDriver,
    build_tlp64,
    parse_tlp64,
    REG_SYS_ID_REV,
    REG_SYS_VENDOR_ID,
    REG_SYS_SCRATCH,
    REG_SYS_LED_CTRL,
    REG_SYS_TIME_LOW,
    REG_SYS_TIME_HIGH,
    REG_MOTOR_CTRL,
    REG_MOTOR_CH1,
    REG_PWM_DEC_CTRL,
    REG_PWM_DEC_CH1,
    REG_NEO_CTRL,
)

class TestAspTlpProtocol(unittest.TestCase):
    def test_build_and_parse_tlp64(self):
        pkt = build_tlp64(0x01, 0x01, REG_SYS_ID_REV, b"\xAB\xF1\x01\x64")
        self.assertEqual(len(pkt), 64)
        
        parsed = parse_tlp64(pkt)
        self.assertEqual(parsed.pkt_type, 0x01)
        self.assertEqual(parsed.channel, 0x01)
        self.assertEqual(parsed.addr, REG_SYS_ID_REV)
        self.assertTrue(parsed.is_valid_device)

    def test_mock_driver_operations(self):
        drv = AspTransportDriver(mock=True)
        
        # Identity Check
        dev_id = drv.reg_read32(REG_SYS_ID_REV)
        self.assertEqual(dev_id, 0xABF10164)
        
        vendor_id = drv.reg_read32(REG_SYS_VENDOR_ID)
        self.assertEqual(vendor_id, 0x19981ACC)

        # R/W Scratchpad
        drv.reg_write32(REG_SYS_SCRATCH, 0x12345678)
        self.assertEqual(drv.reg_read32(REG_SYS_SCRATCH), 0x12345678)

        # Motor Control
        drv.set_motor_throttle(1, 1500)
        self.assertEqual(drv.reg_read32(REG_MOTOR_CH1), 1500)

        # PWM Receiver Input Capture
        self.assertEqual(drv.get_rc_channel_us(1), 1500)
        self.assertEqual(drv.get_rc_channel_us(2), 1000)

if __name__ == "__main__":
    unittest.main()
