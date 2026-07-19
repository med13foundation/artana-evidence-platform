# TG-04 V13 Controlled-Event Topology Contract Result

## Decision

`READY_FOR_DIFFERENT_VISIBLE_CANARY`.

This repository checkpoint fixes the controlled-event ownership failure exposed
by the prior V13 correction call. It does not qualify scientific quality,
authorize a hidden unit, or authorize graph persistence.

## Root Cause Fixed

The prior correction agent understood the scientific claim and repaired the
regulator type, but the provider-facing contract did not explain which event
owned `controlled_event_ref`. The agent therefore placed one reference on an
inner participant and pointed two outer arguments back to the controller.

V13 now uses a versioned normalization schema and an immutable execution policy:

- execution contract: `tg04.finite_source_unit.v13_execution.v1`;
- extraction prompt: `tg04.finite_source_unit.extraction.v22`;
- normalization prompt: `tg04.finite_source_unit.structure_normalization.v5`;
- normalization schema: `SourceUnitNormalizationOutputV13`;
- normalization schema SHA-256:
  `43418016713a4b848069e1a82babd0ab0706a5502889d14209ec371512456e0f`;
- review prompt: `tg04.finite_source_unit.normalized_review.v5`.

The executable V13 wrapper binds these versions together and does not accept a
prepared-prompt override.

## Fail-Closed Rules

- a reference may exist only on a relation-eligible, source-asserted regulation
  event's biological-process `CAUSE` or `THEME`;
- a reference must identify a distinct returned relation-eligible event;
- reference identity is independent of assertion scope, so a valid referenced
  event may be `SOURCE_ASSERTED` or `CONTROLLED_TARGET`;
- every `CONTROLLED_TARGET` requires an incoming reference;
- an explicit ID cannot override distinct-trigger source ambiguity;
- shared-trigger siblings remain valid when source-bound participants distinguish
  them;
- a broad reference is rejected when a narrower source span identifies the
  requested target; and
- deterministic code rejects topology but never chooses or repairs a scientific
  category.

## Adversarial Review

Four review rounds challenged historical custody, assertion-scope coupling,
overlapping sibling swaps, procedural controllers, shared-trigger projections,
wrong extra links, and forged prompt injection. Every actionable finding was
addressed. The final reviewer reproduced the wrong `E16 -> E21` attack as
unlinked and found no remaining actionable issue in the final fixes.

## Historical V4 Custody

The issued V13-v4 normalization receipt records schema SHA-256
`627d8e53aaa24b4017fb24f28370b959502f2fe68fc41a2cb47a8d5de6b8b06f`,
but that exact schema is not reconstructible from the committed historical V12
contract. V13 therefore fails closed: the v4 call cannot be replayed, qualified,
or used as readiness evidence. Its raw output remains preserved only as a
non-qualifying diagnostic.

## Next Gate

Commit and push this exact contract, then pre-register one different visible
source. Run exactly one V13 extractor, one correction agent, and one source-only
falsifier with `openai:gpt-5.6-luna`. Stop after any invalid output, unresolved
topology, unsupported scientific axis, missing provider custody, fallback, or
deterministic scientific repair.
