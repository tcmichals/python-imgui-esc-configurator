# HISTORY

Running technical history log for this repository.

Purpose:

- Keep a concise, human-readable engineering timeline beyond raw git diffs.
- Capture what changed, why it changed, and how it was validated.
- Record pytest/test verification so regressions are easier to triage later.

How to update this file:

For each meaningful commit or milestone, append a new entry with:

- Date (UTC)
- Commit hash (short)
- Scope summary
- Key files/systems touched
- Validation run (pytest command + pass/fail summary)
- Notes/known follow-ups

---

## 2026-04-03

### Commit

- `a9a2ae8` (primary milestone commit for this entry)

### Scope

- Expanded FCSP worker capabilities and capability-aware behavior in optimized mode.
- Added FCSP diagnostics and support-state visibility in UI/app state/export.
- Expanded README technical onboarding and observability documentation.
- Added submodule link to canonical FCSP spec repository.

### Key areas touched

- `imgui_bundle_esc_config/worker.py`
- `imgui_bundle_esc_config/app_state.py`
- `imgui_bundle_esc_config/ui_main.py`
- `imgui_bundle_esc_config/diagnostics_export.py`
- `comm_proto/fcsp.py`
- `unitTests/test_imgui_worker.py`
- `unitTests/test_fcsp.py`
- `unitTests/test_imgui_diagnostics_export.py`
- `README.md`
- `ROADMAP.md`
- `GITHUB_TODO.md`

### Validation

- `./.venv/bin/python -m pytest unitTests -q` → `181 passed in 7.63s`

### Notes

- Protocol tracing is treated as first-class observability across worker-driven MSP/4-way/FCSP paths.
- Keep this file updated each session with short, test-backed entries.

---

## 2026-04-03 (session follow-up)

### Commit

- pending (working tree; not committed yet)

### Scope

- Extended decoded FCSP address-space support flags beyond `ESC_EEPROM` to include:
	- `FLASH`
	- `PWM_IO`
	- `DSHOT_IO`
- Surfaced these support flags in:
	- app state decode logic
	- optimized connection-panel support summary
	- diagnostics export metadata
- Added/updated unit coverage for decoded space flags and diagnostics export assertions.

### Key areas touched

- `imgui_bundle_esc_config/app_state.py`
- `imgui_bundle_esc_config/ui_main.py`
- `imgui_bundle_esc_config/diagnostics_export.py`
- `unitTests/test_imgui_worker.py`
- `unitTests/test_imgui_diagnostics_export.py`
- `GITHUB_TODO.md`

### Validation

- Focused: `./.venv/bin/python -m pytest unitTests/test_imgui_worker.py unitTests/test_imgui_diagnostics_export.py -q` → `63 passed in 7.50s`
- Full: `./.venv/bin/python -m pytest unitTests -q` → `181 passed in 7.63s`

### Notes

- This keeps capability decoding aligned with the “reduce optimized-mode assumptions” goal by making more advertised spaces explicit in UI/diagnostics.

---

## 2026-04-03 (architecture docs follow-up)

### Commit

- pending (working tree; not committed yet)

### Scope

- Documented the worker layer as a reusable backend/kernel rather than GUI-only glue.
- Added explicit philosophy/design requirement that worker/protocol code must remain reusable from pytest, command-line tools, alternate frontends, and `rt-fc-offloader` bring-up helpers.
- Tightened the runtime boundary by adding public frontend-agnostic worker helpers and removing direct private dependency access from `app.py`.

### Key areas touched

- `README.md`
- `imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`
- `imgui_bundle_esc_config/worker.py`
- `imgui_bundle_esc_config/app.py`

### Validation

- Errors: no errors found in updated README, design spec, worker, app, history, and TODO files
- Focused: `./.venv/bin/python -m pytest unitTests/test_imgui_worker.py -q` → `61 passed in 7.23s`
- Full: `./.venv/bin/python -m pytest unitTests -q` → `181 passed in 7.60s`

### Notes

- This makes the reuse/testability philosophy explicit so future changes do not accidentally push protocol behavior back up into the GUI layer.

---

## 2026-04-03 (backend contract extraction)

### Commit

- pending (working tree; not committed yet)

### Scope

- Introduced `imgui_bundle_esc_config/backend_models.py` as the shared command/event contract module.
- Updated `worker.py` to import public command/event types from the shared contract instead of defining duplicate runtime-local copies.
- Updated `ui_main.py`, `app_state.py`, and package exports to consume backend contracts directly while keeping `WorkerController` as the runtime engine.
- Preserved worker compatibility for existing imports and kept all unit tests green.

