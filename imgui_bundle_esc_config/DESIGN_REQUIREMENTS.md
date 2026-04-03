---
title: ImGui ESC Configurator Design Requirements
doc_type: design
status: active
audience:
  - human
  - ai-agent
  - developer
canonicality: canonical
subsystem: imgui-esc-config
purpose: Define the product scope, architecture, feature requirements, and implementation constraints for the Python ImGui ESC configurator replacement.
related_docs:
  - ../../README.md
  - ../../PROMPTS.md
  - ../../docs/DOC_METADATA_STANDARD.md
  - ../../docs/BLHELI_PASSTHROUGH.md
  - ../../docs/MSP_MESSAGE_FLOW.md
  - PROMPT.md
  - WEBAPP_FEATURE_CACHE.md
verified_on: 2026-03-22
---

# ImGui Bundle ESC Configurator — Design, Requirements, and Feature Specification

## Goal

`python/imgui_bundle_esc_config` is intended to become a **full desktop replacement** for the existing web application at:

- `https://esc-configurator.com/`

The replacement should preserve the major workflow and capabilities users expect from `esc-configurator`, while adapting the implementation to a Python desktop application built with `imgui-bundle`.

## AI usage intent

This document is also intended to be used as **prompt context for AI coding agents**.

When used in prompts, this file should be treated as:

- the product definition
- the feature parity target
- the architecture guide
- the implementation constraint list

When an AI agent uses this document, it should prefer the requirements here over inventing alternate workflows unless the user explicitly asks for a deviation.

## Canonical terminology

To reduce ambiguity in future prompts, use these terms consistently:

- **bridge**: this repository's firmware/device that exposes MSP and ESC passthrough behavior
- **web reference app**: `https://esc-configurator.com/`
- **desktop replacement**: the Python `imgui-bundle` application in `python/imgui_bundle_esc_config`
- **worker thread**: the non-UI thread that owns serial/MSP/4-way communication
- **UI thread**: the thread that owns all ImGui calls and rendering
- **ESC family**: firmware family such as BLHeli_S or Bluejay
- **firmware catalog**: remote metadata and downloadable firmware images
- **settings**: EEPROM-derived configuration values displayed and edited in the UI

## Replacement scope

This is **not** a minimal demo and **not** a partial utility.
The target is a practical operator-facing application that can replace the current web workflow for supported ESC families.

The app must support:

- ESC discovery and connection through the local bridge / serial transport
- MSP-based passthrough activation
- BLHeli 4-way protocol transactions
- EEPROM/settings read and write
- Firmware flashing workflow
- Progress, status, validation, and error reporting
- Multi-ESC workflows
- Firmware catalog download and local firmware file loading

## Supported firmware families

The initial replacement must support at minimum:

- **BLHeli_S**
- **Bluejay**

The design should keep room for future expansion, but parity priority is:

1. BLHeli_S
2. Bluejay

## Reference sources

### Local parity reference

Primary behavior reference:

- `https://esc-configurator.com/`

This source should be treated as the reference for:

- workflow sequencing
- feature coverage
- firmware selection behavior
- flashing UX
- multi-ESC handling
- error and retry expectations

Supplementary source-code reference during implementation/debugging:

- Local checked-out source (when available): a local clone of `https://github.com/stylesuxx/esc-configurator`
- Upstream source repository: `https://github.com/stylesuxx/esc-configurator`

### Upstream ESC firmware/source references

Use these when parity or compatibility work requires inspecting firmware-family internals rather than only the configurator UI flow.

#### BLHeli / BLHeli_S

- BLHeli upstream repository: `https://github.com/bitdump/BLHeli`
- BLHeli_S SiLabs source tree: `https://github.com/bitdump/BLHeli/tree/main/BLHeli_S%20SiLabs`
- BLHeli_S main source file: `https://github.com/bitdump/BLHeli/blob/main/BLHeli_S%20SiLabs/BLHeli_S.asm`
- BLHeli_S bootloader source: `https://github.com/bitdump/BLHeli/blob/main/BLHeli_S%20SiLabs/BLHeliBootLoad.inc`

