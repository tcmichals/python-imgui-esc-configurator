---
title: Repository Roadmap
doc_type: roadmap
status: active
audience:
  - human
  - ai-agent
canonicality: canonical
subsystem: repository
purpose: Track implementation phases for the Python full replacement path and the follow-on Tang9K migration path.
related_docs:
  - README.md
  - PROMPTS.md
  - python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md
verified_on: 2026-03-22
---

# Roadmap

## Goal

Deliver a full Python ImGui ESC-configurator replacement first, then migrate the proven host workflow to a Tang9K-friendly stream protocol architecture.

## Phase A — Python full replacement (current priority)

1. ✅ Worker/thread foundation and passthrough controls
2. ✅ 4-way identity read path
3. ✅ Settings read/write workflow baseline (structured decode, editable fields, validation, write/confirm)
4. 🔄 Firmware catalog baseline (Bluejay GitHub releases + BLHeli_S static entries); flashing/verify still pending
5. ⏳ Serial recoverability hardening (busy/disconnect/reconnect/error classes)
6. 🔄 Usability polish + diagnostics/logging improvements (separate windows, protocol trace, Python file logging)
7. ✅ DSHOT speed control baseline (selected motor, MSP_SET_MOTOR path, passthrough safety gating, bounds clamp)

## Phase B — Unified Architecture & Tang Nano 20K (In Progress)

1. ✅ Define **100 MHz** custom stream protocol with **Hardware Framing Assist** (sync 0xA5 + Hardware CRC16)
2. 🔄 **Unified Codebase**: Refactor Pico and SERV logic into shared `src/common` via **HAL**.
3. ✅ Integrate **MSP Hardware Framing Logic** (sync $M + Hardware XOR Checksum) for high-rate passthrough
4. ✅ Port core RTL from **SPIQuadCopter** (`spi_slave`, `dshot`, `pwmDecoder`, `neoPXStrip`, `uart`)
5. ✅ Establish **Unified Build System** (Verilator + CMake + SERV Cross-Compile)
6. 🔄 **Protothreads**: Implement stackless concurrency model (`pt.h`) across both targets.
7. ⏳ End-to-end validation on **Tang Nano 20K** and **Pico**.

### Performance & Design Intent

- **Pico (P2)**: Best for complex processing and rapid software iteration. Uses dual M0+ cores and PIO for flexible but moderately jittered signal generation.
- **SERV (S)**: Best for mission-critical hardware determinism. Uses an 8-bit parallel SERV RISC-V core to orchestrate dedicated **Hardware Framing Engines**, achieving nanosecond-level I/O stability.
- **Goal**: Maintain 1:1 parity so the same application code runs on both, using the Pico for standard builds and the Tang Nano for high-performance offloading.

### Hardware migration intent notes

- **High-Performance Bridge**: This phase replaces the Pico 2 with a Tang Nano FPGA to achieve even better determinism and higher baud rates for ESC passthrough.
- **CPU Choice**: Uses an **8-bit parallel SERV** RISC-V core. This provides the right balance of simplicity and performance for high-level routing and policy.
- **Dual-Target Platform**:
  - **Tang Nano 9K** (Gowin GW1NR-9): Primary target (~31% LUT usage).
  - **Tang Nano 20K** (Gowin GW2AR-18): High-performance target (~12% LUT usage).
- **Offload Strategy**: To ensure the SERV core is not overwhelmed, all bit-level timing, sync-detection, and checksumming (CRC16/XOR) are offloaded to **Hardware Framing Engines** in the FPGA fabric.
- **Software Heritage**: The **Pico C++ codebase** remains the source of truth; hardware-specific drivers (PIO) are replaced by Wishbone-based drivers talking to the FPGA RTL.
- **RTL Inheritance**: Leverages the validated [SPIQuadCopter](file:///media/tcmichals/projects/Tang9K/HacksterIO/SPIQuadCopter) RTL for DSHOT, PWM, and base SPI Slave functionality.

## Guardrails

- Preserve Linux offloading architecture intent (high-level logic on Linux, deterministic I/O path on controller side).
- Preserve watchdog/failsafe behavior as first-class safety requirements.
- Avoid scope collapse: Python app remains a full replacement target, not a partial utility.

## Recent verified findings (for humans + AI)

- Connection flow now carries protocol mode selection (`MSP protocol` vs `Optimized protocol`) while keeping UI workflow protocol-agnostic after connect.
- DSHOT speed commands are routed through worker command path and MSP command `MSP_SET_MOTOR (214)`.
- DSHOT safety semantics are enforced in worker path:
  - speed clamped to `0..2047`
  - invalid motor index rejected
  - speed writes blocked while passthrough is active
- Python unit test suite status: full `python/unitTests` currently passing (`59 passed` at last full run in this session).

## Where to look

- Product requirements: `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`
- Prompt templates and guardrails: `PROMPTS.md`
- Repository context and architecture intent: `README.md`
