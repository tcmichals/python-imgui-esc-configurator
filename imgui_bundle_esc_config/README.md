# ImGui Bundle ESC Configurator (Python)

This directory contains the Python desktop ESC configurator project built with `imgui-bundle`.

It is intended to become a **full desktop replacement** for `https://esc-configurator.com/` for the supported firmware families in this repository's scope.

This project should not be treated as:

- a minimal demo
- a companion utility
- a limited test harness
- a partial reimplementation of the web workflow

See also:

- `DESIGN_REQUIREMENTS.md` — full replacement scope, architecture, detailed feature requirements, and function list.
- `PROMPT.md` — copy-paste prompt templates for implementation/debugging tasks in this folder.
- `WEBAPP_FEATURE_CACHE.md` — cached map of web esc-configurator module ownership, timeout behavior, and protocol framing.
	It now also includes EEPROM/layout findings and structured-settings parsing notes gathered from the web reference source.

## Why this uses `.venv`

Linux distributions like Debian/Ubuntu may block global or user `pip` installs (PEP 668 externally-managed Python).
A project-local virtual environment avoids that issue and keeps dependencies reproducible.

## Contributor Setup (VS Code friendly)

1. Open the repository in VS Code.
2. Create a virtual environment in the project root named `.venv`.
3. Select that interpreter in VS Code (Command Palette → `Python: Select Interpreter`).
4. Install dependencies from this folder's `requirements.txt`.
5. Run `app.py`.

If VS Code does not auto-select `.venv`, manually choose:

- Linux/macOS: `.venv/bin/python`
- Windows: `.venv\\Scripts\\python.exe`

## Suggested terminal flow

From repository root:

- Create env: `python3 -m venv .venv`
- Activate env: `source .venv/bin/activate`
- Install deps: `pip install -r python/imgui_bundle_esc_config/requirements.txt`
- Run app: `python python/imgui_bundle_esc_config/app.py`

## Current status

- ✅ Basic ImGui app shell
- ✅ Phase 1 worker-based application foundation
- ✅ Shared app modules for state, worker lifecycle, and UI composition
- ✅ Focused pytest coverage for the new worker/controller foundation
- ✅ MSP passthrough commands and ESC discovery integration baseline
- ✅ DSHOT speed control baseline for selected motor via worker command path (`MSP_SET_MOTOR`)
- ✅ DSHOT safety handling baseline (range clamp `0..2047`, invalid motor index rejection, passthrough gating)
- ✅ Settings read/write baseline with readback verification
- ✅ Structured settings decode table baseline
- ✅ Metadata-driven editable enum/bool/number widgets baseline
- ✅ Baseline conditional visibility and validation/sanitize rules for selected fields
- ✅ Descriptor coverage: BLHeli_S + Bluejay full field set with group/safety/beacon/individual categories
- ✅ Firmware catalog refresh (Bluejay GitHub releases + BLHeli_S static list), local disk cache
- ✅ Firmware download from web (layout-aware, PWM variant selection for Bluejay)
- ✅ Firmware flash with erase/write/verify pipeline, progress reporting, and compatibility gating
- ✅ Multi-ESC batch flash (Flash All N ESCs) with partial-failure tracking
- ✅ Cancel in-progress flash/download operations
- ✅ Local firmware file picker (Browse… button)
- ✅ Settings grouped by category with collapsible headers
- ✅ Session persistence (last port, baud rate, firmware path, etc. saved to `~/.config/pico-msp-bridge/prefs.json`)
- ✅ Transport loss auto-disconnect (serial I/O errors auto-emit EventDisconnected)
- ✅ Diagnostics export bundle (ui_logs, protocol_traces, session_metadata)

## Current module layout

- `app.py` — application entry point, worker startup/shutdown, ImGui loop, and prefs save/load
- `app_state.py` — UI-facing state, logs, connection settings, and worker event application
- `worker.py` — queue-based worker/controller for serial enumeration, protocol-mode selection, DSHOT, settings R/W, flash/download, cancel, transport loss detection
- `settings_decoder.py` — structured EEPROM/settings decode helpers for BLHeli_S and Bluejay — full field set with group attributes
- `firmware_catalog.py` — remote firmware catalog client, caching, compatibility checks
- `persistence.py` — session prefs save/load to `~/.config/pico-msp-bridge/prefs.json`
- `diagnostics_export.py` — timestamped diagnostics bundle export
- `runtime_logging.py` — Python file logging mirror of the in-app log window
- `ui_main.py` — ImGui rendering helpers for all panels: connection, passthrough/DSHOT, settings, firmware, diagnostics
- `DESIGN_REQUIREMENTS.md` — canonical scope, architecture, and roadmap document

## Validation status

The current Python foundation is validated with:

- syntax compilation of the relevant Python packages
- focused pytest coverage for shared MSP helpers and the ImGui worker/controller layer
- broader regression coverage across `python/unitTests/`

Recent verified run (this session):

- `python/unitTests`: **131 passed**

## Project direction

The intended end state for `python/imgui_bundle_esc_config/` is a practical operator-facing application that can replace the core supported workflows of the web configurator for:

- BLHeli_S
- Bluejay

That includes, at minimum:

- ESC discovery
- MSP passthrough activation
- BLHeli 4-way communication
- settings read/write
- firmware selection
- local and remote firmware loading
- flashing and verification
- progress, status, and error reporting
