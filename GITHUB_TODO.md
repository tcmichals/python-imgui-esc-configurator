# GitHub TODO — python-imgui-esc-configurator

## Current focus

- [ ] Wire FCSP adapter into worker transport selection path
- [ ] Add FCSP discovery handshake handling (`HELLO`, `GET_CAPS`)
- [ ] Keep MSP fallback path fully passing

## Protocol tasks

- [ ] Map worker feature intents to FCSP CONTROL ops
- [ ] Add block read/write helpers for dynamic IO spaces
- [ ] Support dynamic capability rendering (counts/flags from caps TLVs)

## Tests

- [ ] Run focused FCSP tests in `.venv`
- [ ] Add worker-level FCSP mode tests
- [ ] Keep existing MSP/passthrough regression tests green

## Docs

- [ ] Add screenshot(s) section in README (Windows + Linux examples)
- [ ] Keep Windows setup path explicit in README
- [ ] Link to canonical FCSP spec only (no duplicate copies)
