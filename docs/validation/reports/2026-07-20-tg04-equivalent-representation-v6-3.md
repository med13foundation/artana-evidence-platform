# TG04 Equivalent-Representation V6.3 Checkpoint

## Decision

`RAW_COMPLETE_FRAME_PASS_RUN_INVALID`

V6.3 again produced an unanimously complete scientific frame, but the audited
run failed schema validation. It remains nonqualifying, review-only, and cannot
receive trusted-graph credit.

## Controlled change

Relative to V6.2, V6.3 accepted only:

- equivalent direct and inherited declarations of the same participant in the
  same role;
- `SIMILAR_MAGNITUDE` under `NO_DIFFERENCE` when the nested sides exactly matched
  the base comparison sides.

The source, neutral prompt, model, provider-default reasoning, one-call limit,
and safety controls were unchanged.

## Audited result

- Model: `openai:gpt-5.6-sol`
- Provider calls: `1`
- Fallback or replay: `0`
- Graph writes: `0`
- Terminal state: `INVALID_RUN`
- Error: `StructuredModelSchemaError`
- Result SHA-256: `95cda228b39d773d9adf17a9e418c5d86c04132c600dc362ce0535d57c0bfb00`
- V6.3 suite before the call: `53 passed`

The raw payload recovered the same complete scientific content as V6.2:

1. no differential IL-4 promotion of cell growth between FOXP3+ and FOXP3-;
2. enhanced proliferation in both populations;
3. qualitative similarity of that enhancement.

## Independent scientific review

Two blind source-only reviewers unanimously returned `COMPLETE_FRAME PASS`.
They passed exact grounding, comparative null, positive effect, qualitative
degree, population identity, role fidelity, direction, polarity, negative
leakage, and absence of unsupported statistical equivalence.

They specifically found that:

- FOXP3- as comparator under `INCREASES + SIMILAR_MAGNITUDE` provides an
  orientation without turning it into an untreated baseline;
- `both populations` is a clear backward reference to the immediately preceding
  FOXP3+ and FOXP3- pair.

Review packet SHA-256:
`b29b0eda5d72169fb7bb6e814f241f46f07cfdaaa442ee98ab1d87f95b6d0470`.

## Root cause

V6.3 still required one representation rather than one scientific meaning:

- positive relations could not place an effect-comparison participant in
  `comparator_context_ids`;
- nonlocal participant references required explicit inheritance bindings even
  when a role-compatible participant appeared in the preceding assertion.

The schema therefore rejected a scientifically valid frame for bookkeeping
reasons. No accepted system-level improvement can be claimed yet.

## Next gate

V6.4 may accept an effect comparator only when nested comparison sides match the
outer context roles. It may accept an implicit backward participant reference
only when the same participant occupied a role-compatible role in an earlier
source assertion. Forward references, cross-role transitions, unrelated prior
participants, mismatched sides, null leakage, fallback, replay, and graph writes
must remain rejected.

An untouched run remains prohibited until a new live call is schema-valid,
receipt-verified, and unanimously complete under independent source review.
