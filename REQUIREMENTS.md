# Python ESC Configurator Requirements

## Mission

Deliver a desktop ESC configurator that keeps GUI workflows stable while protocol transport evolves from MSP-first validation to FCSP-based runtime paths.

## Must-have requirements

1. GUI workflow parity for supported ESC operations:
   - connect/disconnect
   - passthrough enter/exit
   - settings read/write
   - firmware download/flash/verify
2. Worker-thread protocol ownership (UI remains transport-agnostic).
3. MSP compatibility path remains functional during FCSP migration.
4. FCSP support is adapter-driven (no GUI redesign required).
5. Safety constraints preserved:
   - block DSHOT writes while passthrough active
   - deterministic state transitions and clear error reporting

## Cross-repo contract

- Canonical FCSP spec: `../rt-fc-offloader/docs/FCSP_PROTOCOL.md`
- Do not duplicate FCSP spec locally; reference canonical source.

## Platform expectations

- Development host: Linux-first.
- End users: Windows-friendly runtime and setup guidance.
- `.venv/` remains local-only and must not be committed.
