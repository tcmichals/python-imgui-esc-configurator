---
title: Repository Prompt Templates
doc_type: prompt-templates
status: active
audience:
	- human
	- ai-agent
canonicality: canonical
subsystem: repository
purpose: Provide copy-paste prompt templates for common firmware, passthrough, Python, and documentation tasks.
related_docs:
	- ROADMAP.md
	- README.md
	- docs/README.md
	- docs/DOC_METADATA_STANDARD.md
	- python/AI_PROMPT_GUIDE.md
verified_on: 2026-03-22
---

# Prompt Templates

## Roadmap (top link)

- **Repository roadmap:** `ROADMAP.md`
- 4. `TANG9K_STREAM_PROTOCOL.md`
   - High-performance **90 MHz** design for Tang Nano 20K (Primary) and 9K.
   - Dual-flow hardware framing, 8-bit SERV, and **Verilog PIO** architecture options.
- 5. `BUILD_TUTORIAL.md`
   - Toolchain/build/flash workflow.
- Python full-replacement phase details: `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`

This file provides **copy-paste prompt templates** for common work in this repository.

Use `README.md` as the repo-wide start point.
Use `docs/README.md` for firmware/system documentation.
Use `python/AI_PROMPT_GUIDE.md` for Python-tree routing.

## Project-intent guardrail (use in prompts)

When prompting for architecture, firmware, or tooling changes, preserve this intent:

- this project targets a **better Linux-integrated real-time flight-controller architecture**,
- using an offloading split (Linux control-plane + deterministic controller-side I/O path),
- with SPI as the preferred high-rate host↔controller transport,
- while retaining MSP/ESC compatibility paths where needed.

**Educational Focus**: This repository demonstrates **two hardware offloading paradigms**:
- **RTL**: Hardware-synthesized logic (FPGA) for perfect determinism
- **PIO**: Software-programmable I/O (microcontroller) for flexible acceleration

Prompt snippet you can paste when needed:

> Keep the implementation aligned with the repository mission: improve Linux-integrated real-time flight-control behavior via a split offloading architecture.
> Do not collapse the design back into a monolithic single-domain model unless explicitly requested.
> This project serves as an educational demonstration of RTL vs PIO offloading techniques.

## Multi-Platform Offloading Context

This repository demonstrates **custom hardware offloading** across different platforms. Include this context in prompts involving firmware or hardware implementation:

### Pico (RP2040) - PIO Offloading
- Uses Programmable I/O for PWM decoding and DSHOT protocol
- Dual-core: Core 0 handles SPI/MSP, Core 1 handles PWM background tasks
- ~100ns jitter floor, good for rapid development

### SERV (Tang Nano) - RTL Offloading  
- FPGA fabric provides hardware RTL acceleration for PWM/DSHOT
- RISC-V core with Wishbone bus for SPI/MSP processing
- ~10ns jitter floor, perfect determinism

### Unified Architecture
- Same C++ application code runs on both platforms
- HAL abstraction layer hides platform differences
- SPI register protocol provides unified host interface

### Offloading Implementation Details

#### PIO (Pico) - Software-Programmable Hardware
- Uses Raspberry Pi PIO for PWM/DSHOT offloading
- C code with embedded PIO assembly programs
- DMA Integration: Uses RP2040 DMA controller for zero-CPU data transfer
- ~100ns jitter, good for most applications
- Fast development iteration
- Betaflight Comparison: Betaflight Pico port uses software timing, not PIO + DMA

#### RTL (SERV) - Hardware-Synthesized Logic
- Verilog HDL synthesized into FPGA gates
- Custom modules for PWM/DSHOT timing
- ~10ns jitter, perfect determinism
- Requires FPGA synthesis for changes
- **Why RTL over Verilog PIO**: Chosen for sub-10ns jitter requirements in flight control, prioritizing performance over development simplicity

Prompt snippet for implementation work:

> Consider the offloading approach: PIO uses programmable state machines in C, RTL uses Verilog hardware description. PIO offers flexibility with ~100ns jitter, RTL provides ~10ns hardware determinism. Choose based on performance requirements and development workflow. On FPGA, RTL was selected over PIO-style approaches for perfect timing control in safety-critical motor operations.