#### Bluejay

- Bluejay upstream repository: `https://github.com/bird-sanctuary/bluejay`
- Bluejay main source file: `https://github.com/bird-sanctuary/bluejay/blob/main/src/Bluejay.asm`
- Bluejay DShot / telemetry implementation: `https://github.com/bird-sanctuary/bluejay/blob/main/src/Modules/DShot.asm`
- Bluejay DShot decode / ISR flow: `https://github.com/bird-sanctuary/bluejay/blob/main/src/Modules/Isrs.asm`
- Extended DShot telemetry reference: `https://github.com/bird-sanctuary/extended-dshot-telemetry`

Interpretation note:

- MSP and BLHeli 4-way passthrough behavior lives on the configurator / flight-controller / bridge side.
- Bluejay firmware itself is primarily relevant here for DShot command handling, bidirectional telemetry, extended telemetry, layout details, and EEPROM/firmware-family behavior.

### Local firmware/bridge reference

Bridge behavior and protocol capabilities in this repository:

- `src/msp.cpp`
- `src/msp.h`
- `src/esc_4way.cpp`
- `src/esc_4way.h`
- `src/esc_passthrough.cpp`
- `src/esc_passthrough.h`
- `src/spi_slave.cpp`
- `src/spi_slave.h`

These files indicate the bridge currently supports key 4-way operations such as:

- passthrough start/stop
- interface reset
- flash init
- flash read/write/verify operations
- EEPROM read/write
- multi-motor passthrough selection

## AI implementation constraints

Any AI agent implementing this project should follow these constraints:

- do not collapse the design into a single-threaded blocking UI unless explicitly requested
- do not let the worker thread call ImGui APIs directly
- do not let the UI thread own the live serial port
- do not assume only one ESC exists; design for multi-ESC workflows
- do not implement firmware flashing without compatibility checks and confirmation steps
- do not remove support for local firmware file loading in favor of web-only download flow
- do not hardcode BLHeli_S-only assumptions; Bluejay must be treated as a first-class target
- do not replace message queues with ad-hoc shared mutable state unless there is a strong reason
- prefer explicit models for commands, events, ESC metadata, settings, and firmware images
- preserve enough logging and diagnostics for field debugging
- treat native Python desktop transport/control as the primary delivery path; webapp TCP-bridge compatibility layers are optional future integration work and should not block core replacement milestones

## Implementation priorities for AI agents

If an AI agent is implementing this incrementally, preferred order is:

1. transport and worker skeleton
2. MSP passthrough control
3. 4-way read path
4. ESC discovery and metadata models
5. EEPROM/settings parse and write path
6. UI panels for connect, list, details, logs
7. firmware catalog download and cache
8. flashing and verify workflow
9. persistence and polish

These priorities describe the preferred execution order, but they do **not** reduce the product scope. Incremental work should still be treated as progress toward a full replacement, not as a justification for turning the project into a reduced-scope utility.

## High-level architecture

The desktop app should use a **two-thread design**.

### Thread 1: ImGui/UI thread

Responsibilities:

- render windows and widgets
- process user input
- manage local view state
- enqueue work requests
- consume worker events and update visible state

Important rule:

- the UI thread is the **only** thread allowed to touch ImGui APIs

### Thread 2: command/protocol worker thread

Responsibilities:

- own the serial port / transport session
- execute MSP requests
- execute 4-way commands
- manage timeouts, retries, and cancellation
- stream progress and result events back to the UI

Important rule:

- the worker thread is the **only** thread allowed to access the live serial transport

### Inter-thread communication

Use message passing rather than ad-hoc shared mutable state.

Required communication paths:

- **Command queue**: UI → worker
- **Event queue**: worker → UI

Optional:

- read-only snapshot/status object guarded by a lock if needed for convenience

Suggested queue payload types:

