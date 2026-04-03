---
title: MSP and DSHOT Hardware Requirements
doc_type: requirements
status: active
audience:
  - human
  - ai-agent
  - developer
canonicality: canonical
subsystem: esc-passthrough
purpose: Define practical throughput budgets, timing constraints, and implementation guardrails for MSP passthrough and DSHOT coexistence on Pico and SERV targets.
related_docs:
  - ../README.md
  - README.md
  - MSP_MESSAGE_FLOW.md
  - CODE_DESIGN.md
  - BLHELI_PASSTHROUGH.md
  - TANG9K_STREAM_PROTOCOL.md
verified_on: 2026-04-03
---

# MSP and DSHOT Hardware Requirements

> **AI doc role:** canonical runtime budget + guardrail reference for passthrough and motor-output coexistence.
>
> **Use this in prompts for:** throughput feasibility (60/100 MHz), passthrough stability, FIFO/ISR sizing, and arbitration constraints.

See also:

- `MSP_MESSAGE_FLOW.md` — parser behavior and command/reply expectations
- `CODE_DESIGN.md` — arbitration and lifecycle ownership
- `BLHELI_PASSTHROUGH.md` — line handoff timing and bootloader behavior

## 1) Scope and assumptions

This document focuses on the hot path where:

- MSP command traffic enters the bridge,
- `MSP_SET_PASSTHROUGH` enables ESC serial tunneling,
- DSHOT output must be blocked or resumed safely,
- runtime remains deterministic under load.

Primary assumptions:

- ESC-side passthrough transport often operates around **115200 8N1** in legacy flows.
- Host/control links may be faster (CDC/UART/TCP), but the ESC wire speed is typically the practical limiter for tunnel throughput.
- SERV path should prefer hardware framing/FIFO offload for sustained reliability.

## 2) Throughput feasibility: 100 MHz vs 60 MHz

### Practical verdict

- **100 MHz SERV (8-bit parallel):** comfortable margin for MSP passthrough + diagnostics.
- **60 MHz SERV (8-bit parallel):** still viable for passthrough if hot path is kept minimal and framing/checksum work stays in hardware.

### Why 60 MHz is still acceptable

At 115200 baud, byte rate is roughly:

$$
\frac{115200}{10} \approx 11{,}520 \text{ bytes/s}
$$

Even with protocol framing overhead, this is modest relative to a 60 MHz control core when:

- interrupts are frame- or watermark-driven (not per-byte),
- copies are bounded and contiguous,
- no expensive parsing/log formatting is done in the tunnel fast path.

## 3) Hard guardrails (must not regress)

1. **Single ownership of motor lines**
   - DSHOT and passthrough must never actively drive the same line at once.
   - Enforce `esc_passthrough_begin()` / `esc_passthrough_end()` sequencing.

2. **DSHOT blocked during passthrough**
   - No speed writes applied while passthrough is active.
   - Resume only after configured cooldown delay.

3. **Opaque tunnel behavior**
   - Treat 4-way/MSP bytes as payload in hot path.
   - Avoid deep decode/formatting on critical path.

4. **No per-byte logging in production path**
   - Use counters/rate-limited telemetry instead.

5. **No dynamic allocation in tunnel hot path**
   - Preallocate buffers/FIFOs.

## 4) Recommended buffer and interrupt policy

### FIFO sizing

- Prefer **>= 4 KB RX and >= 4 KB TX** buffering for SERV high-rate/host-burst tolerance.
- At minimum, size FIFOs to absorb burst windows during temporary CPU unavailability.

### IRQ policy

- Prefer interrupt on:
  - complete validated frame, or
  - FIFO watermark / DMA completion,
- Avoid IRQ-per-byte designs.

### Parsing policy

- Hardware framing engine should handle:
  - sync detection,
  - length tracking,
  - checksum/CRC validation,
- CPU handles only semantic dispatch and state transitions.

## 5) Minimal slimmed passthrough protocol profile (recommended)

For ESC serial tunnel channel, keep framing compact and stable:

- fixed sync/version
- channel id (`ESC_SERIAL`)
- payload length
- raw payload bytes
- integrity check (hardware-assisted where available)

Keep the profile intentionally narrow:

- fixed payload caps,
- simple ACK/error policy,
- no feature creep into fast path.

## 6) Validation checklist for 60 MHz deployment

- [ ] Passthrough enter/exit succeeds repeatedly on all motors.
- [ ] No DSHOT activity while passthrough active.
- [ ] No dropped tunnel frames under sustained settings read/write loops.
- [ ] CRC/checksum error rate remains stable under host burst traffic.
- [ ] Latency tails acceptable during simultaneous status polling + passthrough.
- [ ] Auto-exit idle timeout and DSHOT resume delay behave deterministically.

## 7) Instrumentation requirements

Expose and watch these counters during bench runs:

- passthrough begin success/fail counts,
- passthrough auto-exit count,
- MSP CRC/v2 CRC error counts,
- RX/TX FIFO high-water marks,
- tunnel frame drop/overflow counts.

If 60 MHz fails stress validation, first actions are:

1. increase FIFO depth,
2. reduce logging/trace volume,
3. increase batching / reduce IRQ frequency,
4. move any remaining byte-work into hardware path.

## 8) Relationship to existing docs

- Use this document for **budget and limits**.
- Use `MSP_MESSAGE_FLOW.md` for command semantics.
- Use `CODE_DESIGN.md` for ownership/arbitration behavior.
- Use `BLHELI_PASSTHROUGH.md` for line transition details.
