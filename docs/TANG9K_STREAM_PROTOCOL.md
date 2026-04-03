# Tang9K Stream Protocol (Draft v1)

This document defines an optimized binary stream used between desktop tooling and Tang9K firmware for high-rate telemetry and runtime logging.

Target implementation note: this v1 profile is designed for a **SERV RISC-V core** (8-bit parallel mode) at **80-100 MHz** on the **Tang Nano 20K** (GW2AR-18), with compatibility for the Tang Nano 9K.

## Goals

- Keep framing compact and fast to parse.
- Support incremental byte-stream decoding with robust resynchronization.
- Provide a dedicated FC runtime log channel (not multiplexed into MSP).
- Preserve room for future message types and transport options.

## Transport assumptions

- Byte-stream transport (USB CDC, UART, TCP tunnel, etc.).
- No transport-level packet boundaries are assumed.
- Stream parser must handle arbitrary chunking.

## Frame layout

All multi-byte fields are big-endian.

| Field | Size | Description |
|---|---:|---|
| `sync` | 1 | Constant `0xA5` |
| `version` | 1 | Protocol version, currently `1` |
| `flags` | 1 | Bitfield (see below) |
| `channel` | 1 | Logical stream channel |
| `seq` | 2 | Sequence number (`0..65535`, wraps) |
| `payload_len` | 2 | Number of payload bytes |
| `payload` | N | Channel-specific bytes |
| `crc16` | 2 | CRC16/XMODEM over `version..payload` (excludes `sync`) |

Total bytes per frame = `1 + 1 + 1 + 1 + 2 + 2 + payload_len + 2`.

### v1 performance profile (8-bit parallel SERV @ 80-100 MHz)

- **Primary Platform**: **Tang Nano 20K** (Gowin GW2AR-18).
- **CPU Mode**: Target the **8-bit bit-parallel SERV core** (`WIDTH=8`). This provides ~20-25 MIPS at 100 MHz.
- **Hardware Framing Offload**: All sync detection (`0xA5`), length tracking, and **CRC16/XMODEM** calculation MUST be handled in RTL (Hardware Framing Engine).
- **Memory Optimization**: Use large **Block RAM FIFOs (at least 4KB)** for the RX/TX paths to ensure zero data loss during high-rate telemetry bursts.
- **Interrupt Mode**: The SERV core should only be interrupted when a **validated, complete frame** is present in the RX FIFO.
- **32-bit Alignment**: All frames sent from the Python host should be **padded to 4-byte boundaries**. This allows SERV to use fast 32-bit Wishbone transactions for data movement.
- **Batching**: Host should batch multiple small MSP commands into a single Stream Frame to minimize interrupt overhead.

## Flags

- `0x01` = ACK requested
- `0x02` = ACK response
- `0x04` = error indication
- Remaining bits reserved for future use.

## Channels

- `0x01` CONTROL — commands/replies for Tang9K-side control plane
- `0x02` TELEMETRY — high-rate sensor/state stream
- `0x03` FC_LOG — controller-originated runtime logs/events
- `0x04` DEBUG_TRACE — verbose protocol/debug dumps
- **`0x05` ESC_SERIAL** — raw raw MSP/4-way serial tunnel for ESC configuration

## FC_LOG payload (v1)

## ESC_SERIAL payload (v1)

The ESC_SERIAL channel acts as a transparent tunnel for MSP data:

| Field | Size | Description |
|---|---:|---|
| `esc_id` | 1 | Destination ESC ID (1-4) or bitmask |
| `raw_msp` | N | Raw MSP/4-Way packet bytes |

**Note**: The Python host ensures total `payload_len` (including padding) is a multiple of 4 bytes.

## Resynchronization behavior

Receiver should:

1. Scan for `sync` (`0xA5`).
2. Validate header and `payload_len` against configured maximum.
3. Wait for full frame bytes.
4. Validate CRC16/XMODEM.
5. On CRC or decode failure, advance by one byte and continue scanning.