Prompt snippet for implementation work:

> Consider the offloading approach: PIO uses programmable state machines in C, RTL uses Verilog hardware description. PIO offers flexibility with ~100ns jitter, RTL provides ~10ns hardware determinism. Choose based on performance requirements and development workflow.

Prompt snippet for platform-aware work:

> This is a multi-platform project with Pico (PIO offloading) and SERV (RTL offloading) targets. Ensure changes maintain cross-platform compatibility through the HAL layer and consider the different offloading approaches when implementing timing-critical features.
> Preserve deterministic I/O ownership and watchdog/failsafe behavior as first-class safety requirements.

## WebSerial limitation guardrail (important)

When prompting around web esc-configurator compatibility:

- WebSerial requires an OS-visible serial device path the browser can enumerate and user-authorize.
- Plain TCP endpoints are not WebSerial targets.
- PTY/socat shims may help in niche setups but are not a reliable general replacement for real serial device behavior in browser workflows.

Prompt snippet you can paste when needed:

> If the web workflow is blocked by WebSerial/device-enumeration behavior, prioritize the Python desktop path and avoid assuming raw TCP can be used directly by the browser app.

## How to use this file

- Start with the template closest to your goal.
- Include the referenced docs in the prompt context when possible.
- Prefer the canonical docs over legacy/draft docs.
- For behavior/spec questions, **docs drive code**: treat canonical requirements docs as authoritative and align code to them.
- If requirements are outdated, update requirements docs first (or in the same change), then update code.

## Firmware protocol work

Use with:

- `docs/MSP_MESSAGE_FLOW.md`
- `docs/CODE_DESIGN.md`

Template:

> Work in the firmware under `src/`.
> Use `docs/MSP_MESSAGE_FLOW.md` and `docs/CODE_DESIGN.md` as the primary references.
> Preserve existing protocol compatibility unless the task explicitly requires a protocol change.
> Make small, testable changes, validate build/errors after edits, and update docs if behavior changes.

## ESC passthrough / 4-way debugging

Use with:

- `docs/BLHELI_PASSTHROUGH.md`
- `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
- `docs/MSP_MESSAGE_FLOW.md`
- `docs/CODE_DESIGN.md`
- `docs/PINOUT.md`

Template:

> Investigate ESC passthrough and BLHeli 4-way behavior in this repository.
> Use `docs/BLHELI_PASSTHROUGH.md`, `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`, `docs/MSP_MESSAGE_FLOW.md`, `docs/CODE_DESIGN.md`, and `docs/PINOUT.md` as primary references.
> Find the root cause first, preserve motor-line ownership rules, and avoid moving passthrough/DSHOT ownership across threads or cores without strong justification.
> After changes, validate behavior and update the documentation if behavior changed.

## Firmware architecture / refactor work

Use with:

- `docs/SYSTEM_HOW_IT_WORKS.md`
- `docs/CODE_DESIGN.md`
- `docs/architecture.md`
- `docs/implementation_details.md`

Template:

> Refactor or extend the firmware architecture in this repository.
> Focus on the **Unified Codebase** vision: provide 1:1 parity between the **Pico (RP2040)** and **SERV (Tang Nano)** targets.
> **Requirements**:
> - **HAL-Driven**: Use `src/hal/hal.h` for all hardware interaction. Do NOT use platform-specific SDK headers (e.g. `pico/stdlib.h`) in `src/common`.
> - **Protothreads**: Use stackless Protothreads (`pt.h`) for concurrency in the unified app logic.
> - **Performance Logic**: 
>   - **Pico**: Standard software logic + PIO for flexible development.
>   - **SERV**: 8-bit parallel RISC-V orchestrating FPGA-based **Hardware Framing Engines**.
> Use `docs/SYSTEM_HOW_IT_WORKS.md` and `docs/CODE_DESIGN.md` as canonical references.
> Preserve deterministic I/O, watchdog/failsafe semantics, and clear ownership boundaries.

## Python ImGui ESC configurator implementation

Use with:

- `python/AI_PROMPT_GUIDE.md`
- `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`
- `python/imgui_bundle_esc_config/README.md`
- `python/imgui_bundle_esc_config/PROMPT.md`
- `python/imgui_bundle_esc_config/WEBAPP_FEATURE_CACHE.md`
- relevant docs from `docs/`

Template:

> Work in `python/imgui_bundle_esc_config`.
> Use `python/AI_PROMPT_GUIDE.md` and `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md` as the primary requirements and routing docs.
> This app must become a full desktop replacement for `https://esc-configurator.com/`.
> Treat it as a full replacement project for the supported workflows, not as a partial reimplementation or a companion utility.
> Keep the app aligned with the repository architecture: Linux-integrated offloader workflow, deterministic worker-side transport/protocol ownership, and safety-focused watchdog/failsafe expectations.
> Account for browser WebSerial limitations: plain TCP cannot be used directly by the web app as a serial replacement.
> If a task is scoped to one milestone, keep that milestone aligned with the full-replacement roadmap rather than redefining the product scope.
> Use the source code at `https://github.com/stylesuxx/esc-configurator`, or a local clone of that repository, only as a secondary implementation reference when deeper parity investigation is required.
> When researching firmware-family behavior, use authoritative upstream sources such as `https://github.com/bitdump/BLHeli/tree/main/BLHeli_S%20SiLabs`, `https://github.com/bitdump/BLHeli/blob/main/BLHeli_S%20SiLabs/BLHeliBootLoad.inc`, `https://github.com/bird-sanctuary/bluejay/blob/main/src/Bluejay.asm`, and `https://github.com/bird-sanctuary/bluejay/blob/main/src/Modules/DShot.asm`.
> Preserve the two-thread architecture: ImGui UI thread plus worker/protocol thread.
> Support BLHeli_S and Bluejay, retain support for local firmware loading alongside web-based firmware download, implement the next smallest complete milestone, and validate syntax and tests after edits.

## Python transport / MSP debugging

Use with:

- `python/AI_PROMPT_GUIDE.md`
- `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
- `docs/MSP_MESSAGE_FLOW.md`
- `docs/BLHELI_PASSTHROUGH.md`
- `docs/CODE_DESIGN.md`

Template:

> Investigate Python-side transport, MSP, or passthrough behavior for the ImGui ESC configurator.
> Use `python/AI_PROMPT_GUIDE.md`, `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`, `docs/MSP_MESSAGE_FLOW.md`, `docs/BLHELI_PASSTHROUGH.md`, and `docs/CODE_DESIGN.md` as primary references.
> Keep serial ownership in the worker thread, avoid moving protocol logic into the UI thread, explain the root cause before patching, and verify the resulting behavior.

## Python tests

Use with:

- `python/unitTests/`
- target Python modules
- `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md` when relevant

Template:

> Add or update Python tests for this repository.
> Focus on protocol helpers, worker state transitions, parsing, compatibility checks, and transport behavior.
> Avoid GUI-heavy tests unless logic is separated cleanly from the UI layer.
> Keep tests targeted and maintainable.

## Documentation cleanup / AI-friendly docs

Use with:

- `README.md`
- `docs/README.md`
- `python/AI_PROMPT_GUIDE.md`
- target docs to update

Template:

> Improve the repository documentation for both humans and AI coding agents.
> Preserve technical accuracy, make canonical vs supporting vs legacy status explicit, and add concise prompt-friendly guidance without duplicating too much content.
> Validate markdown changes and keep links/navigation coherent.

## Quick reminders for prompts

- Mention the exact target directory.
- Mention the canonical docs to use.
- State whether parity with an external/local reference app is required.
- State whether behavior must be preserved or may change.
- Ask for validation after edits.

## Summary

This file is a convenience layer.

For full context:

- start at `README.md`
- use `docs/README.md` for firmware/system work
- use `python/AI_PROMPT_GUIDE.md` for Python/ImGui work
