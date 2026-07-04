# PR-6 CURIE Entity Linking Evidence Snapshot

Date: 2026-07-03

Branch: planned `alvaro/evidence-pr6-curie-entity-linking`; currently stacked
in worktree branch `alvaro/evidence-pr0-quality-harness` until earlier slices
are split.

## Scope

PR-6 adds explicit entity identity support to the document-extraction path:

- LLM relation extraction can return `subject_curie` and `object_curie`.
- CURIEs are normalized and type-checked before becoming candidate metadata.
- Invalid or label/type-mismatched CURIEs are treated as endpoint abstentions.
- Draft proposals now carry graph entity candidate payloads with identifier maps
  such as `hgnc_id` and `hpo_id`.
- The feasibility audit now reports CURIE-linked gold endpoint counts and rates.

## Strict-Agent Result

The local strict-agent audit remains RED because no LLM/agent extraction cases
completed locally. That is expected in this environment and is still the correct
failure mode: fallback output has zero linked gold endpoints and is not credited
as agent quality.

| Metric | Value |
|---|---:|
| Verdict | RED |
| Precision | 0.7500 |
| Recall | 0.2400 |
| Valuable candidate rate | 0.7500 |
| Generic relation rate | 0.0000 |
| Gold CURIE endpoints | 37 |
| Candidate CURIE endpoints | 0 |
| CURIE-linked gold endpoints | 0 |
| CURIE-linked gold endpoint rate | 0.0000 |
| Agent-completed cases | 0/30 |
| Fallback or unavailable cases | 30/30 |
| Invalid strict-agent cases | 30/30 |

## Deterministic Comparison

The deterministic comparison is triage-only. It is RED for PR-6 because regex
fallback has no ontology linking and therefore cannot satisfy the CURIE gate.

| Metric | Value |
|---|---:|
| Verdict | RED |
| Precision | 0.7500 |
| Recall | 0.2400 |
| Valuable candidate rate | 0.7500 |
| Generic relation rate | 0.0000 |
| Gold CURIE endpoints | 37 |
| Candidate CURIE endpoints | 0 |
| CURIE-linked gold endpoints | 0 |
| CURIE-linked gold endpoint rate | 0.0000 |

## Focused Validation

- RED/GREEN PR-6 tests:
  - `test_extract_relation_candidates_with_llm_preserves_valid_curies_and_abstains_invalid`
  - `test_prompt_schema_builders_validate_structured_outputs`
  - `test_draft_builder_propagates_curie_identifiers_for_graph_entity_creation`
  - `test_audit_requires_curie_linked_gold_entities`
  - `test_audit_turns_red_when_gold_curie_endpoints_are_missing`
- Focused affected bundle passed:
  `tests/unit/test_relation_feasibility_audit.py`,
  `services/artana_evidence_api/tests/unit/test_document_extraction.py`,
  `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`,
  and `services/artana_evidence_api/tests/unit/test_proposal_actions.py`.
- `ruff check` on touched PR-6 files passed.
- `make artana-evidence-api-service-checks` passed. Live external API,
  running-service, and OpenAI-key integration tests were explicitly skipped.

## Artifacts

- Strict-agent JSON:
  `reports/relation_feasibility/2026-07-03-pr6-curie-linking-agent-strict/relation_feasibility_report.json`
- Strict-agent Markdown:
  `reports/relation_feasibility/2026-07-03-pr6-curie-linking-agent-strict/relation_feasibility_report.md`
- Deterministic JSON:
  `reports/relation_feasibility/2026-07-03-pr6-curie-linking-deterministic/relation_feasibility_report.json`
- Deterministic Markdown:
  `reports/relation_feasibility/2026-07-03-pr6-curie-linking-deterministic/relation_feasibility_report.md`

## Hashes

| Artifact | SHA-256 |
|---|---|
| strict JSON | `32e4c619f22cc9c9cc12090332d148c9dba4b087624184f2418b3e3655337b85` |
| strict Markdown | `544097fb4665daa81759242333cd8e0b9e67f7c5e3de1bba712b4e4b7fb7ffb7` |
| deterministic JSON | `db43f21c237397462e62c569261e78484effdd9475919c0d2e9a60396ef13f29` |
| deterministic Markdown | `8d967de7cb7a70dd74afc0595ddd182a4db4185ee1f4a949df69503e020d4d36` |

## Known Remaining Risk

The strict primary gate is not green locally. PR-6 adds the agent contract,
validation, graph-promotion propagation, and audit metric, but a live completed
agent run must still prove `curie_linked_gold_endpoint_rate >= 0.95`.
