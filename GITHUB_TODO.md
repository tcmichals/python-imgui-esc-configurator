# GitHub TODO — python-imgui-esc-configurator

## Current focus

- [x] Implement native FCSP worker ops for the core optimized path
	- [x] `PT_ENTER`
	- [x] `PT_EXIT`
	- [x] `ESC_SCAN`
	- [x] `SET_MOTOR_SPEED`
	- [x] `GET_LINK_STATUS`
- [ ] Start using native FCSP block ops where they replace legacy tunneling cleanly
	- [x] `READ_BLOCK` / `WRITE_BLOCK` for settings (`ESC_EEPROM`) in optimized mode with fallback
	- [ ] `READ_BLOCK` for additional dynamic state / IO windows
	- [ ] `WRITE_BLOCK` for additional dynamic state / IO windows
	- [ ] define migration path for remaining `ESC_EEPROM` / `FLASH` usage
- [ ] Keep MSP fallback path fully passing while FCSP-native paths are added

## Protocol tasks

- [x] Align Python FCSP codec to canonical `rt-fc-offloader/docs/FCSP_PROTOCOL.md`
- [x] Add FCSP discovery handshake handling (`HELLO`, `GET_CAPS`)
- [x] Add spec-aligned block read/write helper codecs
- [x] Support dynamic capability rendering in Python state / UI
- [ ] Add capability-gated behavior in the worker / UI
	- [x] gate actions based on advertised ops (with MSP fallback where applicable)
	- [x] gate actions based on advertised spaces for FCSP settings block path
	- [x] expose decoded op/space support flags in UI/diagnostics state
	- [ ] extend space-gating coverage to all future FCSP block-op features
	- [x] surface profile and capability support more explicitly in diagnostics/export
	- [ ] reduce optimized-mode assumptions when caps say features are unavailable

## Tests

- [x] Run focused FCSP tests in `.venv`
- [x] Add worker-level FCSP discovery tests
- [x] Keep existing MSP/passthrough regression tests green
- [x] Add FCSP-native worker tests for control ops
	- [x] passthrough enter / exit
	- [x] ESC scan
	- [x] motor speed write
	- [x] link status read
- [ ] Add higher-level parity validation still missing from unit coverage
	- [ ] compact / narrow-window UI behavior
	- [ ] offline / corrupt firmware-cache startup behavior
	- [ ] hardware-in-the-loop smoke checklist and results

## Parity / replacement completion

- [ ] Finish the remaining proof points before claiming full web-app replacement parity
	- [ ] validate real hardware multi-ESC flash / cancel / recover behavior
	- [ ] validate optimized-mode runtime behavior beyond discovery handshake
	- [ ] confirm Windows operator setup path is current and documented

## Docs

- [ ] Update README / status docs to reflect current FCSP progress accurately
- [ ] Add screenshot(s) section in README (Windows + Linux examples)
- [ ] Keep Windows setup path explicit in README
- [x] Link to canonical FCSP spec via submodule (`rt-fc-offloader/docs/FCSP_PROTOCOL.md`)

## Recently completed

- [x] Added `rt-fc-offloader` as a git submodule
- [x] Synced Python FCSP codec with the updated canonical spec
- [x] Added spec-aligned `HELLO` / `GET_CAPS` / `READ_BLOCK` / `WRITE_BLOCK` helpers
- [x] Restored full `unitTests` suite to green after FCSP changes
- [x] Added FCSP-native `GET_LINK_STATUS` worker command/event path and UI refresh action
- [x] Added capability-gated FCSP op behavior in worker (advertised-op checks + fallback)
- [x] Added FCSP settings `READ_BLOCK` / `WRITE_BLOCK` path with capability-gated space checks and compatibility fallback
- [x] Added FCSP capability/link snapshot in diagnostics panel and exported metadata bundle
- [x] Added decoded FCSP op/space support flags in state + diagnostics export and gated link-status refresh action in UI
- [x] Re-verified full `unitTests` suite (`181 passed`)
