# PR19 High-Value Relation Recovery Summary

Date: 2026-07-05

Branch: `alvaro/evidence-pr19-high-value-relation-recovery`

Status: implemented locally, validation in progress

## Goal

Recover high-value resistance relations without letting unapproved proposal
surfaces count as trusted graph evidence.

## Governance Decision

PR19 approves `CONFERS_RESISTANCE_TO` as a canonical relation type. This is the
right first-principles path because the benchmark contains repeated, specific,
high-value drug-resistance claims that are not merely generic causation:

- `MET amplification CONFERS_RESISTANCE_TO erlotinib`
- `EGFR T790M CONFERS_RESISTANCE_TO gefitinib`

Governed proposals remain review-only, but resistance evidence no longer has to
travel through `PROPOSE_NEW_RELATION_TYPE` when the source sentence directly
states drug resistance.

## What Changed

- Added `CONFERS_RESISTANCE_TO` to the Evidence API extraction taxonomy and
  prompt guidance.
- Added graph dictionary seed data for `CONFERS_RESISTANCE_TO`.
- Added graph constraints for `VARIANT -> CONFERS_RESISTANCE_TO -> DRUG` and
  `GENE -> CONFERS_RESISTANCE_TO -> DRUG`.
- Added relation synonyms for safe resistance-specific surfaces such as
  `CAUSES_RESISTANCE_TO` and `RENDERS_RESISTANT_TO`.
- Added support-verifier cues for direct resistance wording.
- Added review-surface typo repair for `CONFOERS_RESISTANCE_TO` so it becomes
  a review-required `CONFERS_RESISTANCE_TO` proposal instead of raw unknown
  noise; it does not become trusted canonical evidence.
- Updated the v2 benchmark representation so `EGFR T790M causes resistance to
  gefitinib` is measured as `EGFR T790M CONFERS_RESISTANCE_TO gefitinib`.
- Repaired proposal tests so proposal accounting uses a genuinely unapproved
  relation type instead of the now-canonical resistance relation.

## Validation

Focused tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_keeps_structured_new_type_proposals \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_filters_review_required_raw_types \
  services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  tests/unit/test_relation_feasibility_audit.py \
  services/artana_evidence_db/tests/unit/test_governance.py::test_graph_governance_repository_seeds_builtin_entity_and_relation_types \
  services/artana_evidence_db/tests/unit/test_app.py::test_seed_builtin_dictionary_entries_persists_core_relation_constraints \
  -q
```

Result: 139 passed.

Relation-feasibility gate:

```bash
make relation-feasibility-quality-gate
```

Result: 50 passed.

Strict live-agent run:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr19-high-value-relation-recovery-run2'
```

Report artifacts:

- `reports/relation_feasibility/2026-07-05-pr19-high-value-relation-recovery-run2/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr19-high-value-relation-recovery-run2/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr19-run2/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr19-run2/relation_feasibility_failure_analysis_report.md`

## Live Metrics

| Metric | Value |
|---|---:|
| Verdict | RED |
| Agent completed cases | 30 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Negative-control leakage cases | 0 |
| Completed-agent precision | 0.9048 |
| Completed-agent recall | 0.7600 |
| High-value recall | 0.9500 |
| Completed-agent valuable rate | 0.9048 |
| Generic relation rate | 0.0000 |
| Raw unknown relation types | 0 |
| Raw unknown relation inventory surfaces | 0 |
| Governed proposal candidates | 0 |
| Candidate CURIE present rate | 0.9048 |
| Verified CURIE match rate | 0.8108 |
| Verified CURIE-linked gold endpoint rate | 0.8108 |
| Model CURIE wrong count | 0 |
| Wrong verified CURIE links | 0 |

## Finding Status

Closed or materially improved in PR19:

- M-01 and M-02: MET resistance is represented by canonical
  `CONFERS_RESISTANCE_TO`.
- M-03: EGFR T790M drug resistance now uses the same canonical
  `CONFERS_RESISTANCE_TO` shape.
- FP-01, FP-02, and FP-06: useful resistance evidence no longer has to appear
  as a governed proposal.
- Raw unknown relation surfaces remain at zero.

Remaining blockers:

- Trusted graph readiness remains RED because verified CURIE-linked gold
  endpoint rate is `0.8108`, below the `0.9500` target.
- The one remaining high-value miss in this run is
  `BRCA1 loss SENSITIZES_TO cisplatin`; the extracted subject was shortened to
  `BRCA1`. That is a qualifier-preservation and precision/reranking issue for
  PR20.
- Low-value hedged relations remain intentionally unrecovered by trusted
  extraction and need review-only accounting in PR20.
- PR19 is a single live run; repeatability and model A/B remain PR21 work.

## Validity Assessment

This run is valid for PR19 because it exercised the strict live-agent path and
all hard safety gates stayed clean: fallback 0, invalid-agent 0,
negative-control leakage 0, raw unknown relation surfaces 0, model CURIE wrong
count 0, and wrong verified CURIE links 0.

It is not sufficient to declare trusted graph readiness. PR19 solves the
resistance relation-shape problem, but the broader system still needs PR18,
PR20, PR21, and PR22 merged together and passing worst-run readiness gates.
