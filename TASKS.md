---
title: Project Top-Level Tasks
doc_type: task-tracker
status: active
audience:
  - human
  - ai-agent
  - developer
canonicality: canonical
subsystem: repository
purpose: Track top-level implementation and validation tasks across MSP/DSHOT firmware, Python configurator, docs, and hardware bring-up.
related_docs:
  - README.md
  - ROADMAP.md
  - docs/README.md
  - docs/MSP_MESSAGE_FLOW.md
  - docs/CODE_DESIGN.md
verified_on: 2026-04-03
---

# Top-Level Tasks

Use this file as the single high-level tracker. Keep tasks scoped, testable, and tied to concrete artifacts.

## Current progress snapshot

- ✅ ESC-config stale-cache UX hardening completed (warning + one-click refresh + tests)
- ✅ MSP worker updates landed for Tang mode aliases and broader discovery probes
- ✅ Worker-focused MSP/ESC tests currently green (`python/unitTests/test_imgui_worker.py`)
- ⏳ Full-suite + hardware smoke still required for release-level signoff

## Next 3 tasks (active sprint)

1. Complete and publish canonical hardware requirements doc:
   - `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
2. Add offline cache startup UX tests (missing/corrupt snapshot scenarios) in Python unit suite
3. Run full Python suite + update tracker statuses; then execute Pico/Tang smoke checklist

## 0) Immediate priorities (current)

- [ ] Finalize MSP Python readiness for Pico + Tang mode aliases
  - [x] Confirm protocol-mode aliases (`optimized`, `optimized_tang9k`, Tang20K aliases) map predictably
  - [x] Confirm MSP discovery/probe coverage aligns with `docs/MSP_MESSAGE_FLOW.md`
  - [ ] Verify no regressions in passthrough, settings read/write, and flash flows

- [ ] Add canonical hardware requirements doc (MSP + DSHOT)
  - [x] Create `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md`
  - [ ] Include Pico and Tang responsibilities, ownership rules, timing constraints, and failure handling
  - [x] Cross-link from `docs/README.md` and `README.md`

- [ ] Keep docs stable while planning source reorg
  - [ ] Create source-tree migration map (old path -> new path)
  - [ ] Define phased move plan with build/test gate per phase
  - [ ] Avoid large one-shot moves

## 1) Firmware / hardware contract tasks

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

## 2) Python configurator tasks

- [ ] MSP worker robustness
  - [ ] Expand error categorization for transport-fatal vs recoverable failures
  - [ ] Ensure discovery/probe steps degrade gracefully when partial commands fail

- [ ] UI parity hardening
  - [ ] Compact-layout regression coverage where harness allows
  - [ ] Offline cache startup UX coverage (missing/corrupt cache scenarios)

- [ ] Firmware catalog UX
  - [ ] Keep stale-cache warning + one-click refresh behavior covered by tests

## 3) Documentation tasks

- [ ] Add and maintain canonical requirements docs
  - [x] `docs/MSP_DSHOT_HARDWARE_REQUIREMENTS.md` (new)
  - [ ] Keep `docs/MSP_MESSAGE_FLOW.md`, `docs/CODE_DESIGN.md`, and `docs/BLHELI_PASSTHROUGH.md` synchronized

- [ ] Add migration notes for any source-tree refactor
  - [ ] Track moved files and updated include/import paths
  - [ ] Link migration notes from `docs/README.md`

## 4) Verification tasks

- [ ] Software verification
  - [ ] Run full Python test suite before each mergeable checkpoint
  - [ ] Keep worker-focused regression tests green

- [ ] Hardware smoke tests (after coding checkpoints)
  - [ ] Pico: connect/disconnect, passthrough enter/exit, read settings, flash one ESC, cancel/recover
  - [ ] Tang: equivalent flow on selected transport mode with protocol trace capture

## 5) Definition of done (project checkpoint)

A checkpoint is complete only when all are true:

- [ ] Code changes implemented for scoped tasks
- [ ] Unit/integration tests pass
- [ ] Docs updated for behavior changes
- [ ] No unresolved errors in touched files
- [ ] Hardware smoke pass completed (for hardware-affecting changes)
