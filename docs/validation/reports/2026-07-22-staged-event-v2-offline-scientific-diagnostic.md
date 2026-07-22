# Staged V2 Offline Scientific Diagnostic

**Decision:** `CONTINUE_WITH_CONTEXT_EXPERIMENT`

## Scope

This is a non-qualifying offline diagnostic of preserved exposed-source outputs. V2 remains terminally `INVALID_EXPERIMENT`. This analysis made no provider calls, changed no frozen V2 artifact, accessed no untouched source, wrote nothing to the graph, and enabled no promotion.

## Dependency-Closed Projection

All 39 candidates had matching discovery, participant, role, modifier, and verification identities. Provider accounting matched the preserved receipt, and all five receipts were `VERIFIED_LIVE`.

- Direct verifier exclusions: 7
- Transitive dependency exclusions: 1
- Retained closed subgraph: 31
- Public-gold denominator: 30, unchanged

The quarantined dependency chain was:

```text
E-faf304d73050cfefee5c
  -> E-2773996d557442a07d58
  -> verification:CONTRADICTED (wrong speculation scope)
```

The other direct exclusions were:

```text
E-142d96a6127befa7a558 -> verification:CONTRADICTED
E-81595271d3236055d068 -> verification:CONTRADICTED
E-b98c681634a09b75e298 -> verification:CONTRADICTED
E-c30f1062b5528fce8cc2 -> verification:CONTRADICTED
E-d7ef029df22fe0516c7d -> verification:CONTRADICTED
E-fd54232743ba4d07aba2 -> verification:CONTRADICTED
```

Every excluded event remains explicitly `REVIEW_ONLY`. None entered scoring or promotion.

## Exact Closed-Graph Score

| Measure | V2 result |
|---|---:|
| Complete events | 8/30 |
| Exact triggers | 16/30 |
| Typed arguments and roles | 10/37 |
| Nested arguments | 3/12 |
| Modifiers | 0/2 |
| Predicted retained events | 31 |
| Predicted events outside exact gold | 23 |

The 23 events outside exact gold are benchmark mismatches, not automatically hallucinations. Source validity was adjudicated separately.

## Blinded Adjudication

Two blinded reviewers independently reviewed all 32 V2 `ENTAILED` candidates. They agreed completely on 26/32 cases (81.25%). A third blinded reviewer examined only the six disputed cases and resolved all of them. Unresolved disagreement was 0%, below the 20% invalidation threshold.

| Scientific measure | V1 | V2 | Change |
|---|---:|---:|---:|
| Exact complete gold events | 9/30 | 8/30 | -1 |
| Source-supported complete events | 19 | 18 | -1 |
| Verifier false acceptances | 15/32 | 14/32 | -1 |
| False-acceptance rate | 46.875% | 43.75% | -3.125 points |
| Wrong participants | 15 | 13 | -2 |
| Wrong roles | 16 | 13 | -3 |
| Wrong nesting | 9 | 7 | -2 |
| Wrong modifiers | 4 | 1 | -3 |
| Unsupported claims | 0 | 0 | unchanged |
| Valid extras outside gold policy | 16 | 13 | -3 |

V2 reduced role, nesting, modifier, and verifier errors without introducing unsupported claims. It did not improve event recovery: both exact benchmark events and complete source-supported events declined.

## Case Transitions

- Wrong to correct: none.
- Correct to wrong: gold `E18`.
- Unchanged correct: `E1`, `E20`, `E21`, `E22`, `E23`, `E24`, `E26`, `E27`.
- Unchanged wrong: 21 gold events.
- Newly discovered valid extras: `E-bc37a2c8e84b25cc8803`, `E-bcb6ce67e9169dfcd807`.
- Newly introduced malformed events: `E-6a75a0999b748f2fe913`, `E-c1c8f47ea535c511fb62`.
- Newly introduced unsupported events: none.

## Interpretation

V2 scientifically improved error rejection, especially modifier scope, but did not improve recall or complete-event fidelity. The evidence suggests that event-local context helps prevent some broad role and nesting mistakes while sometimes hiding the paragraph-level scope needed to attach modifiers and participants correctly.

The improvement gate is met only because wrong roles, nesting, modifiers, and verifier false acceptances decreased with zero unsupported claims. This is not qualification and does not reverse V2's invalid terminal result.

## Proposed Next Experiment

Propose, but do not execute, one controlled exposed-source comparison:

1. Arm A: current event-local context.
2. Arm B: structured paragraph context containing sentence boundaries, candidate event scope, neighboring assertion scopes, and explicit occurrence IDs.
3. Keep the same source, Sol model and reasoning effort, stage prompts, schemas, event candidates, budgets, scoring, and reviewer process.
4. Change only the context supplied to semantic stages.
5. Advance only if exact complete events do not decline, role/nesting/modifier fidelity improves, and unsupported claims remain zero.

If that single context experiment fails, pivot to specialized biomedical event candidates with agents retaining final scientific adjudication.
