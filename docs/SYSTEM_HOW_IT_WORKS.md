---
title: Pico MSP Bridge System Overview
doc_type: reference
status: active
audience:
    - human
    - ai-agent
    - developer
canonicality: canonical
subsystem: firmware
purpose: Explain the end-to-end system architecture, subsystem roles, and host-versus-bridge responsibilities.
related_docs:
    - ../README.md
    - README.md
    - DOC_METADATA_STANDARD.md
    - CODE_DESIGN.md
verified_on: 2026-03-22
---

# Pico 2 MSP Bridge — How It Works

> **AI doc role:** canonical system architecture reference
>
> **Use this in prompts for:** top-level system behavior, subsystem responsibilities, hardware/software data flow, host-versus-bridge roles
>
> **Pair with:** `CODE_DESIGN.md` and `BLHELI_PASSTHROUGH.md` for implementation work

See also:

- `DOC_METADATA_STANDARD.md` — lightweight frontmatter and documentation metadata conventions

This document describes the complete hardware and software architecture of the Pico 2 flight controller firmware, based on a study of the Betaflight RP2350 platform implementation and related Pico platform sources.

---

## System Overview

The Raspberry Pi Pico 2 (RP2350) replaces the FPGA (Tang Nano 20K / Arty S7) as the dedicated hardware I/O co-processor for the quadcopter. It runs a custom MSP bridge directly on bare-metal (no Linux), handling all real-time motor, LED, and receiver tasks...

```
┌────────────────────┐         SPI (10+ MHz)         ┌────────────────────────────────┐
│   Pi Zero 2W       │ ◄──────────────────────────►  │   Pico 2 (RP2350)              │
│ Running Linux/INAV │                                │   Running Betaflight (bare-metal)│
│                    │                                │                                │
│  - PID loops       │                                │  - DSHOT600 (4 motors via PIO) │
│  - Sensor fusion   │                                │  - NeoPixel (WS2812 via PIO)   │
│  - High-level nav  │                                │  - PWM Decode (HW slices)      │
│  - Mission planning│                                │  - ESC Config passthrough (USB)│
└────────────────────┘                                └────────────────────────────────┘
```

---

## Hardware Pinout

### SPI Slave (Host Link to Pi Zero 2W) — Hardware SPI0
The Pico 2 is configured as an SPI **Slave** on its dedicated hardware SPI0 block.

| GPIO | SPI0 Function | Description          |
|------|---------------|----------------------|
| GP16 | RX (MOSI)     | Data from Pi Zero    |
| GP17 | CSn           | Chip Select          |
| GP18 | SCK           | Clock from Pi Zero   |
| GP19 | TX (MISO)     | Data to Pi Zero      |

> Betaflight's `bus_spi_pico.c` initializes SPI at 20 MHz by default, supporting DMA double-buffering for TX and RX simultaneously. CPOL/CPHA mode (0 or 3) is set dynamically at runtime.

---

### Motor Outputs — DSHOT600 via PIO
Each motor uses one PIO State Machine. All 4 share a single PIO program loaded into **PIO block 0**.

| GPIO  | Motor | PIO SM |
|-------|-------|--------|
| GP6   | M1    | SM0    |
| GP7   | M2    | SM1    |
| GP8   | M3    | SM2    |
| GP9   | M4    | SM3    |

---

### RC Receiver Inputs — PWM Hardware Slices
6 channels decoded via Hardware PWM Input Edge-Capture mode (zero CPU overhead).

| GPIO | Channel |
|------|---------|
| GP0  | CH1     |
| GP1  | CH2     |
| GP2  | CH3     |
| GP3  | CH4     |
| GP4  | CH5     |
| GP5  | CH6     |

---

### LED Strip (Adafruit RGBW NeoPixel) — PIO Block 1
| GPIO | Function          |
|------|-------------------|
| GP10 | WS2812 Data Out   |

---

### ESC Configuration Passthrough — USB CDC
No dedicated GPIO pins required! ESC configuration software (BLHeli/Betaflight Configurator) connects directly via the **Pico 2's built-in USB for CDC serial (Virtual COM Port)**. The Pico internally bridges USB bytes to the motor UART hardware.

---

## How Each Subsystem Works

### 1. DSHOT600 (Motor Control)

**Source reference:** `betaflight/src/platform/PICO/dshot_pico.c` and `dshot.pio`

DSHOT600 is a digital motor protocol communicating at 600 kbaud. Each frame is exactly 16 bits:
- Bits 15–5: Throttle value (0–2047)
- Bit 4: Telemetry request
- Bits 3–0: CRC checksum

