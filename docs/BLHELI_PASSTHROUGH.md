---
title: BLHeli Passthrough Transition Notes
doc_type: reference
status: active
audience:
   - human
   - ai-agent
   - developer
canonicality: canonical
subsystem: esc-passthrough
purpose: Define the required DSHOT-to-serial handoff, passthrough entry semantics, and 4-way bootloader transition context.
related_docs:
   - ../README.md
   - README.md
   - DOC_METADATA_STANDARD.md
   - MSP_MESSAGE_FLOW.md
   - PINOUT.md
verified_on: 2026-03-22
---

# BLHeli Passthrough Transition Notes (Betaflight Reference)

> **AI doc role:** canonical ESC passthrough handoff reference
>
> **Use this in prompts for:** DSHOT-to-serial transition logic, MSP passthrough compatibility, break/release timing, 4-way bootloader handoff behavior
>
> **Pair with:** `MSP_MESSAGE_FLOW.md`, `PINOUT.md`, and `CODE_DESIGN.md`

See also:

- `DOC_METADATA_STANDARD.md` — lightweight frontmatter and documentation metadata conventions

This note captures the **hardware transition details** needed for reliable ESC passthrough, and where Betaflight implements them.

## Upstream firmware and bootloader references

Use these when passthrough work requires checking how the target ESC firmware expects bootloader entry, serial handoff, or telemetry behavior.

### BLHeli / BLHeli_S

- BLHeli upstream repository: `https://github.com/bitdump/BLHeli`
- BLHeli_S source tree: `https://github.com/bitdump/BLHeli/tree/main/BLHeli_S%20SiLabs`
- BLHeli_S main source file: `https://github.com/bitdump/BLHeli/blob/main/BLHeli_S%20SiLabs/BLHeli_S.asm`
- BLHeli_S bootloader source: `https://github.com/bitdump/BLHeli/blob/main/BLHeli_S%20SiLabs/BLHeliBootLoad.inc`

### Bluejay

- Bluejay upstream repository: `https://github.com/bird-sanctuary/bluejay`
- Bluejay main source file: `https://github.com/bird-sanctuary/bluejay/blob/main/src/Bluejay.asm`
- Bluejay DShot/telemetry implementation: `https://github.com/bird-sanctuary/bluejay/blob/main/src/Modules/DShot.asm`
- Bluejay ISR/decode flow: `https://github.com/bird-sanctuary/bluejay/blob/main/src/Modules/Isrs.asm`
- Extended DShot telemetry reference: `https://github.com/bird-sanctuary/extended-dshot-telemetry`

Practical note:

- BLHeli_S source is useful for bootloader framing and flash-region expectations.
- Bluejay source is useful for DShot command handling, bidirectional telemetry, and extended telemetry behavior.
- Bluejay is not the authoritative source for MSP passthrough framing; MSP and 4-way bridging remain host/bridge-side concerns.

## Where Betaflight does this

Primary files:

- `src/main/io/serial_4way.c`
- `src/main/io/serial_4way_avrootloader.c`

Related platform plumbing (RP2040/RP2350 builds):

- `src/platform/PICO/*` (serial/USB/PIO integration)

In practice, the 4-way layer enters passthrough and the AVR/SiLabs bootloader layer handles the low-level bootloader signaling/timing.

## The critical transition sequence

The ESC line transition is not a simple “switch pin to UART.” A typical successful sequence is:

1. Quiesce/stop DSHOT on selected motor output.
2. Drive ESC signal line **LOW** for a break pulse (commonly ~100ms).
3. Release line **HIGH** briefly (idle recovery).
4. Enter half-duplex serial path and send bootloader init traffic.
5. Bridge 4-way traffic until exit.
6. Restore line idle and re-enable DSHOT ownership.

Why this matters: many ESC bootloaders require a deterministic break + release timing before they respond.

## 4-way vs ESC bootloader protocols

- PC/configurator sends **Betaflight 4-way frames** (`0x2F` sync).
- FC translates/bridges to ESC-side bootloader transport (half-duplex serial).
- ESC replies are re-encapsulated back to 4-way response frames.

