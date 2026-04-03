---
title: MSP Message Flow
doc_type: reference
status: active
audience:
	- human
	- ai-agent
	- developer
canonicality: canonical
subsystem: msp
purpose: Define expected MSP parser behavior, discovery sequence replies, and passthrough command semantics.
related_docs:
	- ../README.md
	- README.md
	- DOC_METADATA_STANDARD.md
	- BLHELI_PASSTHROUGH.md
	- CODE_DESIGN.md
verified_on: 2026-03-22
---

# MSP Message Flow (Message → Reply → Action)

> **AI doc role:** canonical MSP command/reply behavior reference
>
> **Use this in prompts for:** configurator compatibility, MSP parser behavior, discovery sequence expectations, passthrough command semantics
>
> **Treat reply tables here as implementation targets unless code has been intentionally updated**

See also:

- `DOC_METADATA_STANDARD.md` — lightweight frontmatter and documentation metadata conventions

This document defines the expected MSP behavior for this firmware during ESC configurator connection and passthrough.

## Parser states (MSP v1)

The firmware parser in `src/msp.cpp` runs this state machine:

1. `WaitDollar` expects `$`
2. `WaitMOrX` expects `M`
3. `WaitDirection` expects `<` (host to FC)
4. `WaitSizeV1` reads payload length
5. `WaitCmdV1` reads command byte
6. `WaitPayload` reads `len` payload bytes
7. `WaitCrc` validates CRC (`len ^ cmd ^ payload...`)

If CRC fails, packet is dropped and parser returns to `WaitDollar`.

## Discovery sequence (common configurator behavior)

Typical tools probe with these commands first.

| MSP Cmd | ID | Firmware reply | Action |
|---|---:|---|---|
| `MSP_API_VERSION` | 1 | 3 bytes (`0, major, minor`) | Identifies MSP API level |
| `MSP_FC_VARIANT` | 2 | 4 bytes (`BTFL`) | Identifies FC variant |
| `MSP_FC_VERSION` | 3 | 3 bytes | FC version response |
| `MSP_BOARD_INFO` | 4 | board ID payload | Board identification |
| `MSP_BUILD_INFO` | 5 | build timestamp payload | Build metadata |
| `MSP_FEATURE_CONFIG` | 36 | 4 zero bytes | Feature bitmap baseline |
| `MSP_BATTERY_STATE` | 130 | 9 zero bytes | Required by some configurator flows |

## Runtime telemetry-style requests

| MSP Cmd | ID | Firmware reply | Action |
|---|---:|---|---|
| `MSP_STATUS` | 101 | status payload | Basic FC status |
| `MSP_MOTOR` | 104 | motor payload | Motor data reply |
| `MSP_RC` | 105 | 18 channels (36 bytes) | RC channel report |
| `MSP_ANALOG` | 110 | analog payload | Analog/battery-like data |

## Passthrough entry/exit behavior

| MSP Cmd | ID | Input variants accepted | Reply | Action |
|---|---:|---|---|---|
| `MSP_SET_PASSTHROUGH` | 245 | zero-length, `0xFF`, bitfield, legacy `[mode,motor]` | 1 byte ESC count (or 0 on fail) | Enter ESC 4-way passthrough path |

### Motor index normalization

Firmware accepts either:

- `0..3` (0-based), or
- `1..4` (1-based)

Then normalizes to internal `0..3`.

## Debug serial traces

When debug UART tracing is enabled, firmware emits:

- `MSP --> ...` for host-to-FC frames
- `MSP <-- ...` for FC replies
- `ESC --> ...` for bytes written to ESC serial
- `ESC <-- ...` for bytes read from ESC serial

This is intended to mirror Python hexdump-style troubleshooting and make parser/action behavior obvious during bench debug.
