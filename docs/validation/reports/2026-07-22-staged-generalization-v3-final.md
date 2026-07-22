# Staged Generalization V3 Final Report

## Terminal Decision

`PIVOT_WITH_EVIDENCE`

The bounded checkpoint used all three permitted scientific-improvement cycles.
No additional provider call is authorized in this loop.

## What V3 Proved

The comparison canary passed every frozen gate:

- complete event recovery;
- source-semantic participant roles;
- comparison and direction;
- polarity, uncertainty, and statistics;
- exact evidence grounding;
- zero unsupported claims and contradictions.

This directly corrected V2's focal-population role error. Luna used
`POPULATION`, `COMPARATOR`, and `OUTCOME` correctly.

The second case also returned scientifically coherent source meaning:

- one `COMPARISON` event with `NO_DIFFERENCE` direction and comparison;
- `NULL_RESULT`, `ASSERTED`, and `NOT_CLAIMED`;
- an independent `P_VALUE` observation;
- the exact source value `log-rank P = 0.08`;
- RA and non-RA populations plus OS as the outcome;
- no invented significance conclusion.

## Why The Frozen Gate Stopped

The second case failed three connected deterministic equivalence assumptions:

1. Luna returned the exact source mention `RA`. The anchor resolver treated it
   as ambiguous because raw substring matching also found `RA` inside `non-RA`.
   Token-boundary mention identity was not supported.
2. The frozen participant reference accepted `RA NSCLC`, while the source uses
   grammatical ellipsis: `RA and non-RA NSCLC`. The returned `RA` is literal and
   source-supported, but exact reference equality rejected it.
3. The reference stored `P = 0.08`; Luna returned the more complete exact source
   span `log-rank P = 0.08`. Exact statistical-span equality rejected the valid
   containing span.

The participant-link and statistical failures in the result are downstream of
these span-identity rules. V3 remains immutable and is not rescored.

## Deterministic Metrics

- Cases executed: 2/6
- Cases passing the frozen gate: 1/2
- Complete-event recovery: 1/2
- Source participant-role fidelity: 1/2
- Nested-event structure: 2/2
- Direction fidelity: 2/2
- Comparison fidelity: 2/2
- Polarity fidelity: 2/2
- Uncertainty fidelity: 2/2
- Statistical fidelity: 1/2
- Exact grounding under the frozen raw-substring rule: 1/2
- Unsupported count under the frozen reference matcher: 2
- Contradiction count under the frozen matcher: 1

These are evaluator outcomes, not a claim that the second raw output invented
science. The raw output and deterministic result remain separate.

## Provider Accounting

| Case | Response | Input | Output | Total | Latency | Cost |
|---|---|---:|---:|---:|---:|---:|
| Comparison canary | `resp_0ad13c591c926907006a61279b8b2c81989b8bb4402dc87354` | 1,797 | 1,588 | 3,385 | 106.501 s | $0.011325 |
| Null statistics | `resp_0c6f3e0ef36a374d006a612805ccac8198b20e7c9e065a5cc6` | 1,801 | 3,347 | 5,148 | 16.509 s | $0.021883 |
| Total | 2 calls | 3,598 | 4,935 | 8,533 | 123.011 s | $0.033208 |

Every receipt and budget passed. There were zero retries, duplicate creation
calls, fallbacks, graph writes, promotions, or untouched-source accesses.

## Required Pivot

The next architecture checkpoint should be offline first:

1. Resolve mention identity with exact offsets plus token boundaries, so `RA`
   does not collide with the substring inside `non-RA`.
2. Define source-general span-equivalence rules before execution: exact match or
   a uniquely grounded containing span for participant and statistical evidence.
3. Keep categorical scientific meaning exact; span equivalence must never alter
   event type, roles, direction, polarity, uncertainty, or interpretation.
4. Validate those rules on exposed fixtures, then preregister a new experiment.

This is a pivot in deterministic evidence identity, not a reason to add more
one-shot prompt instructions. The staged model showed useful scientific
behavior, but the full six-case generalization claim remains unproven.

## Final Repository Validation

After the frozen V3 result and this report were complete, the recovered working
tree passed the focused role-alignment/generalization tests, Ruff, formatting,
strict MyPy, both architecture guards, independent V3 preregistration
recomputation, and the single final `make service-checks` gate. No scientific
result, provider receipt, frozen reference, or V1-V3 execution artifact was
changed by that validation.
