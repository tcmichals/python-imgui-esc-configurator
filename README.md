---
title: MSP Bridge Repository Guide
doc_type: guide
status: active
audience:
	- human
	- ai-agent
canonicality: canonical
subsystem: repository
purpose: Serve as the top-level entry point for repository navigation, documentation routing, and active work targets.
related_docs:
	- ROADMAP.md
	- PROMPTS.md
	- docs/README.md
	- docs/DOC_METADATA_STANDARD.md
	- python/AI_PROMPT_GUIDE.md
verified_on: 2026-03-22
---

# MSP Bridge

A multi-platform demonstration of **hardware offloading techniques** for real-time flight control, showcasing two fundamental approaches:

- **RTL Offloading**: Hardware-synthesized logic on FPGAs (Tang Nano 9K/20K)
- **PIO Offloading**: Software-programmable I/O on microcontrollers (Raspberry Pi Pico)

## Roadmap (top link)

- **Primary roadmap:** `ROADMAP.md`
- Python full-replacement product phases: `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`

## Project objective

Primary objective for this repository:

- build a **real-time Linux offloader flight-control stack** where a Linux host runs high-level/control-plane workloads, and a low-latency controller path runs through a **Tang Nano 20K/9K (Primary)** or **Pico-based** design using SPI as the deterministic host-controller data path.

In practical terms, this project combines:

- firmware-side timing-critical motor/ESC and passthrough behavior,
- a host-side transport/protocol layer,
- and a desktop tooling path (ImGui configurator) for ESC workflows.

Mission framing:

- this is an intentionally ambitious systems project aimed at improving Linux-integrated real-time controller behavior,
- and it should be evaluated by technical outcomes (determinism, latency/jitter behavior, safety/watchdog behavior, maintainability), not by whether it follows existing mainstream FC architecture conventions.

## Repository split and protocol direction

This standalone repository is focused on the **ESC configurator + host tooling path**.

The FPGA/offload implementation is now tracked in:

- **`rt-fc-offloader`**: `git@github.com:tcmichals/rt-fc-offloader.git`

Protocol strategy for this phase:

- **MSP path (current):** used to validate GUI behavior, workflow parity, and ESC feature coverage quickly.
- **FCSP path (target):** move runtime traffic to **FCSP/1** (Flight Controller Switch Protocol) for better determinism and throughput, while keeping MSP compatibility where it is still useful.

Canonical protocol spec source:

- `rt-fc-offloader/docs/FCSP_PROTOCOL.md` (single source of truth; no duplicate spec copies)

In short: MSP is our validation bridge for feature-complete GUI work; the long-term transport path is FCSP.

## Pico vs SERV Comparison

While both targets share the same **Unified App** codebase, they serve different operational roles:

| Feature           | Pico (RP2040/RP2350)      | SERV (Tang 20K / 9K)             |
| :---------------- | :------------------------ | :------------------------------ |
| **Logic Core**    | Dual Cortex-M0+/M33       | 4/8-bit Parallel RISC-V (SERV)  |
| **Determinism**   | Good (Software + PIO)      | **Perfect** (Hardware RTL + Offload) |
| **Jitter Floor**  | ~100ns (PIO based)        | **~10ns** (Hardware gated)      |
| **Best For**      | Rapid Dev, Standard Builds | High-Performance, Low-Cost FPGA |
| **Primary Strength**| Rich C++ SDK, Fast Logic | Zero-Jitter Hardware Framing    |

**Unified Architecture**: We maintain 1:1 parity between these targets using a shared C++ core and a stackless **Protothread** model. This allows developers to iterate quickly on the Pico and deploy to the Tang Nano for sub-microsecond jitter performance.

## How Offloading Works Across Platforms

This project demonstrates **custom hardware offloading** techniques for flight control timing-critical tasks:

### Pico (RP2040) - PIO-Based Offloading
- **PWM Decoding**: Uses Programmable I/O (PIO) state machines for precise pulse-width measurement
- **DSHOT Protocol**: PIO handles bidirectional DSHOT signal generation and decoding with ~100ns jitter
- **Dual-Core Utilization**:
  - **Core 0**: SPI slave communication, MSP protocol processing, motor command dispatch
  - **Core 1**: Background PWM decoding from RC receivers
- **Benefits**: Rapid development, rich SDK ecosystem, good determinism for most applications

### SERV (Tang Nano 9K/20K) - RTL-Based Offloading  
- **PWM Decoding**: Custom Verilog RTL provides hardware-accelerated pulse measurement with ~10ns precision
- **DSHOT Protocol**: FPGA logic handles full bidirectional DSHOT protocol with zero CPU involvement
- **SPI Communication**: Hardware Wishbone bridge offloads SPI slave operations
- **MSP Processing**: RISC-V core runs C++ logic with hardware-assisted framing and CRC
- **Benefits**: Perfect determinism, ultra-low jitter, ideal for high-performance FPV racing

**Cross-Platform Development**: The unified HAL abstraction layer allows the same C++ application code to run on both platforms, with platform-specific offloading implementations providing different performance characteristics.

### PIO vs RTL Offloading Breakdown

#### PIO (Programmable I/O) on Pico
PIO is Raspberry Pi's custom programmable peripheral that runs small assembly-like programs:

**PWM Decoding with PIO**:
- State machine monitors GPIO pin for rising/falling edges
- Measures pulse width using hardware timers
- Stores decoded values in FIFO for CPU access
- Handles multiple channels simultaneously
- Jitter: ~100ns (limited by CPU interrupt latency)

**DSHOT with PIO**:
- Generates precise timing for DSHOT protocol (150-300kHz)
- Handles bidirectional telemetry decoding
- Uses DMA for efficient data transfer
- CPU overhead: Minimal, mostly setup and result processing

**PIO + DMA Capabilities**:
- PIO state machines can work with RP2040's DMA controller
- Enables zero-CPU-overhead data transfer for high-throughput applications
- DMA can automatically feed PIO FIFOs or drain them to memory
- This project uses PIO with DMA for efficient DSHOT motor control

**Betaflight Pico Implementation**:
- Betaflight has experimental RP2040 support but uses traditional software timing
- Does not extensively leverage PIO + DMA for motor control
- Relies on CPU-based timing loops rather than hardware acceleration
- This project's PIO approach provides better determinism than Betaflight's Pico port

#### RTL (Register-Transfer Level) on SERV
RTL is hardware description using Verilog/VHDL synthesized into FPGA gates:

**PWM Decoding with RTL**:
- Dedicated hardware counters measure pulse widths
- Synchronous design with FPGA clock (100MHz)
- Direct register access via Wishbone bus
- Zero CPU intervention for measurement
- Jitter: ~10ns (hardware-gated, deterministic)

**DSHOT with RTL**:
- Custom Verilog modules handle protocol timing
- Hardware CRC and framing validation
- Bidirectional signal handling with FPGA I/O
- Wishbone interface for CPU control
- CPU overhead: Near zero, hardware autonomous operation

**Key Differences**:
- **PIO**: Software-programmable, flexible, good performance
- **RTL**: Hardware-synthesized, deterministic, ultra-low latency
- **Development**: PIO uses C/Python assembly, RTL uses Verilog
- **Iteration**: PIO changes require recompile, RTL requires synthesis
## Why RTL Instead of Verilog PIO on FPGA

While FPGAs can implement PIO-like programmable state machines in Verilog, this project chose **pure RTL synthesis** for several critical reasons:

### Performance Requirements
- **Flight control demands sub-10ns jitter** for motor synchronization and PWM decoding
- **PIO-style approaches still involve CPU polling** or interrupt handling, introducing latency
- **RTL provides gate-level timing control** with zero software intervention

### Determinism Goals
- **Hardware synthesis eliminates race conditions** between CPU and I/O operations
- **RTL modules run autonomously** on FPGA fabric, independent of processor load
- **Perfect timing predictability** essential for real-time motor control

### Complexity vs. Performance Trade-off
- **PIO is simpler to implement** but trades performance for ease of development
- **RTL requires HDL expertise** but delivers the determinism needed for flight control
- **This project prioritizes performance** over development simplicity for timing-critical paths

### Educational Value
- **Demonstrates both paradigms**: PIO (Pico) vs RTL (FPGA) shows different approaches to the same problem
- **Clear performance comparison**: ~100ns (PIO) vs ~10ns (RTL) jitter illustrates the benefits of hardware synthesis
- **Architecture lessons**: Shows when to choose flexibility vs. when to demand perfection

