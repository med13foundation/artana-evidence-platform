# TG04 Staged Semantics Offline Correction V1

Created: 2026-07-20

Decision: `OFFLINE_CORRECTION_PASSED`

This bounded offline correction addresses the two failures recorded by staged
live development V1. It does not retry or modify that execution. It makes no
provider call, selects no untouched source, changes no frozen V10 file, and
writes nothing to the graph.

## Frozen Failure Evidence

- Live V1 result SHA-256:
  `362a48f416c8eedd8888eff8226dc0c616906cbf44ce630e31cfa0424f84a2e6`
- Frozen V10 tree SHA-256:
  `bb0b66e96646040717b3d7eaea3b062eb3ebe4bf654119aca16e54d7550abc7a`
- Live V1 provider calls added by this correction: 0
- Live V1 retries added by this correction: 0

## Correction 1: Event-Local Role Grounding

The role stage remains the owner of scientific event type, participant role,
and participant evidence. Its categorical result is `RESOLVED` or `ABSTAIN`,
with an explanation for every participant.

The deterministic boundary now receives only:

1. one atomic event passage; and
2. explicitly permitted local context containing that passage.

It resolves each participant anchor inside the atomic passage. It rejects an
anchor that is absent or occurs more than once in that scope. It never searches
the full source for a replacement mention. A valid agent `ABSTAIN` remains an
abstention; invalid or contradictory output is rejected rather than relabeled.

The exposed replay produced these occurrence-local anchors:

| Event | Role | Exact local evidence | Source offsets |
|---|---|---|---:|
| A2 | focal population | `Patients with RA` | 862-878 |
| A2 | comparator population | `patients without RA` | 941-960 |
| A2 | outcome | `comorbidities` | 922-935 |
| A5 | focal population | `the RA` | 1229-1235 |
| A5 | comparator population | `non-RA NSCLC` | 1240-1252 |
| A5 | outcome | `OS` | 1218-1220 |

The source-global phrases borrowed by live V1 are rejected in the corrected
event scopes. An ambiguous local `RA` fixture is also rejected.

## Correction 2: Statistical Observation and Author Claim

The agent-owned statistical result now has independent categorical fields:

- observed evidence: `P_VALUE`, `CONFIDENCE_INTERVAL`, `EFFECT_ESTIMATE`, or
  `NONE`;
- author claim: `SIGNIFICANT`, `NOT_SIGNIFICANT`, or `NOT_CLAIMED`.

Each reported observation carries exact evidence and an explanation. An
explicit author claim also requires its own exact evidence. `NOT_CLAIMED` has
no claim-evidence span.

Deterministic validation checks only category shape, local evidence,
provenance, and contradictions. It does not compare a p-value with a threshold
and does not infer or relabel scientific meaning.

For A5, the corrected replay records:

- `log-rank P = 0.08` as `P_VALUE`;
- `hazard ratio 0.92` as `EFFECT_ESTIMATE`;
- `95% confidence interval 0.78-1.09` as `CONFIDENCE_INTERVAL`;
- author claim as `NOT_CLAIMED`.

The phrase `no difference` remains part of the scientific comparison and does
not become an invented explicit significance claim.

## Replay Evidence

The replay covers A2, A5, negation, comparison, duplicate-event, ambiguous
anchor, source-global anchor borrowing, valid abstention, and explicit versus
implicit significance regressions.

| Metric | Result |
|---|---:|
| Complete events | 2 of 2 |
| Expected semantic stages | 12 |
| Assembled semantic stages | 12 |
| Correctly grounded participant roles | 6 |
| Unsupported claims | 0 |
| Contradictions | 0 |
| Provider calls | 0 |
| Retries | 0 |
| Fallbacks | 0 |
| Untouched sources frozen | 0 |
| Frozen V10 changes | 0 |
| Graph writes | 0 |

The correction and all existing staged-semantic, categorical-cue,
anchor-resolution, and frozen-V10 regressions pass: **103 passed**.

The repository `make service-checks` gate also passes, including static,
architecture, relation-quality, and coverage enforcement. Total coverage is
**87.48%**, above the required 86% floor. Live and external-provider tests were
not enabled, consistent with the offline stop boundary.

Offline receipt SHA-256:
`89ae5e5f7d525c469ea963d300ba43da0c3bc211677b9d65d50929c7e0260d83`

## Ownership Boundary

Agents own biomedical categories, participant roles, comparisons,
measurements, statistical observations, author claims, polarity, uncertainty,
and source-only review. Deterministic code may enforce event scope, resolve
exact offsets, assemble matching assertion IDs, detect duplicates or
contradictions, and calculate metrics. It does not infer a role, significance,
polarity, or any other biomedical conclusion.

## Remaining Uncertainties

- This is an offline replay of exposed fixtures, not evidence that a live agent
  will reliably follow the corrected staged contracts.
- Abstention behavior is covered by regression tests, but its live frequency
  and effect on complete-event recovery are unknown.
- The explicit-author-claim fixtures cover the failure family seen in V1, not
  every way biomedical authors express statistical interpretation.
- Two exposed events are enough to validate the correction boundary, not to
  establish scientific qualification or generalization.
- No repeatability or provider-receipt claim is made by this offline result.

The correction therefore passes its bounded offline gate. Any later live
development execution requires separate authorization and frozen stage
contracts; it must not reuse the consumed V1 execution or an untouched source.
