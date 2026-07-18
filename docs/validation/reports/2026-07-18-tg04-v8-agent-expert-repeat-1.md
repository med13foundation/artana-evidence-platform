# TG-04 V8 Agent-Expert Holdout: Repeat 1

## Immutable Decision

- Result: `STOP_AND_RECALIBRATE_NESTED_EVENT_EXTRACTION`
- Scientific gate: `FAILED`
- Report SHA-256: `b1498772852d13333a1201ddaa02c55098fdcc183bee01ef9da0915faf0ceafd`
- Failed requirement: `complete_acceptable_projection_recovered`
- Repeats 2 and 3: not authorized

The frozen score remains failed. The V8 gold and matcher were not changed after
observing Artana's answer.

## What Passed

The live Luna path completed without fallback. Both provider calls were retrieved
and verified. Repository, model, prompt, schema, source, input, reservation, and
response identities were bound. Extraction and independent verification agreed
on `MIXED_SCIENTIFIC`, both candidates were source-entailed and structurally
eligible, and no binding rejection or controlled-link ambiguity occurred.

Artana preserved two distinct claims:

1. A `SUPPORT` + `PROVISIONAL` positive trend involving RUNX3, CD4+ T cells,
   transfection, FOXP3, and statistical significance.
2. An `ASSERTED` + `NULL_RESULT` positive-regulation test that did not reach
   statistical significance, with the same material participants.

## Why Qualification Failed

Neither event exactly matched either pre-registered projection:

- The intervention phrase was assigned `CAUSE`; the frozen projection assigned
  it `CONTEXT` while retaining RUNX3 as the molecular `CAUSE`.
- The trend used `lead to` as its cue even though that phrase occurs inside the
  negated significance clause; the frozen projection used `trend`.
- Both events used `statistically significant increase` as the `MEASUREMENT`;
  the frozen projection separated `statistically significant` from the increase
  direction.

The matcher therefore returned no candidate for either frozen event and no
complete projection, despite substantial proposition-level overlap.

## Independent Adjudication

Two independent source-only reviews classified the output as
`PARTIALLY_COMPLETE`: the central findings were preserved, but cue scope,
experimental-context role, and measurement boundaries were lossy. A third
benchmark-validity review judged the result predominantly a narrow-projection
false negative because the alternative representation is defensible. All three
agreed that the broad scientific meaning was recovered and that V8 must not be
retroactively rescored.

## Root-Cause Hypothesis

The remaining weakness is not event discovery. It is structured semantic scope:

- distinguishing an experimental manipulation from the molecular regulator;
- selecting a positive-trend cue outside a negated significance predicate;
- separating directional outcome from statistical-significance measurement;
- making the verifier adversarial enough to reject those conflations rather
  than confirming the extractor's representation.

The next experiment must use a new hidden unit. Before spending it, the agent
instructions and adversarial verification questions must target these three
scope distinctions. A new projection set may include independently accepted
source-valid alternatives, but only if frozen before the next Artana output.