- `CommandConnect`
- `CommandDisconnect`
- `CommandEnterPassthrough`
- `CommandExitPassthrough`
- `CommandScanEscs`
- `CommandReadSettings`
- `CommandWriteSettings`
- `CommandRefreshFirmwareCatalog`
- `CommandDownloadFirmware`
- `CommandFlashEsc`
- `EventConnected`
- `EventDisconnected`
- `EventEscListUpdated`
- `EventSettingsLoaded`
- `EventProgress`
- `EventLog`
- `EventError`
- `EventOperationComplete`

## Core user workflow

The intended normal flow is:

1. Launch app
2. Detect available serial targets / bridge endpoints
3. Connect to selected target
4. Query bridge/FC status
5. Enter ESC passthrough for the requested motor(s)
6. Detect connected ESCs
7. Read ESC metadata and EEPROM settings
8. Present editable fields in the UI
9. Optionally fetch firmware catalog from the web
10. Select firmware target and compare compatibility
11. Flash selected ESC(s)
12. Verify success
13. Exit passthrough and cleanly disconnect

## Full replacement milestone roadmap

The project may be implemented in phases, but the intended destination remains a **full desktop replacement** for the supported workflows of `https://esc-configurator.com/`.

### Phase 1 — Transport and application shell

Required outcome:

- responsive ImGui shell
- serial port enumeration and connection handling
- worker-thread ownership of transport
- status, log, and operation lifecycle scaffolding

This phase establishes the runtime foundation only. It is **not** replacement-complete.

### Phase 2 — Passthrough and ESC discovery

Required outcome:

- MSP passthrough entry and exit
- target ESC selection
- ESC discovery and identity readout
- per-ESC visibility in the UI

This phase enables protocol bring-up, but it is still **not** a full replacement.

### Phase 3 — Settings workflow parity

Required outcome:

- EEPROM/settings read path
- structured settings model
- editable settings UI
- validation and write-back flow
- confirmation by re-read where appropriate

At the end of this phase, the application may support meaningful configuration work, but it is still **not** a full replacement until firmware workflows also exist.

### Phase 4 — Firmware catalog and flashing parity

Required outcome:

- remote firmware catalog refresh and caching
- local firmware file import
- compatibility checks before flash
- erase, write, and verify stages with progress and error reporting
- safe flashing workflow for supported ESC families

This is the minimum phase at which the application can begin to qualify as a **full replacement candidate**.

### Phase 5 — Multi-ESC and operational polish

Required outcome:

- stable multi-ESC workflows
- stronger failure recovery
- improved diagnostics and log export
- polished UX gating for destructive actions
- persistence and workflow refinement

This phase turns a parity candidate into a practical daily-use replacement.

### Phase 6 — Replacement completion criteria

The application should be described as a **full replacement** only when all of the following are true for the supported scope:

- BLHeli_S and Bluejay are both supported as first-class families
- users can discover ESCs, read settings, edit settings, and flash firmware from the desktop application
- both local and remote firmware acquisition workflows exist
- flashing includes compatibility checks and verification
- the UI remains responsive during normal operations and failure handling
- diagnostics are sufficient for practical troubleshooting

## Document ownership and update rules

To avoid drift as implementation advances, treat document responsibilities as follows:

- `DESIGN_REQUIREMENTS.md` (this file):
  - canonical product definition
  - required feature behavior and constraints
  - acceptance criteria
  - "what" and "how it must behave"

- `ROADMAP.md` (repository root):
  - phase ordering and current execution focus
  - short progress markers and migration sequencing
  - "what we are doing next"

- chat/session todo list:
  - short-lived execution checklist for the current coding session
  - not canonical for long-term project state

When behavior is implemented or changed, update this file first for semantics, then update `ROADMAP.md` for phase/progress visibility.

Source-of-truth policy (required):

- `DESIGN_REQUIREMENTS.md` is the **driver** for product behavior.
- Implementation code (`*.py`) is an execution artifact of this spec, not a competing source of truth.
- If code and this document conflict, treat the document as authoritative, then either:
  - update code to match the document, or
  - explicitly update this document first when behavior is intentionally changed.
