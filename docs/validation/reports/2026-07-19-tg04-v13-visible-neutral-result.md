# TG-04 V13 Visible Neutral-Regulation Result

## Decision

`SEMANTIC_AXIS_PASS_SCIENTIFIC_CANARY_FAIL`.

This exposed canary is non-qualifying. It does not authorize hidden selection,
replication, or graph persistence.

## Evidence

- model: `openai:gpt-5.6-luna`
- evaluated commit: `e74f2c44`
- provider attempts: `1`
- verified live receipts: `1`
- invalid agent outputs: `0`
- binding rejections: `0`
- deterministic semantic repairs: `0`
- fallback calls: `0`
- raw report SHA-256:
  `7ef0926198a487d27a1145e58d2062c6b53026cc3fa2756dba163b9a64557332`

## Improvement Proven

The exact source shape that failed V12 now passed schema and source binding.
Luna returned:

- a source-asserted neutral `REGULATION` event;
- `SUPPORT` claim outcome and `ASSERTED` epistemic force;
- both `Fas ligand expression` and `cell death` as coordinated themes;
- an `EXPRESSION` controlled target for `Fas ligand expression`; and
- a controlled target for `cell death`, both with `UNSCOPED` and `UNASSERTED`.

This proves the V13 axis language fixed the V12 ambiguity without a retry or
deterministic repair.

## Remaining Scientific Failure

The source-explicit regulator `apoptosis-linked gene 4` was typed as
`OTHER_ENTITY`. The agent's own rationale called it a "Named gene product
presented as the regulator," so its categorical type contradicts its reasoning
and the source wording. The expected type is `GENE_OR_PROTEIN`.

The temporary runner's narrow semantic-axis requirements all passed, but that
does not constitute the full visible-canary gate because regulator typing is a
material participant axis. The full scientific decision is therefore fail.

## Next Adversarial Test

Do not rerun the extractor. Freeze this raw output and ask a distinct
source-only correction agent to return categorical findings and an agent-authored
reframed event. Then ask a third source-only falsifier whether the final type,
participants, outcome, direction, epistemic force, and controlled-event topology
are preserved.

Deterministic code may bind and score those agent outputs. It may not change
`OTHER_ENTITY` into `GENE_OR_PROTEIN`. If the role-separated agents do not
correct and verify this exposed case, V13 must stop before any hidden unit.
