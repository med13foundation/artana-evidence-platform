# TG-04 Projection-Aware Holdout v3: Repeat 1

## Pre-registered execution

- Repository commit: `47dea660`
- Model: `openai:gpt-5.6-luna`
- Unit: `source-unit-98f68d52a357c0fb1153c2fcdcbe1955287cfbfc9a53af84595baaae663cb84c`
- Projection-set SHA-256: `7828ded0f5ccca1ed3e3af1362277688bffad30ccb7bd27318e0196d2a332a21`
- Report SHA-256: `f2d1c55426cf241fa95b7bf06db11cab12749204b0cfd81e8d851811b230cff7`
- Decision: `STOP_AND_RECALIBRATE_NESTED_EVENT_EXTRACTION`
- Repeat 2 and repeat 3: not run

The first launch stopped before provider execution because the dotenv configured
`openai:gpt-5.4-mini`. The qualifying launch used an explicit process-local Luna
override. That preflight stop did not consume the hidden unit.

## What Luna recovered

The extractor returned four source-supported scientific events:

1. IL-13 did not effectively reduce FOXP3 (`NULL_RESULT`).
2. IL-13 failed to induce GATA3 (`NULL_RESULT`).
3. IL-4-dependent inhibition of FOXP3.
4. GATA3 was hypothesized to mediate that inhibition.

This is materially better information preservation than a binary relation-only
answer. The extractor also retained the two null findings instead of discarding
them as context.

## Why the strict gate failed

The second null event used the non-verbatim boundary
`IL-13 ... fails to induce GATA3`. Source binding rejected it as
`EXACT_SPAN_MISSING`. The one audited repair corrected anchor context but, under
the pre-registered semantic-invariance contract, was not allowed to rewrite the
claim boundary. It was recorded as `semantic_invalid`, and execution stopped
before linking and independent verification.

The output also exposed two scientific representation errors that would have
blocked complete projection recovery:

- The outer GATA3 mediation event was typed `NEGATIVE_REGULATION`. A factor that
  mediates an inhibitory process positively regulates or causes that process;
  the inner process's negative direction must not be copied outward.
- The outer cue included modality (`could be mediated by`) and the inner
  inhibition inherited `HYPOTHESIS`. Relation cue and event-level epistemic scope
  need to remain independent.

Both live provider responses were identified and receipt-verified. No
deterministic extraction fallback ran, no relation was trusted, and no graph
persistence was authorized.

## Benchmark findings discovered concurrently

An adversarial reviewer found three valid pre-registration defects. The run did
not falsely pass, but the unit is exposed and cannot be reused for qualification:

- mixed null-result and hypothesis units need an explicit `MIXED_SCIENTIFIC`
  category;
- complete projection matching must reject surplus or reused event arguments;
- projection shape must be rejected before provider execution when it is not
  exactly two events connected by one supported non-self link.

These defects are being corrected before selecting holdout v4. No post-hoc v3
credit will be awarded.
