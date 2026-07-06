# PR33 Review Burden Pruning Summary

## Run Context

- Branch: `alvaro/evidence-pr33-review-burden-pruning`
- Base branch: `alvaro/evidence-pr32-weak-review-recovery`
- Commit: PR branch head
- Fixture path:
  `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- Model label: live agent configured by `.env.postgres`

## Goal

Reduce repeated low-value relation noise from the live-agent path while
preserving trusted-graph readiness. This PR keeps deterministic fallback out of
the evidence path and uses bounded agent retries only.

The repeated review-burden targets were:

- `PAH pathogenic variants ASSOCIATED_WITH elevated phenylalanine`
- `Vemurafenib INHIBITS MAPK signaling`
- `BRAF V600E DOWNSTREAM_OF MAPK signaling`
- `JAK-STAT ACTIVATES macrophages`
- `Sotorasib TARGETS switch-II pocket`

During validation, live runs also exposed two agent-path robustness failures:

- a zero-usable-candidate response for
  `Larotrectinib TREATS NTRK fusion solid tumors`
- schema-invalid output where a canonical `relation_type` was paired with a
  conflicting `proposed_relation_type`

PR33 therefore adds bounded agent-only retries for zero usable candidates and
schema repair. Neither retry uses regex or deterministic fallback evidence.

## Code Changes

- Added sibling-aware review-burden pruning for companion biochemical phenotype
  candidates when a same-sentence disease relation survives.
- Promoted direct-target shadowing from review-only to filtered for pathway and
  process companion effects. After adversarial review, target siblings must pass
  the base quality floor before they can shadow a pathway effect.
- Added clause-scoped downstream-context pruning so direct mechanism context is
  filtered only when it belongs to the same claim.
- Added primary-relation shadowing for cell-context activation candidates such
  as `JAK-STAT ACTIVATES macrophages` beside `IL6 REGULATES inflammatory
  signaling`.
- Added binding-site pruning so `Sotorasib TARGETS switch-II pocket` is
  filtered when `Sotorasib TARGETS KRAS G12C` survives in the same sentence.
- Added a bounded agent-only retry for zero converted-candidate extraction when
  the text contains relation cues. The retry uses prompt-version suffix
  `zero_candidate_retry.v1` and an explicit instruction to re-read the text
  without inventing relations or using deterministic fallback.
- Added a bounded agent-only retry for schema-validation failures. The retry
  uses prompt-version suffix `schema_retry.v1` and instructs the agent not to
  set `proposed_relation_type` when `relation_type` is already canonical.

## Artifact Hashes

- `reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run1/relation_feasibility_report.json`:
  `85e00b39c66485685bdcc3f4c02a5905183c7279940cbeca92376d220a828d5f`
- `reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run2/relation_feasibility_report.json`:
  `c0dcbb359d1aeb2cf99668e179729e48a140cb0bab2ef018247718fa904aef2e`
- `reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run3/relation_feasibility_report.json`:
  `0be2831735545e7a04ec88d8f98f001ef6b18c10a9a211aba0f261fa8bc267b9`
- `reports/relation_feasibility_readiness/2026-07-06-pr33-review-burden-postadversarial3-runs1-3/relation_feasibility_readiness_report.json`:
  `ed00f69d2d8a6d5ef0956b527f7aac8d8cced70d652d7f75b3ba88dff906d97c`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr33-review-burden-postadversarial3-runs1-3/relation_feasibility_failure_analysis_report.json`:
  `999caadcdff5a60aaa512bf1f6a127a00ab413dac6c806accad30ed7dc5808a0`

## Validation

