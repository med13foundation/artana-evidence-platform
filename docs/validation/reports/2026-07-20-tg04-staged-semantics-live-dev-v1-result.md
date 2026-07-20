# TG04 Staged Semantics Live Development V1 Result

Created: 2026-07-20

Decision: `BOUNDED_LIVE_DEVELOPMENT_FAILED_STOP`

Execution 1 failed. The repeatability execution was not run. No prompt,
contract, gate, or architecture file was changed after preregistration.

## Frozen Controls

- Model: `openai:gpt-5.6-sol`
- Reasoning effort: `high`
- Source: exposed development source `pubmed:40289860`
- Frozen V10 tree:
  `bb0b66e96646040717b3d7eaea3b062eb3ebe4bf654119aca16e54d7550abc7a`
- Execution repository commit: `d3e18524c15cafd3d150567b5c1d85f8f0b8e553`
- Execution lock SHA-256:
  `0f590a2814f546761a88987a18b50207aae22d2a1dca543dc4deffa145678286`
- Result artifact SHA-256:
  `362a48f416c8eedd8888eff8226dc0c616906cbf44ce630e31cfa0424f84a2e6`

## Actual Execution

All six independent calls returned schema-valid categorical output and had one
verified-live provider receipt. No call was replayed.

| Stage | Input tokens | Output tokens | Total tokens | Cost USD |
|---|---:|---:|---:|---:|
| Core event and roles | 1,215 | 1,245 | 2,460 | 0.043425 |
| Comparison and direction | 1,153 | 330 | 1,483 | 0.015665 |
| Quantitative measurements | 1,235 | 431 | 1,666 | 0.019105 |
| Statistical evidence | 1,279 | 808 | 2,087 | 0.030635 |
| Epistemic status | 1,171 | 446 | 1,617 | 0.019235 |
| Source-only falsification | 2,924 | 587 | 3,511 | 0.032230 |
| **Execution 1** | **8,977** | **3,847** | **12,824** | **0.160295** |

- Provider calls: 6
- Verified-live receipts: 6
- Retries: 0
- Fallbacks: 0
- Graph writes: 0
- Untouched sources selected or frozen: 0
- Frozen V10 modifications: 0
- Execution 2 calls: 0

## Failure 1: Core Role Provenance

Deterministic assembly rejected both events with
`AMBIGUOUS_OR_MISSING_EVIDENCE`.

For `A2`, the core agent selected the event scope:

`had more comorbidities than patients without RA.`

It then assigned `Patients with RA` as the focal-population evidence. That
evidence is outside the selected event scope.

For `A5`, the core agent selected the correct result sentence as the event
scope but borrowed role wording from the objective:

- focal: `patients with metastatic non-small cell lung cancer (mNSCLC) with
  pre-existing rheumatoid arthritis (RA)`;
- comparator: `those without RA`;
- outcome: `overall survival (OS)`.

Those strings occur elsewhere in the source, not inside the selected A5 result
scope. The result sentence locally contains `RA`, `non-RA NSCLC`, and `OS`.

Root cause: the core agent understood the participants scientifically but did
not preserve occurrence-local role evidence. The core-stage validator checked
source-global presence; scoped deterministic resolution first detected the
violation during assembly after the sixth call. No role was guessed or
rewritten.

## Failure 2: False Significance Classification

The statistical stage returned `NOT_SIGNIFICANT` for both A5 observations,
including evidence containing `log-rank P = 0.08`.

The frozen prompt explicitly required `NOT_CLAIMED` unless the source itself
labels significance and prohibited threshold calculation. The source says
`no difference`, but it does not explicitly say `not statistically
significant`. The agent conflated a null scientific result with an explicit
statistical-significance label.

Root cause: the statistical agent did not maintain the boundary between:

- the reported observation (`P = 0.08`);
- the scientific comparison (`no difference`); and
- an explicit significance claim, which is absent.

This would have failed the preregistered scientific gate even if provenance
assembly had succeeded.

## What Worked

- A2 comparison stage returned
  `OBSERVED_DIFFERENCE / HIGHER / GREATER_THAN`.
- A5 comparison stage returned
  `NO_DETECTED_DIFFERENCE / UNCHANGED / NO_DETECTED_DIFFERENCE`.
- Quantitative extraction preserved the p-value, hazard ratio, and confidence
  interval with correct unadjusted and adjusted scopes.
- Epistemic extraction preserved affirmative A2 and negated-difference A5
  without claiming equivalence.
- Source-only review returned `ENTAILED / COMPLETE_FOR_ASSERTION` for both
  events.
- Every provider call had a verified-live receipt and stayed below its token
  ceiling.

## Required Stop

The experiment stopped at the first deterministic assembly failure. Because
execution 1 did not pass, execution 2 was not authorized and was not run.

Do not retry this frozen execution or alter its artifacts. Before another live
development authorization, separately decide whether to:

1. enforce occurrence-local core-role evidence immediately after the core
   call; and
2. isolate statistical-observation classification from null-result wording so
   absence of an explicit significance label remains `NOT_CLAIMED`.

Both are staged-boundary corrections. Neither requires expanding a one-shot
prompt or allowing deterministic biomedical inference.
