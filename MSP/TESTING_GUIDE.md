# serialMSP.py Testing Guide

See also:

- `../AI_PROMPT_GUIDE.md` — Python-tree routing guide for both humans and AI agents
- `../../docs/MSP_MESSAGE_FLOW.md` — canonical MSP command/reply behavior
- `../../docs/BLHELI_PASSTHROUGH.md` — passthrough transition and 4-way context

> **AI doc role:** supporting test and bench-validation reference
>
> **Use this in prompts for:** serialMSP test flows, MSP command probing, passthrough smoke tests, 4-way bench validation
>
> **Warning:** this is a supporting test guide, not the canonical source of firmware behavior; prefer `docs/` for active protocol semantics

This script provides comprehensive testing for the Tang9K FPGA's serial modes: MSP protocol, BLHeli passthrough, and DSHOT motor control.

## Quick Start

```bash
cd python/MSP
python3 serialMSP.py --port /dev/ttyUSB0 --baud 115200 <command>
```

## Available Commands

### 1. Test MSP Mode (`test_msp`)
Tests the MSP Flight Controller protocol implementation.

```bash
# Test MSP mode on Motor 1 channel
python3 serialMSP.py --port /dev/ttyUSB0 test_msp --channel 0

# Test on Motor 3 channel with debug output
python3 serialMSP.py --port /dev/ttyUSB0 --dump test_msp --channel 2
```

**What it does:**
- Enables MSP mode (msp_mode=1, mux_sel=0, mux_ch=selected)
- Queries MSP_FC_VARIANT (should return "TN9K")
- Queries MSP_FC_VERSION (should return version 1.0.0)
- Queries MSP_API_VERSION
- Queries MSP_BOARD_INFO (should return "T9K")

**Expected results:**
- FC Variant: `TN9K` (Tang Nano 9K)
- FC Version: `1.0.0`
- Board ID: `T9K`

### 2. Test BLHeli Passthrough (`test_passthrough`)
Tests transparent BLHeli passthrough to ESC.

```bash
# Test passthrough on Motor 1
python3 serialMSP.py --port /dev/ttyUSB0 test_passthrough --channel 0

# Send custom test byte
python3 serialMSP.py --port /dev/ttyUSB0 test_passthrough --channel 1 --test-data "2f"
```

**What it does:**
- Enables Passthrough mode (msp_mode=0, mux_sel=0, mux_ch=selected)
- Sends test byte(s) to ESC (default: 0x2f = BLHeli connect)
- Listens for ESC response

**Expected results:**
- If ESC connected: Response bytes from ESC
- If no ESC: "No response received (this is normal if no ESC connected)"

### 3. Test Mode Switching (`test_modes`)
Cycles through all mode combinations.

```bash
# Test all modes with 1 second delay
python3 serialMSP.py --port /dev/ttyUSB0 test_modes

# Faster cycling (0.5s delay)
python3 serialMSP.py --port /dev/ttyUSB0 test_modes --delay 0.5
```

**What it does:**
Cycles through:
1. Passthrough Motor 1-4 (msp_mode=0)
2. MSP Mode Motor 1-4 (msp_mode=1, with FC variant queries)
3. DSHOT Mode (mux_sel=1)

Each mode change is verified and status is displayed.

### 4. Manual Mode Control (`set_mux`)
Manually set mode via MSP command 245.

```bash
# Enable BLHeli passthrough on Motor 1
python3 serialMSP.py --port /dev/ttyUSB0 set_mux --mux-sel 0 --mux-ch 0 --msp-mode 0

# Enable MSP mode on Motor 2
python3 serialMSP.py --port /dev/ttyUSB0 set_mux --mux-sel 0 --mux-ch 1 --msp-mode 1

# Enable DSHOT mode
python3 serialMSP.py --port /dev/ttyUSB0 set_mux --mux-sel 1

# Clear MSP override (zero-length payload)
python3 serialMSP.py --port /dev/ttyUSB0 set_mux --clear
```

