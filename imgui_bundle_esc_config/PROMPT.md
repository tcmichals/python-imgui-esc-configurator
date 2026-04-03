---
title: ImGui ESC Configurator Prompt Pack
doc_type: prompt-context
status: active
audience:
  - ai-agent
  - developer
canonicality: canonical
subsystem: imgui-esc-config
purpose: Provide copy-paste prompts for implementing and debugging the Python ImGui ESC configurator with cached webapp feature mapping and protocol constraints.
related_docs:
  - DESIGN_REQUIREMENTS.md
  - WEBAPP_FEATURE_CACHE.md
  - README.md
  - ../AI_PROMPT_GUIDE.md
  - ../../PROMPTS.md
verified_on: 2026-03-22
---

# `imgui_bundle_esc_config` prompt.md

Use this file as a **local prompt cache** for work in `python/imgui_bundle_esc_config`.

If there is any ambiguity, prioritize:

1. `DESIGN_REQUIREMENTS.md` (product/behavior authority)
2. `WEBAPP_FEATURE_CACHE.md` (webapp module + protocol cache)
3. this file (task prompt templates)

Required policy for AI work:

- **Specs drive code**: treat `DESIGN_REQUIREMENTS.md` as authoritative.
- If code and spec differ, update the spec first (or explicitly with the same change), then align code.
- Do not infer product behavior from incidental current code when requirements are explicit.
- Track parity work using `PARITY_CHECKLIST.md` and keep it synchronized with implementation.

## Core guardrails

- Treat the Python app as a **full desktop replacement** target, not a helper utility.
- Keep serial/MSP/4-way ownership in the worker path.
- Preserve serialized command execution semantics (single transport owner + FIFO command sequencing).
- Keep compatibility with MSP passthrough and BLHeli 4-way frame handling.

## Current verified behavior snapshot (keep in sync)

- Connection panel exposes protocol choice labels: `MSP protocol` and `Optimized protocol`.
- UI flow remains protocol-agnostic after connect; protocol-specific routing happens in worker layer.
- DSHOT speed path exists via worker command and `MSP_SET_MOTOR (214)` for selected motor.
- DSHOT safety semantics in worker:
  - clamp speed to `0..2047`
  - reject invalid motor indices
  - block DSHOT writes while passthrough is active
- Diagnostics/logging windows and protocol trace remain first-class debugging features.

## Prompt: implement next parity feature (cache-first)

> Work in `python/imgui_bundle_esc_config`.
> Use `DESIGN_REQUIREMENTS.md` for required behavior and `WEBAPP_FEATURE_CACHE.md` as the cached map of web esc-configurator module responsibilities.
> Do a cache-first implementation: do not re-scan the web source tree unless required details are missing.
> Preserve worker-owned transport and serialized command execution.
> Treat `DESIGN_REQUIREMENTS.md` as source-of-truth and update it when behavior requirements evolve.
> Implement the next smallest complete parity milestone with tests.

## Prompt: protocol/timeout-sensitive debugging

> Debug protocol behavior in `python/imgui_bundle_esc_config`.
> Use `WEBAPP_FEATURE_CACHE.md` as the baseline for timeout/retry/keepalive values and MSP + BLHeli 4-way framing.
> Focus on root cause first: queueing semantics, frame parse/encode, ACK handling, retry paths, and passthrough sequencing.
> Keep UI thread free of transport/protocol logic.

## Prompt: ESC serial protocol parity check

> Compare Python 4-way frame encode/decode behavior against the cached web framing in `WEBAPP_FEATURE_CACHE.md`.
> Validate: start byte, command/address placement, param-count handling (`0 -> 256`), CRC16 XMODEM calculation scope, ACK byte position, and retry/timeout handling.
> Report any mismatch as a concrete table and patch minimally.

## Prompt: EEPROM format and structured settings parsing

> Implement or debug EEPROM/settings parsing in `python/imgui_bundle_esc_config`.
> Use `WEBAPP_FEATURE_CACHE.md` as the first reference for EEPROM layout findings, conversion rules, BLHeli_S vs Bluejay format differences, and the settings-description model.
> Preserve the distinction between:
> 1. raw EEPROM bytes,
> 2. layout-based field extraction,
> 3. UI metadata such as labels, enums, visibility, and validation.
> Do not guess field names from hex dumps if the cached layout info already covers them.

## Prompt: update cache when web behavior changes

> Update `WEBAPP_FEATURE_CACHE.md` with new findings from the web esc-configurator source.
> Keep only durable ownership/protocol/timeout facts.
> If behavior changed, update this `PROMPT.md`, `../AI_PROMPT_GUIDE.md`, and `../../PROMPTS.md` links/references as needed.

## Quick timeout/protocol checklist

Before finalizing protocol changes, verify:

- queue timeout budget alignment (web default uses 1000 ms command timeout)
- 4-way retry behavior and spacing
- keepalive interval/idle threshold behavior
- MSP passthrough entry/exit sequencing
- 4-way read/write/verify ACK-path behavior
- EEPROM decode rules for 1-byte, 2-byte, string, and melody fields
- BLHeli_S vs Bluejay layout-size and offset differences when parsing settings
