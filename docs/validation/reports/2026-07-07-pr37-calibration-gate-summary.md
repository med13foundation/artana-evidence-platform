# PR37 Calibration Gate Summary

## Run Context

- Branch: `alvaro/evidence-pr37-calibration-gate`
- Base branch: `alvaro/evidence-pr36-v4-live-readiness`
- Fixture path:
  `scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json`
- Model label: live agent configured by `.env.postgres`

## Goal

Turn trusted-lane audit score calibration from an unmeasured
Definition-of-Green item into a repeatable validation gate. The trusted graph
readiness gate now requires the trusted-candidate support-calibration expected
calibration error (ECE) to stay at or below `0.0500`.

## Root Cause

The tracker required calibrated scores, but the relation feasibility reports did
not emit calibration metrics. That meant a readiness report could be GREEN while
still proving nothing about whether the audit quality score aligned with
observed gold support.

The first PR37 implementation had an adversarially found design flaw: it
rebuilt a private "confidence" score from the same flags used to define
`is_valuable`, which made trusted-candidate ECE look perfect by construction.
The post-review fix now uses only pre-gold verification signals for the score
and compares that score against gold support, not against the derived
`is_valuable` label.

The final fix keeps two lanes separate:

- trusted-candidate ECE is a readiness metric for auto-promotion safety;
- all-candidate ECE remains visible as a review-lane support-calibration signal.

This avoids hiding review-lane noise while also avoiding a false blocker from
review-only evidence that is intentionally not trusted graph material.

## Code Changes

- Added `scripts/validation/relation_feasibility/metrics/calibration.py` for
  single-responsibility score calibration accounting.
- Added candidate and trusted-candidate calibration fields to
  `FeasibilitySummary` JSON.
- Rendered calibration metrics in Markdown feasibility reports.
- Printed calibration metrics from `scripts/run_relation_feasibility_audit.py`.
- Added `trusted_candidate_score_ece` and `candidate_score_ece` to readiness
  worst/mean metrics.
- Added `max_trusted_candidate_score_ece = 0.0500` to the readiness threshold
  contract.
- Added calibration sample counts to readiness worst/mean metrics so score
  coverage is visible.
- Added calibration deltas to model-comparison reports.
- Updated model-comparison synthetic report tests so they emit the same required
  metrics as real audit reports.
- Added direct tests for missing and invalid calibration metrics.

## Artifact Hashes

- `reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run1/relation_feasibility_report.json`:
  `5f9324f5e0bf5f4c79a021beb9f32b78d7358767c769deba7a9d873dc843b59f`
- `reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run2/relation_feasibility_report.json`:
  `16d980a128578caddd75112b2d4a2d1f46d5f108af5437d85ac14f773b6c9d5c`
- `reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run3/relation_feasibility_report.json`:
  `c8b353e101826ce14a6e12c36a07a722a07261b5d9659c5eae8792405fa5b8ce`
- `reports/relation_feasibility_readiness/2026-07-07-pr37-calibration-gate-postreview/relation_feasibility_readiness_report.json`:
  `e9946153ec97f8f92cf7ef97558f1f9b812a626b130e8994c9c1c595e04b10d9`

## Validation

RED tests observed:

```bash
uv run pytest \
  tests/unit/test_relation_feasibility_audit.py::test_audit_reports_candidate_score_calibration_error \
  tests/unit/test_relation_feasibility_readiness_gate.py::test_readiness_gate_blocks_poor_trusted_candidate_score_calibration \
  -q
```

Initial result: both tests failed because the audit summary had no calibration
fields and the readiness gate ignored high trusted-candidate ECE.

GREEN focused suite:

```bash
uv run pytest \
  tests/unit/test_relation_feasibility_audit.py \
  tests/unit/test_relation_feasibility_readiness_gate.py \
  -q
```

Result: `72 passed`.

Post-adversarial focused checks:

```bash
uv run pytest \
  tests/unit/test_relation_feasibility_audit.py::test_audit_reports_candidate_score_calibration_error \
  tests/unit/test_relation_feasibility_readiness_gate.py::test_readiness_gate_blocks_poor_trusted_candidate_score_calibration \
  tests/unit/test_relation_feasibility_readiness_gate.py::test_readiness_gate_blocks_missing_or_invalid_required_metrics \
  tests/unit/test_relation_feasibility_model_comparison.py::test_model_comparison_adopts_candidate_when_worst_run_readiness_improves \
  -q
```

