# Lossless Scientific Event IR Checkpoint

## Decision

`REPRESENTABILITY_GATE_PASSED`

The new upstream intermediate representation preserves all exposed BioNLP-ST
2013 Cancer Genetics development annotations. It supports zero, one, or many
participants; direct and nested event references; repeated source roles; exact
trigger and participant offsets; source event types; optional agent-owned
Artana event families; event-local modifiers; and immutable source lineage.

No provider was called. Frozen V10 and V3 semantics were not modified. No test
split was parsed, no graph write occurred, and promotion remains disabled.

## Full Replay

| Measure | Result |
| --- | ---: |
| Development documents | 100 / 100 |
| Events | 2,915 / 2,915 |
| Participant mentions | 3,634 / 3,634 |
| Triggers | 2,451 / 2,451 |
| Arguments | 3,884 / 3,884 |
| Nested event arguments | 1,274 / 1,274 |
| Negation/speculation modifiers | 214 / 214 |
| Field-level mismatches | 0 |
| Unresolved references | 0 |
| Unauthorized semantic mappings | 0 |

Canonical projection SHA-256:
`819565ff039c421d4fa4e67a508995859221a988c81d33aa849e3bcb24320ca4`.

The projector copies event types and roles exactly. It does not normalize
`Theme2` to `Theme`, map a public category to an Artana category, fill a missing
participant, flatten nested events, or use `OTHER_EXPLICIT`.

## Responsibilities

The event contract stores scientific decisions but does not make them. Future
agents must choose event categories, roles, modifiers, and optional Artana event
families. Deterministic validation is limited to source hashes, exact offsets,
annotation identities, typed references, cycle detection, lineage consistency,
canonical serialization, and equality metrics.

This representation remains upstream of claim framing and graph projection. It
does not alter the existing frozen one-shot or staged semantics.

## Regression Evidence

Focused tests cover:

- zero-argument and unary-compatible events;
- multi-participant and repeated-role events without merging;
- nested event references;
- negation and speculation attached to their target event;
- unsupported source categories preserved with no Artana relabeling;
- missing references and cyclic references rejected;
- invalid and ambiguous offsets rejected;
- deterministic serialization and hash stability;
- exact standoff replay with participant, trigger, role, modifier, and nested
  reference equality.

`make service-checks` passed, including lint, typing, service boundaries,
generated contracts, architecture checks, migrations, and the complete
database-backed test suite at 87.64% coverage.

## Frozen Next Experiment

The smallest controlled development experiment is frozen but unauthorized. It
selects one exposed development abstract by the lowest source SHA-256, uses one
`openai:gpt-5.6-sol` call at high reasoning effort, permits no retry or fallback,
and compares the complete event graph deterministically. Gold identifiers,
counts, phrases, and annotations remain hidden from the agent.

The selected source is `PMID-10473104`, containing 29 gold events and 15 nested
arguments. The experiment must stop after its single call whether it passes or
fails. It remains development-only and cannot qualify trusted promotion.

Explicit authorization is required before that provider call.
