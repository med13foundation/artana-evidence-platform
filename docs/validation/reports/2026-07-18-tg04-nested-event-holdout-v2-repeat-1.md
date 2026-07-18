# TG-04 Nested Event Holdout V2: Repeat 1

## Decision

**STOP_AND_RECALIBRATE_NESTED_EVENT_EXTRACTION**

Repeat 1 failed the deterministic gate. Repeats 2 and 3 were not run. This unit
is now development-only and cannot receive fresh qualification credit.

## Sealed Unit

- Case: `bionlp-ge-2011-holdout:PMC-2806624-07-DISCUSSION`
- Unit: `source-unit-edb3591fbea79678533ddb57259dddfc3be3bb0e8f003c2e06c62fbf4b50f0cd`
- Input SHA-256: `4e9bca5f89e9ece248a0acc9405ebdc7abb6b386ef69c3b910a9c8aaa82df920`
- Expert graph SHA-256: `b881b0e63ac7ea503820a444b0352160277e5b4d6df695430a283a0eea610696`
- Report SHA-256: `389cd720a6064e7546a56a5384c0b3a009b5bbe9a2f7dc78ecd3df41e2a3dd3e`
- Model: configured `openai:gpt-5.6-luna`; executed `openai/gpt-5.6-luna`

Source unit:

> Specifically, Foxp3 physically interacts with RORgammat, and this interaction
> inhibits RORgammat function (Zhou et al., 2008).

## What Worked

- Luna returned two scientifically appropriate events: physical interaction and
  inhibition of RORgammat function.
- The outer candidate used `this interaction` as a BIOLOGICAL_PROCESS CAUSE and
  declared the complete Foxp3-RORgammat interaction as its referent.
- Both agents independently classified the unit as a finding.
- Provider execution, model identity, source identity, and two live provider
  receipts were verified.
- No deterministic biomedical fallback was used.

## What Failed

The outer inhibition candidate was rejected during source binding. Its
`RORgammat function` mention anchor claimed the immediate right context was
`.`. The source actually continues with ` (Zhou et al., 2008).` Because the
verbatim context was wrong, the strict binder rejected the whole candidate as
`ARGUMENT_MENTION_INVALID`.

Only the binding candidate reached the verifier. The verifier therefore
correctly returned `MISSING_EVENT`, no event-reference link survived, and the
complete sealed graph did not match.

## Scientific Interpretation

This is not evidence that Luna missed the inhibition claim. It generated that
claim correctly at the semantic level, but failed an exact source-copy detail.
Artana was correct to fail closed rather than silently repair the agent output.

Two ontology differences also require explicit treatment:

- BioNLP represents symmetric binding participants as `THEME` and `THEME`;
  Luna used `AGENT` and `TARGET`.
- BioNLP records inhibition of the protein `RORgammat`; Luna preserved the more
  specific source process `RORgammat function` plus RORgammat as a site.

The latter is source-supported and arguably more useful, but it was not frozen
as an acceptable alternative before execution. It cannot be added after seeing
the output for qualification credit.

## Root Causes

1. The finite trial forced mention anchors even for unique spans, increasing
   avoidable exact-copy failures.
2. The diagnostic had no bounded agent repair call for a source-binding error,
   although production extraction already follows an agent-retry pattern.
3. Evaluation froze corpus gold but did not freeze independently adjudicated
   source-valid projection alternatives before extraction.
4. Binding-role policy did not explicitly require symmetric THEME roles.

## Next Controlled Loop

1. Preserve rejection evidence in the report, not only its count.
2. Tell agents to omit mention anchors for unique spans and use symmetric THEME
   roles for physical binding.
3. Add at most one audited agent repair attempt after binding rejection; never
   repair spans or meaning deterministically.
4. Use this exposed unit only as a regression for successful agent repair,
   referent linking, and source-valid refined target structure.
5. Select a third unit content-blindly and freeze both corpus fidelity and
   independently adjudicated acceptable projections before Luna runs.

Automatic persistence remains unauthorized.