- PR/review acceptance should include a parity check against this file for any user-visible behavior change.

## Feature behavior and implementation status map

The table below summarizes key replacement features, required behavior, and current implementation status.

Status legend:

- ✅ implemented baseline
- 🔄 in progress
- ⏳ not started

| Feature area | Required behavior summary | Status (current) | Primary implementation location |
|---|---|---:|---|
| App shell + worker threading | Non-blocking ImGui UI + dedicated worker owning transport/protocol | ✅ | `python/imgui_bundle_esc_config/app.py`, `worker.py`, `ui_main.py`, `app_state.py` |
| Serial connection lifecycle | Enumerate, connect/disconnect, visible state and errors | ✅ | `worker.py`, `ui_main.py` |
| MSP passthrough control | Enter/exit passthrough via MSP command flow with motor selection | ✅ | `worker.py` (`CommandEnterPassthrough`, `CommandExitPassthrough`) |
| ESC discovery count | Scan path exposing detected ESC count | ✅ | `worker.py` (`CommandScanEscs`, `EventEscScanResult`) |
| 4-way identity read | Read interface name/protocol/interface version and surface in UI | ✅ | `worker.py` (`CommandReadFourWayIdentity`), `ui_main.py` |
| EEPROM/settings read | Read raw settings bytes from active ESC and surface preview | ✅ (read baseline) | `worker.py` (`CommandReadSettings`, `EventSettingsLoaded`), `ui_main.py` |
| EEPROM/settings write | Edit/validate/write settings and re-read for confirmation; baseline descriptor-driven editor exists for selected fields | ✅ (baseline) | `worker.py`, `settings_decoder.py`, `ui_main.py` |
| Firmware catalog refresh | Download/cache metadata and list firmware options | ✅ | `firmware_catalog.py`, `worker.py` (`CommandRefreshFirmwareCatalog`) |
| Firmware flash + verify | Compatibility checks, staged erase/write/verify, progress/error handling | ✅ | `worker.py` (`CommandFlashEsc`, `CommandFlashAllEscs`), `ui_main.py` |
| Serial recoverability hardening | Transport loss auto-disconnect; error/busy state reset on `EventError`; cancel in-progress ops | ✅ | `worker.py` (`_is_transport_fatal`), `app_state.py` |
| Multi-ESC operations | Safe per-ESC and batch workflows where applicable | ✅ | `worker.py` (`CommandFlashAllEscs`, multi-motor passthrough), `ui_main.py` |
| Diagnostics/export | In-app logs, trace toggles, export for bug reports | ✅ | `diagnostics_export.py`, `runtime_logging.py`, `ui_main.py` |
| Session persistence | Save/restore operator preferences between sessions | ✅ | `persistence.py`, `app.py` |

Implementation note:

- "✅ implemented baseline" means the path exists and is test-covered at unit-test level; it does not imply final UX polish or full parity edge-case coverage.

Desktop differentiation note:

- The desktop replacement should exceed the web reference app in protocol observability.
- Dedicated operator-log and protocol-trace windows are first-class features because they make MSP transactions, BLHeli 4-way requests/responses, ACK results, and decode behavior visible during bring-up and failure analysis.
- Python-side file logging should mirror these views so field captures survive app restarts and can be attached to bug reports.

## Detailed requirements

### 1. Connection and transport requirements

The app must:

- enumerate available serial ports
- allow manual serial port entry if enumeration fails
- allow configurable baud rate where needed
- connect/disconnect cleanly
- detect connection loss and surface it clearly
- recover from transient port errors without requiring app restart where possible
- expose a visible connection state

### 2. Bridge and passthrough requirements

The app must:

- detect whether the bridge/flight controller supports ESC passthrough
- enter passthrough via MSP command flow compatible with this repository
- support selecting target ESC / motor index
- support re-entering passthrough for another ESC without restarting the app
- detect passthrough timeout / auto-exit conditions
- clearly report whether passthrough is active
- support explicit passthrough exit

