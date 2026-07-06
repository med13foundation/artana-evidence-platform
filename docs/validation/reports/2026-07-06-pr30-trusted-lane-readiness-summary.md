# PR30 Trusted-Lane Readiness Accounting Summary

## Run Context

- Branch: `alvaro/evidence-pr30-trusted-lane-readiness`
- Base branch: `alvaro/evidence-pr29-v3-curie-recovery`
- Commit: pending
- Fixture path: `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json`
- Model label: live agent configured by `.env.postgres`

## Goal

Separate trusted graph readiness metrics from review-only and all-candidate
triage metrics so the readiness gate measures auto-promotion safety without
hiding review burden.

## Code Changes

- Added trusted-eligible high-value metrics:
  - `trusted_eligible_high_value_gold_relation_count`
  - `trusted_eligible_high_value_match_count`
  - `trusted_eligible_high_value_recall`
- Added trusted candidate quality metrics:
  - `trusted_candidate_count`
  - `trusted_candidate_supported_count`
  - `trusted_candidate_valuable_count`
  - `trusted_candidate_generic_relation_count`
  - `trusted_candidate_precision_against_gold`
  - `trusted_candidate_valuable_rate`
  - `trusted_candidate_generic_relation_rate`
- Added `review_only_gold_trusted_leakage_count` as a hard failure so a
  candidate matching review-only gold cannot inflate trusted precision/value.
- Centralized the trusted graph candidate predicate so review-only context
  relations such as `DOWNSTREAM_OF` and `UPSTREAM_OF` cannot inflate trusted
  candidate or trusted endpoint metrics.
- Updated single-run verdict warnings and repeatability readiness thresholds to
  use trusted-lane metrics.
- Split markdown reporting into trusted graph readiness, review lane, and
  all-candidate triage sections.
- Kept all-candidate metrics in JSON/Markdown reports for triage visibility.
- Updated model comparison, failure attribution, and adversarial report wording
  to include the new trusted-lane metrics.

## Artifact Hashes

- `reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run5/relation_feasibility_report.json`:
  `01a33534e0265a2a8b50b8878bf15872a8d7c987472b08e652df713704e6b40a`
- `reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run6/relation_feasibility_report.json`:
  `2cfe64b101c885d894342f87740790c059f21e677e4431dc06b9f76582872987`
- `reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run7/relation_feasibility_report.json`:
  `afb11b278d0ce546ffa9c2290ce25ef66f7c289faa26723e0b078d8b5acba7c0`
- `reports/relation_feasibility_readiness/2026-07-06-pr30-trusted-lane-readiness-runs5-7/relation_feasibility_readiness_report.json`:
  `9db75b06aef3e9391443432a9e355ff94309965af9ea4c1121f9208540767ac9`
- `reports/relation_feasibility_failure_analysis/2026-07-06-pr30-trusted-lane-readiness-runs5-7/relation_feasibility_failure_analysis_report.json`:
  `66b3b294722e5de38c1d97970822e39e8fec1dabfc4b67b23f064d66a7cb8167`

## Validation

```bash
uv run pytest tests/unit/test_relation_feasibility_audit.py \
  tests/unit/test_relation_feasibility_readiness_gate.py \
  tests/unit/test_relation_feasibility_model_comparison.py \
  tests/unit/test_relation_feasibility_failure_analysis.py

uv run ruff check \
  scripts/validation/relation_feasibility/adversarial.py \
  scripts/validation/relation_feasibility/endpoint_metrics.py \
  scripts/validation/relation_feasibility/failure_analysis.py \
  scripts/validation/relation_feasibility/models.py \
  scripts/validation/relation_feasibility/readiness.py \
  scripts/validation/relation_feasibility/reporting.py \
  scripts/validation/relation_feasibility/summary_scoring.py \
  scripts/validation/relation_feasibility/model_comparison.py \
  scripts/validation/relation_feasibility/trusted_metric_rules.py \
  tests/unit/test_relation_feasibility_audit.py \
  tests/unit/test_relation_feasibility_readiness_gate.py \
  tests/unit/test_relation_feasibility_model_comparison.py \
  tests/unit/test_relation_feasibility_failure_analysis.py

make relation-feasibility-quality-gate
make service-checks
```

