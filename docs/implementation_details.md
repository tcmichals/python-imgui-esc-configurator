---
title: Pico 2 Flight Controller Implementation Details
doc_type: legacy-reference
status: historical
audience:
	- human
	- ai-agent
	- developer
canonicality: supporting
subsystem: firmware
purpose: Preserve historical implementation notes, earlier pin mappings, and prior protocol explanations for reference.
related_docs:
	- ../README.md
	- README.md
	- DOC_METADATA_STANDARD.md
	- SYSTEM_HOW_IT_WORKS.md
verified_on: 2026-03-22
---

# Pico 2 Flight Controller Implementation Details

> **AI doc role:** supporting/legacy implementation context
>
> **Use this in prompts for:** historical rationale, earlier hardware mapping assumptions, protocol background
>
> **Warning:** parts of this file may predate the current bridge implementation; prefer canonical docs for active behavior

See also:

- `DOC_METADATA_STANDARD.md` — lightweight frontmatter and documentation metadata conventions

## Minimum Recommended Pinout (RP2350)
The Pico 2 (RP2350) allows flexible pin routing, but certain pins map efficiently to dedicated underlying hardware blocks without using up Programmable I/O (PIO) unnecessarily.

### Inter-Processor Link (Pi Zero 2W Host)
*Utilizes Hardware `SPI0` operating in Slave Mode.*
- **GP16** - SPI0 `RX` (MOSI - from Pi Zero)
- **GP17** - SPI0 `CSn` (Chip Select)
- **GP18** - SPI0 `SCK` (Clock)
- **GP19** - SPI0 `TX` (MISO - to Pi Zero)

### RC Receiver Inputs (PWM Decoding)
*Utilizes Hardware PWM Slices configured in Input Edge-Measurement Mode.*
- **GP0 to GP5** (Maps to PWM Slices 0, 1, and 2 independently).

### Motor Control (DSHOT600)
*Utilizes Programmable I/O (PIO).*
- **GP6 to GP9** - Motors 1 through 4 sequentially.

Operational note (desktop control path):

- DSHOT speed commands are treated as `0..2047` values.
- Values outside range are clamped into bounds.
- Motor index must be valid (`0..3`), otherwise command is rejected.
- DSHOT speed writes are blocked while passthrough mode is active.

### LED Control (NeoPixel WS2812)
*Utilizes Programmable I/O (PIO).*
- **GP10** - Data out line to the LED strip.

### ESC Telemetry / Configuration
*Utilizes Hardware `UART1` for ESC Config Passthrough half-duplex bridging.*
- **GP20 / GP21** - (RX/TX tied via resistor or configured logic for ESC single-wire protocols).

### Debugging
*Utilizes Native Hardware USB.*
- Emulates a USB CDC (Virtual COM Port) over the physical Micro-USB/USB-C connection exclusively for `printf()` serial outputs.

---

## The SPI Protocol (Master → Slave Communication)
The Pico 2 strictly adheres to the exact same little-endian byte protocol designed inside the original FPGA. The Pico 2 `SPI0` peripheral acts as the Slave, constantly polling for `0xA1` or `0xA2` commands and streaming the results back synchronously.

### Constants
```c
#define CMD_READ    0xA1
#define CMD_WRITE   0xA2
#define SYNC_BYTE   0xDA
#define PAD_BYTE    0x55
#define RESP_READ   0x21  // A1 ^ 0x80
#define RESP_WRITE  0x22  // A2 ^ 0x80
```

### The State Machine flow
All transactions are shifted by 1 byte over Full-Duplex SPI because replacing the MISO TX-buffer requires pre-loading. Any multi-byte addresses or payloads are strictly Little-Endian. Total Byte Length MUST be a multiple of 4 bytes.

**Read Example [4 bytes]:**
1. **Master TX:** `0xA1` (Read) → **Pico RX:** Prepares the `0xDA` sync flag. Let's Master know SLAVE is alive.
2. **Master TX:** `LL` `LL` (2 bytes of length) → **Pico RX:** Parses payload size.
3. **Master TX:** `AA` `AA` `AA` `AA` (4 bytes of address) → **Pico RX:** Identifies the memory-mapped register (e.g. DSHOT motor demands vs PWM inputs).
4. **Master TX:** `0x55` (Padding) → **Pico TX:** `0x21` (Valid Read response code) & length / address echoes.
5. **Master TX:** `0x55` (Padding) → **Pico TX:** Actual memory-mapped data (`0xEF`, `0xBE`, `0xAD`, `0xDE`).
6. **Master TX:** `0xDA` (Terminate).

### Architecture Abstraction
When the Pi Zero sends a `Write` command spanning `Address 0x4000_0300` (which was the FPGA `WB_DSHOT_BASE`), the Pico 2 `main.c` intercepts the transaction from the SPI FIFO, bypasses Wishbone entirely, and directly populates the `DSHOT` PIO TX FIFO buffers. From the Pi Zero's perspective, the register interface remains compatible even though the underlying implementation has changed.