#### DSHOT control safety semantics (desktop replacement)

When the desktop app issues DSHOT speed commands (web-app style motor speed control), the following semantics are required:

- Valid speed range is **0..2047** (DSHOT throttle payload domain).
- Input values outside this range must be **clamped** before transmit:
  - values `< 0` become `0`
  - values `> 2047` become `2047`
- Motor index must be validated to **0..(motor_count-1)** using FC-reported motor count; invalid index must raise a user-visible error and must not transmit.
- DSHOT speed writes must be blocked while ESC passthrough is active (to avoid conflicting DSHOT/UART ownership on the target path).
- “Stop motor” behavior is implemented as speed `0` for the selected motor.

UI parity note:

- For operator parity with the web reference app motor-control UX, slider presentation should default to **1000..2000** for throttle test controls.
- Protocol/backend command domain remains `0..2047`; UI may intentionally expose a safer subrange.

Definition used in this project:

- **clamping** means coercing an out-of-range value into the nearest allowed bound, i.e. $v' = \min(\max(v, 0), 2047)$.

### 3. ESC discovery requirements

The app must:

- discover up to the expected motor count exposed by the bridge
- show per-ESC presence/absence
- identify active selection
- support rescanning
- handle missing ESCs gracefully
- allow per-ESC and batch operations when safe

### 4. BLHeli_S and Bluejay support requirements

The app must support:

- identification of BLHeli_S ESCs
- identification of Bluejay ESCs
- family-specific metadata handling where layouts differ
- presentation of firmware family, version, target, and MCU when available
- safe gating so a Bluejay image is not flashed blindly to an incompatible target
- safe gating so BLHeli_S and Bluejay targets are distinguished before flash commit

### 5. EEPROM/settings requirements

The app must:

- read EEPROM/settings from the selected ESC
- parse fields into a structured editable model
- display known fields with human-readable labels
- preserve raw data for unknown fields
- allow editing supported settings
- validate edits before write
- write modified settings back to the ESC
- re-read after write when requested or required for confirmation
- warn the user before overwriting settings

### 6. Firmware flashing requirements

The app must support:

- loading firmware from a **local file**
- downloading firmware from the **web/catalog source**
- validating target compatibility before flash
- showing firmware metadata before committing
- erase/write/verify stages with progress reporting
- cancel behavior where protocol-safe
- clear success/failure states
- batch flashing support only when compatibility is established per selected ESC

### 7. Firmware download from web requirements

The app must include a firmware acquisition path comparable to the web tool.

At a minimum it needs:

- a remote firmware catalog source abstraction
- catalog refresh action
- local caching of catalog metadata
- optional local caching of downloaded firmware binaries
- display of firmware family, target, version, revision, and source
- filtering by ESC family (BLHeli_S / Bluejay)
- filtering by target/platform where metadata is available
- explicit compatibility checks before enabling Flash
- visible download progress and retry/error messaging
- offline fallback to previously cached catalog or user-supplied file

Recommended implementation model:

- `FirmwareCatalogClient` fetches JSON/index metadata
- `FirmwareRepository` manages cache and local storage
- `FirmwareImage` model contains decoded metadata and binary payload

Current implementation note:

- a first Python `FirmwareCatalogClient` baseline now exists
- current baseline covers:
  - Bluejay release discovery from GitHub releases metadata
  - BLHeli_S static release entries aligned to the web reference bundle
- cache persistence, firmware image download, and compatibility filtering are still pending

### 8. UI/UX requirements

The UI must present a workflow-oriented desktop layout with at least:

- connection panel
- device/ESC list panel
- settings/details panel
- firmware selection panel
- flash/progress/log panel
- status bar / health summary

The UI should support:

- clear busy/idle state
- disabled controls during incompatible operations
- progress bars for long tasks
- modal confirmations for destructive operations
- log output with timestamps
- filtering/search where firmware catalogs get large

Required ESC-link interaction semantics:

- The primary ESC workflow entry is a single **Read Settings** action.
- `Read Settings` must auto-enter passthrough for the selected ESC target when passthrough is not active.
- `Read Settings` should bootstrap required ESC-link metadata (identity/version) as part of this flow when available.
- A visible **Exit Passthrough** action must be available when passthrough is active.
- Legacy/manual controls that confuse the primary flow (e.g., separate `Enter Passthrough`/`Scan ESCs` buttons in the default view) should remain hidden or advanced-only.

Required target-selection semantics:

- ESC target selection for settings operations must be explicit and clearly labeled as ESC-selection (not motor-throttle control).
- Prefer a selector (`ESC 1..N`) over a generic numeric slider for target selection clarity.

Required status-bar health semantics:

- Bottom health strip must include protocol-mode visibility that changes with runtime state (e.g., `MSP` vs `ESC Serial`/passthrough).
- Bottom health strip must expose MSP transport health metrics:
  - usage/success percentage
  - error percentage
  - message rate (messages per second)

### 9. Error handling requirements

The app must:

- distinguish transport errors from protocol errors from compatibility errors
- preserve last error details for troubleshooting
- show actionable error messages
- capture worker exceptions and surface them in UI
- never hard-freeze the UI during worker failure
- reset internal busy state after operation failure

### 10. Logging and diagnostics requirements

The app must support:

- in-app log viewer
- operation timeline / recent events
- optional debug-level logging
- raw protocol trace capture toggle for development
- export of logs for bug reports

Protocol-channel note:

- MSP request/response is required for compatibility and control operations, but it is not by itself an ideal transport for continuous general-purpose FC runtime logging.
- For Tang9K migration work, plan a dedicated custom stream-log/event channel for controller-originated diagnostic output (timing markers, runtime warnings, continuous status lines) while keeping MSP-focused traces for command-level debugging.

### 11. Configuration and persistence requirements

The app should persist user preferences such as:

- last selected serial port
- preferred baud rate
- last firmware family filter
- last firmware download/cache location
- window layout preferences
- optional advanced mode toggle

Persistence should **not** store dangerous live protocol state.

### 12. Safety requirements

The app must:

- require explicit confirmation before flashing
- require explicit confirmation before writing settings
- check compatibility before enabling destructive actions
- prevent concurrent flash/write operations on the same transport
- avoid hidden background flashing behavior
- surface target/firmware mismatch clearly

## Function list

The following function list describes the major application responsibilities. The exact Python signatures may change, but the capability set should exist.

### Application bootstrap

- `main()`
  - initialize app
  - load config
  - start worker
  - start ImGui loop

- `create_app_state()`
  - construct root UI/application state

- `shutdown_app()`
  - orderly shutdown of worker, transport, and persistence

### Worker lifecycle

- `start_worker()`
- `stop_worker()`
- `worker_loop()`
- `enqueue_command(command)`
- `poll_events()`
- `handle_worker_event(event)`

### Connection and serial transport

- `list_serial_ports()`
- `connect_serial(port, baudrate)`
- `disconnect_serial()`
- `is_connected()`
- `probe_bridge_status()`

### MSP / passthrough functions

- `send_msp(command_id, payload)`
- `enter_passthrough(motor_index)`
- `exit_passthrough()`
- `get_passthrough_status()`
- `select_target_esc(motor_index)`

### ESC discovery and metadata

- `scan_escs()`
- `read_esc_identity(esc_index)`
- `read_all_esc_identities()`
- `get_esc_summary_list()`
- `set_active_esc(esc_index)`

### EEPROM/settings operations

- `read_eeprom(esc_index)`
- `parse_settings(raw_bytes)`
- `build_settings_view_model(parsed_settings)`
- `update_setting(field_name, value)`
- `validate_settings_for_write(settings)`
- `write_eeprom(esc_index, raw_bytes)`
- `save_settings(esc_index, settings)`
- `reload_settings(esc_index)`

### Firmware catalog and downloads

