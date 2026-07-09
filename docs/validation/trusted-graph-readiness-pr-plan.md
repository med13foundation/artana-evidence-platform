# Trusted Graph Readiness PR Plan

Created: 2026-07-04

This document turns the post-PR #93 evidence-quality findings into a concrete
set of follow-up PRs. The goal is to move Artana Evidence from a live-agent path
that completes into a trusted graph path that can promote high-confidence
relations without confusing fallback, generic claims, or unverified entity IDs
with real evidence.

## Baseline

Baseline evidence:

- Merged foundation PR:
  `https://github.com/med13foundation/artana-evidence-platform/pull/93`
- Live-agent summary:
  `docs/validation/reports/2026-07-03-pr8-live-agent-remediation-summary.md`
- Progress tracker:
  `docs/validation/evidence-excellence-progress-tracker.md`
- Audit command:
  `scripts/run_relation_feasibility_audit.py --extractor agent`

Current strict live-agent result:

| Metric | Current | Trusted-readiness target |
|---|---:|---:|
| Agent-completed cases | 30/30 | 30/30 |
| Fallback cases | 0 | 0 |
| Invalid strict-agent cases | 0 | 0 |
| Negative-control leakage cases | 0 | 0 |
| Completed-agent precision | 0.6552 | >= 0.8000 |
| Completed-agent recall | 0.7600 | >= 0.8000 |
| High-value recall | 0.8500 | >= 0.9000 |
| Completed-agent valuable rate | 0.5517 | >= 0.7000 |
| Generic relation rate | 0.1379 | <= 0.0500 |
| Entailment checked rate | 0.9630 | 1.0000 |
| Governed proposal recall among eligible gold | 0.5000 | 1.0000 |
| Candidate CURIE present rate | 0.5690 | >= 0.9500 |
| Verified CURIE match rate | 0.0000 | >= 0.9500 |
| Verified CURIE-linked gold endpoint rate | 0.0000 | >= 0.9500 |
| Wrong verified CURIE links | Not allowed | 0 |

## Merge Rules For Every PR

Every PR in this plan must preserve these invariants:

- Deterministic fallback output can support local triage, but it must not count
  as trusted agent evidence.
- `fallback_case_count` must remain `0` in strict live-agent audit results.
- `invalid_agent_case_count` must remain `0` in strict live-agent audit results.
- Negative controls must stay empty: no negative-control leakage cases.
- Model-provided CURIEs are hints only. A CURIE is trusted only after resolver,
  dictionary, or graph-backed verification.
- Missing verification must fail closed into review or rejection, not promotion.
- New graph trust behavior must be enforced in `services/artana_evidence_db`.
- Extraction, prompting, review staging, and audit behavior must stay in
  `services/artana_evidence_api` or `scripts/validation`.

Each PR must include this evidence in the PR description:

```text
PR:
Branch:
Base commit:
Goal:
Primary metric changed:
Files changed:
Focused tests:
Repository gates:
Live-agent audit command:
Live-agent report path:
Before metrics:
After metrics:
Fallback cases:
Invalid strict-agent cases:
Negative-control leakage cases:
Known remaining risk:
Adversarial review notes:
```

Do not mark a PR ready to merge if the live-agent evidence uses
`--allow-fallback` or if the report path is missing from the PR description.

## Required Validation Commands

Run these before merging any code PR:

```bash
git fetch origin main
git rebase origin/main
git diff --check
make setup-postgres
make relation-feasibility-quality-gate
make service-checks
```

Run the strict live-agent audit with model credentials available:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/YYYY-MM-DD-prNN-short-slug
```

Record hashes for committed report summaries or archived artifacts:

```bash
shasum -a 256 reports/relation_feasibility/YYYY-MM-DD-prNN-short-slug/relation_feasibility_report.json
shasum -a 256 reports/relation_feasibility/YYYY-MM-DD-prNN-short-slug/relation_feasibility_report.md
```

Use these service-specific gates when the PR touches those service boundaries:

```bash
make artana-evidence-api-service-checks
make graph-service-checks
```

For doc-only PRs, run:

```bash
git diff --check
```

## PR Dependency Order

```text
PR-11 Verified entity linking
  -> PR-12 Precision and valuable-candidate improvement
  -> PR-13 Generic relation noise reduction
  -> PR-14 Entailment coverage hardening
  -> PR-15 Governed relation proposal recall
  -> PR-16 Final trusted-readiness repeatability gate
