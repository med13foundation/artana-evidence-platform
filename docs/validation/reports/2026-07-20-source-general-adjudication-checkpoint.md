# Source-General Adjudication Checkpoint

Date: 2026-07-20

## Decision

`REVISE_ONCE`

The exposed provider verification experiment did not run. This first packet
construction checkpoint was invalid because one primary artifact violated
event-local evidence custody and the tiebreaker violated its schema. The
adversarial review authorized one bounded correction cycle; this report remains
the immutable V1 failure record.

## Frozen Corpus

- Five previously exposed PubMed abstracts.
- Thirty-one previously exposed discovery scopes.
- Corpus and every source are SHA-256 bound.
- Exact passage offsets are validated against the committed source text.

The corpus is frozen at
`scripts/validation/source_general_claim_verification/fixtures/exposed_31_scope_corpus.json`.

## Independent Adjudication

Two blinded `gpt-5.6-sol` Codex subagents independently received source text,
scope identity, and the categorical packet contract. They did not receive
generator reasoning, candidate output, reports, or each other's answer.

| Reviewer | Adjudicated | Ambiguous | Abstain | Artifact validation |
| --- | ---: | ---: | ---: | --- |
| A | 13 | 18 | 0 | valid |
| B | 17 | 14 | 0 | invalid on six event-local evidence scopes |
| C, disagreement-only | 14 | 16 | 0 | schema-invalid on all 30 packets |

Reviewer C received only the 30 disputed scope IDs and disputed field names.
It did not receive either primary answer. Its `complete_event` field was a
boolean in every packet even though the frozen contract required a short
source-grounded string. The output was preserved verbatim and rejected rather
than coerced.

## Agreement Gate

Deterministic comparison covers only material categorical and structured
fields: decision, event type, participants and roles, direction, comparison,
polarity, uncertainty, quantitative evidence, statistical observation, author
interpretation, required modifiers, and completeness.

| Metric | Numerator | Denominator | Rate |
| --- | ---: | ---: | ---: |
| Initial scope disagreement | 30 | 31 | 96.8% |
| Unresolved after tiebreak attempt | 30 | 31 | 96.8% |
| Allowed unresolved maximum | 6 | 31 | 19.4% |

Because invalid reviewer artifacts cannot establish a scientific disagreement
rate, `30/31` is retained only as the number of exact material differences that
could not be resolved in this invalid run. The terminal is
`INVALID_ADJUDICATION_CHECKPOINT`, not a scientific reliability conclusion.

## Root Cause

The 31 entries were designed as discovery-recall scopes, not as atomic complete
event annotations. Several scopes:

- bundle multiple scientific outcomes;
- overlap narrower and wider versions of the same sentence;
- contain sentence fragments whose participants live outside the span;
- admit multiple reasonable participant-role granularities;
- mix observed quantities with broader author conclusions.

The dominant disagreement was not whether the biology existed. It was where
one event ends, which participants and modifiers are essential, and whether a
fragment is complete enough to serve as gold. Treating these scopes as exact
single-event packets would encode arbitrary reviewer preferences into the
benchmark.

## Experiment Accounting

| Resource | Result |
| --- | ---: |
| Provider framing calls | 0 |
| Provider verification calls | 0 |
| Provider repair calls | 0 |
| Provider tokens | 0 |
| Provider latency | 0 seconds |
| Provider cost | USD 0 |
| Fallback calls | 0 |
| Graph writes | 0 |
| Untouched sources accessed | 0 |

Codex subagent token and cost accounting is unavailable and is explicitly
recorded as unavailable, not zero. Agent task identities, configured model,
artifact hashes, prompts, raw outputs, validation failures, and stop transition
are preserved in the checkpoint artifacts.

## Malformed Controls And Metrics

The deterministic harness implements all ten requested malformed families and
their metric contracts. They were not instantiated against this corpus because
there is no reliable frozen reference packet set from which to derive them.
Generating controls from disputed gold would make false-acceptance metrics
meaningless.

Accordingly, framing precision/recall, verifier false acceptance, repair rates,
scientific fidelity, unsupported claims, and contradictions are `NOT_RUN`, not
zero. The blocked preregistration and zero-call receipt record this distinction.

## Correct Pivot

Do not retry these same 31 scope packets or run Artana against them as exact
event gold. The next bounded checkpoint should re-segment the same exposed
source text into atomic assertion units before semantic adjudication:

1. A source-only boundary agent proposes atomic event spans without semantic
   labels.
2. Two blinded semantic adjudicators label only those frozen atomic spans.
3. Nested and coordinated events receive explicit parent/child identities.
4. Fragmentary scopes are expanded to the minimum self-contained sentence or
   excluded before adjudication.
5. Continue only if unresolved categorical disagreement is at most 20%.

This is a benchmark-unit pivot, not evidence that source verification itself is
ineffective. The present checkpoint proves that the current discovery scopes
cannot support a trustworthy scientific pass/fail claim.
