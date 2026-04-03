---
title: Python Directory AI Prompt Guide
doc_type: prompt-guide
status: active
audience:
	- human
	- ai-agent
canonicality: canonical
subsystem: python
purpose: Route humans and AI agents to the correct Python subtree, active target, and prompt context.
related_docs:
	- ../README.md
	- ../PROMPTS.md
	- ../docs/DOC_METADATA_STANDARD.md
	- imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md
verified_on: 2026-03-22
---

# Python Directory — AI Prompt Guide

See also:

- `../README.md` — top-level repository guide for both humans and AI agents
- `../docs/DOC_METADATA_STANDARD.md` — lightweight frontmatter and documentation metadata conventions

## Purpose

This file is a **prompt-oriented guide** for AI coding agents working inside the `python/` tree.

Use it to quickly determine:

- which Python subdirectory is the active target
- which files are canonical for the ImGui ESC configurator replacement
- which Python tools are legacy/supporting utilities
- how to compose high-signal prompts for implementation or debugging

## Educational Context

This repository demonstrates **two fundamental hardware offloading paradigms**:

- **RTL Offloading**: Hardware-synthesized Verilog logic on FPGAs (perfect determinism, ~10ns jitter)
- **PIO Offloading**: Software-programmable I/O on microcontrollers (flexible acceleration, ~100ns jitter)

The Python tools interact with both approaches through a unified MSP/serial interface, allowing comparison of performance characteristics across offloading techniques.

## Directory intent summary

### `imgui_bundle_esc_config/`

**Primary active target** for new desktop ESC configurator work.

Treat this as the repository's **full replacement target** for `https://esc-configurator.com/` within the supported scope. It is not a side utility or a reduced-scope demo target.

Use this directory for:

- the full `esc-configurator` desktop replacement
- ImGui Bundle UI work
- serial/MSP transport implementation
- BLHeli 4-way protocol client logic
- BLHeli_S and Bluejay support
- firmware catalog download/cache logic

Canonical docs in this subtree:

- `imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`
- `imgui_bundle_esc_config/README.md`
- `imgui_bundle_esc_config/PROMPT.md`
- `imgui_bundle_esc_config/WEBAPP_FEATURE_CACHE.md`

### `MSP/`

Supporting scripts and notes for MSP communication experiments.

Use this directory for:

- MSP framing examples
- serial communication experiments
- testing reference material

### `comm_proto/`

Supporting Python protocol/helpers area.

Use when protocol helpers already exist and can be reused, but verify contents before assuming completeness.

### `unitTests/`

Python-side regression and behavior tests.

Use for:

- validating protocol helpers
- transport behavior tests
- integration test additions for new Python code when practical

## Platform Awareness for Python Tools

The Python tooling in this repository interacts with **multi-platform firmware targets** that demonstrate different hardware offloading approaches:

### Pico (RP2040/RP2350) Target
- **Offloading Method**: PIO (Programmable I/O) for PWM/DSHOT
- **Architecture**: Dual Cortex-M0+ cores
  - Core 0: SPI slave, MSP processing, motor dispatch
  - Core 1: Background PWM decoding
- **Python Interaction**: SPI register protocol, MSP passthrough
- **Development Focus**: Rapid iteration, rich SDK ecosystem

### SERV (Tang Nano 9K/20K) Target  
- **Offloading Method**: RTL (Verilog) hardware acceleration
- **Architecture**: 4/8-bit parallel RISC-V core with FPGA fabric
- **Python Interaction**: SPI register protocol, hardware framing assist
- **Development Focus**: Ultra-low jitter, perfect determinism

### Cross-Platform Considerations
- **Unified Protocol**: Same SPI/MSP interface across platforms
- **Performance Differences**: SERV provides ~10ns jitter, Pico ~100ns
- **Python Code**: Transport layer should be platform-agnostic
- **Testing**: Validate on both platforms when possible

### PIO vs RTL Implementation Details

#### PIO (Pico Implementation)
- **PWM**: PIO state machines with edge detection and timing measurement
- **DSHOT**: PIO programs for protocol timing and bidirectional handling
- **DMA Integration**: Uses RP2040 DMA controller for zero-CPU data transfer
- **Development**: C code with embedded PIO assembly, fast iteration
- **Limitations**: ~100ns jitter from CPU interrupt handling
- **Betaflight Comparison**: Betaflight Pico port uses software timing, not PIO + DMA

#### RTL (SERV Implementation)  
- **PWM**: Verilog modules with synchronous counters and registers
- **DSHOT**: Custom Verilog state machines for protocol handling
- **Development**: Verilog HDL with synthesis, slower iteration
- **Advantages**: ~10ns hardware determinism, zero CPU load
- **Why RTL not PIO**: Chosen for sub-10ns jitter requirements over PIO's simpler but less deterministic approach

When implementing platform-specific features, understand these fundamental differences in offloading approaches.

When implementing Python tools, consider how they will interact with both offloading architectures and ensure transport code remains portable.

If the user asks for the Python ESC configurator, the default target should be:

- `python/imgui_bundle_esc_config/`

Unless explicitly requested otherwise, new feature work for the desktop configurator should go there.

## AI implementation rules

When working in the Python tree, prefer these rules:

- use `imgui_bundle_esc_config/` for new desktop configurator code
- treat `imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md` as the authoritative behavior spec (**specs drive code**)
- if behavior changes, update `DESIGN_REQUIREMENTS.md` first (or in the same change) and only then adjust code
- treat the ImGui configurator as a full replacement project, not as a partial helper tool
- keep the ImGui app structured and modular rather than growing a monolithic `app.py`
- follow the two-thread model for UI + worker/protocol execution
- keep serial/MSP/4-way ownership in the worker thread
- do not let worker code call ImGui APIs directly
- preserve local file firmware loading in addition to any web download flow
- treat BLHeli_S and Bluejay as first-class supported families
- remember WebSerial/browser constraints for the web reference flow: plain TCP is not a direct WebSerial replacement path
- prefer the native Python full-replacement path for delivery; treat webapp TCP-bridge work as a later optional integration effort unless explicitly prioritized