Schema-retry RED/GREEN regression:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_retries_schema_validation_failure
```

Result:

- before implementation: failed with escaped Pydantic `ValidationError`
- after implementation: `1 passed in 0.19s`

Focused PR33 suite:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_filters_pathway_target_sibling \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_retries_zero_candidate_agent_pass \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_retries_zero_converted_candidates \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_retries_schema_validation_failure \
  services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_uses_agent_review_only_pass \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_scopes_step_key_to_document_payload \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_reads_beyond_first_chunk \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_repairs_weak_met_resistance_object \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_keeps_weak_generic_review_only \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_prompt_preserves_useful_weak_claims_as_review_only \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_weak_review_prompt_names_repeated_v3_review_misses \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_schema_ignores_spurious_proposal_on_canonical_relation \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_schema_rejects_unknown_proposal_on_canonical_relation \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_schema_rejects_conflicting_proposal_on_canonical_relation
```

Result: `80 passed in 0.87s`

Focused quality-filter suite:

```bash
uv run pytest services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py
```

Result: `47 passed in 0.16s`

Touched-file Ruff:

```bash
uv run ruff check \
  services/artana_evidence_api/document_extraction.py \
  services/artana_evidence_api/document_extraction_support/llm_extraction \
  services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py
```

Result: `All checks passed!`

Quality gate:

```bash
make relation-feasibility-quality-gate
```

Result: relation feasibility audit, readiness, model comparison, fixture
validation, and summary tests passed.

Full service gate:

```bash
make service-checks
```

Result: passed with coverage `87.03%` against the `86%` floor.

Strict live-agent runs:

```bash
set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run1

set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run2

set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run3
```

Aggregate reports:

```bash
uv run python scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run1 \
  --report reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run2 \
  --report reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run3 \
  --min-runs 3 \
  --output-dir reports/relation_feasibility_readiness/2026-07-06-pr33-review-burden-postadversarial3-runs1-3

uv run python scripts/summarize_relation_readiness_failures.py \
  --report postadversarial3-run1=reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run1 \
  --report postadversarial3-run2=reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run2 \
  --report postadversarial3-run3=reports/relation_feasibility/2026-07-06-pr33-review-burden-postadversarial3-run3 \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-06-pr33-review-burden-postadversarial3-runs1-3
```

## Three-Run Readiness Result

Trusted graph readiness is **READY** for the measured v3 live-agent trusted
lane.

| Metric | Worst | Mean |
|---|---:|---:|
| Completed-agent precision | 1.0000 | 1.0000 |
| Completed-agent recall | 1.0000 | 1.0000 |
| Completed-agent valuable candidate rate | 0.5333 | 0.5333 |
| High-value recall | 1.0000 | 1.0000 |
| Trusted candidate precision | 1.0000 | 1.0000 |
| Trusted candidate valuable rate | 1.0000 | 1.0000 |
| Trusted candidate generic relation rate | 0.0000 | 0.0000 |
| Trusted-eligible high-value recall | 1.0000 | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 | 1.0000 |
| Entailment checked rate | 1.0000 | 1.0000 |
| All-candidate generic relation rate | 0.3000 | 0.3000 |
| Verified CURIE match rate | 0.7250 | 0.7250 |

Hard failures across post-adversarial3 runs1-3:

- fallback case count: `0`
- invalid agent case count: `0`
- negative control leakage count: `0`
- raw unknown relation type count: `0`
- raw unknown relation type surface count: `0`
- wrong verified CURIE link count: `0`
- weak claim trusted leakage count: `0`
- review-only gold trusted leakage count: `0`

Failure attribution after PR33:

- missed gold relations: `none`
- repeated false positives: `none`
- CURIE gaps: `35`, mostly review-only endpoint decisions, missing low-value
  review endpoints, and unverified model hints

## Interpretation

PR33 converts repeated live-agent review noise into code-enforced pruning and
adds bounded agent-only recovery passes for two observed live-path robustness
failures: zero usable candidates and schema-invalid canonical/proposal output.

The trusted lane is ready in the three-run post-adversarial3 batch: no blocking
readiness reasons, trusted precision `1.0000`, trusted valuable rate `1.0000`,
trusted generic relation rate `0.0000`, and hard safety failures all `0`.

The all-candidate lane still shows useful follow-up work. CURIE gaps remain for
review-only or low-value evidence. Those are not trusted auto-promotion blockers
for PR33, but they should continue feeding the next remediation loop.
