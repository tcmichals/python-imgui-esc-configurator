---
title: Project Tasks & Roadmap
doc_type: task-tracker
status: active
audience:
  - human
  - ai-agent
  - developer
canonicality: canonical
subsystem: repository
purpose: Track high-level strategic roadmap phases, design intents, and top-level implementation/validation tasks.
related_docs:
  - README.md
  - docs/README.md
  - docs/MSP_MESSAGE_FLOW.md
  - docs/CODE_DESIGN.md
  - imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md
verified_on: 2026-06-17
---

# Top-Level Tasks & Roadmap

Use this file as the single high-level tracker for the repository roadmap phases and active tasks.

## High-Level Roadmap

### Phase A — Python Full Replacement (Current Priority)
1.  [x] Worker/thread foundation and passthrough controls
2.  [x] 4-way identity read path
3.  [x] Settings read/write workflow baseline (structured decode, editable fields, validation, write/confirm)
4.  [x] Firmware catalog baseline (Bluejay GitHub releases + BLHeli_S static entries)
5.  [x] Serial recoverability hardening (busy/disconnect/reconnect/error classes)
6.  [x] Usability polish + diagnostics/logging improvements (separate windows, protocol trace, Python file logging)
7.  [x] DSHOT speed control baseline (selected motor, MSP_SET_MOTOR path, passthrough safety gating, bounds clamp)
8.  [x] Local firmware file picker (Browse...) and flashing/verify pipeline
9.  [ ] Multi-ESC batch flash UX validation with real hardware
10. [ ] Validate optimized-mode runtime behavior beyond discovery handshake

### Phase B — Unified Architecture & Tang Nano 20K (In Progress)
1.  [x] Define **100 MHz** custom stream protocol with **Hardware Framing Assist** (sync 0xA5 + Hardware CRC16)
2.  [ ] **Unified Codebase**: Refactor Pico and SERV logic into shared `src/common` via **HAL**.
3.  [x] Integrate **MSP Hardware Framing Logic** (sync $M + Hardware XOR Checksum) for high-rate passthrough
4.  [x] Port core RTL from **SPIQuadCopter** (`spi_slave`, `dshot`, `pwmDecoder`, `neoPXStrip`, `uart`)
5.  [x] Establish **Unified Build System** (Verilator + CMake + SERV Cross-Compile)
6.  [ ] **Protothreads**: Implement stackless concurrency model (`pt.h`) across both targets.
7.  [ ] End-to-end validation on **Tang Nano 20K** and **Pico**.

### Phase C — Asyncio & Scalability
1.  [x] **Full Kernel Asyncio Transition**: Refactor the entire `WorkerController` (the backend kernel) and transport layers to use `asyncio`.
2.  [ ] **High-Rate Telemetry**: Leverage `asyncio` to handle high-bandwidth telemetry streams from the FPGA without blocking the UI or worker logic.

---

## Performance & Design Intent

- **Pico (P2)**: Best for complex processing and rapid software iteration. Uses dual M0+ cores and PIO for flexible but moderately jittered signal generation (~100ns jitter floor).
- **SERV (S)**: Best for mission-critical hardware determinism. Uses an 8-bit parallel SERV RISC-V core to orchestrate dedicated **Hardware Framing Engines**, achieving nanosecond-level I/O stability (~10ns jitter floor).
- **Goal**: Maintain 1:1 parity so the same application code runs on both, using the Pico for standard builds and the Tang Nano for high-performance offloading.

### Hardware Migration Intent Notes
- **High-Performance Bridge**: This phase replaces the Pico 2 with a Tang Nano FPGA to achieve even better determinism and higher baud rates for ESC passthrough.
- **CPU Choice**: Uses an **8-bit parallel SERV** RISC-V core. This provides the right balance of simplicity and performance for high-level routing and policy.
- **Dual-Target Platform**:
  - **Tang Nano 9K** (Gowin GW1NR-9): Primary target (~31% LUT usage).
  - **Tang Nano 20K** (Gowin GW2AR-18): High-performance target (~12% LUT usage).
- **Offload Strategy**: To ensure the SERV core is not overwhelmed, all bit-level timing, sync-detection, and checksumming (CRC16/XOR) are offloaded to **Hardware Framing Engines** in the FPGA fabric.
- **Software Heritage**: The **Pico C++ codebase** remains the source of truth; hardware-specific drivers (PIO) are replaced by Wishbone-based drivers talking to the FPGA RTL.
- **RTL Inheritance**: Leverages the validated SPIQuadCopter RTL for DSHOT, PWM, and base SPI Slave functionality.