So a healthy MSP handshake alone is not sufficient; the physical line handoff must succeed.

## MSP passthrough motor index semantics (important)

`MSP_SET_PASSTHROUGH` motor selection can arrive in multiple formats depending on host tool.

Current firmware behavior:

- **Zero-length payload**: enter ESC 4-way passthrough (defaults to internal motor index `0`).
- **One-byte payload = `0xFF`**: Betaflight-style ESC 4-way selector, enters passthrough (internal motor `0`).
- **One-byte bitfield format** (`mux_sel/mux_ch/msp_mode`):
   - passthrough accepted when `msp_mode=0` and `mux_sel=0`
   - `mux_ch` interpreted as motor select
- **Legacy two-byte format**: `[mode, motor]` with `mode=SerialEsc`

### Accepted motor numbering

For tool compatibility, motor values are accepted as either:

- `0..3` (**0-based**), or
- `1..4` (**1-based**)

Firmware normalizes both to internal **0-based** indices:

- ESC1 → internal motor `0`
- ESC2 → internal motor `1`
- ESC3 → internal motor `2`
- ESC4 → internal motor `3`

If an out-of-range motor is provided, passthrough entry is rejected.

## Timing values seen in references

Common values used by Betaflight-like flows:

- ESC break low pulse: ~100ms (some flows tolerate wider ranges)
- Release-high stabilization: a few ms
- Bootloader bit timing often around 19200 8N1 for BLHeli_S paths

Treat these as implementation defaults, then tune with scope/logic analyzer if needed.

## Implementation checklist for this project

- [x] Accept `MSP_SET_PASSTHROUGH` payload variants (including zero-length).
- [x] Avoid accidental passthrough exit on arbitrary binary bytes.
- [x] Add explicit line transition (LOW → HIGH) before passthrough entry.
- [x] Replace hardware UART passthrough with PIO-based serial transport for motor pins GP6..GP9.
- [ ] Confirm line polarity/level compatibility for target ESC family.
- [ ] Verify per-motor path on real wiring (ESC1..ESC4) with powered ESC.
- [ ] Validate with one powered ESC and capture line waveform during entry.

### Current implementation note

This project now uses a dedicated PIO serial bridge module:

- `src/esc_pio_uart.pio`
- `src/esc_pio_serial.cpp`

`msp.cpp` disables the selected DSHOT SM, performs break/release timing, and then bridges bytes via PIO serial on the selected motor pin.

## Why PIO serial is used vs software-coded ESC serial

In this project, ESC passthrough serial is implemented with a dedicated PIO program (`esc_pio_serial`) instead of bit-banged software UART logic.

Primary reasons:

- **Deterministic timing under load**
   - PIO shifts bits with hardware timing independent of CPU jitter.
   - This matters when Core 0 is also servicing MSP parsing, SPI tasks, and mode transitions.

- **Cleaner DSHOT↔serial ownership handoff**
   - The same motor pin is shared between DSHOT output and passthrough serial.
   - The firmware can disable the DSHOT state machine, apply break/release timing, start PIO serial, then reverse that sequence on exit with fewer race-like edge cases.

- **Reduced ISR/bit-bang fragility**
   - A software-coded UART path would rely on tight polling/interrupt timing and is more sensitive to temporary CPU contention.
   - Passthrough reliability is strongly tied to stable edge timing, especially during bootloader entry.

- **Scalable per-motor pin routing on RP2040/RP2350**
   - PIO is already central to this firmware's motor signaling strategy.
   - Reusing PIO for ESC serial keeps the low-level signal path consistent with the rest of the motor-line architecture.

Software-coded serial is still possible in principle, but for this repository's real-time split architecture (Linux offloader + controller-side deterministic I/O), PIO provides a more robust and maintainable signal path.

## Practical debug steps

1. Test with one ESC only (known-good signal/ground/power).
2. Enter passthrough and observe line on scope:
   - break low pulse present
   - release high present
   - subsequent serial activity present
3. If no response, test alternate motor channel and confirm pin mux/hardware path.
4. Compare captured timing against Betaflight reference behavior.