The choice reflects the project's mission: **perfect determinism for safety-critical flight control**, even at the cost of increased development complexity.
## Why offloading is needed

The offloading model is used here because flight-control-adjacent systems often have two competing needs:

- **hard timing constraints** for low-level signal generation and protocol handoff (motor outputs, ESC passthrough transitions), and
- **high-level flexibility** for richer compute, orchestration, logging, networking, and rapid iteration.

Running everything in one place forces tradeoffs. This architecture splits responsibilities so each side does what it is best at:

- **controller-side firmware path** handles deterministic, timing-sensitive I/O behavior,
- **Linux-side path** handles higher-level control-plane workloads and integration logic.

Benefits for this project:

- reduced jitter risk in timing-critical motor/ESC paths,
- cleaner isolation between real-time I/O and non-real-time application workloads,
- easier evolution of host logic without destabilizing low-level signal behavior,
- stronger observability/debugging opportunities on Linux while keeping safety-critical timing in firmware.

In short, offloading is not just about performance; it is about **predictability + maintainability** in a split real-time system.

## Why SPI instead of serial (for the offloader path)

For the real-time Linux offloader design, SPI is preferred over UART/serial for the host↔controller high-rate channel because:

- **higher sustained throughput** at typical embedded clock rates,
- **full-duplex transfers** with predictable framing cadence,
- **lower per-byte protocol overhead** for register-style transactions,
- **tighter latency and jitter control** than asynchronous serial links,
- **better fit for structured command/data frames** used by this repository's SPI protocol.

Serial/UART remains useful for specific interfaces (for example MSP/ESC passthrough compatibility), but with SPI as the preferred high-rate host↔controller transport,
- using **Hardware Framing Engines** (CRC16/XOR) and **original SPI/DSHOT RTL** to offload the CPU,
- while retaining MSP/ESC compatibility paths where needed.

## Important note: web esc-configurator and WebSerial

When using the browser-based esc-configurator workflow:

- WebSerial expects an OS-visible serial device path that the browser can enumerate and the user can grant.
- A plain TCP endpoint is **not** a WebSerial transport target.
- Linux `socat`/PTY shims can sometimes help in niche setups, but are not a reliable general replacement for a real serial device path in browser workflows.

Practical implication:

- If the web workflow is blocked by serial enumeration/permission/device behavior, the Python desktop replacement path is preferred because it can manage serial (and optionally TCP-style backends) directly without browser WebSerial constraints.

## Why this code differs from Betaflight and INAV

This repository is intentionally **not** a fork or drop-in replacement of Betaflight/INAV firmware architecture. Instead, it serves as an **educational demonstration** of advanced hardware offloading techniques for real-time systems.

Key differences:

- **System role differs**:
	- Betaflight/INAV are full flight stacks running estimator/control/navigation logic on the flight controller MCU.
	- This project is aimed at a **Linux offloader architecture** where high-level logic runs on Linux, while this firmware focuses on deterministic bridge/offload interfaces and timing-critical I/O paths.

- **Hardware offloading approaches**:
	- This repository demonstrates **two fundamentally different offloading paradigms**:
		- **RTL**: Hardware-synthesized logic (FPGA) for perfect determinism
		- **PIO**: Software-programmable I/O (microcontroller) for flexible acceleration
	- Betaflight/INAV rely on traditional MCU peripherals and software timing.

- **Scope differs**:
	- Betaflight/INAV include broad FC features (full sensor fusion, nav stacks, tuning ecosystems, etc.).
	- This codebase is deliberately narrower: MSP compatibility surfaces, ESC passthrough/4-way bridging, DSHOT/motor-line arbitration.

## Educational Value

This project serves as a **practical comparison** of hardware offloading techniques:

- **RTL Approach**: Shows how FPGA synthesis enables sub-10ns jitter with zero CPU intervention
- **PIO Approach**: Demonstrates microcontroller-based acceleration with ~100ns jitter
- **Unified Architecture**: Same application code runs on both platforms via HAL abstraction
- **Performance Trade-offs**: Clear demonstration of determinism vs. development flexibility

## Phase B — Unified Architecture & Tang Nano 20K (In Progress)

