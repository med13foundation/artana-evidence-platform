# PR-7 Evidence-Aware Scoring Evidence Snapshot

Date: 2026-07-03

Branch: planned `alvaro/evidence-pr7-evidence-aware-scoring`; currently stacked
in worktree branch `alvaro/evidence-pr0-quality-harness` until earlier slices
are split.

## Scope

PR-7 makes document-extraction proposal ranking depend on evidence quality, not
only review labels:

- Reviewed candidate ranking now includes grounded sentence, both arguments
  present, entailment support, and relation specificity components.
- Document proposal review passes evidence-grounding and support-verification
  metadata into the ranking helper.
- Ranking metadata now exposes each evidence component and the combined
  `evidence_quality_component`.

## Focused Result

Two claims with identical factual, relevance, priority, document, and evidence
reference inputs now rank differently when only evidence quality differs:

| Scenario | Evidence Quality | Score |
|---|---:|---:|
| Grounded, both arguments present, entailed, specific relation | 1.0000 | 0.9220 |
| Ungrounded, missing arguments, not entailed, generic relation | 0.0000 | 0.7220 |

## Validation

- RED/GREEN PR-7 tests:
  - `test_rank_reviewed_candidate_claim_rewards_grounded_entailed_specific_evidence`
  - `test_review_helpers_rank_specific_grounded_entailed_claim_above_generic_ungrounded_claim`
- Focused affected bundle passed:
  `services/artana_evidence_api/tests/unit/test_ranking.py`,
  `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`,
  and `services/artana_evidence_api/tests/unit/test_document_extraction.py`.
- `ruff check` on touched PR-7 files passed.
- `make artana-evidence-api-service-checks` passed. Live external API,
  running-service, and OpenAI-key integration tests were explicitly skipped.

## Known Remaining Risk

This slice improves proposal ordering after candidates exist. It does not prove
live-agent extraction quality, CURIE linking, or trusted-tier precision by
itself.