---

## Active Task List

### Next 3 Tasks (Active Sprint)
1. [x] Add offline cache startup UX tests (missing/corrupt snapshot scenarios) in Python unit suite.
2. [x] Debug why MSP passthrough is failing to send serial messages (GUI shows red error dialog, logic analyzer shows no traffic).
3. [ ] Complete full Python suite + update tracker statuses; then execute Pico/Tang smoke checklist.
4. [ ] Validate real hardware multi-ESC flash/cancel/recover behavior and capture screenshots on Windows.

### 0) Immediate priorities (current)
- [x] Debug MSP passthrough serial protocol start issue (GUI red error dialog)
- [ ] Finalize MSP Python readiness for Pico + Tang mode aliases
  - [x] Confirm protocol-mode aliases (`optimized`, `optimized_tang9k`, Tang20K aliases) map predictably
  - [x] Confirm MSP discovery/probe coverage aligns with `docs/MSP_MESSAGE_FLOW.md`
  - [ ] Verify no regressions in passthrough, settings read/write, and flash flows
- [ ] Add screenshots section in README (Windows + Linux examples)
- [ ] Keep docs stable while planning source reorg
  - [ ] Create source-tree migration map (old path -> new path)
  - [ ] Define phased move plan with build/test gate per phase

### 1) Firmware / hardware contract tasks
- [ ] MSP command contract parity
  - [ ] API/variant/version/board/build/status/motor/uid/feature/battery/rc/analog behavior documented and validated
  - [ ] Passthrough entry/exit motor index semantics verified (0-based + 1-based normalization where applicable)
- [ ] DSHOT arbitration and safety
  - [ ] Enforce DSHOT blocked during passthrough
  - [ ] Verify resume-delay and idle-exit timing behavior
  - [ ] Validate latest-value-wins motor mailbox behavior under burst input
- [ ] Tang path integration readiness
  - [ ] Confirm optimized transport selection path is explicit and traceable in logs
  - [ ] Define acceptance criteria for full non-MSP optimized transport handoff (future)

### 2) Python configurator tasks
- [ ] MSP worker robustness
  - [ ] Expand error categorization for transport-fatal vs recoverable failures
  - [ ] Ensure discovery/probe steps degrade gracefully when partial commands fail
- [ ] UI parity hardening
  - [ ] Compact-layout regression coverage where harness allows
  - [ ] Offline cache startup UX coverage (missing/corrupt cache scenarios)
- [ ] Asyncio Kernel Transition (Phase C)
  - [x] Implement `AsyncWorkerController` with `pyserial-asyncio`
  - [x] Establish **Thread-Safe Bridge** (`call_soon_threadsafe`) for UI/Kernel boundary
  - [x] Implement multiplexed dispatcher for solicited vs unsolicited frames
  - [x] Port MSP, 4-Way, and FCSP clients to async
  - [x] Establish Performance Test Bench (`tests/benchmark_async.py`)
  - [ ] Integrate into main `app.py` as default backend
  - [ ] Final hardware validation on Tang Nano 20K

### 3) Documentation tasks
- [ ] Add and maintain canonical requirements docs
  - [x] `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md` (new)
  - [ ] Keep `docs/MSP_MESSAGE_FLOW.md`, `docs/CODE_DESIGN.md`, and `docs/BLHELI_PASSTHROUGH.md` synchronized
- [ ] Add migration notes for any source-tree refactor
  - [ ] Track moved files and updated include/import paths
  - [ ] Link migration notes from `docs/README.md`

### 4) Verification tasks
- [ ] Software verification
  - [ ] Run full Python test suite before each mergeable checkpoint
  - [ ] Keep worker-focused regression tests green
- [ ] Hardware smoke tests (after coding checkpoints)
  - [ ] Pico: connect/disconnect, passthrough enter/exit, read settings, flash one ESC, cancel/recover
  - [ ] Tang: equivalent flow on selected transport mode with protocol trace capture

### 5) Definition of Done (project checkpoint)
A checkpoint is complete only when all are true:
- [ ] Code changes implemented for scoped tasks
- [ ] Unit/integration tests pass
- [ ] Docs updated for behavior changes
- [ ] No unresolved errors in touched files
- [ ] Hardware smoke pass completed (for hardware-affecting changes)

---

## Guardrails
- Preserve Linux offloading architecture intent (high-level logic on Linux, deterministic I/O path on controller side).
- Preserve watchdog/failsafe behavior as first-class safety requirements.
- Avoid scope collapse: Python app remains a full replacement target, not a partial utility.