## Prompt bundles

### Prompt bundle: implement ImGui ESC configurator features

Use these files first:

- `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`
- `python/imgui_bundle_esc_config/README.md`
- `docs/BLHELI_PASSTHROUGH.md`
- `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
- `docs/MSP_MESSAGE_FLOW.md`
- `docs/CODE_DESIGN.md`
- `docs/PINOUT.md`

Suggested prompt framing:

- implement the next milestone in `python/imgui_bundle_esc_config`
- treat the application as a full replacement for the supported workflows of `https://esc-configurator.com/`
- scope work by replacement phase, but preserve the full-replacement end state
- preserve the two-thread architecture
- keep parity with `https://esc-configurator.com/`
- support BLHeli_S and Bluejay
- prefer incremental, testable modules

When deeper parity or compatibility investigation is needed, also consult:

- BLHeli upstream repo: `https://github.com/bitdump/BLHeli`
- BLHeli_S source tree: `https://github.com/bitdump/BLHeli/tree/main/BLHeli_S%20SiLabs`
- BLHeli_S bootloader source: `https://github.com/bitdump/BLHeli/blob/main/BLHeli_S%20SiLabs/BLHeliBootLoad.inc`
- Bluejay upstream repo: `https://github.com/bird-sanctuary/bluejay`
- Bluejay main source: `https://github.com/bird-sanctuary/bluejay/blob/main/src/Bluejay.asm`
- Bluejay DShot/telemetry code: `https://github.com/bird-sanctuary/bluejay/blob/main/src/Modules/DShot.asm`
- Bluejay ISR/decode flow: `https://github.com/bird-sanctuary/bluejay/blob/main/src/Modules/Isrs.asm`
- Extended DShot telemetry reference: `https://github.com/bird-sanctuary/extended-dshot-telemetry`

### Prompt bundle: debug MSP or passthrough issues

Use these files first:

- `docs/MSP_MESSAGE_FLOW.md`
- `docs/BLHELI_PASSTHROUGH.md`
- `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
- `docs/CODE_DESIGN.md`
- `src/msp.cpp`
- `src/esc_4way.cpp`
- `src/esc_passthrough.cpp`
- relevant Python transport files in `python/imgui_bundle_esc_config/`

Suggested prompt framing:

- debug why the Python app cannot enter passthrough or complete 4-way traffic
- compare expected MSP flow against current bridge behavior
- preserve worker-thread transport ownership

### Prompt bundle: add Python tests

Use these files first:

- `python/unitTests/`
- target Python module(s)
- `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md` if testing the new configurator logic

Suggested prompt framing:

- add focused unit/integration tests for protocol encoding, worker state transitions, or firmware catalog parsing
- avoid GUI-heavy tests unless logic can be separated cleanly

## Copy-paste prompt templates

### Template: build the next ImGui milestone

> Work in `python/imgui_bundle_esc_config`.
> Use `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md` as the primary requirements document.
> Treat requirements/specifications as the driver and code as the implementation artifact.
> This app must become a full desktop replacement for `https://esc-configurator.com/`.
> Scope the work to the next replacement phase, but do not redefine the product into a reduced-scope tool.
> Use local or upstream source code only as an implementation aid when deeper parity investigation is needed.
> When firmware-family internals matter, prefer authoritative upstream sources such as `https://github.com/bitdump/BLHeli/tree/main/BLHeli_S%20SiLabs` and `https://github.com/bird-sanctuary/bluejay` rather than guessing from secondary summaries.
> Preserve the two-thread design: ImGui UI thread plus worker/protocol thread.
> Support BLHeli_S and Bluejay.
> Implement the next smallest complete milestone with modular code, update docs as needed, and validate syntax/tests after changes.

### Template: debug Python transport behavior

> Investigate Python-side transport behavior for the ImGui ESC configurator.
> Use `docs/MSP_MESSAGE_FLOW.md`, `docs/BLHELI_PASSTHROUGH.md`, and `docs/CODE_DESIGN.md` as protocol/runtime references.
> Keep serial ownership in the worker thread, do not move protocol work into the UI thread, and explain the root cause before patching.
> If the issue stems from browser WebSerial limitations, prioritize native Python transport handling rather than trying to force raw TCP into a web serial workflow.

### Template: extend firmware download support

> Extend the firmware catalog/download subsystem in `python/imgui_bundle_esc_config`.
> Keep support for both local firmware file loading and remote catalog download.
> Preserve compatibility checks before flash and treat BLHeli_S and Bluejay as first-class targets.

## What not to do

- do not assume the TUI code is the desired final UI
- do not implement a blocking single-thread GUI unless explicitly requested
- do not remove safety checks around flash/write flows
- do not assume only one ESC is present
- do not treat draft docs as implemented behavior without checking code

## Recommended next Python milestones

1. establish the transport and worker shell
2. add MSP passthrough control and ESC discovery
3. implement settings read/write parity
4. implement firmware catalog, local import, and flash/verify workflows
5. complete multi-ESC handling, diagnostics, and operational polish

These milestones are phases toward a full replacement, not independent end states.

## Summary

For AI work in the Python tree:

- target `imgui_bundle_esc_config/` for the new desktop configurator
- use `DESIGN_REQUIREMENTS.md` as the main product/architecture doc
- pair it with firmware/runtime docs from `docs/`
- treat TUI/MSP scripts as supporting references, not the final destination
- preserve the full-replacement objective even when implementing one phase at a time
