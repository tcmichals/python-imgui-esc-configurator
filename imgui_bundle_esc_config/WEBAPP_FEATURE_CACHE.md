---
title: ESC Configurator Webapp Feature Cache
doc_type: reference-cache
status: active
audience:
  - ai-agent
  - developer
canonicality: supporting
subsystem: imgui-esc-config
purpose: Cache the web esc-configurator module responsibilities, protocol flow, timeout behavior, and ESC serial packet format to avoid repeated rediscovery.
related_docs:
  - DESIGN_REQUIREMENTS.md
  - README.md
  - ../AI_PROMPT_GUIDE.md
  - ../../PROMPTS.md
verified_on: 2026-03-22
source_snapshot:
  - /media/tcmichals/projects/pico/flightcontroller/webapp/esc-configurator/src
---

# Web esc-configurator feature cache (for AI parity work)

This file is a **cache reference** for parity work against the web app at:

- `https://esc-configurator.com/`
- source snapshot used: local clone at `/media/tcmichals/projects/pico/flightcontroller/webapp/esc-configurator`

Use this to avoid repeatedly re-parsing module responsibilities.

## Architecture ownership map

### Top-level flow

- `src/Containers/App/index.jsx`
  - Main orchestration container.
  - Owns lifecycle: serial connect/disconnect, MSP FC info read, passthrough/read/flash/write sequences.
  - Wires UI callbacks into protocol actions (`onEscsRead`, `onEscsWriteSettings`, `onEscsFlashUrl`, etc.).

- `src/Components/App/index.jsx`
  - Presentation composition root.
  - Connects `PortPicker`, `MainContent`, `Statusbar`, `Log`, settings dialogs.

- `src/Components/MainContent/index.jsx`
  - Feature routing by state:
    - disconnected -> `Home` + `Changelog`
    - selecting firmware -> `FirmwareSelector`
    - active/normal -> `Flash`, `MotorControl`, action `Buttonbar`

### Feature modules

- `src/Components/PortPicker/index.jsx`
  - Port selection/permission, baud-rate selector, connect/disconnect button.

- `src/Components/Flash/index.jsx`
  - Common + individual ESC settings panels; dump actions and per-ESC progress widgets.

- `src/Components/FirmwareSelector/index.jsx`
  - Firmware family/version/layout/PWM selection.
  - Remote URL and local-file flash entry points.
  - Safety toggles: `force` and `migrate`.

- `src/Components/MotorControl/*`
  - Direct motor spin controls when not in 4-way read mode.

- `src/Components/Statusbar/*`
  - Telemetry/health strip (including packet error accumulation).

- `src/Components/Log/*`
  - User-facing operation/event logging.

### Protocol and transport modules

- `src/utils/Serial.js`
  - Unified transport abstraction.
  - Owns queue-based FIFO command execution.
  - Hosts both MSP (`Msp`) and 4-way (`FourWay`) clients.

- `src/utils/helpers/QueueProcessor.js`
  - Single-command-at-a-time queue.
  - Prevents serial race conditions.
  - Timeout and partial-buffer handling.

- `src/utils/Msp.js`
  - MSP v1 and v2 encode/decode.
  - FC metadata/status/features queries.
  - passthrough request: `MSP_SET_PASSTHROUGH` (`245`).

- `src/utils/FourWay.js`
  - BLHeli 4-way message creation/parsing.
  - Read/write EEPROM, flash write/verify, reset, keepalive.

- `src/utils/FourWayConstants.js`
  - 4-way command IDs, ACK enum, interface modes.

### Firmware catalog modules

- `src/Containers/App/configsSlice.js`
  - loads firmware `versions` and `escs` maps for each source at startup/background refresh.
- `src/sources/Source.js`
  - base abstraction for firmware families.
  - owns EEPROM layouts, settings descriptions, ESC layouts, revisions, and versions metadata.
- `src/sources/GithubSource.js`
  - GitHub releases-based source helper.
  - maps release metadata to `{ name, key, url, releaseUrl, prerelease, published_at }`.
- bundled static source JSON is used where webapp does not fetch release metadata dynamically.

## Timeout / retry behavior (webapp baseline)

Values below come directly from the source snapshot listed in frontmatter.

- Queue command timeout:
  - default `1000 ms` in `QueueProcessor.addCommand(..., timeout = 1000)`.
- 4-way command retries:
  - `sendMessagePromised(..., retries = 10)` in `FourWay.js`.
  - retry spacing: `250 ms` (`retry(processMessage, retries, 250)`).
- 4-way keepalive cadence:
  - interval tick every `800 ms`.
  - send `cmd_InterfaceTestAlive` if no command for `> 900 ms`.
- ESC boot stabilization delay after entering 4-way:
  - `1200 ms` wait in `handleReadEscs` before reading ESC info.

Operational implication:

- The web stack intentionally serializes all wire operations through a single FIFO queue.
- A Python parity worker should preserve this single-owner, serialized I/O pattern.

## Protocol breakdown

### MSP side (FC control / passthrough entry)

Core commands used during connect/bring-up include:

- `MSP_API_VERSION (1)`
- `MSP_FC_VARIANT (2)`
- `MSP_FC_VERSION (3)`
- `MSP_BUILD_INFO (5)`
- `MSP_BOARD_INFO (4)`
- `MSP_UID (160)`
- `MSP_STATUS (101)`
- `MSP_MOTOR (104)`
- `MSP_SET_PASSTHROUGH (245)` -> enter ESC interface

MSP v1 frame encoding in source:

- header: `$`, `M`, `<`
- then: payload length, command, payload bytes, XOR checksum

MSP v2 frame encoding in source:

- header: `$`, `X`, `<`
- then: flag, command LSB/MSB, length LSB/MSB, payload, DVB-S2 CRC8

### ESC serial protocol (BLHeli 4-way framing)

Host -> device frame built in `FourWay.createMessage`:

- `byte0`: `0x2f` (PC marker)
- `byte1`: command
- `byte2..3`: address (big-endian)
- `byte4`: param count (`0` means `256` bytes)
- `byte5..`: params
- last 2 bytes: CRC16 XMODEM over message without trailing checksum

Device -> host frame parsed in `FourWay.parseMessage`:

- `byte0`: `0x2e` (interface marker)
- `byte1`: command echo
- `byte2..3`: address
- `byte4`: param count (`0` => `256`)
- `byte5..(5+count-1)`: params
- `byte(5+count)`: ACK
- `byte(6+count)..(7+count)`: CRC16 XMODEM

Selected command IDs (`FourWayConstants.js`):

- `0x30` test alive
- `0x34` interface exit
- `0x35` device reset
- `0x37` init flash
- `0x39` page erase
- `0x3a` read
- `0x3b` write
- `0x3d` read EEPROM
- `0x3e` write EEPROM

ACK success code:

- `ACK_OK = 0x00`

## EEPROM / settings format findings

The web app does **not** treat EEPROM as opaque bytes forever.
It uses a consistent three-layer model:

1. raw EEPROM byte array
2. layout definition (`offset` + `size` per field)
3. settings-description metadata (`type`, labels, enum options, visibility rules)

### Core conversion rules (from `src/utils/helpers/Convert.js`)

The web app decodes EEPROM bytes with these rules:

- `size == 1`
  - decode as unsigned 8-bit integer
- `size == 2`
  - decode as big-endian unsigned 16-bit integer
- `size > 2`
  - decode as ASCII string and trim trailing spaces
- exception: `STARTUP_MELODY`
  - keep as raw byte array rather than converting to string

Writeback uses the inverse rules:

- 1-byte fields -> single byte
- 2-byte fields -> big-endian pair
- strings -> padded with spaces
- `STARTUP_MELODY` -> copied as byte list with zero fill

### BLHeli_S EEPROM layout baseline

Source reference:

- `src/sources/Blheli/eeprom.js`

Key findings:

- `LAYOUT_SIZE = 0x70`
- key offsets include:
  - `0x00` `MAIN_REVISION`
  - `0x01` `SUB_REVISION`
  - `0x02` `LAYOUT_REVISION`
  - `0x0D..0x0E` `MODE` (2-byte)
  - `0x40..0x4F` `LAYOUT` (16-byte string)
  - `0x50..0x5F` `MCU` (16-byte string)
  - `0x60..0x6F` `NAME` (16-byte string)

The BLHeli_S settings-description side is keyed by `LAYOUT_REVISION` and split into:

- `COMMON[layout_revision]`
- `INDIVIDUAL[layout_revision]`
- `DEFAULTS[layout_revision]`

That means the layout file defines **where bytes live**, while the settings file defines **what the UI should show/edit**.

### Bluejay EEPROM layout baseline

Source references:

- `src/sources/Bluejay/eeprom.js`
- `src/sources/Bluejay/settings.js`

Key findings:

- `LAYOUT_SIZE = 0xFF`
- Bluejay keeps the BLHeli-style core header/identity region and extends it with melody data.
- notable offsets:
  - `0x00` `MAIN_REVISION`
  - `0x01` `SUB_REVISION`
  - `0x02` `LAYOUT_REVISION`
  - `0x40..0x4F` `LAYOUT`
  - `0x50..0x5F` `MCU`
  - `0x60..0x6F` `NAME`
  - `0x70..0xEF` `STARTUP_MELODY` (128 bytes)
  - `0xF0..0xF1` `STARTUP_MELODY_WAIT_MS` (2-byte)

Bluejay settings descriptions are also keyed by `LAYOUT_REVISION`.
Observed revisions in the source snapshot include `200..209`.

### Settings-description model

The web UI does not render fields directly from raw layout definitions.
It uses a second metadata layer with entries like:

- `name`
- `type` (`bool`, `number`, `enum`, `melody`, etc.)
- `label`
- `min` / `max` / `step`
- `options` for enums
- `group` / `order`
- optional dynamic rules such as `visibleIf` and `sanitize`

Observed rule patterns from the reference source that matter for Python parity:

- some fields are only shown when another setting enables them
  - example: Bluejay dynamic PWM thresholds only matter when PWM frequency is `Dynamic`
  - example: center throttle style fields may only matter for 3D / forward-reverse modes