### Key areas touched

- `imgui_bundle_esc_config/backend_models.py`
- `imgui_bundle_esc_config/worker.py`
- `imgui_bundle_esc_config/ui_main.py`
- `imgui_bundle_esc_config/app_state.py`
- `imgui_bundle_esc_config/__init__.py`
- `README.md`

### Validation

- Errors: no errors found in updated backend model/runtime/frontend files
- Focused: `./.venv/bin/python -m pytest unitTests/test_imgui_worker.py unitTests/test_imgui_parity.py unitTests/test_imgui_settings_decoder.py -q` → `133 passed in 7.72s`
- Full: `./.venv/bin/python -m pytest unitTests -q` → `181 passed in 7.65s`

### Notes

- This strengthens the “project as classroom/reference” goal by making the backend contract boundary explicit and reusable across frontends/tests.

---

## 2026-04-03 (headless classroom frontend)

### Commit

- pending (working tree; not committed yet)

### Scope

- Added a minimal headless frontend module `imgui_bundle_esc_config/headless_cli.py` that demonstrates non-ImGui usage of the shared backend command/event boundary.
- Added `unitTests/test_headless_cli.py` with fake-controller driven tests for ports listing, connect/disconnect flow, and timeout behavior.
- Exported `run_headless_frontend` from package `__init__.py` and documented the headless frontend in README files.

### Key areas touched

- `imgui_bundle_esc_config/headless_cli.py`
- `unitTests/test_headless_cli.py`
- `imgui_bundle_esc_config/__init__.py`
- `README.md`
- `imgui_bundle_esc_config/README.md`

### Validation

- Focused: `./.venv/bin/python -m pytest unitTests/test_headless_cli.py unitTests/test_imgui_worker.py -q` → `64 passed in 7.32s`
- Full: `./.venv/bin/python -m pytest unitTests -q` → `184 passed in 7.64s`

### Notes

- This provides a concrete “frontend can change, backend contract stays” classroom example, reinforcing the project’s architecture standard for humans and AI agents.

---

## 2026-04-03 (classroom/reference policy follow-up)

### Commit

- pending (working tree; not committed yet)

### Scope

- Documented the repository as a classroom/reference implementation in addition to being a product.
- Added policy wording that the repo should teach humans and AI agents the preferred standard for GUI/backend separation, reuse, pytest-driven validation, and observability.

### Key areas touched

- `README.md`
- `imgui_bundle_esc_config/DESIGN_REQUIREMENTS.md`

### Validation

- Errors: no errors found in updated README, design spec, history, and TODO files

### Notes

- This makes the educational intent explicit so future contributors treat code clarity and architectural demonstration as part of the deliverable.

---

## 2026-04-03 (headless monitor mode)

### Commit

- pending (working tree; not committed yet)

### Scope

- Extended `imgui_bundle_esc_config/headless_cli.py` with a `monitor` subcommand for classroom/demo event streaming.
- Added `monitor --duration` and `monitor --refresh-ports` options to demonstrate passive observation and active trigger paths.
- Added monitor-specific unit tests for streaming output and refresh command enqueue behavior.

### Key areas touched

- `imgui_bundle_esc_config/headless_cli.py`
- `unitTests/test_headless_cli.py`

### Validation

- Focused: `./.venv/bin/python -m pytest unitTests/test_headless_cli.py -q` → `5 passed in 0.28s`
- Full: `./.venv/bin/python -m pytest unitTests -q` → `186 passed in 7.92s`

### Notes

- This strengthens the “frontend can change, backend contract stays” lesson by making backend events easy to inspect without a GUI.

---

## 2026-04-03 (firmware cache recovery hardening)

### Commit

- pending (working tree; not committed yet)

### Scope

- Hardened firmware-catalog startup behavior when cached snapshot JSON is corrupt/unreadable.
- Added automatic quarantine of corrupt cache files (`catalog_snapshot.corrupt.<timestamp>.json`) so future refresh/load attempts can recover cleanly.
- Added startup observability: app now logs/cache-warns when cache load fails and emits a UI-visible warning log event before live refresh.
- Added unit coverage for corrupt-cache quarantine and offline behavior when only corrupt cache exists.

### Key areas touched

- `imgui_bundle_esc_config/firmware_catalog.py`
- `imgui_bundle_esc_config/worker.py`
- `imgui_bundle_esc_config/app.py`
- `unitTests/test_firmware_catalog.py`

### Validation

- Focused: `./.venv/bin/python -m pytest unitTests/test_firmware_catalog.py unitTests/test_imgui_worker.py -q` → `76 passed in 7.34s`
- Full: `./.venv/bin/python -m pytest unitTests -q` → `187 passed in 7.93s`