The Pico 2 implementation works in 3 layers:

**PIO Layer (dshot.pio):**
The PIO assembly program runs entirely in hardware. It sits waiting at a `pull block` instruction until the CPU writes a 32-bit packet to the TX FIFO. When data arrives, the PIO shifts out each bit at exactly the right timing:
- Logic `1` bit: HIGH for 27 cycles, LOW for 13 cycles (at DSHOT600 timing)
- Logic `0` bit: HIGH for 13 cycles, LOW for 27 cycles
- Clock divider is set dynamically based on DSHOT150 / DSHOT300 / DSHOT600 speed selection

**Bidirectional DSHOT (dshot.pio `dshot_600_bidir` program):**
After transmitting, the same PIO state machine dynamically switches its pin direction from output to input, listening for the ESC's telemetry response over the same wire. It uses `wait` instructions to catch the precise falling/rising edges (jmp pin is broken on RP2350 so `wait` is used instead). The incoming signal is oversampled at 5.56x for noise immunity, then pushed to the CPU's RX FIFO.

**C Layer (dshot_pico.c):**
The CPU prepares the 16-bit frame using `prepareDshotPacket()`, then writes it into `outgoingPacket[]`. On the 8kHz gyro loop tick, `dshotUpdateComplete()` checks the PC (program counter) of each PIO state machine to verify it's in a "safe" state (idle at instruction 0 or post-receive state 30+), then puts the packet into the PIO TX FIFO and enables all 4 SMs simultaneously via `pio_set_sm_mask_enabled()`.

#### Desktop control semantics (MSP bridge / configurator)

For desktop-side DSHOT speed controls (web-app style motor speed adjustment), the bridge/controller path follows these safety semantics:

- Accepted motor speed domain is `0..2047`.
- Out-of-range user values are **clamped** before transmit:
    - `< 0` becomes `0`
    - `> 2047` becomes `2047`
- Invalid motor index (outside `0..3`) is rejected and no command is sent.
- DSHOT speed writes are blocked while ESC passthrough is active.
- A stop action is represented as speed `0` for the selected motor.

Clamping definition used by project code:

$$
v' = \min(\max(v, 0), 2047)
$$

---

### 2. NeoPixel / WS2812 RGBW Strip

**Source reference:** `betaflight/src/platform/PICO/light_ws2811strip_pico.c`

WS2812/SK6812 LEDs are driven by a 4-instruction PIO program using **side-set** to generate precise 800kHz pulse widths:
- `T1=3, T2=3, T3=4` cycles per bit segment

Color data is held in a `led_data[]` buffer as 32-bit URGBW words. When `ws2811LedStripStartTransfer()` is called, a **DMA channel** automatically streams the entire buffer directly to the PIO TX FIFO without CPU involvement. A DMA-completion interrupt fires when the strip update is done, setting a cooldown timer (50µs minimum reset gap before the next update is accepted) to ensure the WS2812 latches correctly.

RGBW-capable strips use a 4-byte format: The white channel is reconstructed from the minimum of R, G, and B to drive the white LED element.

---

### 3. ESC Configuration Passthrough (4-Way Interface)

**Source reference:** `betaflight/src/main/io/serial_4way.c`

When the ESC Configurator (BLHeli Suite, Betaflight Configurator, etc.) connects via USB and sends the MSP `MSP_SET_PASSTHROUGH` command, the Pico enters ESC Passthrough mode:

1. The Betaflight MSP handler detects the passthrough request.
2. The firmware halts the DSHOT PIO state machine for the targeted motor.
3. The firmware reconfigures the motor output pin as a **half-duplex UART** using the hardware UART or `uart_pio.c` PIO program.
4. The USB CDC port (`serial_usb_vcp_pico.c`) forwards raw bytes to/from the ESC at whatever baud rate the configurator requests.
5. The ESC replies identically to how it would over a direct serial connection.
6. When the passthrough mode ends, the PIO DSHOT program is reloaded and motors resume.

This dynamic pin switching (DSHOT → UART → DSHOT) is the core of what the Betaflight 4-Way Interface protocol enables, and is achieved entirely in software by swapping PIO programs at runtime.

For exact transition sequencing notes (line-low/line-high bootloader handoff) and direct Betaflight source pointers, see:
- `docs/BLHELI_PASSTHROUGH.md`

#### 4-Way Protocol Commands and ACK Codes

