# AI System Prompt: Phase B (Tang Nano 20K Migration)

## Project Context
This project is migrating the flight controller bridge from a Raspberry Pi Pico to a **Tang Nano 20K FPGA** (Gowin GW2AR-18). The core objective is to create a high-performance, deterministic Linux-offloader bridge using an **8-bit parallel SERV RISC-V core**.

## Architectural Requirements [MANDATORY]
1.  **System Clock**: **100 MHz**. All RTL and firmware must target this frequency.
2.  **Processor**: **SERV RISC-V** in **4-bit parallel mode** (`WIDTH=4`).
3.  **Unified Codebase**: 1:1 functional parity between the **Pico (RP2040)** and **SERV (Tang Nano)** targets.
4.  **Hardware Abstraction Layer (HAL)**: All high-level logic in `src/common` MUST use `src/hal/hal.h`. Do NOT use platform-specific SDK headers in common code.
5.  **Hardware Offloading**:
    *   **Hardware CRC Engine**: `rtl/crc/crc16_xmodem.v` (Polynomial 0x1021) handles all stream validation.
    *   **Hardware Framing**: Dedicated RTL in `rtl/framing/` handles sync detection (`0xA5`, `$M`) and length tracking.
    *   **Interrupt-Driven**: The SERV core only processes packets after the framing engine validates the CRC/Checksum.
6.  **Software Architecture**:
    *   **Protothreads**: Use lean, stackless C++ Protothreads (`pt.h`) for asynchronous task management (MSP/ESC interaction).
    *   **Deterministic ISRs**: Keep Interrupt Service Routines under 20 cycles; use them only to signal the Protothreads.
6.  **Memory**: Use **4KB+ Block RAM FIFOs** for the Stream path to ensure zero data loss at 100 MHz.
7.  **RTL Inheritance**: Reuse the validated modules in `rtl/` (ported from `SPIQuadCopter`):
    *   `spi_slave`, `dshot`, `pwmDecoder`, `neoPXStrip`, `verilog-uart`.

## Repository Structure
- **`rtl/`**: Verilog/SystemVerilog sources for the FPGA fabric.
- **`firmware/`**: SERV firmware (C++), ported from the original `src/` directory.
- **`sim/`**: Verilator-based C++ testbench environment with **`SimBridge.h`** (PTY/TCP support).
- **`docs/`**: Canonical system and protocol documentation (see **`SIM_BRIDGE.md`**).

## Primary Documentation
- **`docs/TANG9K_STREAM_PROTOCOL.md`**: The source of truth for the binary framing and hardware-offloading specs.
- **`docs/SIMULATION_BRIDGE.md`**: Setup and usage guide for the Python <=> Verilator bridge.
- **`docs/RISCV_TOOLCHAIN.md`**: Manual installation guide for the xPack RISC-V GCC toolchain.
- **`docs/DESIGN_PHASE_B.md`**: Comprehensive design specification for the Tang 20K migration.
- **`ROADMAP.md`**: Tracking Phase B goals and progress.

## AI Guardrails
- **Preserve Offloading**: Never move "math" (CRC, Checksum) or "bit-timing" (DSHOT, Sync) into the SERV core; these MUST remain in RTL.
- **Software Style**: Prefer Protothreads over C++20 coroutines to minimize RAM and cycle overhead on the 8-bit parallel SERV.
- **32-bit Alignment**: All host-to-FPGA packets must be padded to **4-byte boundaries** to allow the 8-bit SERV to use 32-bit Wishbone transactions for data movement.
- **Better/Faster**: Prioritize simulation speed (Verilator) and hardware determinism over architectural simplicity.