- `refresh_firmware_catalog()`
- `load_cached_firmware_catalog()`
- `search_firmware_catalog(filters)`
- `download_firmware_manifest()`
- `download_firmware_image(firmware_id)`
- `cache_firmware_image(image)`
- `import_local_firmware_file(path)`
- `inspect_firmware_image(image)`
- `match_firmware_to_esc(image, esc_info)`

### Flashing operations

- `prepare_flash_session(esc_index, firmware_image)`
- `erase_flash(esc_index)`
- `write_flash_block(esc_index, address, data)`
- `verify_flash(esc_index, firmware_image)`
- `flash_esc(esc_index, firmware_image)`
- `flash_selected_escs(esc_indices, firmware_image)`
- `cancel_current_operation()`

### UI rendering functions

- `render_main_window()`
- `render_connection_panel()`
- `render_esc_list_panel()`
- `render_settings_panel()`
- `render_firmware_panel()`
- `render_flash_panel()`
- `render_log_panel()`
- `render_status_bar()`

### Persistence/config functions

- `load_user_config()`
- `save_user_config(config)`
- `get_cache_directory()`
- `get_download_directory()`

### Diagnostics

- `append_log(level, message)`
- `set_operation_progress(stage, current, total)`
- `export_logs(path)`
- `enable_protocol_trace(enabled)`

## Proposed module layout

A clean module layout for the desktop replacement is:

- `app.py`
  - program entry point
- `app_state.py`
  - UI state and shared models
- `worker.py`
  - background worker loop and command execution
- `transport_serial.py`
  - serial port ownership and framing
- `transport_msp.py`
  - MSP encode/decode and commands
- `protocol_4way.py`
  - 4-way command definitions and transactions
- `esc_models.py`
  - ESC metadata, settings, and firmware models
- `firmware_catalog.py`
  - remote catalog download, caching, filtering
- `settings_store.py`
  - user config persistence
- `ui_main.py`
  - top-level window composition
- `ui_panels.py`
  - panel-specific rendering helpers
- `log_view.py`
  - log model and display helpers

## Prompt-ready summary for AI agents

If this project is handed to an AI coding agent, the concise prompt summary is:

- Build a Python desktop ESC configurator in `python/imgui_bundle_esc_config` using `imgui-bundle`.
- It must be a **full replacement** for the web reference app at `https://esc-configurator.com/` for the initial supported families.
- Support **BLHeli_S** and **Bluejay**.
- Use a **two-thread architecture**: ImGui UI thread plus worker/protocol thread.
- The worker owns serial, MSP, and BLHeli 4-way operations.
- Implement connection, passthrough, ESC discovery, EEPROM/settings read/write, firmware catalog download, local firmware import, flash, verify, logging, progress, and failure recovery.
- Prefer message queues between threads.
- Treat this file as the authoritative requirements baseline unless the user explicitly overrides it.

## Non-goals for first parity milestone

These items may come later if needed, but they should not block the first full replacement milestone:

- mobile/touch-specific UI optimization
- translation/localization parity with the web app
- cloud sync of preferences
- support for firmware families beyond BLHeli_S and Bluejay

## Acceptance criteria for first full replacement milestone

The first milestone can be considered successful when the desktop app can:

- connect to the bridge from this repository
- enter passthrough reliably
- enumerate all exposed ESCs
- read BLHeli_S and Bluejay settings
- edit and write supported settings
- fetch firmware metadata from the web or cache
- load a local firmware file
- flash a compatible BLHeli_S or Bluejay image
- verify the flash result
- keep the UI responsive throughout the process
- recover cleanly from common failures

## Summary

The desktop ImGui application should be implemented as a **full esc-configurator replacement** with parity-oriented behavior, not a narrow testing tool.

The design center is:

- **ImGui thread for UI**
- **worker thread for commands/protocol**
- **full BLHeli_S and Bluejay support**
- **firmware download from web plus local file flashing**
- **safe, operator-friendly workflow with strong validation and diagnostics**