Strict live-agent runs:

```bash
set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run5

set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run6

set -a; source .env.postgres; set +a; \
  PYTHONPATH="$(pwd)/services:$(pwd)" \
  .venv/bin/python3 scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v3.json \
  --output-dir reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run7
```

Aggregate reports:

```bash
.venv/bin/python3 scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run5 \
  --report reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run6 \
  --report reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run7 \
  --min-runs 3 \
  --output-dir reports/relation_feasibility_readiness/2026-07-06-pr30-trusted-lane-readiness-runs5-7

.venv/bin/python3 scripts/summarize_relation_readiness_failures.py \
  --report run5=reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run5 \
  --report run6=reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run6 \
  --report run7=reports/relation_feasibility/2026-07-06-pr30-trusted-lane-readiness-run7 \
  --output-dir reports/relation_feasibility_failure_analysis/2026-07-06-pr30-trusted-lane-readiness-runs5-7
```

## Three-Run Readiness Result

Trusted graph readiness remains **NOT READY**.

Blocking reasons:

- 1 source audit report was RED.
- Worst-run trusted candidate precision is below target.
- Worst-run trusted-eligible CURIE-linked gold endpoint rate is below target.

| Metric | Worst | Mean |
|---|---:|---:|
| Completed-agent precision | 0.8485 | 0.8745 |
| Completed-agent recall | 0.9000 | 0.9222 |
| Trusted candidate precision | 0.7778 | 0.8042 |
| Trusted-eligible high-value recall | 0.8571 | 0.9524 |
| Trusted candidate valuable rate | 0.7778 | 0.8042 |
| Trusted candidate generic relation rate | 0.0000 | 0.0000 |
| Trusted-eligible CURIE endpoint rate | 0.8571 | 0.9524 |
| Entailment checked rate | 1.0000 | 1.0000 |
| All-candidate generic relation rate | 0.2727 | 0.2631 |

Hard safety failures across the three runs:

| Failure | Count |
|---|---:|
| Fallback cases | 0 |
| Invalid strict-agent cases | 0 |
| Negative-control leakage | 0 |
| Raw unknown candidate relation types | 0 |
| Raw unknown relation-type surfaces | 0 |
| Weak-claim trusted leakage | 0 |
| Review-only gold trusted leakage | 0 |
| Wrong verified CURIE links | 0 |

## Interpretation

PR30 fixes the mixed-lane accounting problem. The trusted lane now separates
auto-promotion readiness from review/all-candidate triage burden:

- trusted candidate generic relation rate is stable at `0.0000`
- review-only gold trusted leakage is stable at `0`
- all hard safety failures remain at `0`
- all-candidate generic/valuable rates remain visible but no longer decide
  trusted graph auto-promotion readiness

The system is still not trusted-graph ready. The remaining blockers are real
live-agent repeatability failures:

- run5 missed `Larotrectinib TREATS NTRK fusion solid tumors`, dropping trusted
  high-value recall and trusted endpoint recovery to `0.8571`
- runs6 and 7 dropped trusted precision to `0.7778`
- recurring trusted false positive: `Vemurafenib INHIBITS MAPK signaling`
- additional trusted false positives:
  - `JAK-STAT ACTIVATES macrophages`
  - `KRAS G12D ACTIVATES pancreatic cancer cell proliferation`

## Remaining Work

- Add a precision guard for unsupported pathway/proliferation/context candidates
  that are true in the sentence but not the curated trusted relation.
- Improve repeatability for the Larotrectinib/NTRK tumor-agnostic treatment
  extraction case; the dictionary already contains the required entities.
- Decide whether these extra mechanistic/context candidates should become
  review-only context evidence or be filtered when they are not the benchmark
  relation target.
- Rerun at least three strict live-agent v3 reports and require readiness to
  pass on worst-run trusted candidate precision and trusted endpoint recovery.
- Keep review-only/all-candidate metrics visible as triage burden, but do not
  use them as trusted graph auto-promotion blockers.