## Leveraging existing PIO path

This repository already contains PIO UART programs (`src/esc_pio_uart.pio`, `src/dshot.pio`).
Tang9K integration can reuse the same architectural idea:

- Hardware/Pio-like block handles byte capture/shift timing.
- SERV firmware consumes bytes from a FIFO and runs the frame FSM + CRC.
- Optional TX path can enqueue already-built frames to a byte shifter without bit-level software timing.

That split keeps SERV focused on protocol semantics instead of tight serial timing loops.

### Resource Budget (Tang Nano 20K & 9K)

| Component | Est. LUTs | Notes |
|---|---|---|
| **SERV (8-bit parallel)** | ~1,000 | Conservative for `WIDTH=8` |
| **SPI Slave + WB Bridge** | ~300 | From `SPIQuadCopter` |
| **Hardware Framing Engine** | ~500 | Sync, Length, CRC16/XMODEM offload |
| **DSHOT + PWM Drivers** | ~400 | Reused RTL peripherals |
| **Verilog PIO (Optional)** | ~1,500 | Flexible software-timed I/O |
| **Wishbone / FIFOs** | ~500 | Interconnect and dual-port buffers |
| **Total** | **~3,000-4,200** | **~15-20% of Tang 20K** |

### Architecture Option: Verilog PIO vs. Dedicated RTL

For Phase B, we can leverage two different offloading models for I/O:

1. **Dedicated RTL (Recommended for High-Rate)**: Reusing the `spi_slave`, `dshot`, and `pwmDecoder` RTL from the local [SPIQuadCopter](file:///media/tcmichals/projects/Tang9K/HacksterIO/SPIQuadCopter) path. This provides the highest deterministic performance and lowest power at 90 MHz.
2. **Verilog PIO (Flexible Extension)**: Using an FPGA-based PIO (similar to the RP2040 PIO). This allows the SERV core to load small state-machine assembly programs to handle arbitrary timing-sensitive protocols without changing the FPGA bitstream.

The Tang Nano 20K has enough LUTs to easily support **both** simultaneously.

## Can this be done with PIO only (no SERV)?

Short answer: **yes for fixed/streamlined behaviors**, but **not ideal** for feature growth (rich diagnostics, adaptive parsing, retries, and complex policy).

### PIO-only architecture (feasible path)

- Use state machines for RX/TX byte timing and framing boundaries.
- Use PIO FIFOs for data movement into host-visible registers.
- Add small RTL helpers (non-CPU):
	- CRC16/XMODEM unit
	- frame length tracker / sync scanner
	- simple channel arbiter
	- status/error counters

This is effectively a hardware protocol engine with no firmware CPU loop.

### What PIO-only does well

- Deterministic I/O timing.
- Very low software overhead.
- Great for stable frame formats and repetitive high-rate traffic.

### What becomes painful without a CPU

- Dynamic policy changes (e.g., changing retry/timeout rules by channel).
- Complex log filtering/rate limiting logic.
- On-device diagnostics formatting and richer metadata decisions.
- Evolving protocol versions and backward-compat negotiation.

### Recommended compromise

For this project, the most robust path remains:

- PIO/RTL for precise I/O + framing primitives
- tiny control-plane firmware (SERV or equivalent) for policy/state/error handling

If you choose full PIO-only, keep protocol scope narrow (fixed channels, fixed payload caps, simple ACK policy) so the hardware state machine remains maintainable.

## Logging parity expectations

Desktop diagnostics should print directional and channel-aware traces:

- `TANG9K -> CH=FC_LOG SEQ=... LEN=...: <HEX>`
- `TANG9K <= CH=FC_LOG SEQ=... LEN=...: <HEX>`

FC log events should be rendered with decoded source/level/timestamp where possible.

## Compatibility notes

- MSP remains for compatibility/control workflows.
- Tang9K stream is preferred for continuous runtime diagnostics and high-rate telemetry.
- Future versions can extend channels/payload schemas while preserving base framing.
