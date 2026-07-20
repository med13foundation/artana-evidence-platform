# TG04 Categorical Cue Stage V1

Created: 2026-07-20

Decision: `FOCUSED_STAGE_PROVEN_STOP_ON_SECOND_SEMANTIC_FAMILY`

No provider was called, no source was selected or frozen, frozen V10 was not
modified, and no graph write occurred.

## Exact Original Failure

The exposed V2 response reached event `A2` after deterministic anchor
resolution.

- Scientific category: `OBSERVED_DIFFERENCE`
- Outcome direction: `HIGHER`
- Contrast operator: `GREATER_THAN`
- Predicate evidence: `had more comorbidities than`
- Direction cue: `more`
- Outcome: `comorbidities`
- Comparator: `patients without RA`
- Source coordinates: `[913, 940)`

The exposed gold adjudication independently represents this claim as
`GREATER_THAN`, `MORE_IN_RA`, and `POSITIVE_DIFFERENCE`. The agent's
scientific meaning was therefore correct.

Frozen V10 accepts `more` for `GREATER_THAN`, but its lexical compatibility
table does not accept `more` or `more comorbidities` for `HIGHER` and
`OBSERVED_DIFFERENCE`. This is a category-cue vocabulary mismatch, not a
biomedical reasoning failure.

## Ownership Boundary

The focused semantic stage preserves these responsibilities:

- The agent owns result state, direction, contrast, roles, and rationale.
- Deterministic anchor resolution owns exact source coordinates.
- Deterministic semantic validation may confirm or contradict the supplied
  category tuple against exact provenance.
- Deterministic code may not create a category, relabel an event, infer a
  biomedical conclusion, or mutate agent output.

For explicit amount comparisons, the stage validates the already supplied
`OBSERVED_DIFFERENCE / HIGHER / GREATER_THAN` tuple against the exact form
`more <owned outcome> than <owned comparator>`. Contradictory categories or
missing provenance fail closed.

## Exposed Fixture Result

The stage returned one immutable decision:

- Assertion: `A2`
- Status: `VALIDATED`
- Exact evidence: `had more comorbidities than`
- Coordinates: `[913, 940)`
- Scientific output changed: no

This fixes the original ownership problem without adding another one-shot
prompt rule or weakening the frozen V10 baseline.

## Required Stop

A diagnostic-only in-memory compatibility probe allowed only the validated
`A2` wording so the next failure could be identified. It was not persisted.
Compilation then reached event `A5` and failed in a different semantic family:

- Category supplied by agent: qualifier `MEASUREMENT`
- Evidence: `log-rank P = 0.08`
- V10 expectation: an equal p-value must be categorized as
  `STATISTICALLY_SIGNIFICANT` or `NOT_STATISTICALLY_SIGNIFICANT`
- Scientific event: null overall-survival comparison

This is qualifier/significance interpretation, not comparative amount-cue
ownership. Per the preregistered stop rule, this investigation does not fix or
bypass it. The new failure shows that broader staged semantic decomposition is
required before another untouched source is justified.

## Regression Evidence

Tests prove that:

- exposed `A2` validates with exact coordinates and unchanged agent output;
- a contradictory agent direction is rejected without deterministic
  relabeling;
- missing exact provenance fails closed;
- the narrowly corrected compatibility probe stops on the unrelated `A5`
  qualifier family.

Validation:

- focused stage Ruff: pass
- focused stage strict MyPy: pass
- focused stage, anchor stage, and frozen V10 suite: 80 passed
- repository `make service-checks`: pass
- repository coverage: 87.48% (required: 86%)
- provider calls: 0
- retries: 0
- fallbacks: 0
- frozen V10 file changes: 0
- graph writes: 0

External development package SHA-256 values:

- `__init__.py`:
  `03d01abcfe42cf578bab25ab0c64bc18c361d43be5db4848e056f9b3c6d65c29`
- `models.py`:
  `a13a869d83273a8722bbb02a4dc84eb11749ef6a745dc6dda57e0e19abd724c7`
- `stage.py`:
  `a6bf3476b56b023cf439060977c606d1e7345199434e4d2a2cd476310e677b99`
- `test_stage.py`:
  `6087ef71de2311fd0c8b802cf9bb5fde7c74cf0ff2a1ac447b07e18d1f270eff`

## Next Decision

Stop provider experiments. Design a staged categorical-semantics pass in
which an agent separately classifies result state, direction, contrast, and
statistical qualifier meaning with exact evidence and falsification
explanations. Deterministic code should validate provenance and cross-category
consistency only. Prove that design on exposed fixtures before authorizing any
new untouched source.