1. ✅ Define **100 MHz** custom stream protocol with **Hardware Framing Assist** (sync 0xA5 + Hardware CRC16)
2. 🔄 **Unified Codebase**: Refactor Pico and SERV logic into shared `src/common` using a **HAL** (Hardware Abstraction Layer).
3. ✅ Integrate **MSP Hardware Framing Logic** (sync $M + Hardware XOR Checksum) for high-rate passthrough
4. ✅ Port core RTL from **SPIQuadCopter** (`spi_slave`, `dshot`, `pwmDecoder`, `neoPXStrip`, `uart`)
5. ✅ Establish **Unified Build System** (Verilator + CMake + SERV Cross-Compile)
6. 🔄 **Protothreads**: Implement stackless concurrency model for shared logic across targets.
7. ⏳ End-to-end validation on **Tang Nano 20K**, **Tang Nano 9K**, and **Pico**.

### Hardware Migration Intent Notes (Phase B)

- **Platform**:
  - **Tang Nano 20K (Gowin GW2AR-18)**: High-performance target (100MHz).
  - **Tang Nano 9K (Gowin GW1NR-9)**: Resource-optimized target (60-80MHz).
  - **Raspberry Pi Pico (RP2040/RP2350)**: Reference platform for rapid development.
- **Performance Architecture**:
  - **Hardware Offload**: RTL handles Framing, CRC, and Jitter.
  - **Brains**: 8-bit parallel SERV RISC-V handles C++ logic in **16KB RAM**.
  - **Software Architecture**: Stackless **Protothreads** triggered by low-latency Interrupts.
