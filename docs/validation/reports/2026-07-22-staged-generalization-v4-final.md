# Staged Generalization V4 Final Report

## Terminal Decision

`PIVOT_WITH_EVIDENCE`

V4 made two valid Luna-high calls and stopped at the first frozen scientific
gate failure. It made no retries, fallback calls, graph writes, promotions, or
untouched-source accesses. No V1-V3 result was modified or rescored.

## What V4 Corrected

The comparison canary passed every gate. The fresh null-statistics output also
passed the failure family that stopped V3:

- `RA` grounded uniquely without colliding with the suffix in `non-RA`;
- `log-rank P = 0.08` preserved and matched the exact frozen `P = 0.08` value;
- direction, comparison, polarity, uncertainty, statistics, and author
  interpretation were faithful;
- exact evidence grounding passed;
- the three required core roles were present: `POPULATION`, `COMPARATOR`, and
  `OUTCOME`;
- contradiction count remained zero.

The offline identity pivot therefore generalized to a fresh provider response.
This is evidence that the V3 deterministic root cause was corrected; it is not
six-case generalization or qualification.

## Why V4 Stopped

Luna returned two additional grounded participants from the exact source
sentence:

1. `NSCLC` as a `CANCER` node linked as `CONTEXTUAL_PARTICIPANT`.
2. `Kaplan-Meier survival curves` as a `MEASUREMENT` node linked with the
   `MEASUREMENT` role.

The frozen minimal reference contained only RA, non-RA NSCLC, and OS. Its exact
inventory rule therefore counted the two extra nodes and two extra links as
four unsupported items, even though the text is explicit and the output did
not contradict the source.

This exposes a contract inconsistency rather than a demonstrated biomedical
reasoning failure: the prompt asks the agent to inventory every explicit
participant, while the evaluator treats any source-supported contextual
participant outside its minimal core graph as unsupported.

V4 remains immutable and receives no qualification credit. The completed run
is not reinterpreted as a pass.

## Deterministic Metrics

- Cases executed: 2/6
- Cases passing the frozen gate: 1/2
- Complete-event recovery: 1/2
- Participant-role fidelity: 1/2
- Nested-event structure: 2/2
- Direction fidelity: 2/2
- Comparison fidelity: 2/2
- Polarity fidelity: 2/2
- Uncertainty fidelity: 2/2
- Statistical fidelity: 2/2
- Exact evidence grounding: 2/2
- Unsupported count under the frozen exact-inventory rule: 4
- Contradiction count: 0

## Provider Accounting

| Case | Response | Input | Output | Total | Latency | Cost |
|---|---|---:|---:|---:|---:|---:|
| Comparison canary | `resp_0d164465d3d77877006a612d35dbdc8198bcbd59d628f802c1` | 1,797 | 1,589 | 3,386 | 22.868 s | $0.0097164 |
| Null statistics | `resp_0e8374dd5ffcb7e1006a612d4bf320819bb854051d10ee881e` | 1,801 | 14,254 | 16,055 | 64.256 s | $0.0857068 |
| Total | 2 calls | 3,598 | 15,843 | 19,441 | 87.124 s | $0.0954232 |

Every receipt and frozen budget passed.

## Required Next Architecture

The next checkpoint must change the evaluator contract offline before another
provider call:

1. Separate **required core arguments** from **permitted explicit contextual
   participants**.
2. Require every core event, role, participant, and semantic axis exactly;
   optional context must never compensate for a missing core item.
3. Admit optional context only when its node and link are exact-source grounded,
   correctly typed, nonduplicative, and attached through an explicitly allowed
   contextual role.
4. Keep source-entailed optional context review-only and prohibited from graph
   promotion in this qualification path.
5. Count absent, contradictory, mistyped, or unapproved additions as unsupported
   exactly as before.

This is a pivot from exact minimal-graph equality to a core-plus-context
contract. It is not a reason to weaken grounding or categorical fidelity.

## Final Repository Validation

After the V4 result and report were frozen, the single final
`make service-checks` gate passed. No executable code, scientific output,
receipt, preregistration, reference, or metric changed after that gate.