```

PR-12, PR-13, PR-14, and PR-15 can be developed in parallel after PR-11 lands,
but PR-16 must run after all previous slices are merged.

## PR-11: Verified Entity Linking And CURIE Adjudication

Suggested branch: `alvaro/evidence-pr11-verified-curie-linking`

Goal: make extracted subject and object identifiers verifiable. Model CURIE
hints may guide lookup, but only resolver-verified CURIEs can enter graph
identifiers or trusted metadata.

Likely files:

- Modify: `services/artana_evidence_api/entity_curie_linking.py`
- Modify: `services/artana_evidence_api/document_extraction_drafts.py`
- Modify: `services/artana_evidence_api/document_extraction_contracts.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v2.json`
- Test: `services/artana_evidence_api/tests/unit/test_entity_curie_linking.py`
- Test: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

Implementation requirements:

- Normalize gene, variant, disease, drug, and phenotype aliases before lookup.
- Verify model CURIE hints against normalized labels and allowed namespaces.
- Reject namespace mismatches such as a drug label linked as a gene CURIE.
- Return an explicit abstain result when the resolver cannot verify a label.
- Keep abstained entities in review metadata without graph identifiers.
- Add an audit metric for wrong verified CURIE links; the allowed count is `0`.

Focused tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_draft_builder_propagates_curie_identifiers_for_graph_entity_creation \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_draft_builder_keeps_model_curie_hints_out_of_graph_identifiers \
  tests/unit/test_relation_feasibility_audit.py::test_audit_requires_curie_linked_gold_entities \
  tests/unit/test_relation_feasibility_audit.py::test_model_curie_hints_do_not_count_as_verified_gold_endpoint_links \
  -q
```

Merge gate:

- `verified_curie_match_rate >= 0.9500`
- `verified_curie_linked_gold_endpoint_rate >= 0.9500`
- `wrong_verified_curie_link_count == 0`
- `fallback_case_count == 0`
- `invalid_agent_case_count == 0`
- `negative_control_leakage_case_count == 0`

## PR-12: Precision And Valuable Candidate Improvement

Suggested branch: `alvaro/evidence-pr12-precision-value-gates`

Goal: reduce unsupported, over-broad, and low-value candidates while preserving
high-value recall.

Likely files:

- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction.py`
- Modify: `services/artana_evidence_api/evidence_support_verifier.py`
- Modify: `services/artana_evidence_api/document_extraction_drafts.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Test: `services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py`
- Test: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

Implementation requirements:

- Reject candidates when the evidence sentence mentions both entities but does
  not entail the relation.
- Reject relation candidates whose subject or object is broader than the
  evidence-supported claim.
- Add prompt language that asks the agent to abstain instead of guessing.
- Add adversarial cases for weak association, reversed direction, and mechanism
  overclaiming.
- Split reporting for high-value misses versus low-value triage misses.

Focused tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_candidate_extraction_trust_requires_entailing_support \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_conversion_rejects_broadened_specific_object_label \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_review_helpers_rank_specific_grounded_entailed_claim_above_generic_ungrounded_claim \
  tests/unit/test_relation_feasibility_audit.py::test_audit_requires_entailment_support_for_valuable_candidate \
  tests/unit/test_relation_feasibility_audit.py::test_summary_reports_high_value_and_low_value_recall_separately \
  -q
```

Merge gate:

- `completed_agent_precision_against_gold >= 0.8000`
- `completed_agent_valuable_candidate_rate >= 0.7000`
- `high_value_recall >= 0.9000`
- `fallback_case_count == 0`
- `invalid_agent_case_count == 0`
- No decrease in verified CURIE metrics from PR-11.

## PR-13: Generic Relation Noise Reduction

Suggested branch: `alvaro/evidence-pr13-specificity-noise-reduction`

Goal: remove redundant generic relations and push the agent toward the most
specific supported biomedical relation.

Likely files:

- Modify: `services/artana_evidence_api/relation_specificity_pruning.py`
- Modify: `services/artana_evidence_api/document_extraction_relation_taxonomy.py`
- Modify: `services/artana_evidence_api/document_extraction_prompting.py`
- Modify: `services/artana_evidence_api/document_extraction_drafts.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Test: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

