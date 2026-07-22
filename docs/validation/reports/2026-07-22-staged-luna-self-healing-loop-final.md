# Staged Luna Self-Healing Loop Final Report

## Decision

`STOP_OPERATIONAL_BLOCKER`

The loop did not obtain a valid scientific result. It stopped because repeated
provider output-token ceiling violations are not deterministic defects that can
be repaired offline without changing the frozen experiment or making
hope-based retries.

## Version History

V3 preserved a verified receipt and canonical output in one atomic bundle, then
failed because custody readback compared Python tuples with JSON lists. The
isolated canonicalization defect was corrected and covered by regression tests.

V4 then failed at the strict provider budget boundary. Luna returned 18,778
output tokens against the frozen 16,000 maximum. Scientific interpretation was
correctly withheld. This repeats the output-ceiling behavior previously seen in
Source-First V1, so another unchanged automatic call is prohibited.

## Scientific Answers

- Did Luna find `sensitivity`? **Unknown.** Neither rejected output may be
  reinterpreted.
- Did Luna connect the three event levels? **Not tested.** Stage 2 never ran.
- Where did scientific reasoning fail? **It was not reached.** The terminal
  blocker is provider budget compliance.

## Complete Loop Accounting

- New provider creation calls: 2 of 4 allowed
- Provider retries: 0
- V3 cost: $0.017762
- V4 cost: $0.113504
- Total cost: $0.131266 of $1.00 allowed
- Stage 2 calls: 0
- Graph writes and promotions: 0

## Engineering Result

The loop did materially harden execution integrity:

- typed outputs are consumed directly without JSON-to-strict-model revalidation;
- output, total-token, latency, and cost budgets are independently enforced;
- creation reservations are process-exclusive and durable;
- response IDs are persisted before binding and latency validation;
- canonical payload plus receipt are atomically preserved before derivative
  serialization;
- terminal files are atomically replaced and parent-directory fsynced;
- deterministic anchoring remains source-local and fail-closed;
- Stage 2 cannot run unless Stage 1 passes exact inventory comparison.

These improvements make future results auditable, but they do not constitute a
scientific success. A future experiment needs an officially supported way to
obtain hard output-token compliance or a separately authorized contract change;
this loop cannot silently change that boundary.

The final `make service-checks` run passed with 87.62% coverage. No executable
code changed after that full gate.
