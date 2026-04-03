---
title: Pinout Reference
doc_type: reference
status: active
audience:
	- human
	- ai-agent
	- developer
canonicality: canonical
subsystem: firmware
purpose: Define the active GPIO, transport, and debug-pin mappings for the bridge firmware.
related_docs:
	- ../README.md
	- README.md
	- DOC_METADATA_STANDARD.md
	- SYSTEM_HOW_IT_WORKS.md
	- BLHELI_PASSTHROUGH.md
verified_on: 2026-03-22
---

# Pinout Reference (`pico-msp-bridge`)

> **AI doc role:** canonical GPIO and transport mapping reference
>
> **Use this in prompts for:** hardware wiring, board bring-up, passthrough pin ownership, debug-probe separation, host/target USB questions
>
> **Do not invent alternate pin mappings without explicit user approval**

See also:

- `DOC_METADATA_STANDARD.md` — lightweight frontmatter and documentation metadata conventions

This document summarizes the active firmware pin mapping for **Raspberry Pi Pico (RP2040)** and **Raspberry Pi Pico 2 (RP2350)**.

## Quick answer

For this project, the runtime GPIO mapping is currently the **same on Pico and Pico 2**.

---

## SPI host link (Pi Zero 2W ↔ Pico)

Uses **SPI0 slave**.

| GPIO | SPI0 Role | Direction (Pico view) | Purpose |
|---|---|---:|---|
| GP16 | RX / MOSI | In  | Data from host |
| GP17 | CSn       | In  | Chip select |
| GP18 | SCK       | In  | SPI clock |
| GP19 | TX / MISO | Out | Data to host |

---

## DSHOT motor outputs (PIO0)

From `src/dshot.h`.

| Motor | GPIO |
|---|---|
| ESC1 / M1 | **GP6** |
| ESC2 / M2 | GP7 |
| ESC3 / M3 | GP8 |
| ESC4 / M4 | GP9 |

---

## RC PWM inputs

From `src/pwm_decode.h`.

| Channel | GPIO |
|---|---|
| CH1 | GP0 |
| CH2 | GP1 |
| CH3 | GP2 |
| CH4 | GP3 |
| CH5 | GP4 |
| CH6 | GP5 |

---

## NeoPixel output

From `src/neopixel.h`.

| Function | GPIO |
|---|---|
| NeoPixel data out | GP10 |

---

## USB / MSP / Configurator transport

MSP frame parsing uses stdio (`getchar_timeout_us`, `putchar_raw`) in `src/msp.cpp`, so whichever stdio backend is enabled in CMake carries MSP traffic.


### Probe vs target serial ports

When using **picoprobe**, keep these transports separate:

- **Probe `/dev/ttyACM*`** = the probe's own USB serial/UART bridge.
- **Target `/dev/ttyACM*`** = the target Pico's USB CDC device, available only if the **target board's USB port is also connected to the host**.

For this firmware as currently configured:

- **MSP / configurator traffic uses the target Pico USB CDC port**.
- **Debug trace output uses the probe UART bridge on GP4/GP5**.

So if Linux shows only one ACM device and it belongs to the probe, that does **not** mean the target MSP USB port is up. The configurator must connect to the **target** USB CDC device, not the probe ACM port.

---

## Optional debug UART note

For picoprobe SWD+UART debug, this project's MSP/ESC trace output is configured for:

- **Target UART1 TX:** GP4
- **Target UART1 RX:** GP5
- **Baud:** 115200 8N1

Recommended probe wiring:

- Probe GND → Target GND
- Probe GP2 → Target SWCLK
- Probe GP3 → Target SWDIO
- Probe GP4 (TX) → Target GP5 (RX)
- Probe GP5 (RX) → Target GP4 (TX)

⚠ **Important:** GP4/GP5 are also RC input channels CH5/CH6 in this firmware. During UART debug capture, treat CH5/CH6 as unavailable (or remap RC inputs for debug builds).

---

## Board notes

### Pico (RP2040)
- Uses the GPIO assignments above directly.

### Pico 2 (RP2350)
- Uses the same GPIO assignments in this project.
- Be sure your board definition and wiring match the same GP numbers.

---

## Source of truth in repo

- `src/dshot.h`
- `src/pwm_decode.h`
- `src/neopixel.h`
- `src/spi_slave.cpp`
- `docs/SYSTEM_HOW_IT_WORKS.md`
- `docs/implementation_details.md`
