---
title: Python ESC Configurator
doc_type: guide
status: active
audience:
  - human
  - ai-agent
canonicality: canonical
subsystem: python
purpose: Provide a concise product-focused entry point for the Python ESC configurator repository.
related_docs:
  - REQUIREMENTS.md
  - GITHUB_TODO.md
  - imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md
  - ../rt-fc-offloader/docs/FCSP_PROTOCOL.md
verified_on: 2026-04-03
---

# Python ESC Configurator

This repository is the **desktop Python ESC configurator**.

It is the **full-featured ESC configurator target** for this project — not a stripped-down demo, not a temporary helper tool.

It is also intended to serve as a **classroom / reference implementation** for how to structure this kind of software well.

That means the repo is meant to teach:

- users how the tool works
- programmers how to structure non-blocking GUI applications
- engineers how to separate frontend workflow from protocol/backend execution
- AI coding agents what this project considers the preferred architecture standard

## What it does

- ESC passthrough
- ESC discovery
- settings read/write
- firmware catalog/download
- firmware flash/verify workflows
- diagnostics, logs, and protocol traces
- simple headless backend frontend (`python -m imgui_bundle_esc_config.headless_cli`) for classroom/reference use

## Protocol status

- **MSP is fully supported today** and remains the complete compatibility path.
- **FCSP** is the new protocol path being added for the next-generation offloader architecture.
- The GUI should remain stable while transport/protocol details evolve underneath the worker layer.

In short:

- **today:** fully featured MSP-based ESC configurator
- **next:** same configurator workflows over FCSP where appropriate

### FCSP implementation status (current)

| Feature | Status |
|---|---|
| Frame codec (`encode_frame` / `decode_frame`) | ✅ complete |
| HELLO handshake | ✅ complete |
| GET_CAPS + capability TLVs | ✅ complete |
| `PT_ENTER` / `PT_EXIT` / `ESC_SCAN` native | ✅ complete, with MSP fallback |
| `SET_MOTOR_SPEED` native | ✅ complete, with MSP fallback |
| `GET_LINK_STATUS` native | ✅ complete |
| `READ_BLOCK` for `ESC_EEPROM` (settings read) | ✅ complete, with 4-way fallback |
| `WRITE_BLOCK` for `ESC_EEPROM` (settings write) | ✅ complete, with 4-way fallback |
| `READ_BLOCK` / `WRITE_BLOCK` for IO windows (`DSHOT_IO`, `PWM_IO`) | ✅ complete, no fallback (space-gated) |
| Capability-gated op / space availability in AppState | ✅ complete |
| `WRITE_BLOCK` for `FLASH` space (native firmware flash) | 🔜 migration path defined, hardware validation pending |
| Optimized-mode runtime beyond discovery (multi-ESC real HW) | 🔜 pending hardware evidence |

## Companion repository

The FPGA/offloader repository is:

- `rt-fc-offloader`

Canonical FCSP spec lives there:

- `rt-fc-offloader/docs/FCSP_PROTOCOL.md`

Do not duplicate the FCSP spec in this repository.

## Screenshots

Current Python ImGui ESC configurator UI:

![Python ImGui ESC Configurator screenshot](docs/assets/python-imgui-esc-configurator-main.png)

Windows operator screenshot:

- Pending capture on a live Windows operator station. (Tracked in `GITHUB_TODO.md`.)

## Windows operator setup (explicit path)

From repository root in PowerShell:

- Create venv: `py -3 -m venv .venv`
- Activate: `.\.venv\Scripts\Activate.ps1`
- Install deps: `pip install -r imgui_bundle_esc_config/requirements.txt`
- Run app: `python -m imgui_bundle_esc_config.app`

If script execution is restricted, run:

- `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`

Then activate `.\.venv\Scripts\Activate.ps1` again.

## Start here

- `REQUIREMENTS.md` — clear repository requirements
- `GITHUB_TODO.md` — active GitHub task list
- `HISTORY.md` — running technical history (changes + pytest verification)
- `docs/HIL_SMOKE_CHECKLIST.md` — operator hardware smoke checklist
- `docs/PARITY_SIGNOFF_TEMPLATE.md` — GO/NO-GO replacement parity decision template
- `imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md` — detailed application requirements

## Classroom / reference-implementation goal

This project is not only trying to ship a useful ESC configurator.

It is also trying to **show the standard** for this style of application.

