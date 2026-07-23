# Staged Generalization V12 Exposed Gate

## 1. Adjudicated root cause

`FOCUS_EVENT_ANCHORING_PROMPT_GAP`.

## 2. Scientific change

`FOCUS_EVENT_ANCHORING`; the V9/V11 schema and the frozen grader were not relaxed.

## 3. Source-semantic lane

Drug-sensitivity source lane: `PASS`.

## 4. Exact CG projection lane

Drug-sensitivity review-only projection: `PASS`.

## 5. Exposed case outcomes and first frontier

- `generalization-comparison-canary`: scientific pass `True`, focus `True`, source `PASS`, CG `NOT_APPLICABLE`, failure `None`.
- `generalization-drug-sensitivity`: scientific pass `True`, focus `True`, source `PASS`, CG `PASS`, failure `None`.
- `generalization-explicit-nested-cause`: scientific pass `False`, focus `False`, source `FAIL`, CG `NOT_APPLICABLE`, failure `UNRELATED_REGRESSION`.

First failure: `UNRELATED_REGRESSION` at `generalization-explicit-nested-cause`.

## 6. Evaluator and frozen grader

Executed `3` of `6` cases; all admitted evaluations persisted: `True`.

## 7. Exactly-once provider evidence

Provider calls `3`, retries `0`, duplicate creations `0`, receipts valid `True`.

## 8. Usage, latency, and spend

Input `9096`, cached input `0`, output `9751`, reasoning `7432`, total `18847`, latency `81.4646856670006`, spend `$0.067602`.

## 9. Operational budget

Limit `$5.0`; remaining `$4.932398`; exhausted `False`. Telemetry did not affect scientific scoring.

## 10. Historical replay and sealing

V9/V11 replay remained diagnostic-only with zero retroactive credit; sealed V11 hashes preserved: `True`.

## 11. Fresh-case accounting

Fresh cases consumed `0`; untouched fresh cases `7`; next draft `None`.

## 12. Graph and promotion state

Graph writes `0`; trusted promotion `False`.

## 13. Terminal decision

`V12_EXPOSED_GATE_FAIL_UNRELATED_REGRESSION`
