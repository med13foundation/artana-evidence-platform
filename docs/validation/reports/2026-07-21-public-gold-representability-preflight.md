# Public-Gold Representability Preflight

## Decision

`BLOCK_PROVIDER_EXECUTION`

No Artana model run was made. The current claim inventory cannot losslessly
represent enough of the BioNLP-ST 2013 Cancer Genetics development gold for a
model score to measure scientific extraction quality. Running Luna or Sol now
would primarily measure contract incompatibility.

This is a development-only integration result. The sealed test split was not
parsed or scored, graph promotion remained disabled, and no graph write,
fallback, retry, or provider call occurred.

## Deterministic Result

The adapter replayed all 2,915 development events from all 100 documents
against the current Artana claim inventory contract.

| Measure | Result |
| --- | ---: |
| Exactly representable events | 224 / 2,915 (7.68%) |
| Excluded events | 2,691 / 2,915 (92.32%) |
| Development documents included | 100 / 100 |

Exclusive primary exclusion reasons sum to all 2,691 excluded events:

| Primary reason | Events |
| --- | ---: |
| Unsupported event type | 1,144 |
| Nested event argument | 997 |
| Fewer than two distinct direct arguments | 550 |

Because one event can violate several contract dimensions, the diagnostic
counts below are intentionally non-exclusive:

| Contract dimension | Events affected |
| --- | ---: |
| Fewer than two distinct direct arguments | 1,729 |
| Unsupported event type | 1,144 |
| Event used as an event argument | 1,002 |
| Unsupported argument role | 240 |

Numbered BioNLP arguments such as `Theme2` were normalized structurally to
their base role, `Theme`, before counting. No biomedical category was inferred
or relabeled. Unsupported event labels were not credited through
`OTHER_EXPLICIT`, because doing so would make exact event-type fidelity
impossible while concealing the mismatch.

## Root Cause

The public corpus represents scientific findings as an event graph. It includes
unary events, events whose arguments are other events, and a broader set of
typed biological processes and participant roles. Artana's current inventory
requires at least two distinct source-span arguments, cannot point one event to
another event, and uses a smaller closed event and role vocabulary.

This is an information-model boundary failure. Prompt tuning, greater reasoning
effort, an adversarial second call, or a stronger model cannot emit a valid
structure that the receiving schema forbids.

## BioRED Intake Correction

The same pre-execution audit found a separate adapter defect: official BioRED
uses `Novel` and `No`, while the adapter recognized only `Yes` as novel. The
adapter now maps the two official labels explicitly and rejects unknown labels.
The corrected development projection contains 835 novel and 327 background
relations and has SHA-256
`6c33bb41182305bf2a0874fd8c21b4f762373799268bb7a5de4b623a3b05b944`.

This correction changes no Artana scientific output because execution has not
started.

## Required Next Checkpoint

Before a provider call, introduce one bounded, lossless scientific event
intermediate representation with these minimum capabilities:

1. Zero, one, or many direct participants without inventing a second endpoint.
2. Typed event-to-event arguments for nested findings.
3. Source event labels preserved independently from any later graph relation.
4. Repeated typed roles and source roles retained without participant merging.
5. Negation and speculation attached to the event they modify.

The change must remain upstream of graph projection. Agent stages own the
scientific labels; deterministic code may validate identifiers, references,
offsets, arity, lineage, and exact benchmark equality, but may not infer a
biomedical category.

The checkpoint passes only when the deterministic preflight can represent all
development gold without dropping or relabeling information. Only then should
the model, prompts, schemas, token budget, and code hashes be frozen for a
development execution.

## Validation Evidence

- Focused adapter and representability tests cover supported n-ary events,
  repeated numbered roles, nested arguments, overlapping blockers, official
  BioRED novelty labels, unknown-label rejection, and sealed test access.
- All counts are produced by deterministic code from the pinned development
  distributions.
- `make service-checks` passed, including lint, typing, boundaries, generated
  contracts, migrations, and the full database-backed suite at 87.65% coverage.
- Raw benchmark files and generated projections remain local and uncommitted.