Concretely, the repository is intended to teach humans and AI agents how to:

- build responsive GUI applications without blocking the render loop
- separate frontend code from protocol/transport/backend code
- use typed command/event boundaries instead of ad-hoc shared state
- keep protocol logic reusable across GUI, CLI, tests, and alternate frontends
- use pytest to validate backend behavior directly
- preserve logs, traces, diagnostics, and history as first-class engineering tools

In other words: this repo should be understandable as both a product and a **worked example of good architecture**.

## GUI loop / thread separation (quick pointers)

If you want the short version of how we keep the UI reactive:

- `imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md` ("High-level architecture") — canonical two-thread model
- `imgui_bundle_esc_config/app.py` — main ImGui frame loop (`immapp.run(gui)`), event drain, and render path
- `imgui_bundle_esc_config/worker.py` — command/protocol worker thread and queue-driven command handling
- `imgui_bundle_esc_config/ui_main.py` + `imgui_bundle_esc_config/app_state.py` — worker event application into UI state each frame

Design rule of thumb:

- UI thread owns ImGui calls
- worker thread owns serial/protocol I/O
- queues connect them (`Command*` UI→worker, `Event*` worker→UI)

## Worker-as-kernel philosophy

The worker layer is intentionally treated as a **stand-alone backend/kernel**, not as GUI-only glue.

That is a deliberate reuse decision:

- the current ImGui desktop app is one frontend for it
- pytest modules can drive it directly with fake transports/clients
- future command-line tools can reuse the same command/event model
- the same threading/queue model can power another app frontend without rewriting protocol logic
- if ImGui is replaced later, the protocol/backend code should still be reusable
- embedded `rt-fc-offloader` bring-up helpers and diagnostics tools can reuse the same backend behavior patterns

Practical meaning:

- keep protocol/transport logic in `imgui_bundle_esc_config/worker.py`
- keep UI rendering concerns in `imgui_bundle_esc_config/ui_main.py`
- prefer typed commands/events over direct GUI-owned protocol calls
- keep worker code usable with test doubles, simulated transports, and non-GUI harnesses

Example mindset:

- if we want to start another app later, we should be able to keep the worker/threading model and build a different frontend on top of it
- if we replace ImGui with something else, the protocol code should mostly be reused rather than rewritten
- the frontend can change; the backend command/event kernel should stay reusable

This is not just an implementation convenience; it is a project philosophy. Reuse through a worker/backend boundary is a deliberate requirement because it improves bring-up speed, testability, CLI/tooling reuse, and future integration with offloader-side workflows.

It also supports the classroom goal of the repository: people should be able to study this split and learn a reusable pattern they can apply in their own projects.

## Protocol separation (MSP + FCSP)

We intentionally separate **GUI intent** from **transport/protocol execution** so the same UI flow can run over two protocol paths:

- **MSP path** (current full compatibility baseline)
- **FCSP path** (new optimized/offloader path)

Quick pointers:

- `imgui_bundle_esc_config/worker.py` — protocol-mode selection and command handling (`msp` vs `optimized_tang9k`)
- `imgui_bundle_esc_config/ui_main.py` — user chooses protocol mode in the connection panel
- `imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md` — architecture rule: keep protocol details in worker layer, keep GUI workflow stable
- `rt-fc-offloader/docs/FCSP_PROTOCOL.md` — canonical FCSP mapping and migration intent

Design rule of thumb:

- GUI issues feature-intent commands (`connect`, `read settings`, `flash`, etc.)
- worker maps those intents to MSP/4-way or FCSP operations
- adding/extending FCSP should not require redesigning user-facing GUI flows

## If you want to use ImGui here (what to do)

Recommended starting path:

1. Start from `imgui_bundle_esc_config/app.py` to understand the frame loop and startup/shutdown flow.
2. Add or adjust UI in `imgui_bundle_esc_config/ui_main.py` (panels, controls, button handlers).
3. Keep persistent UI/session state in `imgui_bundle_esc_config/app_state.py`.
4. Add/update shared command/event contracts in `imgui_bundle_esc_config/backend_models.py`, then implement handling in `imgui_bundle_esc_config/worker.py`.
5. Add unit tests in `unitTests/test_imgui_worker.py` and related state/export tests when behavior changes.

Practical suggestions:

- Keep render callbacks lightweight (no blocking I/O in UI code).
- Use typed `Command*` and `Event*` models instead of ad-hoc shared state.
- Gate actions in UI when capability/support is missing, but keep fallback paths in worker where possible.
- Prefer small, incremental UI changes with focused tests first, then full regression.

Quick anti-pattern checklist:

- Don't call ImGui APIs from worker code.
- Don't access serial transport directly from UI code.
- Don't hard-wire protocol details into UI flow logic.
- Don't make worker behavior depend on ImGui-only state or widget lifetimes.

## Pytest and module-reuse mindset

Code reuse through pytest-friendly modules is a first-class design goal here.

Why that matters:

- worker behavior can be validated without launching the UI
- fake MSP / 4-way / FCSP transports can exercise protocol flows deterministically
- this repository can help users, programmers, and engineers learn how to structure GUI code around a reusable backend instead of burying logic inside widgets
- the same backend patterns can support GUI apps, command-line tools, simulations, and embedded bring-up helpers
- regressions can be caught at the module boundary before they become UI bugs

Good examples already in the repo:

- `unitTests/test_imgui_worker.py` drives `WorkerController` directly
- fake transports/clients are injected into the worker for deterministic tests
- app-state/export tests validate the non-UI layers independently of rendering

Rule of thumb:

- if logic is useful for UI, CLI, simulation, or embedded bring-up, it belongs in the reusable worker/protocol layer first
- the GUI should mainly orchestrate and visualize that backend behavior

This is part of the standard the repo is trying to teach.

## Why we chose `imgui-bundle`

Short answer: it fits this tool's operator-focused, hardware-adjacent workflow very well.

Key reasons:

- **Fast iteration for tooling UIs**: immediate-mode UI is quick to evolve while protocol behavior is still changing.
- **Great for live diagnostics**: log panels, protocol traces, status bars, and progress updates are straightforward to build and maintain.
- **Low friction Python integration**: works well with the existing Python worker/state architecture without introducing a browser/web stack.
- **Clear thread boundaries**: easy to keep rendering on the UI thread while serial/protocol work stays in the worker thread.
- **Cross-platform desktop delivery**: practical for Linux development and Windows operator usage.
- **Built-in developer ergonomics**: metrics/debug windows and mature widgets help debugging complex ESC/config flows.

This does **not** mean protocol logic belongs in UI code — the design remains:

- UI = intent + rendering
- worker = transport/protocol execution

### Technical details (for AI engines and first-time ImGui users)

- Main frame loop lives in `imgui_bundle_esc_config/app.py` via `immapp.run(gui)`.
- Each frame does this order: `drain_worker_events(state, worker)` → `render_main_window(state, worker)`.
- Worker communication uses two `queue.Queue` channels in `WorkerController`:
  - command queue (UI → worker)
  - event queue (worker → UI)
- `poll_events(max_events=100)` bounds per-frame event processing so UI stays responsive under bursty updates.
- Worker loop is a background thread with a short queue wait (`get(timeout=0.1)`) to stay responsive to shutdown/cancel.
- Protocol mode is selected in UI and passed through `CommandConnect`:
  - `msp`
  - `optimized_tang9k` (plus compatibility aliases mapped in worker)
- Feature intent remains stable (`CommandReadSettings`, `CommandFlashEsc`, etc.); worker decides protocol path (MSP/4-way vs FCSP).
- FCSP control path uses capability-aware behavior in worker (advertised op/space checks) with MSP/4-way fallback where applicable.
- State changes are event-driven through `AppState.apply_event(...)` so UI rendering stays read-mostly and predictable.

### UI tech showcase (multi-window workflow)

This project intentionally demonstrates a **multi-window ImGui desktop tool** pattern:

- **Main workflow window**: connect, ESC link, settings, firmware actions
- **Log window**: operator-facing runtime logs with filtering
- **Protocol trace window**: full low-level MSP / 4-way / FCSP TX/RX visibility for worker-driven operations
- **Optional ImGui debug windows**: metrics/debug-log views for development

Why this matters:

- Operators can keep workflow controls open while watching live diagnostics.
- Developers can inspect protocol behavior without pausing or instrumenting the UI flow.
- AI-assisted changes can target the right surface quickly (`ui_main.py` for windows, `app_state.py` for event-backed state).

Quick flow:

`UI interaction` → `Command* enqueue` → `worker executes protocol path` → `Event* emit` → `state update` → `all windows re-render next frame`

### Protocol logging coverage (ALL worker traffic)

Protocol tracing is designed to be comprehensive for worker-driven protocol operations:

- **MSP**: request and response frames are traced (`MSP -> ...`, `MSP <= ...`)
- **4-way**: request and response frames plus ACK/CRC status are traced
- **FCSP**: control-channel request and response frames are traced

Where this is wired:

- `imgui_bundle_esc_config/worker.py` emits `EventProtocolTrace` for protocol TX/RX paths
- `imgui_bundle_esc_config/app_state.py` stores traces in `protocol_traces`
- `imgui_bundle_esc_config/runtime_logging.py` mirrors traces to rotating runtime log files
- `imgui_bundle_esc_config/diagnostics_export.py` exports traces to `protocol_traces.json`

In short: protocol logging is not "best effort" for a few commands; it is treated as a first-class observability surface across the worker protocol stack.

### Log-driven troubleshooting workflow (find what's wrong quickly)

Use this sequence when diagnosing failures:

1. Reproduce the issue once with the **Log window** and **Protocol trace window** visible.
2. Confirm the user action appears as expected (connect/read/write/flash) in UI logs.
3. Check protocol trace TX/RX pairs around that moment:
  - missing response (timeout path)
  - error ACK/result code
  - malformed or unexpected payload length
4. Compare with status/error events in UI logs (`EventError`, disconnect reason, verification failure).
5. Export a diagnostics bundle and inspect:
  - `ui_logs.json`
  - `protocol_traces.json`
  - `session_metadata.json`
  - runtime log copy (`imgui_esc_config.log`)

What this gives you:

- **Intent** (what the operator clicked)
- **Transport/protocol reality** (what actually went over MSP / 4-way / FCSP)
- **App interpretation** (what state/error the app concluded)

This triad is the fastest path to root cause (UI misuse vs capability mismatch vs protocol/transport failure).

### Saving logs to files (what gets persisted)

Runtime logs are persisted automatically to disk:

- Default directory: `./logs/`
- Default file: `./logs/imgui_esc_config.log`
- Rotation: ~1 MiB per file, 3 backups (`imgui_esc_config.log`, `.1`, `.2`, `.3`)

You can override the log directory with:

- environment variable: `ESC_CONFIG_LOG_DIR`

Diagnostics export also writes structured files to disk:

- default export root: `./diagnostics/`
- bundle format: `esc-config-diagnostics-<timestamp>/`
- includes:
  - `ui_logs.json`
  - `protocol_traces.json`
  - `session_metadata.json`
  - copied runtime log file (`imgui_esc_config.log`) when present

Practical tip: for bug reports, include both the diagnostics bundle and the active runtime log so timeline + protocol details line up.

### How windows and "canvas" work in this app

In `imgui-bundle`, UI is redrawn every frame (immediate mode), so there is no retained widget tree or persistent canvas object.

How it is structured here:

- Top-level window orchestration happens in `render_main_window(...)` in `imgui_bundle_esc_config/ui_main.py`.
- Themed windows are created with `_begin_themed_window(...)` / `_end_themed_window(...)`.
- Additional windows are rendered each frame:
  - `render_log_window(...)`
  - `render_protocol_window(...)`
  - optional ImGui debug windows (`render_imgui_debug_windows(...)`)

About "canvas" behavior in this codebase:

- Most content uses standard ImGui layout primitives (text, buttons, tables, separators, collapsing headers).
- Scrollable regions act as local content surfaces via `imgui.begin_child(...)` (used for log/protocol streams).
- For dynamic lists/tables (settings, releases), data is pulled from `AppState` every frame and rendered fresh.
- Custom drawing can be added later via ImGui draw lists, but current UI primarily uses standard widgets for clarity and maintainability.

Mental model:

- **Window** = a top-level container rendered every frame.
- **Child region** = a scrollable sub-area inside a window (often what people call a canvas in tool UIs).
- **State** = lives in `app_state.py`; rendering reads this state each frame and emits commands on user actions.

## Development notes

- Development is Linux-first.
- End-user friendliness should remain strong for Windows users.
- Keep `.venv/` local-only and out of git.

## Scope guardrails

- Keep this repo focused on the Python ESC configurator.
- Keep MSP working while FCSP is introduced.
- Do not push protocol details into the GUI layer unless absolutely necessary.
- Preserve a fully featured user-facing configurator experience.