Result: passed.

Touched-file Ruff:

```bash
uv run ruff check \
  scripts/validation/relation_feasibility/metrics/calibration.py \
  scripts/validation/relation_feasibility/summary_scoring.py \
  scripts/validation/relation_feasibility/models.py \
  scripts/validation/relation_feasibility/reporting.py \
  scripts/validation/relation_feasibility/readiness.py \
  scripts/validation/relation_feasibility/model_comparison.py \
  scripts/run_relation_feasibility_audit.py \
  tests/unit/test_relation_feasibility_audit.py \
  tests/unit/test_relation_feasibility_readiness_gate.py \
  tests/unit/test_relation_feasibility_model_comparison.py
```

Result: `All checks passed!`

Relation-feasibility quality gate:

```bash
make relation-feasibility-quality-gate
```

Result: passed.

Strict v4 live-agent runs:

```bash
set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json \
  --output-dir reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run1

set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json \
  --output-dir reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run2

set -a; source .env.postgres; set +a; \
  uv run python scripts/run_relation_feasibility_audit.py \
  --extractor agent \
  --cases scripts/validation/relation_feasibility/fixtures/biomedical_relation_goldset_v4.json \
  --output-dir reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run3
```

Readiness aggregate:

```bash
uv run python scripts/run_relation_feasibility_readiness_gate.py \
  --report reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run1 \
  --report reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run2 \
  --report reports/relation_feasibility/2026-07-07-pr37-calibration-gate-postreview-run3 \
  --min-runs 3 \
  --output-dir reports/relation_feasibility_readiness/2026-07-07-pr37-calibration-gate-postreview \
  --fail-on-not-ready
```

Result:

- `relation_feasibility_readiness status=ready`
- runs evaluated: `3 / 3`
- blocking reasons: `0`

## Three-Run Readiness Result

Trusted graph readiness remains **READY** with the new calibration threshold
enabled.

| Metric | Worst | Mean |
|---|---:|---:|
| Trusted candidate score ECE | 0.0000 | 0.0000 |
| Trusted calibration samples | 10.0000 | 10.0000 |
| All-candidate score ECE | 0.0732 | 0.0671 |
| All-candidate calibration samples | 71.0000 | 72.6667 |
| Completed-agent precision | 0.9718 | 0.9770 |
| Completed-agent recall | 0.9200 | 0.9467 |
| Completed-agent valuable rate | 0.5493 | 0.5640 |
| High-value recall | 0.9200 | 0.9600 |
| Trusted candidate precision | 1.0000 | 1.0000 |
| Trusted candidate valuable rate | 1.0000 | 1.0000 |
| Trusted candidate generic rate | 0.0000 | 0.0000 |
| Trusted-eligible high-value recall | 1.0000 | 1.0000 |
| Trusted-eligible CURIE endpoint rate | 1.0000 | 1.0000 |
| Entailment checked rate | 1.0000 | 1.0000 |
| Verified CURIE match rate | 0.7931 | 0.8276 |
| All-candidate generic relation rate | 0.3239 | 0.3166 |

Hard failures across PR37 postreview runs1-3:

- fallback case count: `0`
- invalid agent case count: `0`
- negative-control leakage count: `0`
- raw unknown relation type count: `0`
- raw unknown relation type surface count: `0`
- review-only gold trusted leakage count: `0`
- weak-claim trusted leakage count: `0`
- wrong verified CURIE link count: `0`

Run-level calibration metrics:

| Run | Trusted samples | Trusted ECE | All samples | All-candidate ECE |
|---|---:|---:|---:|---:|
| postreview-run1 | 10 | 0.0000 | 73 | 0.0712 |
| postreview-run2 | 10 | 0.0000 | 74 | 0.0568 |
| postreview-run3 | 10 | 0.0000 | 71 | 0.0732 |

## Interpretation

PR37 closes the previously unmeasured audit support-calibration requirement for
the trusted auto-promotion lane. The readiness gate now fails closed if future
strict live-agent reports omit calibration metrics or if trusted-candidate ECE
exceeds `0.0500`.

This does not prove that every production ranking score or human-review
priority score is calibrated. It proves that the strict relation-feasibility
audit now measures and gates trusted-lane support calibration using pre-gold
verification signals. Production review-queue ranking calibration remains a
separate follow-up.