Implementation requirements:

- Prune generic `ASSOCIATED_WITH` siblings when the same sentence supports a
  more specific relation.
- Keep a generic relation only when no specific relation is supported by the
  same evidence sentence.
- Teach the prompt to prefer canonical specific relations over broad labels.
- Add negative tests proving a generic relation from a different sentence is not
  pruned when it expresses a distinct claim.

Focused tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_draft_builder_prunes_redundant_generic_relation_siblings \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_draft_builder_keeps_generic_relation_from_different_sentence \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_draft_builder_skips_weak_generic_relation_candidates \
  tests/unit/test_relation_feasibility_audit.py::test_audit_flags_generic_and_unsupported_relations_as_low_value \
  tests/unit/test_relation_feasibility_audit.py::test_audit_counts_pruned_generic_relation_siblings \
  -q
```

Merge gate:

- `generic_relation_rate <= 0.0500`
- `completed_agent_precision_against_gold >= 0.8000`
- `high_value_recall >= 0.9000`
- No increase in negative-control leakage.
- No decrease in verified CURIE metrics from PR-11.

## PR-14: Entailment Coverage And Fail-Closed Promotion

Suggested branch: `alvaro/evidence-pr14-entailment-coverage`

Goal: make support verification complete for every trusted candidate and
enforce the same rule in graph promotion.

Likely files:

- Modify: `services/artana_evidence_api/evidence_support_verifier.py`
- Modify: `services/artana_evidence_api/document_extraction_drafts.py`
- Modify: `services/artana_evidence_db/validation/claim_ai_evidence_validation.py`
- Modify: `services/artana_evidence_db/validation/trusted_evidence_floor.py`
- Modify: `services/artana_evidence_db/graph_validation_service.py`
- Test: `services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py`
- Test: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Test: `services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

Implementation requirements:

- Every trusted candidate must have verifier status `entails`.
- Verifier errors, skipped verifier calls, and missing verifier metadata must
  produce review-only or rejected candidates.
- Graph promotion must reject AI-generated trusted claims with missing or
  non-entailing support verification.
- The audit must report unchecked support as a blocking quality issue.

Focused tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_draft_builder_omits_support_verification_when_grounding_fails \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_candidate_extraction_trust_requires_all_hard_floors \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py::test_ai_claim_requires_entailing_support_verification \
  services/artana_evidence_db/tests/unit/test_claim_ai_evidence_validation.py::test_ai_relation_create_requires_entailing_support_verification \
  tests/unit/test_relation_feasibility_audit.py::test_audit_requires_entailment_support_for_valuable_candidate \
  -q
```

Merge gate:

- `entailment_checked_rate == 1.0000`
- Trusted candidates without entailing support verification: `0`
- Graph trusted promotion without entailing support verification: rejected
- `fallback_case_count == 0`
- `invalid_agent_case_count == 0`

## PR-15: Governed Relation Proposal Recall

Suggested branch: `alvaro/evidence-pr15-governed-relation-proposals`

Goal: make missing-but-valid biomedical relation types visible as governed
review proposals instead of losing credit or becoming raw relation strings.

Likely files:

- Modify: `services/artana_evidence_api/proposal_relation_type_guard.py`
- Modify: `services/artana_evidence_api/document_extraction_relation_taxonomy.py`
- Modify: `services/artana_evidence_api/document_extraction_drafts.py`
- Modify: `services/artana_evidence_db/graph_validation_service.py`
- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Test: `services/artana_evidence_api/tests/unit/test_document_extraction_modules.py`
- Test: `services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py`
- Test: `tests/unit/test_relation_feasibility_audit.py`

Implementation requirements:

- Stage unknown but well-supported relation types as governed proposals.
- Keep raw unknown relation strings out of trusted graph writes.
- Credit governed proposal recall separately from trusted recall.
- Require support sentence, both arguments, and proposed semantics for every
  governed relation-type proposal.

Focused tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_schema_accepts_structured_new_relation_proposal \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_draft_builder_stages_governed_relation_type_proposals \
  services/artana_evidence_db/tests/integration/test_artana_evidence_db_validation.py \
  tests/unit/test_relation_feasibility_audit.py::test_governed_relation_proposal_counts_proposal_recall_without_trusted_recall \
  tests/unit/test_relation_feasibility_audit.py::test_governed_proposal_recall_uses_proposal_eligible_denominator \
  -q
```

