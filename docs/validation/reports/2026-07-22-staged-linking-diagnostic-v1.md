# Staged Linking Diagnostic V1

## Decision

`STOP_EVENT_LINKING_SCIENTIFIC_FAILURE`

This was a valid, exposed-development diagnostic. It is review-only, receives no
qualification credit, performed no graph writes, and enables no promotion.

## What Passed

- The preserved V3 inventory replay passed custody and hash verification as
  `NONCREDITABLE_DIAGNOSTIC_STAGE1_PASS`.
- Luna preserved all three immutable event nodes: decrease, sensitivity, and
  enhancement.
- Luna attached `c-Myc` to the decrease event as `THEME`.
- Luna attached `cancer cell` and `vinblastine` to the sensitivity event.
- Participant spans and entity types were exact.
- The enhancement event linked the decrease event as `CAUSE` and the sensitivity
  event as `THEME`.
- The enhancement event was the correct root.
- No unsupported, disconnected, contradictory, or cyclic nodes were introduced.
- Both provider receipts passed output-token, total-token, latency, and cost
  budgets with zero retries and zero duplicate creation calls.

## Scientific Failure

The sensitivity event assigned vinblastine the role `OTHER_EXPLICIT`. The exposed
public annotation requires `CAUSE`. Because role fidelity is part of complete
event equality, deterministic comparison returned:

- participant fidelity: pass;
- root fidelity: pass;
- nesting fidelity: fail;
- exact complete event: fail.

The model explicitly reasoned that the phrase `sensitivity to vinblastine` did
not establish a cause or instrument. This is a scientific/annotation-policy
role disagreement, not a missing-event, participant-merging, or graph-flattening
failure.

## Source-Only Review

The blinded reviewer returned `SUPPORTED` and stated that the complete nested
structure was source-supported. Its evidence field was not an exact source span:
it concatenated two quoted sentences. Deterministic anchor resolution therefore
failed closed. The review was preserved in custody but was not accepted as a
valid source-grounded review result.

This reviewer behavior does not override the deterministic role mismatch.

## Provider Accounting

| Stage | Response | Input | Output | Total | Latency | Cost |
|---|---|---:|---:|---:|---:|---:|
| Linking | `resp_063763339a6a1e71006a60fd95a758819997228d5e74ad77af` | 1,196 | 7,764 | 8,960 | 280.684 s | $0.047780 |
| Review | `resp_08c8d9a59c15986f006a60fead99d48199b16de9d88c9ec1d2` | 1,056 | 1,149 | 2,205 | 38.041 s | $0.007950 |
| Total | 2 calls | 2,252 | 8,913 | 11,165 | 318.725 s | $0.055730 |

The loop used two of the maximum three creation calls and $0.055730 of the $1.00
global budget. It stopped because a valid scientific failure must not trigger
prompt rewriting or another provider call.

## Validation

- Focused source-first suite: 34 passed.
- Ruff: passed.
- MyPy on the new modules: passed.
- Architecture structure guard: passed.
- `make service-checks`: passed once after the terminal result.
- Coverage: 87.62%, above the required 86%.

## Plain-Language Conclusion

The staged design materially improved structure. Luna found and kept the missing
sensitivity event, assigned the right entities, and connected the three event
levels without flattening them. It still did not reproduce the expert benchmark
role for vinblastine. Therefore staged linking is promising, but this diagnostic
does not pass complete scientific fidelity and cannot qualify the system.
