serialMSP — quick README

See also:

- `../AI_PROMPT_GUIDE.md` — Python-tree routing guide for both humans and AI agents
- `TESTING_GUIDE.md` — fuller testing and command-flow reference for `serialMSP.py`
- `../../docs/MSP_MESSAGE_FLOW.md` — canonical MSP behavior reference

> **AI doc role:** supporting script usage reference
>
> **Use this in prompts for:** quick `serialMSP.py` invocation patterns, 4-way command examples, raw serial/MSP experimentation
>
> **Warning:** examples here are convenience-oriented and may reflect bench workflows rather than the canonical firmware contract

This script helps send MSP (MultiWii Serial Protocol) frames and arbitrary raw bytes (e.g. BLHeli_S command frames)
over a serial port for testing FPGA or ESC interfaces.

Usage examples:

- Send MSP command id 105 with payload 0x01 0xff:
  python3 serialMSP.py --port /dev/ttyUSB0 --baud 115200 msp --cmd 105 --payload 01ff

- Send raw BLHeli frame (hex):
  python3 serialMSP.py --port /dev/ttyUSB0 raw --data 0A0B0C

- Listen and print serial bytes as hex:
  python3 serialMSP.py --port /dev/ttyUSB0 --baud 115200 listen --hex

Notes / caveats:
- Install pyserial: pip install pyserial
- BLHeli/BLHeli_S ESCs commonly require inverted UART levels and sometimes a single-wire half-duplex connection.
  Ensure your FPGA or adapter provides correct inversion and direction control. This script writes TTL-level bytes
  as-is and does not perform inversion or GPIO direction switching.
- The script implements basic MSP framing: header "$M<", size, cmd, payload, checksum (xor of size/cmd/payload)
  and will attempt to parse responses with header "$M>".

If you want specific BLHeli commands implemented (read/write config, set motor params), provide the packet definitions
and I can add convenience functions that build those packets directly.

4-Way Interface Testing (BLHeli ESC Configuration)
---------------------------------------------------

The `fourway` subcommand implements the Betaflight 4-Way Interface Protocol for configuring BLHeli ESCs.

### Quick Start

1. **Test basic connectivity (keep-alive ping)**:
   ```bash
   python3 serialMSP.py --port /dev/ttyUSB1 fourway --passthrough --cmds test_alive
   ```

2. **Initialize ESC 0 for flashing (enter bootloader)**:
   ```bash
   python3 serialMSP.py --port /dev/ttyUSB1 fourway --passthrough --cmds test_alive init_flash --esc 0
   ```

3. **Full test sequence**:
   ```bash
   python3 serialMSP.py --port /dev/ttyUSB1 fourway --passthrough --cmds test_alive init_flash exit --esc 0
   ```

### Available 4-Way Commands

| Command       | Description                                      |
|---------------|--------------------------------------------------|
| test_alive    | Keep-alive ping (verify connection)              |
| get_version   | Get protocol version                             |
| get_name      | Get interface name ("T9K-4WAY")                  |
| get_if_version| Get interface version                            |
| exit          | Exit 4-way mode, restore DSHOT                   |
| reset         | Reset ESC                                        |
| init_flash    | Initialize ESC for programming (enter bootloader)|
| read          | Read from ESC flash (use --address, --length)    |
| write         | Write to ESC flash                               |
| read_eeprom   | Read ESC EEPROM                                  |
| write_eeprom  | Write ESC EEPROM                                 |

### Command Options

- `--passthrough`: Send MSP_SET_PASSTHROUGH (245) first to enter 4-way mode
- `--esc N`: Select ESC channel 0-3 (for init_flash, reset)
- `--address 0xNNNN`: Flash/EEPROM address (for read/write)
- `--length N`: Number of bytes to read (default: 128)
- `--delay N`: Delay in seconds between commands (default: 0.1)

### Example Sessions

**Verify 4-way mode works:**
```bash
python3 serialMSP.py --port /dev/ttyUSB1 fourway --passthrough --cmds test_alive get_name get_version exit
```

**Initialize ESC and read signature:**
```bash
python3 serialMSP.py --port /dev/ttyUSB1 fourway --passthrough --cmds test_alive init_flash --esc 0
```

Expected success response:
```
4way RX: cmd=0x37 addr=0x0000 ack=OK params=07e86301
  CRC: recv=0x.... calc=0x.... ok=True
ESC 0 bootloader active, signature: 07e86301
```

The params decode as:
- `07` = SIGNATURE_002 (sig low byte)
- `e8` = SIGNATURE_001 (sig high byte) → signature 0xE807 (EFM8BB21)
- `63` = BOOT_MSG last char ('c' = version)
- `01` = interfaceMode (1 = SiLabs bootloader)

**Read flash after init:**
```bash
python3 serialMSP.py --port /dev/ttyUSB1 fourway --passthrough --cmds test_alive init_flash read --esc 0 --address 0x0000 --length 64
```

### Troubleshooting

**No response to init_flash:**
- Check ESC power is connected
- Verify signal wire to correct motor pin
- Check mux is selecting correct channel
- ESC may need longer break signal (increase delay in firmware)

**ACK = GENERAL_ERROR (0x0F):**
- ESC saw break but no bootloader response
- Response params contain debug info: mux_before, mux_break, mux_after, channel, bytes_received

**CRC mismatch:**
- Communication error, try again
- Check baud rate (115200 for USB, 19200 for ESC)

set_mux example
----------------
Set the serial/DSHOT mux using MSP id 245 (convenience `set_mux` subcommand):

- Select passthrough, channel 3 (which maps to physical `o_motor1` in the design), MSP mode off:
  python3 serialMSP.py --port /dev/ttyUSB0 set_mux --mux-sel 0 --mux-ch 3 --msp-mode 0 --dump

- Clear any MSP override (send zero-length payload):
  python3 serialMSP.py --port /dev/ttyUSB0 set_mux --clear --dump

The payload layout (1 byte) is: bit0=mux_sel, bits[2:1]=mux_ch, bit3=msp_mode. A length==0 packet clears the override.
