# Hardware-in-the-Loop Smoke Checklist

Purpose:

- Provide a repeatable, operator-facing checklist for validating parity-critical workflows on real hardware.
- Record concrete outcomes (pass/fail/notes) so replacement-complete claims are evidence-based.

Run context:

- Date:
- Operator:
- Host OS:
- Bridge/FC target:
- ESC family:
- ESC count:
- Firmware baseline:
- App version/commit:

## 1) Connection and discovery

- [ ] Serial port detected in app
- [ ] Connect succeeds (no restart required)
- [ ] Read Settings auto-enters passthrough
- [ ] ESC count shown correctly
- [ ] 4-way identity fields populate

Result notes:

- Outcome: PASS / FAIL
- Notes:

## 2) Settings workflow

- [ ] Read settings succeeds on selected ESC
- [ ] Edit at least one setting and write succeeds
- [ ] Verify readback confirms write
- [ ] Exit passthrough succeeds

Result notes:

- Outcome: PASS / FAIL
- Notes:

## 3) Single-ESC firmware flash

- [ ] Local firmware path selected
- [ ] Family/layout compatibility gating works
- [ ] Flash stages run (erase/write/verify)
- [ ] Post-flash reset succeeds
- [ ] App remains responsive throughout

Result notes:

- Outcome: PASS / FAIL
- Notes:

## 4) Multi-ESC flash / cancel / recover

- [ ] Batch flash starts for N ESCs
- [ ] Per-ESC progress and summaries visible
- [ ] Cancel mid-batch works cleanly
- [ ] Recover and rerun succeeds without app restart

Result notes:

- Outcome: PASS / FAIL
- Notes:

## 5) Optimized-mode runtime beyond handshake

- [ ] Connect using `optimized_tang9k`
- [ ] FCSP HELLO / GET_CAPS shown
- [ ] FCSP-native control ops exercised on real target
- [ ] Fallback behavior confirmed when capability missing

Result notes:

- Outcome: PASS / FAIL
- Notes:

## 6) Diagnostics capture

- [ ] UI logs visible and useful
- [ ] Protocol trace window captures expected traffic
- [ ] Diagnostics export bundle generated
- [ ] Runtime log file captured for bug report

Result notes:

- Outcome: PASS / FAIL
- Notes:

## Session summary

- Overall: PASS / FAIL / PARTIAL
- Blocking issues:
- Follow-up actions:
