---
title: Pico MSP Bridge Code Design
doc_type: design
status: active
audience:
  - human
  - ai-agent
  - developer
canonicality: canonical
subsystem: firmware
purpose: Describe runtime ownership, arbitration, mailbox behavior, passthrough lifecycle, and key implementation responsibilities.
related_docs:
  - ../README.md
  - README.md
  - DOC_METADATA_STANDARD.md
  - SYSTEM_HOW_IT_WORKS.md
  - MSP_MESSAGE_FLOW.md
verified_on: 2026-03-22
---

# Unified Architecture & Code Design

> **AI doc role:** Canonical reference for the Hardware Abstraction Layer (HAL) and Unified Logic.
>
> **Design Pattern:** The same high-level application logic (MSP, 4-Way, DShot policy) runs on both **Pico (RP2040)** and **SERV (RISC-V)** by targeting a common `hal.h` interface.

## 1) High-level architecture

The firmware is split into three distinct layers to ensure 1:1 parity across hardware targets:

- **App Layer (`src/common`)**: Platform-agnostic C++ logic. Uses **stackless Protothreads** (`pt.h`) to manage concurrency without the overhead of an RTOS.
- **HAL Layer (`src/hal`)**: A unified C interface (`hal.h`) that abstracts hardware-specific peripherals (Timers, GPIO, SPI, UART, DShot).
- **Driver Layer**: Platform-specific implementations of the HAL:
  - **Pico Driver (`src/pico/hal_pico.cpp`)**: Uses RP2040 SDK, PIO, and DMA.
  - **SERV Driver (`firmware/hal_serv.cpp`)**: Uses Wishbone memory-mapped registers and FPGA Hardware Framing Engines.

Design goal: The **App Layer** should never include platform-specific headers. All I/O occurs through the HAL.

## 2) Message queue vs mailbox behavior

### Motor overrides use a mailbox (latest-value-wins)

Implementation: `src/msp.cpp`

- Incoming `MSP_SET_MOTOR` writes a `MotorOverrideMessage` into a single shared slot (`motor_override_mailbox`) and marks it valid.
- Main loop consumes using:
  - `msp_motor_override_pop_latest(unsigned short *out_values, unsigned char motor_count, unsigned int *out_update_us32)`
- Behavior:
  - **Not FIFO**
  - Newer command overwrites older command
  - Best fit for motor control where freshness is more important than preserving every intermediate value

## 3) Motor output arbitration (single source of truth)

Implementation: `src/main.cpp`

`MotorLineMode` controls final source for each motor update:

- `PassthroughBlocked` -> force stop (`dshot_force_stop_all`)
- `MspOverride` -> MSP slider values mapped via `msp_slider_to_dshot`
- `SpiLive` -> use SPI motor commands
- `FailsafeStale` -> output zero throttle

Key helpers:

- `determine_motor_line_mode(...)`
- `resolve_motor_output(...)`

Timing source is centralized in `src/timing_config.h`.

## 4) MSP protocol pipeline

Implementation: `src/msp.cpp`

Supports:

- MSP v1 (`$M<...`)
- MSP v2 (`$X<...`)
- MSP v2-in-v1 encapsulation (`cmd=255` wrapper)

Key commands handled:

- `API_VERSION (1)`
- `FC_VARIANT (2)`
- `FC_VERSION (3)`
- `BOARD_INFO (4)`
- `BUILD_INFO (5)`
- `FEATURE_CONFIG (36)`
- `STATUS (101)`
- `MOTOR (104)`
- `BATTERY_STATE (130)`
- `UID (160)`
- `SET_MOTOR (214)`
- `SET_PASSTHROUGH (245)`

Compatibility notes:

- `MSP_STATUS` payload is Betaflight-style length expected by ESC Configurator read flow.
- `MSP_MOTOR` returns legacy-compatible 4-motor payload (8 bytes).

## 5) ESC passthrough lifecycle

### Entry

- Triggered by `MSP_SET_PASSTHROUGH`.
- `esc_passthrough_begin(motor)`:
  - marks passthrough active
  - disables target motor DSHOT SM
  - performs line transition sequence
  - starts PIO half-duplex serial on motor pin

### Active mode

- `msp_task` routes to `esc_4way_task` while passthrough is active.
- 4-way frames are parsed/handled in `src/esc_4way.cpp`.

### Exit

- Explicit via 4-way interface exit command, or
- Auto-exit after idle timeout (`timing_config::PassthroughIdleExitUs`) when no real 4-way frames are seen.

`esc_passthrough_end()`:

- stops PIO serial
- restores pin function to PIO0 DSHOT
- resets/clears DSHOT SM state
- blocks DSHOT for cooldown (`timing_config::DshotResumeDelayUs`)

## 6) Debug levels and metrics

Implementation: `src/msp.cpp`, API in `src/msp.h`

Runtime debug levels:

- `0 = Off`
- `1 = Basic`
- `2 = Verbose`

Control API:

- `msp_set_debug_level(uint8_t level)`
- `msp_get_debug_level(void)`

Custom MSP command:

- `253` sets debug level from first payload byte, replies with active level.

Protocol counters:

- `msp_get_crc_error_count()`
- `msp_get_v2_crc_error_count()`
- `msp_get_passthrough_begin_ok_count()`
- `msp_get_passthrough_begin_fail_count()`
- `msp_get_passthrough_auto_exit_count()`
- `msp_get_unhandled_cmd_count()`

## 7) Shared timing configuration

Implementation: `src/timing_config.h`

Contains centralized constants for:

- watchdog and DSHOT frame cadence
- passthrough idle-exit and DSHOT resume delay
- USB startup timing

This avoids duplicated timing literals across modules.

## 8) Key files and responsibilities

- `src/main.cpp` — Core0 orchestration, arbitration, DSHOT scheduling
- `src/msp.cpp` / `src/msp.h` — MSP parser, command handlers, mailbox, counters/debug control
- `src/esc_passthrough.cpp` / `.h` — mode switch and motor-line state ownership
- `src/esc_4way.cpp` / `.h` — BLHeli 4-way frame engine
- `src/esc_pio_serial.cpp` — half-duplex serial transport over motor line
- `src/dshot.cpp` / `.h` — DSHOT packet generation and PIO write path
- `src/spi_slave.cpp` / `.h` — host bridge SPI register protocol
- `src/timing_config.h` — global timing constants

## 9) Current known behavior

- MSP and passthrough are functional with ESC Configurator.
- System auto-exits passthrough after 4-way idle timeout.
- Motor control path uses mailbox semantics for latest-command priority.