The 4-way protocol uses `0x2F` as a host sync byte and `0x2E` as a device response sync byte. Core command IDs:

| Cmd ID | Name | Purpose |
|--------|------|---------|
| `0x30` | `cmd_InterfaceTestAlive` | Ping / keepalive |
| `0x34` | `cmd_InterfaceExit` | Close passthrough, reset pins |
| `0x35` | `cmd_DeviceReset` | Hard reset ESC MCU |
| `0x37` | `cmd_DeviceInitFlash` | Initialize flash programming mode (**must be sent first**) |
| `0x39` | `cmd_DevicePageErase` | Erase flash page |
| `0x3A` | `cmd_DeviceRead` | Read chunk from flash memory |
| `0x3B` | `cmd_DeviceWrite` | Write chunk to flash memory |
| `0x3D` | `cmd_DeviceReadEEprom` | Read settings from EEPROM (Atmel/SimonK only) |
| `0x3E` | `cmd_DeviceWriteEEprom` | Write settings to EEPROM (Atmel/SimonK only) |

ACK status codes returned in the response frame:

| Code | Name | Meaning |
|------|------|---------|
| `0x00` | `ACK_OK` | Transaction succeeded |
| `0x01` | `ACK_I_ERROR` | Interface error / sync failed |
| `0x02` | `ACK_I_INVALID_CMD` | Command not supported for this MCU/bootloader class |
| `0x03` | `ACK_VERIFY_ERROR` | Flash verification failed |
| `0x04` | `ACK_CMD_UNKNOWN` | Command not recognized by the interface |

#### Betaflight Protocol Constraint: EEPROM Commands Blocked for Silabs/ARM

> **CRITICAL**: In standard Betaflight firmware (`src/main/io/serial_4way.c`), `cmd_DeviceReadEEprom` (`0x3D`) and `cmd_DeviceWriteEEprom` (`0x3E`) are **not implemented** for Silabs (`imSIL_BLB`) or ARM (`imARM_BLB`) bootloader modes. These commands return `ACK_I_INVALID_CMD` (`0x02`).

This is the root cause of `INVALID_CMD` failures when a host tool unconditionally sends EEPROM read/write commands to a Silabs-based ESC (BLHeli_S, Bluejay) through a Betaflight flight controller.

The `serial_4way.c` switch statement handles it as follows:
- `cmd_DeviceReadEEprom` (`0x3D`): Falls through to `default`, returning `ACK_I_INVALID_CMD`.
- `cmd_DeviceWriteEEprom` (`0x3E`): Has an explicit `case` that returns `ACK_I_INVALID_CMD`.
- Only **Atmel** (`imATM_BLB`) and **SimonK** (`imSK`) bootloader modes implement these EEPROM commands.

#### Dynamic Command Routing by interfaceMode

The `cmd_DeviceInitFlash` (`0x37`) response payload contains a critical `interfaceMode` byte (byte index 3) that identifies the ESC MCU/bootloader class. The host configurator **must** inspect this byte and route read/write operations accordingly:

| interfaceMode | MCU Class | Settings Read Command | Settings Write Command |
|---|---|---|---|
| `1` (`imSIL_BLB`) | Silabs (BLHeli_S, Bluejay) | `cmd_DeviceRead` (`0x3A`) | `cmd_DeviceWrite` (`0x3B`) |
| `2` (`imATM_BLB`) | Atmel | `cmd_DeviceReadEEprom` (`0x3D`) | `cmd_DeviceWriteEEprom` (`0x3E`) |
| `3` (`imSK`) | SimonK | `cmd_DeviceReadEEprom` (`0x3D`) | `cmd_DeviceWriteEEprom` (`0x3E`) |
| `4` (`imARM_BLB`) | ARM | `cmd_DeviceRead` (`0x3A`) | `cmd_DeviceWrite` (`0x3B`) |

**JavaScript reference**: The web configurator (`esc-configurator/src/utils/FourWay.js`) implements this branching in the `getInfo` and `writeSettings` methods, reading the ESC interface mode and selecting the appropriate command path. Early Python ports missed this conditional branching and unconditionally used EEPROM commands, resulting in failures on standard Betaflight flight controllers.

#### Settings Memory Map

Silabs and ARM ESCs store configuration settings at MCU-dependent flash addresses, **not** at `0x0000`. The correct address is resolved from the MCU signature returned by `init_flash`:

