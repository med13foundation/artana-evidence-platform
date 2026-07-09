# PR20 Qualifier Preservation And Precision Summary

Date: 2026-07-05

Branch: `alvaro/evidence-pr20-qualifier-precision-adjudication`

Base: `alvaro/evidence-pr19-high-value-relation-recovery` at `726ec5b`

Status: implemented locally, adversarial review issues addressed, strict gate RED

## Goal

Prevent relation evidence from becoming over-broad while preserving high-value
live-agent recall.

## What Changed

- Added quality-filter protection against dropped biomedical modifiers.
- Filtered `BRCA1 SENSITIZES_TO cisplatin` when the evidence sentence says
  `BRCA1 loss`.
- Preserved `BRCA1 loss SENSITIZES_TO cisplatin` when the modifier is present
  in the extracted subject.
- Added sibling-aware filtering for context relations such as
  `ERK phosphorylation DOWNSTREAM_OF MEK` when a direct mechanism candidate in
  the same sentence already captures the valuable claim.
- Added audit summary fields for trusted high-value recall and low-value review
  accounting.

## Validation

Focused PR20 tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_relation_candidate_quality_filter.py \
  services/artana_evidence_api/tests/unit/test_evidence_grounding.py \
  services/artana_evidence_api/tests/unit/test_document_extraction_modules.py \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_extract_relation_candidates_with_llm_prunes_redundant_generic_siblings \
  services/artana_evidence_api/tests/unit/test_document_extraction.py::test_discover_relation_candidates_reports_llm_pruned_generic_siblings \
  services/artana_evidence_api/tests/unit/test_evidence_support_verifier.py \
  tests/unit/test_relation_feasibility_audit.py \
  -q
```

Latest result after adversarial-review fixes: 151 passed.

Relation-feasibility gate:

```bash
make relation-feasibility-quality-gate
```

Latest result after adversarial-review fixes: 53 passed.

Strict live-agent run:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4'
```

Report artifacts:

- `reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr20-qualifier-precision-run4/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr20-run4/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr20-run4/relation_feasibility_failure_analysis_report.md`

## Live Metrics

| Metric | Value |
|---|---:|
| Verdict | RED |
| Agent completed cases | 30 |
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Negative-control leakage cases | 0 |
| Completed-agent precision | 0.9500 |
| Completed-agent recall | 0.7600 |
| Completed-agent valuable rate | 0.9500 |
| High-value recall | 0.9500 |
| Trusted high-value recall | 0.5500 |
| Low-value recall | 0.0000 |
| Low-value review candidates | 0 |
| Generic relation rate | 0.0500 |
| Pruned generic relation siblings | 4 |
| Quality-filtered candidates | 7 |
| Candidate CURIE present rate | 0.9000 |
| Verified CURIE match rate | 0.8108 |
| Verified CURIE-linked gold endpoint rate | 0.8108 |
| Raw unknown relation types | 0 |
| Raw unknown relation inventory surfaces | 0 |
| Model CURIE wrong count | 0 |
| Wrong verified CURIE links | 0 |

## Finding Status

Closed or materially improved in PR20:

- F-02: the broad `BRCA1` subject substitution is blocked when the source says
  `BRCA1 loss`.
- F-03: the `ERK phosphorylation DOWNSTREAM_OF MEK` context relation is no
  longer counted as a trusted candidate when the direct `Trametinib INHIBITS
  ERK phosphorylation` relation is present.
- F-04: low-value review accounting is explicit in the audit summary and
  Markdown report.
- Adversarial P1/P2 follow-up: common modifier detection now covers deletion,
  depletion, knockdown, knockout, overexpression, deficiency, and silencing;
  `trusted_high_value_recall` now requires completed-agent provenance and
  verified gold endpoints; low-value review metrics now require governed
  review-only proposals; context shadowing preserves separate pathway claims.
- Adversarial re-review follow-up: modifier detection is now claim-clause scoped
  so valid unmodified claims in separate clauses are preserved, and context
  relation types are review-only for trusted high-value recall.
- Final re-review follow-up: comma-and coordinated claims are also scoped as
  separate clauses, and the external reviewer found no remaining PR20 blocker.

Remaining blockers:

- Trusted graph readiness remains RED because verified CURIE-linked gold
  endpoint rate is `0.8108`, below the `0.9500` target.
- Trusted high-value recall is `0.5500` under the stricter verified-endpoint
  definition, which confirms that PR18/PR21 must finish before trusted
  promotion can be enabled.
- Current PR20 live run intentionally does not recover the five low-value
  hedged relations as trusted evidence.
- Run3 reached precision `1.0000`, high-value recall `1.0000`, trusted
  high-value recall `0.6000`, and verified endpoint rate `0.8649`; run4
  regressed to the latest values above, so repeatability and model A/B remain
  PR21/PR24 work.
- Runtime graph promotion hard gates remain PR22 work.

## Validity Assessment

This run is valid for PR20 because it exercised the strict live-agent path and
all hard safety gates stayed clean: fallback 0, invalid-agent 0,
negative-control leakage 0, raw unknown relation surfaces 0, model CURIE wrong
count 0, and wrong verified CURIE links 0.

It is not sufficient to declare trusted graph readiness. PR20 fixes precision
and qualifier preservation, but the broader system still needs the verified
entity grounding, repeatability, and graph-promotion enforcement lanes.
