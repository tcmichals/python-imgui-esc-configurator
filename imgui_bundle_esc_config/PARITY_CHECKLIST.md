---
title: ImGui vs Web 1:1 Parity Checklist
doc_type: parity-checklist
status: active
audience:
  - human
  - ai-agent
canonicality: canonical
subsystem: imgui-esc-config
purpose: Track feature-by-feature parity between the web esc-configurator flow and the Python ImGui desktop replacement.
related_docs:
  - DESIGN_REQUIREMENTS.md
  - WEBAPP_FEATURE_CACHE.md
  - PROMPT.md
verified_on: 2026-04-03
---

# 1:1 Parity Checklist (Web → ImGui)

## Rules

- `DESIGN_REQUIREMENTS.md` is the source of truth for behavior.
- This checklist is the execution tracker for parity status.
- Any feature marked ✅ must have code + tests aligned.

Status legend:

- ✅ complete
- 🔄 in progress
- ⏳ missing

## Connection / session

- ✅ Port detect + manual override + connect/disconnect
- ✅ Protocol mode choice (MSP / optimized)
- ✅ Connection status in UI
- ✅ Web-like bottom health bar polish
  - ✅ Mode (`MSP` / `ESC Serial`)
  - ✅ MSP usage %
  - ✅ MSP error %
  - ✅ MSP message rate
  - ✅ Color-coded connection dot + structured two-row layout

## ESC link / passthrough

- ✅ Primary `Read Settings` flow
- ✅ Auto-enter passthrough on selected ESC target
- ✅ Explicit `Exit Passthrough` in active passthrough mode
- ✅ Clear ESC target selection (`Target ESC for Read Settings`)
- ✅ Multi-ESC batch flash (Flash All ESCs in one click)
- ✅ ESC stabilization delay (1.2 s after auto-enter passthrough, matching web app)
- ✅ Multi-ESC scan/read sequencing edge cases

## DSHOT / motor control

- ✅ DSHOT hidden while passthrough active
- ✅ Separate per-motor sliders (no master coupling)
- ✅ Safety gating (`SAFE` / `ARMED`)
- ✅ Dynamic motor count from FC reply
- ✅ Web-like slider range behavior
  - ✅ web source confirmed 1000..2000
  - ✅ ImGui sliders now use 1000..2000 UI range
  - ✅ UI range policy aligned to requirements and web parity

## Settings workflow

- ✅ EEPROM read + decoded settings table
- ✅ Editable baseline fields (enum/bool/number)
- ✅ Write + verify path
- ✅ Bluejay STARTUP_MELODY field (128-byte, read-only raw bytes display)
- ✅ Bluejay STARTUP_MELODY_WAIT_MS field (2-byte editable uint16)
- ✅ Descriptor/rules parity
  - ✅ conditional visibility parity (3D-mode, dynamic-PWM gating)
  - ✅ sanitize/validation parity (Bluejay threshold ordering enforced)
  - ✅ LOW_RPM_POWER_PROTECTION + STARTUP_BEEP + RAMPUP_RPM_POWER_PROTECTION added (safety/beacon groups)
  - ✅ Settings table grouped by category with collapsible headers

## Firmware workflow

- ✅ Firmware catalog baseline
- ✅ End-to-end flash/verify UX parity
  - ✅ worker flash init/erase/write/verify/reset baseline
  - ✅ local-file flashing baseline with compatibility gating + progress
  - ✅ remote image download path from catalog selection
  - ✅ multi-ESC batch flash (Flash All N ESCs)
- ✅ Full compatibility gating parity
- ✅ Local-file + remote-flow parity polish
- ✅ Local firmware file picker (Browse… button)

## Diagnostics / logs

- ✅ Operator log window
- ✅ Protocol trace window (MSP/4WAY/Tang9K)
- ✅ Export/log-bundle parity
  - ✅ ui_logs + protocol_traces + session_metadata in timestamped folder
  - ✅ session_metadata includes decoded settings snapshot (family/layout/revision/count)
  - ✅ session_metadata includes firmware flash history + flash-all summary
  - ✅ session_metadata includes firmware catalog loaded state

## Testing parity

- ✅ Worker-focused regression suite active
- ✅ Add explicit parity tests for bottom MSP metrics and mode transitions
- ✅ Add feature-level parity tests for full settings + firmware flows

## Current priority queue

1. Verify bottom-bar readability under constrained window widths and long status strings
2. Expand UI-level regression coverage for compact-layout rendering decisions (where harness support allows)
3. Run hardware-in-the-loop smoke pass for multi-ESC flash/cancel/recover flows
4. Add focused offline-snapshot UX tests for missing/corrupt cache startup flows
