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
