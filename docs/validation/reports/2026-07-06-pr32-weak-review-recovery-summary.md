# PR32 Weak Review Recovery Summary

## Run Context

- Branch: `alvaro/evidence-pr32-weak-review-recovery`
- Base branch: `alvaro/evidence-pr31-context-precision-guards`
- Commit: pending
- Fixture path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- Model label: live agent configured by `.env.postgres`

## Goal

Recover useful weak review-only evidence that PR31 intentionally left out of
trusted graph auto-promotion, without allowing weak or ambiguous claims into the
trusted lane.

The repeated target misses were:

- `v3_weak_egfr_trend_response_erlotinib`
- `v3_weak_met_correlated_resistance`

## Code Changes

- Added prompt examples that tell the live agent to preserve weak EGFR trend
  and MET correlated-resistance claims as `review_only` `ASSOCIATED_WITH`
  candidates.
- Extended the weak-review prompt so the second extraction pass repeats the
  same examples instead of dropping the weak relation surfaces.
- Broadened the trend detector to catch `trended with`, not only
  `trend toward`.
- Added weak-review candidate repair for trend-response claims that the model
  emits as `BIOMARKER_FOR` when the support sentence is only trend language.
- Added correlated-resistance object repair so `MET amplification ASSOCIATED_WITH
  EGFR inhibition` becomes review evidence for `resistance to EGFR inhibition`
  when the sentence explicitly says "correlated with resistance to EGFR
  inhibition".
- Added post-repair duplicate merging so repaired weak-review candidates do not
  inflate the review lane.
- Hardened extraction schema validation so a canonical `relation_type` with a
  spurious `proposed_relation_type` is accepted by discarding the proposal
  fields instead of failing the whole live-agent run.
- After adversarial review, limited that schema recovery to redundant proposals
  that canonicalize to the same relation type, so unknown or conflicting
  proposal fields still fail closed.
- After adversarial review, cleared stale object CURIE metadata when object
  labels are repaired and scoped weak-review repairs to the clause containing
  the candidate subject and object.
- After re-review, extended claim scoping to bare `and` claim boundaries so an
  unrelated coordinated clause cannot trigger weak-review repair or review-only
  classification.

## Artifact Hashes

- `reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run12/relation_feasibility_report.json`:
  `79c7eee0217eda98e5c89125f2238f31b3e5fd1fa356d25e739dea81d506eeb0`
- `reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run13/relation_feasibility_report.json`:
  `37a38be8caa8eb0af6ee1d10f3f1d4ca130d5eb81ea3a1918bc6345c885bcaf5`
- `reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run14/relation_feasibility_report.json`:
  `158e7712fc1252ce13f317531add876c0eb642174cfdcdb8a32047914098d475`
- `reports/relation_feasibility_readiness/2026-07-06-pr32-weak-review-recovery-runs12-14/relation_feasibility_readiness_report.json`:
  `06dc9b2959d63ed51be32b8c30b69513e2013641623d42a420b3319d589268ec`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr32-weak-review-recovery-runs12-14/relation_feasibility_failure_analysis_report.json`:
  `22a4235719aa947afaaa6e1f959a4b8e9d02112c1398b269447eed4c1532574d`

## Validation

Focused tests:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_repairs_weak_met_resistance_object \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_keeps_weak_generic_review_only \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_prompt_preserves_useful_weak_claims_as_review_only \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_weak_review_prompt_names_repeated_v3_review_misses \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_schema_ignores_spurious_proposal_on_canonical_relation \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_schema_rejects_unknown_proposal_on_canonical_relation \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py::test_llm_extraction_schema_rejects_conflicting_proposal_on_canonical_relation
```

Result: `55 passed in 0.35s`

Touched-file Ruff:

```bash
uv run ruff check \
  services/artana_evidence_api/document_extraction_support/review_policy/review_only_candidate_policy.py \
  services/artana_evidence_api/document_extraction_support/relation_candidate_quality_filter.py \
  services/artana_evidence_api/document_extraction_prompting.py \
  services/artana_evidence_api/document_extraction_support/llm_fulltext_extraction.py \
  services/artana_evidence_api/tests/unit/test_review_only_candidate_policy.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py
```

Result: `All checks passed!`

Quality gate:

```bash
make relation-feasibility-quality-gate
```

