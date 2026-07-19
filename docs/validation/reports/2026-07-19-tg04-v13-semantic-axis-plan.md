# TG-04 V13 Orthogonal Semantic-Axis Plan

## Status

Design frozen for implementation and visible-canary review. No V13 hidden unit
has been selected or spent.

V12 remains an immutable negative result. Its report SHA-256 is
`5d9310ddf9a1e5236b4517e5c179e526b473c50532eaeb4d9b2193de6124a4f6`.
The single Luna response preserved the complete neutral regulation claim but
was rejected because `UNSCOPED` was interpreted as effect direction in a field
that the validator reserves for non-asserted controlled targets.

## Root Cause

The current domain has four scientific axes, but one name and one enum blur
their ownership:

1. `event_type` already carries source-explicit effect direction, such as
   `POSITIVE_REGULATION`, `NEGATIVE_REGULATION`, or neutral `REGULATION`.
2. `polarity` is intended to record whether the source supports, refutes, or
   reports a null result, but its documentation also calls it direction.
3. `epistemic_status` records how strongly the source presents the event.
4. `assertion_scope` records whether the event is independently asserted or is
   preserved only as a controlled target.

V13 will make these axes orthogonal. It will not add a second agent-authored
direction value that can contradict `event_type`.

## V13 Domain Contract

### Effect Direction

Effect direction is a deterministic view of the agent-authored `event_type`:

- `POSITIVE`: `POSITIVE_REGULATION` and `INCREASE`;
- `NEGATIVE`: `NEGATIVE_REGULATION` and `DECREASE`;
- `UNDIRECTED`: neutral `REGULATION`, `ASSOCIATION`, and event categories that
  assert an occurrence without positive or negative direction; and
- `NOT_APPLICABLE`: `NO_EFFECT`.

This mapping classifies the categorical event type exactly. It never changes an
event type or invents scientific meaning.

### Claim Outcome

Replace the scientific meaning of inventory `polarity` with an explicitly named
`claim_outcome`:

- `SUPPORT`: the source asserts the event or relationship;
- `REFUTE`: the source explicitly refutes the event or relationship;
- `NULL_RESULT`: the source reports a tested no-effect, no-association, or
  threshold-failing result;
- `NOT_APPLICABLE`: the item is only a non-asserted controlled target; and
- `UNRESOLVED`: the agent cannot determine outcome without guessing.

`UNRESOLVED` is review-only. It cannot qualify for trusted promotion.

### Epistemic Force

Retain the independent categorical values `ASSERTED`, `PROVISIONAL`,
`UNCERTAIN`, `HYPOTHESIS`, and `UNASSERTED`. Hypothesis and uncertainty belong
only here, never in claim outcome.

### Assertion Scope

Retain `SOURCE_ASSERTED` and `CONTROLLED_TARGET`. Scope says whether the event is
a standalone source assertion; it does not describe effect direction or claim
outcome.

## Cross-Field Invariants

| Source meaning | Event type | Claim outcome | Epistemic force | Scope |
|---|---|---|---|---|
| neutral asserted regulation | `REGULATION` | `SUPPORT` | `ASSERTED` | `SOURCE_ASSERTED` |
| positive proposed mechanism | `POSITIVE_REGULATION` | `SUPPORT` | `HYPOTHESIS` | `SOURCE_ASSERTED` |
| asserted negative regulation | `NEGATIVE_REGULATION` | `SUPPORT` | `ASSERTED` | `SOURCE_ASSERTED` |
| explicit refutation | source-tested event type | `REFUTE` | source-stated force | `SOURCE_ASSERTED` |
| nonsignificant tested direction | directional tested event type | `NULL_RESULT` | source-stated force | `SOURCE_ASSERTED` |
| explicit no effect | `NO_EFFECT` | `NULL_RESULT` | source-stated force | `SOURCE_ASSERTED` |
| inner event named only as target | source-explicit inner type | `NOT_APPLICABLE` | `UNASSERTED` | `CONTROLLED_TARGET` |

Hard validation rules:

- `CONTROLLED_TARGET` requires `NOT_APPLICABLE` plus `UNASSERTED`.
- `SOURCE_ASSERTED` forbids `NOT_APPLICABLE` and `UNASSERTED`.
- `UNRESOLVED` is allowed only as fail-closed review evidence.
- `NO_EFFECT` requires `NULL_RESULT`.
- hypothesis and uncertainty never substitute for claim outcome.
- neutral `REGULATION` never implies an unknown or non-asserted claim.
- deterministic code rejects contradictions but never rewrites agent categories.

## Production-Aligned Migration

1. Introduce `InventoryClaimOutcome` and the event-type direction view in the
   core claim-inventory package, not inside the benchmark.
2. Change new agent schemas and prompts to expose `claim_outcome`. Accept the old
   wire name only at persisted-data read boundaries, never in new model output.
3. Preserve legacy `UNCERTAIN` or `HYPOTHESIS` polarity as explicit unresolved,
   review-only data. Never infer `SUPPORT`, `REFUTE`, or `NULL_RESULT` from it.
4. Carry `claim_outcome` through claim framing and the qualified claim ledger.
   Keep graph projections fail-closed until their legacy polarity field is
   explicitly migrated or losslessly projected.
5. Update the agent-output registry and generated service contracts before a
   hidden unit is eligible.

## Visible Canary Gate

Before content-blind hidden selection, run Luna once on each visible case:

1. neutral asserted regulation with two coordinated targets;
2. positive regulation;
3. negative regulation;
4. asserted no-effect or nonsignificant result;
5. explicit refutation;
6. positive-direction hypothesis;
7. controlled target plus source-asserted outer event; and
8. wording whose direction is genuinely unresolved.

Every case must satisfy all of these deterministic requirements:

- schema-valid agent output: `100%`;
- correct eligibility category: `100%`;
- expected event inventory recovered: `100%`;
- cross-field invariant violations: `0`;
- unsupported participants or direction: `0`;
- deterministic semantic repairs: `0`;
- fallback calls: `0`;
- provider-linked raw output and receipts: `100%`.

Agent explanations and exact evidence spans are retained for adversarial review,
but agents do not generate numeric quality scores.

## Fresh Hidden Gate

Only after the visible gate and all repository checks pass:

1. select one fresh unit content-blind using the finalized V12 report hash;
2. freeze its source identity, acceptable complete representations, prompts,
   schema hashes, and deterministic gate before any provider call;
3. run one extractor, one normalization agent, and one source-only falsifier;
4. require one complete source-entailed representation, zero material loss,
   zero unsupported additions, exact provider custody, and zero fallback; and
5. stop after any failure. Do not retry the unit or repair its output.

A pass authorizes two new pre-registered replications. A failure preserves the
artifact and starts one new root-cause cycle without reusing the hidden source.
