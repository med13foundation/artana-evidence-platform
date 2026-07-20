# TG04 Staged Semantics V1 Result

Created: 2026-07-20

Decision: `EXPOSED_REPLAY_PASSED_STOP_BEFORE_PROVIDER`

The previous checkpoint was frozen at commit `545af25c`. No provider was
called, no untouched source was selected or frozen, frozen V10 was not
modified, and no graph write occurred.

## Architecture

Scientific interpretation is decomposed into six immutable agent-owned
contracts:

1. Core event and participant roles.
2. Comparison result, direction, and operator.
3. Quantitative measurements and their analysis scope.
4. Statistical observations and whether significance was explicitly claimed.
5. Polarity, uncertainty, and epistemic status.
6. Source-only support, falsification, and completeness review.

Every stage returns categorical findings, exact evidence text, and a short
explanation. The source review also returns a falsification question.

Deterministic responsibilities are limited to:

- resolving exact evidence inside the agent-owned event scope;
- assembling six findings with the same assertion identity;
- rejecting duplicate events, ambiguous evidence, and explicit cross-stage
  contradictions;
- calculating counts for stage completion, provenance, support, completeness,
  and contradictions.

The assembler copies the six stage objects unchanged. It has no path that
creates, relabels, merges, or numerically scores biomedical meaning.

## Exposed Replay

The replay used only the frozen exposed V2 payload and exposed adjudication for
`pubmed:40289860`.

### A2

- Result: `OBSERVED_DIFFERENCE`
- Direction: `HIGHER`
- Operator: `GREATER_THAN`
- Evidence: `had more comorbidities than`
- Statistical evidence: `NONE_REPORTED`
- Epistemic status: `OBSERVED_DESCRIPTIVE_RESULT`
- Source review: `ENTAILED / COMPLETE_FOR_ASSERTION`

The staged categories exactly match the exposed agent output. The valid
meaning is preserved without relying on frozen V10's narrower lexical table.

### A5

- Result: `NO_DETECTED_DIFFERENCE`
- Direction: `UNCHANGED`
- Operator: `NO_DETECTED_DIFFERENCE`
- Polarity: `NEGATED_DIFFERENCE`
- Epistemic status: `OBSERVED_NULL_RESULT`
- Source review: `ENTAILED / COMPLETE_FOR_ASSERTION`

One event preserves three quantitative observations:

- `P_VALUE / UNADJUSTED`: `log-rank P = 0.08`
- `EFFECT_ESTIMATE / ADJUSTED`: `hazard ratio 0.92`
- `CONFIDENCE_INTERVAL / ADJUSTED`:
  `95% confidence interval 0.78-1.09`

The statistical stage represents `log-rank P = 0.08` as
`OBSERVED / NOT_CLAIMED`. It does not deterministically infer either
`SIGNIFICANT` or `NOT_SIGNIFICANT`.

## Deterministic Scorecard

- Events: 2
- Expected stages: 12
- Assembled stages: 12
- Evidence items: 23
- Resolved evidence items: 23
- Contradictions: 0
- Unsupported claims: 0
- Incomplete reviews: 0
- Scoped exposed fixtures passed: yes

The receipt SHA-256 is
`987ead271ab68a51434061fe4bfad320776ca3af0508c6c174ff9ceb40bc2e75`.

## Regression Coverage

The combined suite preserves:

- event-scoped anchor resolution for globally repeated text;
- fail-closed ambiguity when text repeats inside one event scope;
- the 93-anchor and 25-participant exposed V2 resolution;
- duplicate-event rejection;
- negation and polarity contradiction rejection;
- amount-comparison direction and operator preservation;
- quantitative/statistical separation;
- unchanged stage objects after deterministic assembly.

Validation:

- staged package Ruff: pass
- staged package strict MyPy: pass
- staged, cue, anchor, and frozen V10 suites: 90 passed
- repository `make service-checks`: pass
- repository coverage: 87.48% (required: 86%)
- frozen V10 tree SHA-256:
  `bb0b66e96646040717b3d7eaea3b062eb3ebe4bf654119aca16e54d7550abc7a`

## Remaining Ambiguities

This is an architecture proof, not scientific qualification:

- The six replay findings were reconstructed from already exposed agent output
  and adjudication. No fresh agent demonstrated reliable staged production.
- `P = 0.08` is safely preserved without a significance claim. A future
  statistical agent must decide whether the source supports an explicit
  significance category; deterministic code must not make that decision.
- A5 preserves unadjusted and adjusted measurements under one scientific
  event, but graph projection of those analysis scopes remains untested.
- Source-only support and completeness pass for A2 and A5, but independence and
  repeatability have not been tested with a live review agent.
- The categorical vocabulary is intentionally limited to these exposed
  fixtures. It is not a new general-purpose rule catalog.

## Stop

Stop before provider calls. The next experiment, if separately authorized,
should run the six stages on exposed development material first and compare
their assembled result with this receipt. No untouched source is justified
until staged agent production and independent review are repeatable without
unsupported claims.

External implementation SHA-256 values:

- `models.py`:
  `ced64001960ff11f01e780e6b82ee141926eb5929cd7c2de591d05a26afa9a1d`
- `provenance.py`:
  `ec300dcefac392beebfb6514c2bf15eeae64439002f2f2a5d89273b207525bd1`
- `contradictions.py`:
  `25af07ebaa11fbf0f181f346f38c8327676198a208287267ae5d88f6edae1638`
- `assembler.py`:
  `79d8a05bbae86727406c9745164020408f8dc396703f00e5e81dfb038b9f5a76`
- `metrics.py`:
  `00091b7fe4d8afe50ddfa2e062f536c0e471296245bc3cea2f84772443019b06`
- `fixtures.py`:
  `4b11a80615aace62e54d1845c7346ea9c45a939ede8a380fa131cf514b674bc9`
- `run_exposed.py`:
  `6ae878866087cc7c703e330151049b2cfa9c8dc0a836d851fd30479e4c9e4269`
- `test_staged_semantics.py`:
  `c30789884a37a53682cbbda68bfa1a34ae350a8681b86bc52984ade5d76e9ba3`
