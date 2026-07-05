# PR21 Verified Grounding And Review-Only Abstention Summary

Date: 2026-07-05

Branch: `alvaro/evidence-pr21-verified-grounding-closure`

Status: implemented locally, adversarial review blockers addressed, strict gate RED

## Goal

Improve verified endpoint recovery and trusted high-value recall without trusting
raw model CURIE hints or broad ontology shortcuts.

## What Changed

- Moved local verified entity curation into
  `document_extraction_support/entity_grounding/`.
- Added verified grounding for safe process/pathway labels:
  `MAPK signaling`, `homologous recombination DNA repair`, and
  `cardiac septal development`.
- Kept broad or composite labels review-only:
  `ERK phosphorylation`, `aggressive tumor growth`, and
  `response to pembrolizumab`.
- Re-verified caller-provided `verified_linker` input so it cannot bypass the
  local dictionary or review-only policy.
- Added relation-safe alias matching that requires a verified CURIE match; it
  does not reuse identity aliases such as `BRCA1 loss -> BRCA1`.
- Added failure-attribution rows for CURIE endpoints lost because a gold
  relation was missed.

## Validation

Focused tests:

```bash
PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 -m pytest \
  services/artana_evidence_api/tests/unit/test_entity_curie_linking.py \
  services/artana_evidence_api/tests/unit/test_verified_entity_dictionary.py \
  tests/unit/test_relation_feasibility_audit.py \
  tests/unit/test_relation_feasibility_failure_analysis.py \
  -q
```

Latest result: 75 passed.

Relation feasibility gate:

```bash
make relation-feasibility-quality-gate
```

Latest result: 56 passed.

Strict live-agent run:

```bash
bash -lc 'set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --output-dir reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run3'
```

Report artifacts:

- `reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_report.json`
- `reports/relation_feasibility/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_report.md`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_failure_analysis_report.json`
- `reports/relation_feasibility_failure_analysis/2026-07-05-pr21-verified-grounding-closure-run3/relation_feasibility_failure_analysis_report.md`

## Live Metrics

| Metric | PR20 run4 | PR21 run3 |
|---|---:|---:|
| Verdict | RED | RED |
| Completed-agent precision | 0.9500 | 1.0000 |
| Completed-agent recall | 0.7600 | 0.8000 |
| Completed-agent valuable rate | 0.9500 | 1.0000 |
| High-value recall | 0.9500 | 1.0000 |
| Trusted high-value recall | 0.5500 | 0.8500 |
| Generic relation rate | 0.0500 | 0.0000 |
| Candidate CURIE present rate | 0.9000 | 0.9250 |
| Verified CURIE-linked endpoint rate | 0.8108 | 0.8810 |
| Wrong verified CURIE links | 0 | 0 |
| Fallback cases | 0 | 0 |
| Invalid strict-agent cases | 0 | 0 |
| Negative-control leakage cases | 0 | 0 |
| CURIE gaps in failure attribution | 8 | 3 |
| False positives | 1 | 0 |

## Adversarial Review

External adversarial review found five issues. Addressed blockers:

- Caller-supplied `verified_linker` could bypass local verification. Fixed by
  rechecking every `verified_linker` input against dictionary/review-only policy
  and downgrading unknown labels to untrusted hints.
- `ERK phosphorylation` was over-broadly linked to `GO:0018108`. Fixed by
  making it review-only.
- Review-only endpoints appeared as `flags=none`. Fixed by adding
  `review_only_subject_grounding` and `review_only_object_grounding` flags.
- CURIE failure attribution underexplained denominator loss. Fixed by adding a
  `CURIE Endpoints Lost To Missed Gold` table.

## Remaining Risk

PR21 is not trusted-graph ready by itself. The strict gate remains RED because
verified CURIE-linked endpoint rate is `0.8810`, below the `0.9500` target.
The remaining gap is now mostly low-value/review-lane work plus review-only
endpoint policy, not raw model-hint verification.
