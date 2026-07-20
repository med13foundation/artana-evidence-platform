# TG04 Compiled-Anchor V9 Exposed Stop

Date: 2026-07-20

## Decision

`INVALID_RUN`. Do not assign a scientific score and do not treat this receipt as
evidence of scientific improvement.

The preregistered exposed-source experiment made exactly one live provider call
and stopped on deterministic semantic compilation. It used no retry, fallback,
replay, or graph write.

## Sealed Arm

- Source: exposed development PMID `40289860`
- Source SHA-256: `e933d6dbc1e7599e41e093c5ad321131572ccdaddf871c8b610749519fe5ef84`
- Model: `openai:gpt-5.6-sol`
- Reasoning effort: provider default
- Provider response: `resp_0f82b3cc5bec948f006a5e0f0b08ac8199adba3c2d74a22f79`
- Contract SHA-256: `2dd67aeea5558037a7c8a71e2d4bb43e8702e661b70f5e93d78d7b0e69a6a53b`
- Runner SHA-256: `c43aed41a7859c726695588fc75bc8e428eda4a127f0703cbc364c80a1e25cd2`
- Result SHA-256: `8bf8eacab905331298d9be26e2df1cdec6f80baf19982ca9628e5d27dea8a887`
- Provider calls: `1`
- Retry/fallback/replay/graph writes: `0/0/0/0`

## What Improved

The provider no longer calculated numeric offsets. It returned exact source
anchors, 11 participants, 13 candidate assertions, and five categorical
exclusions. The raw response separated coordinated findings, preserved both
unadjusted and adjusted null survival results, and retained the sensitivity
null result. These are diagnostic observations only because compilation did not
pass.

Before the call, the V9 boundary passed:

- 76 combined V8 and V9 regressions;
- strict MyPy;
- Ruff;
- independent biomedical adversarial review: `GO`;
- independent structural adversarial review: `GO`.

## Terminal Failure

The compiler raised `IncompleteExcludedStatementError`. Four exclusions omitted
section headings that were outside the semantic sentence anchor, while one
legitimate background exclusion was an embedded parenthetical phrase rather
than a complete sentence. The V9 rule incorrectly treated every exclusion as
the same evidence unit.

No retry is allowed on this receipt.

## Offline Structural Diagnosis

Per-assertion compilation of the captured raw payload, without another provider
call, exposed the deeper common cause:

- one descriptive cohort result had no artificial `OUTCOME` role;
- most assertions supplied implicit analysis-purpose labels without exact cues;
- source-level study design was attached as assertion-local result evidence;
- provider-authored result scopes frequently failed to contain their repeated
  predicate anchor;
- some conclusion clauses omitted section-heading text from the complete atomic
  source segment.

After diagnostic normalization of only purpose and study-design fields, 12 of
13 assertions still failed a representation-shape rule. This is not evidence
that the biomedical findings were wrong. It proves that V9 still asked the model
to construct redundant containment and context bookkeeping.

## Root-Cause Hypothesis For V10

The provider should identify atomic scientific evidence, not calculate nested
evidence envelopes.

V10 will isolate this change:

1. The agent returns exact anchors for predicate, result cue, direction,
   polarity, roles, qualifiers, and explicit local analysis facets.
2. Deterministic code derives the complete atomic clause containing the
   predicate.
3. Deterministic code derives the minimal result envelope containing all local
   event cues.
4. Source-level study context is preserved in a separate typed audit frame and
   is never forced inside assertion-local result evidence.
5. Explicit analysis purposes require exact cues; an empty list compiles to
   categorical `UNSPECIFIED`.
6. Objective, methods, and eligibility exclusions compile to their containing
   atomic statement. Embedded background exclusions retain their exact fragment
   and may share a clause only when they do not overlap scientific evidence.
7. Descriptive scientific results may bind a subject and measurement without
   inventing an outcome role.

Only one new exposed call may follow a fresh adversarial `GO`. Untouched sources
remain sealed, and Artana remains review-only.
