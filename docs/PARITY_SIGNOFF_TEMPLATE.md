# Parity Sign-off Template (Python ESC Configurator vs Web App)

Purpose:

- Provide a single operator-facing form to decide **GO / NO-GO** for replacement parity.
- Capture objective evidence for each parity-critical workflow.
- Avoid ambiguous "looks good" sign-offs.

Run metadata:

- Date:
- Operator:
- Host OS:
- App version/commit:
- Hardware target (FC / bridge):
- ESC family/layout:
- ESC count:
- Protocol mode(s) tested: MSP / optimized_tang9k
- Diagnostics bundle path:

## Decision rule

- **GO** = every required section passes, with evidence attached.
- **NO-GO** = any required section fails, is skipped, or lacks evidence.

---

## Section A — Core workflow parity (required)

### A1. Single-ESC end-to-end

- [ ] Connect succeeds without restart
- [ ] Read settings succeeds
- [ ] Write settings succeeds
- [ ] Readback verification succeeds
- [ ] Single-ESC flash succeeds
- [ ] Flash verify succeeds

Evidence:

- Logs / trace excerpt:
- Notes:
- Outcome: PASS / FAIL

### A2. Multi-ESC batch + cancel/recover

- [ ] Batch flash starts for all target ESCs
- [ ] Progress + per-ESC result visibility is correct
- [ ] Cancel mid-batch works cleanly
- [ ] Recover + rerun succeeds without app restart

Evidence:

- Logs / trace excerpt:
- Notes:
- Outcome: PASS / FAIL

---

## Section B — Protocol behavior parity (required)

### B1. Optimized mode runtime beyond handshake

- [ ] `optimized_tang9k` connect succeeds
- [ ] FCSP capability snapshot is populated
- [ ] FCSP-native controls exercised on hardware
- [ ] Behavior remains stable through repeated operations

Evidence:

- Capability summary line:
- Native paths summary line:
- Notes:
- Outcome: PASS / FAIL

### B2. MSP fallback compatibility

- [ ] Core settings workflow validated in MSP mode
- [ ] Flash path validated in MSP/4-way compatibility path
- [ ] No regression vs baseline expected behavior

Evidence:

- Logs / trace excerpt:
- Notes:
- Outcome: PASS / FAIL

---

## Section C — Observability + operator readiness (required)

### C1. Diagnostics parity

- [ ] Diagnostics export bundle generated
- [ ] Bundle includes FCSP capability/native/block-I/O summaries
- [ ] Runtime log present and useful for postmortem

Evidence:

- Bundle folder:
- Metadata snippets:
- Outcome: PASS / FAIL

### C2. Operator readiness

- [ ] Windows operator setup path validated
- [ ] Current screenshot artifacts updated in docs

Evidence:

- Screenshot path(s):
- Notes:
- Outcome: PASS / FAIL

---

## Sign-off summary

Section outcomes:

- A1:
- A2:
- B1:
- B2:
- C1:
- C2:

Blocking issues (if any):

- 

Risk assessment:

- Low / Medium / High
- Justification:

**Final decision:** GO / NO-GO

Approver:

- Name:
- Date:
- Signature/initials:
