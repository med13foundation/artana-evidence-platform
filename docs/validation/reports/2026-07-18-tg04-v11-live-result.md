# TG-04 V11 Live Result: Meaning Preserved, Workflow Invalid

## Decision

V11 is a finalized negative diagnostic. It does not qualify scientific quality,
authorize replication, or authorize graph persistence.

The result does not show that Luna failed to understand the source. Call 1 and
Call 2 preserved the principal scientific meaning, but Call 2 violated a
structural output invariant before the independent review role could run.

## Immutable Evidence

- Frozen repository commit: `423b366f`
- Model for both completed calls: `openai:gpt-5.6-luna`
- Final report:
  `/private/tmp/artana-tg04/v11/tg04-v11-live-authenticated-20260718-repeat-1.json`
- Final report SHA-256:
  `ac922afa3297dd94810ff8f96078357e36ab725efa1352c45f63f414d6a3f2e7`
- Reservation status: `FINALIZED_DIAGNOSTIC`
- Gate decision: `STOP_WORKFLOW_INVALID`
- Verified provider receipts: 2 of 2
- Deterministic fallback: unavailable
- Deterministic scientific repair: unavailable
- Persistence authorized: no

Two earlier pre-provider failures were retained separately. A model-configuration
mismatch did not claim the lease. A missing-key invocation created no provider
response or payload. Neither is counted as a scientific result.

## What Luna Preserved

The extraction agent correctly returned `NULL_RESULT` and one source-asserted
`NO_EFFECT` event. The normalization agent preserved:

- endogenous IL-4 and IFN-gamma as the tested causal participants;
- Foxp3 expression as the theme;
- naive CD4+ T cells as the population;
- both `CbfbF/F CD4-cre` and `CbfbF/F control mice` groups;
- anti-CD3/anti-CD28, IL-2, and TGF-beta stimulation;
- absence versus presence of IL-4/IFN-gamma neutralizing antibodies;
- crossed genotype and treatment dimensions;
- null-result polarity and source-asserted epistemic scope.

This is meaningful progress over V10's scientific loss. It is not a qualifying
score because the third role never received a valid normalized structure.

## Exact Failure

Call 2 returned context dimensions whose `applies_to_local_event_ids` contained
`"0"`, while its normalized event had `local_event_id: null`.

The binder correctly rejected this with:

`context dimensions require local IDs on every normalized event`

The root cause is a contract mismatch. The JSON schema exposes
`local_event_id` as optional, while deterministic validation conditionally
requires it when context dimensions exist. The agent therefore produced a
schema-valid but semantically unbindable object.

## Recalibrated Plan

1. Define a normalization-specific event contract with a required, nonempty,
   unique `local_event_id` for every non-abstaining event.
2. Require context dimensions to reference only those schema-required IDs.
3. State the same requirement explicitly in the normalization prompt; do not
   generate or repair IDs deterministically.
4. Add schema, provider-boundary, replay, and adversarial regressions for missing,
   duplicate, and unknown IDs.
5. Freeze a V12 prompt fingerprint and select a fresh content-blind hidden unit.
6. Run exactly one no-retry three-role V12 diagnostic.
7. Proceed to two fresh replications only if V12 completes all three roles,
   preserves every material axis, recovers an acceptable projection, verifies
   every receipt, and has zero unsupported additions.

If V12 is scientifically incomplete after the structural contract is fixed,
compare a stronger model under the identical frozen protocol. Do not add a
same-model self-review loop first: correlated review cannot repair a missing
representation contract and is not independent evidence.

## Honest Status

Safety and auditability are strong. Scientific meaning preservation improved on
this unit. Scientific repeatability and trusted-graph readiness remain unproven.
