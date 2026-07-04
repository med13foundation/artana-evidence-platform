# PR-8 Trust Ladder Hard Floors Evidence Snapshot

Date: 2026-07-03

Branch: planned `alvaro/evidence-pr8-trust-ladder-hard-floors`; currently
stacked in worktree branch `alvaro/evidence-pr0-quality-harness` until earlier
slices are split.

## Scope

PR-8 makes trusted evidence a derived hard-floor result:

- Document-extraction proposal drafts now receive `trust_tier`,
  `trust_floor_failures`, and final `trusted_evidence_eligible` metadata from a
  trust ladder.
- Graph validation rejects AI-authored writes that claim trusted status without
  completed agent extraction, no fallback output, grounded evidence, entailing
  support, and linked subject/object CURIEs.
- Promotion request metadata cannot override verifier-owned trust tier,
  trust-floor failures, grounding, support, fallback, or eligibility fields.

## Focused Result

| Scenario | Result |
|---|---|
| All trusted hard floors pass | Accepted as `trust_tier=trusted` |
| Missing linked subject CURIE while claiming trusted | Rejected |
| Fallback output while claiming trusted, even with override metadata | Rejected |
| Review request tries to upgrade trust tier | Ignored; verifier metadata preserved |

Focused adversarial trusted-tier precision: `1.00`.

## Validation

- RED/GREEN PR-8 tests:
  - `test_candidate_extraction_trust_requires_all_hard_floors`
  - `test_candidate_extraction_trust_marks_verified_linked_agent_relation_trusted`
  - `test_ai_claim_rejects_claimed_trusted_tier_without_linked_entities`
  - `test_ai_claim_rejects_claimed_trusted_tier_from_fallback_output`
  - `test_ai_claim_accepts_claimed_trusted_tier_when_hard_floors_pass`
  - `test_build_graph_claim_request_preserves_verifier_owned_metadata`
  - `test_build_graph_relation_request_preserves_verifier_owned_metadata`
- Focused affected bundle passed across document extraction, documents router,
  variant-aware extraction, graph AI validation, and proposal actions.
- `ruff check` on touched PR-8 files passed.
- `make artana-evidence-api-service-checks` passed. Live external API,
  running-service, and OpenAI-key integration tests were explicitly skipped.
- `make graph-service-checks` passed.

## Known Remaining Risk

This slice prevents false trusted claims. It does not prove live-agent gold
precision because local agent extraction still has not completed in the strict
audit environment.