Merge gate:

- `governed_proposal_recall_among_proposal_eligible_gold == 1.0000`
- Raw unknown relation inventory count: `0`
- Governed proposals are not counted as trusted evidence until approved.
- No decrease in precision, high-value recall, or verified CURIE metrics.

## PR-16: Final Trusted-Readiness Repeatability Gate

Suggested branch: `alvaro/evidence-pr16-trusted-readiness-gate`

Goal: prove the combined system is repeatable enough to guard future trusted
graph promotion work.

Likely files:

- Modify: `scripts/validation/relation_feasibility/scoring.py`
- Modify: `scripts/validation/relation_feasibility/reporting.py`
- Modify: `docs/validation/evidence-excellence-progress-tracker.md`
- Modify: `.github/workflows/evidence-api-service-checks.yml`
- Modify: `.github/workflows/graph-service-checks.yml`
- Test: `tests/unit/test_relation_feasibility_audit.py`
- Test: `tests/unit/test_ci_service_check_planner.py`

Implementation requirements:

- Add a final readiness verdict that requires all trusted-readiness metrics.
- Record two strict live-agent runs and compare the metric deltas.
- Fail the readiness verdict if either run uses fallback or invalid agent cases.
- Keep the normal CI-safe quality gate deterministic; live-agent runs remain
  opt-in unless repository secrets are available for a protected CI job.

Focused tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  tests/unit/test_relation_feasibility_audit.py \
  tests/unit/test_ci_service_check_planner.py \
  -q
```

Live repeatability commands:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/YYYY-MM-DD-pr16-live-run-1

PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/YYYY-MM-DD-pr16-live-run-2
```

Merge gate:

- Both strict live-agent runs satisfy every trusted-readiness target in this
  document.
- Metric deltas between the two live runs are documented.
- `make service-checks` passes.
- `make live-agent-relation-feasibility-check` passes.
- The progress tracker has a dated evidence-log entry with report paths and
  hashes.

## Adversarial Review Loop

Run this loop before every PR is marked ready:

1. Ask one reviewer to look only for false positives: unsupported claims,
   wrong CURIEs, generic relation inflation, and hidden fallback credit.
2. Ask one reviewer to look only for false negatives: missed high-value
   relations, over-pruning, over-abstention, and relation proposal misses.
3. Convert each accepted finding into a failing unit or audit test.
4. Fix the implementation.
5. Rerun focused tests, `make service-checks`, and the strict live-agent audit.
6. Update the PR description and progress tracker with the after metrics.

If reviewers disagree, use the gold fixture and support sentence as the source
of truth. Do not settle disagreements by lowering a trust gate.

## Definition Of Trusted-Graph Ready

The system is trusted-graph ready only when all of these are true in the same
strict live-agent report:

- Agent completion rate is 100%.
- Fallback cases are 0.
- Invalid strict-agent cases are 0.
- Negative-control leakage cases are 0.
- Completed-agent precision is at least 0.8000.
- Completed-agent recall is at least 0.8000.
- High-value recall is at least 0.9000.
- Completed-agent valuable rate is at least 0.7000.
- Generic relation rate is at most 0.0500.
- Entailment checked rate is 1.0000.
- Verified CURIE match rate is at least 0.9500.
- Verified CURIE-linked gold endpoint rate is at least 0.9500.
- Wrong verified CURIE links are 0.
- Governed proposal recall among proposal-eligible gold is 1.0000.
- Graph promotion rejects every AI trusted claim that lacks verified entities,
  entailing support, provenance, and no-fallback agent trace metadata.
