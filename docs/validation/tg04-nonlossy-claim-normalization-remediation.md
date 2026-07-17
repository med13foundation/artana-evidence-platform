# TG-04 Non-Lossy Claim Normalization Remediation

Created: 2026-07-17

Status: implemented on `alvaro/tg04-nonlossy-claim-normalization`, stacked on
the bounded-convergence TG-04 work.

## Problem

The frozen TG-04 benchmark and the product answer different questions:

- the benchmark asks whether Artana recovered a finite, predeclared set of
  complete scientific events;
- the product asks an agent to discover scientifically meaningful claims and
  then normalize their entities, relations, and aliases.

The dictionary can normalize two surface forms to the same concept. It cannot
decide that two claims have the same scientific meaning, that one is more
specific, or that a novel hypothesis should be discarded. Those decisions
require semantic adjudication with the source in view.

The previous semantic-incompleteness route returned no visible candidates. It
correctly blocked benchmark credit, but it also hid source-bound discoveries
from human review. This confused **not benchmark-qualified** with **not useful**.

## Implemented Flow

```text
source document
  -> agent event inventory
  -> exact-span and typed-role binding
  -> dictionary/entity resolution and governed concept proposals
  -> non-lossy candidate drafts
  -> independent categorical claim adjudication
  -> deterministic review-only or promotion-eligible routing
  -> existing relevance review
  -> proposal persistence
```

The implementation preserves these independent facts:

1. **Inventory completeness:** did the bounded extraction task converge?
2. **Source support:** is the individual claim entailed, contradicted,
   insufficient, or should the adjudicator abstain?
3. **Claim atomicity:** is the claim atomic, bundled, or unresolved?
4. **Claim relationship:** is it canonical, the same as an earlier claim, a
   refinement, a generalization, a contradiction, or unresolved?
5. **Dictionary identity:** can the entities and aliases be resolved to
   governed concepts?

No one answer overwrites another.

## Safety Rules

- A semantically incomplete inventory preserves its bound candidates as
  `review_only`; it never receives scored benchmark credit or automatic trust.
- Unresolved missing-claim descriptors remain diagnostics. They are not
  converted into executable graph claims.
- The adjudication agent returns closed categories, exact source spans,
  reasoning, and a falsification condition. It does not return numeric scores.
- Code deterministically computes counts and applies score ceilings.
- A claim is promotion-eligible only when it is atomic, source-entailed,
  canonical, independently agent-verified, and already satisfies the existing
  entity, provenance, variant, and relation-governance gates.
- Same-as, refinement, generalization, and contradiction findings are stored
  as review-only relation proposals with stable target lineage.
- Missing, invalid, incomplete, or unavailable adjudication fails closed and
  leaves every affected claim review-only.
- No deterministic semantic fallback is credited as agent evidence.

## Deterministic Measurements

The agent authors categorical artifacts. Code derives:

- total, atomic, and bundled claim counts;
- source-entailed, contradicted, insufficient, and abstained counts;
- canonical, same-as, refining, generalizing, and contradicting counts;
- review-only event count for semantically incomplete TG-04 runs.

No adjudication metric is named or interpreted as promotion eligibility. That
decision requires the complete deterministic promotion preflight, entity
resolution, provenance, and graph-governance context.

Scientific precision and recall still require a frozen independent reference
set. Preserved review-only discoveries are reported separately and are not
silently counted as false positives or true positives. A future expert or
source-only adjudication may classify an unmatched discovery as valid outside
the gold set, invalid, duplicated, or unresolved without changing the frozen
benchmark labels.

## Code Boundaries

- `document_extraction_support/claim_adjudication/contracts.py`: closed
  categorical contracts.
- `document_extraction_support/claim_adjudication/service.py`: independent
  source-only agent invocation, validation, fail-closed routing, and semantic
  relation proposals.
- `document_extraction_support/claim_adjudication/metrics.py`: deterministic
  counts only.
- `document_extraction_support/claim_adjudication/candidate_preservation.py`:
  non-lossy review routing for deterministically pruned candidates.
- `document_extraction.py`: non-lossy routing for incomplete inventories.
- `routers/documents.py`: interactive document extraction integration.
- `research_init_document_extraction_runtime.py`: research-init integration.
- `promotion_policy.py`: deterministic promotion gate.
- `scripts/validation/claim_events/runner.py`: separates scored events from
  review-only events.
- `scripts/validation/claim_events/evidence_binding.py`: independently replays
  and verifies review-only event lineage.

## Merge Validation

Required before merge:

- focused unit and regression tests for extraction, adjudication, promotion,
  API integration, and TG-04 evidence replay;
- Evidence API lint, strict type check, boundary check, contract check, and
  full service test suite;
- repository `make service-checks`;
- adversarial review that attempts unknown targets, fabricated spans, partial
  coverage, numeric model judgments, semantic fallback credit, and promotion
  from incomplete inventories;
- live GitHub review-thread, approval, conflict, and required-check inspection.

### Local evidence

Validated on 2026-07-17:

- focused extraction, adjudication, promotion, and TG-04 replay suite: green;
- Evidence API lint and strict mypy over 612 production modules: green;
- agent-output schema registry and boundary validation: green;
- OpenAPI, service boundary, architecture-size, and architecture-structure
  checks: green;
- repository `make service-checks`: green with `87.47%` measured coverage;
- fresh ephemeral PostgreSQL migrations and full service tests: green.

Three adversarial review rounds found and closed these gaps:

- deterministic pruning and candidate overflow could hide claims before agent
  adjudication;
- evidence spans could come from another claim in the same document;
- an empty review-only list could bypass preservation comparison;
- later relevance review could overwrite adjudication score ceilings;
- a categorical count was misleadingly named as promotion eligibility;
- research-init discarded document-level adjudication diagnostics;
- quality-filter many-to-one repair could break source-order reconstruction;
- an unbounded adjudication prompt could fail all overflow candidates;
- a batch could target an earlier claim absent from its bounded context.

The final design preserves stable per-input lineage, uses source-order batches of
at most 12 claims with at most 24 visible prior targets, and rejects relations
to claims outside the actual adjudication context.

## Stop/Go Decision

This remediation improves information preservation and promotion safety. It
does not by itself prove scientific accuracy.

Continue to a larger run only when the small frozen sample shows at least one
exact whole-event recovery and no safety regression. If exact recovery remains
zero, stop prompt-loop expansion and compare the finite source-unit task with
an expert-seeded or hybrid candidate workflow. Do not enable trusted graph
promotion from review-only discoveries.
