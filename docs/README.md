---
title: Firmware and System Documentation Index
doc_type: index
status: active
audience:
   - human
   - ai-agent
canonicality: canonical
subsystem: documentation
purpose: Route readers to the canonical firmware and system documents and explain how to bundle them for prompts.
related_docs:
   - ../README.md
   - DOC_METADATA_STANDARD.md
   - BLHELI_PASSTHROUGH.md
   - MSP_DSHOT_HARDWARE_REQUIREMENTS.md
   - SYSTEM_HOW_IT_WORKS.md
verified_on: 2026-03-22
---

# Documentation Index

See also:

- `../README.md` — top-level repository guide for both humans and AI agents
- `DOC_METADATA_STANDARD.md` — lightweight frontmatter and documentation metadata conventions

Use this file as the entry point for project docs.

## AI prompt usage

This directory is intended to be usable by both humans and AI coding agents.

When using these docs in a prompt:

- start with the canonical references below
- use supporting docs to fill in architecture, history, and implementation rationale
- treat files marked as legacy or draft as context, not as the final source of truth
- if code and docs disagree, inspect code and then update the docs

### Recommended prompt bundle order

For most implementation prompts, provide documents in this order:

1. `BLHELI_PASSTHROUGH.md`
2. `MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
3. `SYSTEM_HOW_IT_WORKS.md`
4. `CODE_DESIGN.md`
5. `MSP_MESSAGE_FLOW.md`
6. `PINOUT.md`

### Canonicality legend

- **canonical**: primary source of truth for active behavior
- **supporting**: useful implementation or system context
- **legacy**: helpful background, may be partially outdated
- **draft**: planned design, not guaranteed implemented yet

## Canonical references (current)

1. `BLHELI_PASSTHROUGH.md`
   - ESC passthrough transition requirements (DSHOT off, line break/release, serial handoff),
   - and Betaflight 4-way context.

2. `MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
   - Throughput budgets and guardrails for MSP passthrough + DSHOT coexistence.

3. `SYSTEM_HOW_IT_WORKS.md`
   - System-level architecture and runtime flow.

4. `BUILD_TUTORIAL.md`
   - Toolchain/build/flash workflow.

## Supporting docs

- `architecture.md` — high-level architecture notes.
- `implementation_details.md` — implementation discussion/history.
- `PINOUT.md` — pin mapping reference.
- `CODE_DESIGN.md` — runtime ownership, arbitration, passthrough lifecycle, and key file responsibilities.
- `MSP_MESSAGE_FLOW.md` — MSP command/reply expectations relevant to configurator interactions.
- `MSP_DSHOT_HARDWARE_REQUIREMENTS.md` — concrete performance budgets, FIFO/IRQ guidance, and 60/100 MHz feasibility guardrails.

## Notes

- If protocol behavior in code and docs diverge, update code or docs immediately.
- FCSP protocol specification is canonical in `rt-fc-offloader/docs/FCSP_PROTOCOL.md`; keep a single source of truth and do not create duplicate spec copies in this repository.
- Browser-based esc-configurator workflows depend on WebSerial, which expects OS-visible serial devices; plain TCP endpoints are not direct WebSerial targets.
- A webapp TCP bridge can be built with a local helper/service layer, but that is a separate integration project; for near-term delivery, the Python full-replacement path is the primary route.

## Quick prompt recipes

### Prompt for firmware protocol work

Use:

- `MSP_MESSAGE_FLOW.md`
- `CODE_DESIGN.md`

### Prompt for ESC passthrough / configurator work

Use:

- `BLHELI_PASSTHROUGH.md`
- `MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
- `MSP_MESSAGE_FLOW.md`
- `CODE_DESIGN.md`
- `PINOUT.md`

### Prompt for architecture / onboarding

Use:

- `SYSTEM_HOW_IT_WORKS.md`
- `architecture.md`
- `implementation_details.md`