### Notes

- This closes a parity checklist gap around offline/corrupt firmware-cache startup behavior and improves field diagnosability.

---

## 2026-04-03 (compact/narrow-window parity coverage)

### Commit

- pending (working tree; not committed yet)

### Scope

- Added a pure status-bar layout helper in `ui_main.py` to make compact-vs-full width behavior deterministic and unit-testable.
- Added parity tests covering compact threshold boundary and compact/full truncation limits for status/port/metrics text widths.

### Key areas touched

- `imgui_bundle_esc_config/ui_main.py`
- `unitTests/test_imgui_parity.py`

### Validation

- Focused: `./.venv/bin/python -m pytest unitTests/test_imgui_parity.py -q` → `61 passed in 0.49s`
- Full: `./.venv/bin/python -m pytest unitTests -q` → `190 passed in 7.82s`

### Notes

- This closes the parity checklist item for compact/narrow-window UI behavior at the unit-test level.

---

## 2026-04-03 (feature-completeness docs pass)

### Commit

- pending (working tree; not committed yet)

### Scope

- Added explicit Windows operator setup steps to the root `README.md`.
- Expanded screenshot section to call out current Linux capture and track pending Windows capture.
- Added `docs/HIL_SMOKE_CHECKLIST.md` to standardize real-hardware validation runs and result recording.

### Key areas touched

- `README.md`
- `docs/HIL_SMOKE_CHECKLIST.md`
- `GITHUB_TODO.md`

### Validation

- Full: `./.venv/bin/python -m pytest unitTests -q` → `190 passed in 7.85s`

### Notes

- Remaining parity blockers are now primarily hardware-evidence dependent (multi-ESC flash/cancel/recover, optimized-mode runtime beyond handshake, and Windows screenshot capture).

---

## 2026-04-03 (fcsp diagnostics parity follow-up)

### Commit

- pending (working tree; not committed yet)

### Scope

- Extended diagnostics export metadata to include newer FCSP op-support flags (`PT_ENTER`, `PT_EXIT`, `ESC_SCAN`, `SET_MOTOR_SPEED`).
- Exported derived native-path availability booleans so diagnostics bundles show what the UI/worker infer from capability TLVs.
- Exported the last generic `READ_BLOCK` / `WRITE_BLOCK` snapshot metadata (space/address/size/preview/verified).
- Expanded the optimized-mode FCSP diagnostics section in `ui_main.py` to show raw op support, derived native-path availability, and last block-I/O activity.
- Added AppState-owned operator summary helpers (`fcsp_capability_summary_line`, `fcsp_native_paths_summary_line`, `fcsp_last_block_io_summary_line`) and used them in both diagnostics UI and export metadata.

### Key areas touched

- `imgui_bundle_esc_config/app_state.py`
- `imgui_bundle_esc_config/diagnostics_export.py`
- `imgui_bundle_esc_config/ui_main.py`
- `unitTests/test_imgui_parity.py`
- `unitTests/test_imgui_diagnostics_export.py`
- `GITHUB_TODO.md`

### Validation

- Focused: `./.venv/bin/python -m pytest unitTests/test_imgui_diagnostics_export.py unitTests/test_imgui_parity.py unitTests/test_imgui_worker.py -q` → `137 passed in 7.75s`
- Focused (latest summary-helper pass): `./.venv/bin/python -m pytest unitTests/test_imgui_parity.py unitTests/test_imgui_diagnostics_export.py -q` → `71 passed in 0.56s`
- Full: `./.venv/bin/python -m pytest unitTests -q` → `204 passed in 7.87s`

### Notes

- Remaining proof points are still the real-hardware checklist items and screenshot capture, not missing software-side FCSP metadata visibility.

---

## 2026-04-03 (parity sign-off template)

### Commit

- pending (working tree; not committed yet)

### Scope

- Added `docs/PARITY_SIGNOFF_TEMPLATE.md` as a one-page operator form for explicit GO/NO-GO replacement parity decisions.
- Linked the new template in `README.md` "Start here" so it is discoverable alongside the HIL smoke checklist.
- Updated `GITHUB_TODO.md` recently completed list to reflect the sign-off artifact.

### Key areas touched

- `docs/PARITY_SIGNOFF_TEMPLATE.md`
- `README.md`
- `GITHUB_TODO.md`

### Validation

- Documentation-only update; no runtime behavior changes.

### Notes

- This enables a single-session parity decision workflow, but final GO still depends on real-hardware evidence completion.