- **RTL Inheritance**: Leverages the validated [SPIQuadCopter](file:///media/tcmichals/projects/Tang9K/HacksterIO/SPIQuadCopter) reference path.

---

## 🛠 Developer Quickstart (Phase B)

### 1. Install RISC-V Toolchain
Follow the **[Manual RISC-V Guide](docs/RISCV_TOOLCHAIN.md)** to install the xPack RISC-V GCC into `~/.tools`.

### 2. Launch Simulation
Build and run the Verilator simulation with the PTY/TCP bridge:
```bash
cmake -B build_sim -S . -DVERILATOR_SIM=ON
cmake --build build_sim --target sim_stream_framer
```

### 3. Connect Python Configurator
Attach the Python host to the simulation PTY:
```bash
python3 python/imgui_bundle_esc_config/main.py --port /dev/pts/X
```

- **Concurrency and ownership choices differ**:
	- This repository emphasizes strict ownership boundaries around passthrough vs DSHOT and host interface arbitration for predictable behavior in a split Linux+MCU architecture.

- **Tooling strategy differs**:
	- Betaflight/INAV rely on their established configurator ecosystems.
	- This project includes an evolving Python ImGui desktop configurator effort targeted to this bridge architecture and supported ESC workflows.

In short: behavior may look familiar at the MSP/ESC edges for compatibility, but the internal architecture is optimized for a different deployment model and set of constraints.

## Start here

This repository contains firmware, Python tooling, and project documentation for a **multi-platform MSP/ESC bridge** demonstrating **two hardware offloading paradigms**:

- **RTL Offloading** (Tang Nano 9K/20K): Hardware-synthesized Verilog logic for perfect determinism
- **PIO Offloading** (Pico): Software-programmable I/O state machines for flexible acceleration

Both approaches achieve the same functional goals but showcase fundamentally different implementation philosophies and performance characteristics.

See also:

- `PROMPTS.md` — copy-paste prompt templates for common firmware, passthrough, and Python ImGui tasks
- `docs/DOC_METADATA_STANDARD.md` — lightweight frontmatter and documentation metadata conventions

This top-level guide is intended for **both humans and AI coding agents**.

Use it as the first entry point when you need to:

- understand the repository layout
- find the current source-of-truth docs
- determine which subdirectory is the active implementation target
- assemble high-signal prompt context for coding or debugging

## Repository structure

### `src/`

Firmware source for the MSP bridge.

Use this area for:

- MSP command handling
- ESC passthrough logic
- 4-way protocol handling
- SPI register protocol
- DSHOT / motor-line arbitration
- **Tang20K/9K SERV Port** (Phase B)

### `docs/`

Canonical firmware/system documentation.

Primary doc hub:

- `docs/README.md`

Use `docs/` for:

- protocol definitions
- system architecture
- passthrough behavior
- pin mapping
- build instructions
- AI-friendly prompt bundles for firmware work

### `python/`

Python tooling and the new desktop ESC configurator work.

Primary Python prompt/doc hub:

- `python/AI_PROMPT_GUIDE.md`

Active target for the new desktop configurator:

- `python/imgui_bundle_esc_config/`

### `build/`

Generated build output and SDK/toolchain artifacts.

Treat as generated state, not the design source of truth.

## Current active targets

### Firmware / bridge behavior

Use these first:

- `docs/TANG9K_STREAM_PROTOCOL.md` (Design for Tang20K/9K)
- `docs/BLHELI_PASSTHROUGH.md`
- `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
- `docs/CODE_DESIGN.md`
- `docs/MSP_MESSAGE_FLOW.md`

### Python desktop ESC configurator

Use these first:

- `python/AI_PROMPT_GUIDE.md`
- `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`
- `python/imgui_bundle_esc_config/README.md`
- `https://esc-configurator.com/` as the product parity reference
- `https://github.com/stylesuxx/esc-configurator` or a local checkout only as source-code references when needed
- `https://github.com/bitdump/BLHeli/tree/main/BLHeli_S%20SiLabs` for BLHeli_S source and bootloader inspection
- `https://github.com/bird-sanctuary/bluejay` for Bluejay mainline firmware behavior, DShot, and telemetry inspection

This target should be treated as a **full desktop replacement effort** for the supported configurator workflows, not as a limited utility.

## Human workflow quick start

### If you want to build the firmware

Start with:

- `docs/4. `TANG9K_STREAM_PROTOCOL.md`
   - High-performance 90 MHz design for Tang Nano 20K/9K.
   - Dual-flow hardware hardware framing and 8-bit SERV architecture.

5. `BUILD_TUTORIAL.md`
   - Toolchain/build/flash workflow.

### If you want to understand the system

Start with:

- `docs/README.md`
- `docs/SYSTEM_HOW_IT_WORKS.md`

### If you want to work on ESC passthrough or configurator compatibility

Start with:

- `docs/BLHELI_PASSTHROUGH.md`
- `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
- `docs/MSP_MESSAGE_FLOW.md`
- `docs/CODE_DESIGN.md`
- `docs/PINOUT.md`

### If you want to work on the Python ImGui ESC configurator

Start with:

- `python/AI_PROMPT_GUIDE.md`
- `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`

## AI prompt usage

If you are an AI coding agent, use this repository with the following rules:

- prefer the canonical docs in `docs/` over legacy planning notes
- use `python/AI_PROMPT_GUIDE.md` for Python-tree routing
- use `python/imgui_bundle_esc_config/` as the default target for new desktop ESC configurator work
- preserve the two-thread UI/worker model for the ImGui configurator unless explicitly told otherwise
- treat BLHeli_S and Bluejay as first-class supported firmware families for the desktop configurator
- if code and docs disagree, inspect the code, resolve the discrepancy, and update the docs

## Recommended prompt bundles

### Firmware protocol work

Use:

- `docs/MSP_MESSAGE_FLOW.md`
- `docs/CODE_DESIGN.md`

### ESC passthrough / 4-way work

Use:

- `docs/BLHELI_PASSTHROUGH.md`
- `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
- `docs/MSP_MESSAGE_FLOW.md`
- `docs/CODE_DESIGN.md`
- `docs/PINOUT.md`

### Python ImGui ESC configurator work

Use:

- `python/AI_PROMPT_GUIDE.md`
- `python/imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`
- `python/imgui_bundle_esc_config/README.md`
- relevant firmware docs from `docs/`

## Canonicality notes

- **Canonical:** active protocol/runtime/build behavior references
- **Supporting:** useful design or implementation context
- **Legacy/Draft:** helpful background, but verify against current code and canonical docs

## Current reality check

- Firmware/bridge work is active and documented in `docs/`
- The Python ImGui ESC configurator currently has documentation and a starter app shell
- The ImGui configurator is intended to become a **full functional replacement** for the supported workflows, but it is **not yet there** until transport, worker, passthrough, 4-way, settings, and flashing workflows are implemented

## Summary

If you only read one file first, read this one.

Then:

- go to `docs/README.md` for firmware/system work
- go to `python/AI_PROMPT_GUIDE.md` for Python/ImGui configurator work