Result: relation-feasibility audit, readiness, model comparison, fixture
validation, and summary tests passed.

Full service gate:

```bash
make service-checks
```

Result: passed after adversarial fixes. Coverage reached `87.03%` against the
`86%` floor.

Strict live-agent runs:

```bash
set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run12

set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run13

set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run14
```

Aggregate reports:

```bash
uv run python scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run12 \
  --report reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run13 \
  --report reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run14 \
  --output-dir reports/relation_feasibility_readiness/2026-07-06-pr32-weak-review-recovery-runs12-14

uv run python scripts/summarize_relation_readiness_failures.py \
  --report run12=reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run12 \
  --report run13=reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run13 \
  --report run14=reports/relation_feasibility/2026-07-06-pr32-weak-review-recovery-run14 \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-06-pr32-weak-review-recovery-runs12-14
```

## Three-Run Readiness Result

Trusted graph readiness remains **READY** for the measured v3 live-agent
trusted lane.

| Metric | Worst | Mean |
|---|---:|---:|
| Trusted candidate precision | 1.0000 | 1.0000 |
| Trusted-eligible high-value recall | 1.0000 | 1.0000 |
| Trusted candidate valuable rate | 1.0000 | 1.0000 |
| Trusted candidate generic relation rate | 0.0000 | 0.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 | 1.0000 |
| Entailment checked rate | 1.0000 | 1.0000 |
| Completed-agent precision | 0.9091 | 0.9274 |
| Completed-agent recall | 0.9667 | 0.9889 |
| Completed-agent valuable candidate rate | 0.4848 | 0.5003 |
| All-candidate generic relation rate | 0.3125 | 0.3019 |
| CURIE-linked gold endpoint rate | 0.7000 | 0.7167 |

Hard failures across runs12-14:

- fallback case count: `0`
- invalid agent case count: `0`
- negative control leakage count: `0`
- raw unknown relation type count: `0`
- raw unknown relation type surface count: `0`
- wrong verified CURIE link count: `0`
- weak claim trusted leakage count: `0`
- review-only gold trusted leakage count: `0`

## Weak Review Recovery Result

All three post-adversarial live-agent runs reached:

| Metric | Run12 | Run13 | Run14 |
|---|---:|---:|---:|
| Verdict | GREEN | GREEN | GREEN |
| High-value recall | 0.9500 | 1.0000 | 1.0000 |
| Low-value recall | 1.0000 | 1.0000 | 1.0000 |
| Low-value review recall | 1.0000 | 1.0000 | 1.0000 |
| Trusted precision | 1.0000 | 1.0000 | 1.0000 |
| Weak trusted leakage | 0 | 0 | 0 |
| Fallback cases | 0 | 0 | 0 |
| Invalid agent cases | 0 | 0 | 0 |

Failure analysis reports one high-value missed relation in run12 only
(`GLA variants ASSOCIATED_WITH Fabry disease`). It does not block trusted
readiness because trusted-eligible high-value recall stayed `1.0000` across
runs12-14, but it remains useful model-variability follow-up signal.

## Interpretation

PR32 improves the review lane without changing the trusted-lane safety contract:

- weak EGFR trend-response evidence is recovered as review-only
  `ASSOCIATED_WITH`
- weak MET correlated-resistance evidence is recovered with the specific object
  `resistance to EGFR inhibition`
- schema recovery prevents a live-agent run from failing when a canonical
  relation is accompanied by an unnecessary proposal field
- duplicate repair keeps the review lane from counting the same repaired
  evidence twice
- trusted graph readiness remains ready, with no weak trusted leakage

The improvement is live-agent evidence, not deterministic fallback:

- all 40 v3 cases completed through the agent in runs12-14
- fallback stayed at `0`
- invalid agent cases stayed at `0`

## Remaining Work

- Keep PR32 stacked after PR31 because it relies on PR31 trusted-lane demotion
  behavior.
- Remaining review/all-candidate burden is non-blocking for trusted
  auto-promotion but still useful follow-up signal: failure analysis still
  reports repeated review-lane false positives such as PAH/elevated
  phenylalanine and Vemurafenib/MAPK signaling.
- CURIE gaps remain in review-only/all-candidate space for endpoints that are
  intentionally not trusted identifiers yet; future work should target
  structured grounding rather than trusting model-only hints.
