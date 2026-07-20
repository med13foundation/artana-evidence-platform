# TG04 Comparative-Degree V6.2 Checkpoint

## Decision

`RAW_COMPLETE_FRAME_PASS_RUN_INVALID`

V6.2 produced the first unanimously complete null-plus-positive scientific frame
for this exposed source, but the audited run failed schema validation. It does
not count as a benchmark pass, qualification run, or trusted-graph input.

## Controlled change

The source, neutral prompt, `openai:gpt-5.6-sol`, provider-default reasoning,
one-call limit, and safety gates were held fixed against V6.1. The only intended
scientific change was a categorical `effect_comparison` capable of preserving
qualitative degree words such as `similarly` without claiming statistical
equivalence.

## Audited result

- Provider calls: `1`
- Fallback or replay: `0`
- Graph writes: `0`
- Terminal state: `INVALID_RUN`
- Error: `StructuredModelSchemaError`
- Result SHA-256: `ff9061bc300ecd685eabde8041655253996c096ff3e3c5cca5a1109888ecb7cb`
- V6.2 adversarial contract suite before the call: `45 passed`

The raw provider payload explicitly recovered:

1. `NO_DIFFERENCE / NULL_RESULT` for differential IL-4 promotion of cell growth
   in FOXP3+ versus FOXP3- populations.
2. `INCREASES / SUPPORT` for enhanced proliferation in both populations.
3. `SIMILAR_MAGNITUDE` grounded in `similarly enhanced proliferation`.

## Independent scientific review

Two source-only reviewers unanimously returned `COMPLETE_FRAME PASS`. They also
passed exact evidence, roles, direction, polarity, population cardinality,
null-positive separation, negative-leakage safety, and absence of unsupported
claims or invented statistical equivalence.

Review packet SHA-256:
`e9e0c1a6a62f364962994fe75983052b92610a174f8452111acd6f0bf98ca3bf`.

This is a measurable scientific improvement over V6.1's unanimous
`COMPLETE_FRAME FAIL`: the structured payload now preserves `similarly`. It is
not yet an accepted system improvement because invalid output cannot receive
credit.

## Root cause

The contract rejected two representations that both reviewers classified as
scientifically harmless:

- A2 declared the same intervention and populations both directly and through
  role-compatible inheritance.
- A1 attached `SIMILAR_MAGNITUDE` to `NO_DIFFERENCE` over the same comparison
  sides.

Neither changed participant identity, role, direction, polarity, or scientific
meaning. V6.2 optimized representational uniqueness more strictly than the
scientific objective required.

## Next gate

V6.3 may accept only equivalent same-role redundancy and only
`SIMILAR_MAGNITUDE` under `NO_DIFFERENCE` when its sides exactly equal the base
comparison sides. It must continue rejecting cross-role overlap, mismatched
sides, different or directional magnitude under a null relation, contradictory
frames, fallback, replay, and graph writes.

One new exposed call is justified only after adversarial replay gives `GO`. An
untouched source remains prohibited until a fully valid live run also receives
unanimous source-only scientific approval.