- some value sets require post-edit sanitizing
  - example: Bluejay threshold ordering where `96->48` should not exceed `48->24`

This is important for Python parity:

- raw EEPROM parsing alone is **not enough** for a parity editor
- you also need a field-description layer to drive labels, widgets, validation, and visibility

### Common fields identified in source snapshot

Commonly surfaced fields include:

- `MOTOR_DIRECTION`
- `COMMUTATION_TIMING`
- `DEMAG_COMPENSATION`
- `BEEP_STRENGTH`
- `BEACON_STRENGTH`
- `BEACON_DELAY`
- `BRAKE_ON_STOP`
- `TEMPERATURE_PROTECTION`
- `PWM_FREQUENCY`
- Bluejay-specific additions such as:
  - `STARTUP_POWER_MIN`
  - `STARTUP_POWER_MAX`
  - `BRAKING_STRENGTH`
  - `POWER_RATING`
  - `FORCE_EDT_ARM`
  - `THRESHOLD_96to48`
  - `THRESHOLD_48to24`
  - `STARTUP_MELODY`

### Parity implications for Python implementation

For `python/imgui_bundle_esc_config`, a realistic parity path is:

1. keep raw read/write support for transport debugging
2. decode EEPROM bytes using layout definitions
3. attach settings-description metadata for display/edit widgets
4. later add `visibleIf` / sanitize / grouping behavior

Do **not** assume that BLHeli_S and Bluejay share identical editable-field sets even when many offsets overlap.

Current repository implementation status:

- raw EEPROM read/write baseline exists in the Python worker
- a first Python structured decoder now exists for BLHeli_S / Bluejay core fields
- the current ImGui UI can show a decoded structured table after a settings read
- field-level editable widgets now exist for enum/bool/number baseline fields
- Python-side payload serialization now reuses the decoded field metadata and existing worker write+verify path
- selected metadata-driven visibility/sanitize rules now exist in the Python implementation
- wider descriptor coverage is still pending
- a first firmware catalog client now exists in Python

## Firmware catalog format findings

The web reference keeps firmware selection data in two parallel structures per source:

- `versions[source_name]`
  - release/version entries
- `escs[source_name]`
  - available ESC layout keys/names for that firmware family

### Version-entry shape

Observed version entry fields include:

- `name`
- `key`
- `url` (download-base or template)
- `releaseUrl` (GitHub tag page, when applicable)
- `prerelease`
- `published_at`

### Bluejay source behavior

Bluejay uses GitHub releases metadata via:

- `src/sources/GithubSource.js`
- repo: `bird-sanctuary/bluejay`

Behavior:

- fetch release list from GitHub API
- ignore releases with no assets
- ignore blacklisted tags (observed blacklist includes `v0.8`)
- expose release metadata as version entries

### BLHeli_S source behavior

BLHeli_S in the web reference uses bundled static `versions.json` entries rather than GitHub releases parsing.

Behavior:

- each entry has a display name, key, and download URL template
- URL templates contain a layout placeholder such as `{0}`
- actual firmware URL is formed later using selected layout key

### ESC layout catalog shape

Both BLHeli_S and Bluejay sources expose `escs.json` with:

- `layouts` object keyed by layout token (e.g. `#A_H_30#`)
- value contains human-facing `name`

Observed pattern difference:

- BLHeli_S layouts use timing-oriented variants like `A-H-30`
- Bluejay layouts use `120` style suffix families like `A-H-120`

### Python implementation note

Current Python baseline:

- `firmware_catalog.py`
  - Bluejay GitHub release parsing baseline
  - BLHeli_S static release baseline
- worker refresh command/event path exists
- cache persistence, image download, and layout-aware filtering are still pending

### Cache note for future AI passes

If you need EEPROM parsing or structured settings UI work:

- consult this section first
- then inspect the matching web source files only if the current task needs a field not listed here
- avoid starting from raw byte dumps with guessed field names

## Practical parity mapping to Python replacement

Use this mapping when implementing `python/imgui_bundle_esc_config`:

- Web `Containers/App/index.jsx` -> Python `worker.py` command handlers + app orchestration
- Web `Serial.js` + `QueueProcessor.js` -> Python worker-owned serial client + strict FIFO command queue
- Web `Msp.js` -> Python MSP framing/command module (`python/MSP/protocol.py` and worker integration)
- Web `FourWay.js` -> Python 4-way framing/ops module (`python/MSP/fourway.py` and worker integration)
- Web UI components -> Python `ui_main.py` + panel modules/state models

## Cache prompt (copy/paste)

Use this prompt to force feature parsing from the cached map before coding:

> Work in `python/imgui_bundle_esc_config`.
> Before implementing, use `python/imgui_bundle_esc_config/WEBAPP_FEATURE_CACHE.md` as the authoritative cache for web esc-configurator module responsibilities, timeout behavior, and protocol flow.
> Do not re-discover module ownership from scratch unless this cache is missing details required for the specific task.
> Preserve worker-thread transport ownership and serialized command execution semantics.
> Keep MSP passthrough and BLHeli 4-way behavior compatible with the cached protocol breakdown (including frame format, ACK handling, retry/timeout expectations).