| MCU Signature | MCU Name | EEPROM Offset | Page Size | Notes |
|---|---|---|---|---|
| `0xE8B1` | EFM8BB10x | `0x1A00` | 512 | BLHeli_S / Bluejay |
| `0xE8B2` | EFM8BB21x | `0x1A00` | 512 | Most common BLHeli_S / Bluejay MCU |
| `0xE8B5` | EFM8BB51x | `0x3000` | 2048 | Newer Silabs |
| `0x0000` | AM32 (ARM) | `0x7C00` | 1024 | AM32 ARM ESCs |
| `0x1F32` | AT32F421 (ARM) | `0xF800` | 1024 | AT32 variant |

Settings lengths:
| Family | Length |
|---|---|
| BLHeli_S | 48 bytes |
| Bluejay | 128 bytes |

> **Note**: Reading/writing address `0x0000` on a real Betaflight flight controller will result in `ACK_I_INVALID_CMD` (`0x02`) or a timeout. The Python desktop configurator auto-detects the correct address from the MCU descriptor table (`mcu_descriptors.py`).

#### Page Erase Before Settings Write (Silabs Only)

Silabs flash memory requires **erasing the settings page before writing**. The erase page number is calculated as:
`eepromOffset / pageSize * pageMultiplier` (where `pageMultiplier = 4` if `pageSize != 512`, else `1`).

ARM ESCs do **not** require the erase step.

#### Initialization Requirement

Before any read or write operation, the host **must** send `cmd_DeviceInitFlash` (`0x37`) to select the ESC and transition the bootloader into programming mode. A successful response returns:
- **Bytes 0-1**: MCU signature (big-endian, used for MCU descriptor lookup)
- **Byte 3**: `interfaceMode` (1=Silabs, 2=Atmel, 3=SimonK, 4=ARM)

Example: response `E8 B2 63 01` → signature `0xE8B2` (EFM8BB21x), interfaceMode `1` (Silabs).

If `init_flash` is omitted, subsequent commands will fail or time out.

---

### 4. SPI Slave Protocol (Host Communication)

**Source reference:** `betaflight/src/platform/PICO/bus_spi_pico.c` and `docs/SPI_SLAVE_WB_BRIDGE_DESIGN.md`

The Pi Zero 2W sends structured SPI frames to demand motor throttle values, configure LEDs, and read telemetry. The protocol uses a specific byte-framing to aid debugging on logic analyzers:

| Byte | Name        | Value       | Description                                  |
|------|-------------|-------------|----------------------------------------------|
| 0    | cmd         | `0xA1/0xA2` | Read or Write command                        |
| 1–2  | len         | LE uint16   | Payload length in bytes (must be multiple of 4) |
| 3–6  | addr        | LE uint32   | Target register address                      |
| 7+   | data/pad    | `0x55...`   | Write data or padding for reads              |
| last | terminator  | `0xDA`      | Frame end                                    |

The SPI is DMA-double-buffered using dedicated Pico RX and TX DMA channels initialized in `spiInitBusDMA()`. SPI clock phase (CPOL/CPHA) is configurable at runtime, supporting both Mode 0 and Mode 3 sensors/hosts.

---

### 5. Dual-Core Usage (multicore.c)

**Source reference:** `betaflight/src/platform/PICO/multicore.c`

The RP2350 has two independent 150 MHz ARM Cortex-M33 cores. Betaflight uses both:
- **Core 0**: Main flight loop, MSP processing, LED updates, USB CDC.
- **Core 1**: Offloaded tasks dispatched via an inter-core message queue (`queue_t`). Blocking or non-blocking functions can be pushed to Core 1 without halting Core 0's gyro loop.

The inter-core communication uses Pico SDK's `pico/util/queue.h` FIFO primitives which are hardware-safe across both cores without needing mutexes.

---

## Build System

The project uses CMake with the official `pico-sdk`.

```cmake
pico_sdk_init()
target_link_libraries(msp_bridge
    pico_stdlib
    hardware_spi    # SPI slave
    hardware_pwm    # PWM input decode
    hardware_pio    # DSHOT + NeoPixel
    hardware_dma    # DMA-backed SPI + LED
    hardware_uart   # ESC passthrough
)
pico_enable_stdio_usb(msp_bridge 1)  # USB Serial debug
```

To build:
```bash
mkdir build && cd build
cmake -DPICO_BOARD=pico2 ..
make -j4
```
This produces a `.uf2` file you drag onto the Pico 2's UF2 mass-storage device when in bootloader mode (hold BOOTSEL button while plugging in USB).