### 5. Send MSP Command (`msp`)
Send custom MSP commands.

```bash
# Query FC variant (cmd 2)
python3 serialMSP.py --port /dev/ttyUSB0 msp --cmd 2

# Query FC version (cmd 3)
python3 serialMSP.py --port /dev/ttyUSB0 msp --cmd 3

# With hex payload
python3 serialMSP.py --port /dev/ttyUSB0 msp --cmd 10 --payload 01ff
```

### 6. Listen Mode (`listen`)
Monitor serial traffic.

```bash
# Listen as ASCII
python3 serialMSP.py --port /dev/ttyUSB0 listen

# Listen with hex output
python3 serialMSP.py --port /dev/ttyUSB0 --dump listen --hex
```

### 7. Test 4-Way Protocol (`test_4way`)
Tests the 4-way interface encapsulation used by ESC configurators.

```bash
python3 serialMSP.py --port /dev/ttyUSB0 test_4way
```

**What it does:**
- Automatically enables Passthrough mode.
- Sends 4-way sync bytes (`0x2F`) and commands.
- Verifies the FPGA responds as a 4-way translator (T9K-FC).

**Expected results:**
- Alive Response OK
- Interface Name: `T9K-FC`
- Version: `1`

## Mode Register (Address 0x0400)

The mux register controls operating mode:

| Bit | Name | Description |
|-----|------|-------------|
| [0] | mux_sel | 0=Serial modes, 1=DSHOT |
| [2:1] | mux_ch | Motor channel (0-3) |
| [3] | msp_mode | 0=Passthrough, 1=MSP protocol |

### Mode Examples

| Value | Mode | Description |
|-------|------|-------------|
| 0x00 | Passthrough Motor 1 | BLHeli tools can configure ESC on Motor 1 |
| 0x02 | Passthrough Motor 2 | BLHeli tools can configure ESC on Motor 2 |
| 0x04 | Passthrough Motor 3 | BLHeli tools can configure ESC on Motor 3 |
| 0x06 | Passthrough Motor 4 | BLHeli tools can configure ESC on Motor 4 |
| 0x08 | MSP Motor 1 | FC protocol active on Motor 1 |
| 0x0A | MSP Motor 2 | FC protocol active on Motor 2 |
| 0x0C | MSP Motor 3 | FC protocol active on Motor 3 |
| 0x0E | MSP Motor 4 | FC protocol active on Motor 4 |
| 0x01 | DSHOT | Normal flight mode (all motors) |

## Troubleshooting

### No Response from MSP Commands
- Check that FPGA firmware is loaded
- Verify serial port baud rate (115200)
- Try `--dump` flag to see raw frames
- Ensure `msp_mode=1` for MSP protocol

### BLHeli Passthrough Not Working
- Ensure `msp_mode=0` (not 1!)
- Verify ESC is powered and connected
- Check ESC signal wire to correct motor pin
- BLHeli_S requires 19200 baud (FPGA handles conversion)

### Permission Denied on Serial Port
```bash
sudo chmod 666 /dev/ttyUSB0
# Or add user to dialout group
sudo usermod -a -G dialout $USER
```

## Protocol Details

### BLHeli Protocol
- **Command-Reply pattern**: Each command gets a response
- **Packet size**: ~32 bytes maximum (each direction)
- **Baud rates**: 
  - USB UART (PC): 115200 baud
  - ESC Serial: 19200 baud (automatic conversion in FPGA)
- **Half-duplex**: Only one device transmits at a time

### MSP Protocol
- **Header**: `$M<` (to FC) or `$M>` (from FC)
- **Frame**: `$M< [size] [cmd] [payload...] [checksum]`
- **Checksum**: XOR of size, cmd, and payload bytes

## Development

Add new test modes by:
1. Adding a subparser in the `main()` function
2. Adding handler in the mode dispatch section
3. Using the `MSP()` class for protocol communication
