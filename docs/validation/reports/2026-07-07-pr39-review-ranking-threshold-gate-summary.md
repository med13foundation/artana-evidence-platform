# PR39 Review-Ranking Threshold Gate Summary

## Run Context

- Branch: `alvaro/evidence-pr39-review-ranking-threshold-gate`
- Base branch: `alvaro/evidence-pr38-review-ranking-calibration`
- Scope: Evidence API review-ranking calibration gate and executable seed fixture

## Goal

Make expert/shadow-mode review-ranking thresholding executable instead of
leaving it as a prose-only follow-up from PR38.

## Root Cause

PR38 made production review-ranking calibration observable from decided
workspace outcomes, but there was still no reusable gate for deciding whether an
expert or shadow-mode review set was large enough, balanced enough, source
complete enough, duplicate-free, and calibrated enough to support a threshold.
Without that gate, a future team could over-interpret a tiny or one-sided review
set as evidence that ranking is production ready.

## Code Changes

- Added review-ranking calibration gate helpers to
  `artana_evidence_api.evidence_selection_validation` with typed expert/shadow
  decisions, thresholds, gate reports, and fail-closed blocking reasons.
- Added `scripts/run_evidence_selection_review_calibration_gate.py` to load
  review-ranking decision JSON, evaluate the gate, and write JSON/Markdown
  artifacts.
- Added the seed fixture
  `scripts/validation/evidence_selection/fixtures/review_ranking_shadow_seed_v1.json`.
- Updated evidence-selection validation docs and reviewer template with the
  calibration label format and runner command.

## Gate Semantics

The gate fails closed unless all of these are true:

- sample count is at or above the configured minimum;
- both positive and negative reviewer outcomes are present;
- both proposal and review-item source decisions are present;
- no duplicate source/item decision keys are present;
- review-ranking expected calibration error is at or below the configured
  threshold;
- scores discriminate positive outcomes from negative outcomes with ROC AUC and
  positive-vs-negative mean score separation at or above configured thresholds.

The production default threshold is `0.05` ECE. The seed fixture uses an
explicit relaxed `0.15` threshold only to prove mechanics on a small committed
example; it is not a production readiness claim. The production default also
requires ROC AUC >= `0.70` and mean score separation >= `0.10`.

## Validation

RED tests observed:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_review_calibration.py \
  tests/unit/test_run_evidence_selection_review_calibration_gate.py \
  -q
```

Initial result: collection failed because
the review-ranking calibration helpers and
`scripts.run_evidence_selection_review_calibration_gate` did not exist.

GREEN focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_review_calibration.py \
  tests/unit/test_run_evidence_selection_review_calibration_gate.py \
  -q
```

Result after adversarial fixes: `11 passed`.

Touched-file Ruff:

```bash
uv run ruff check \
  services/artana_evidence_api/evidence_selection_validation.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_review_calibration.py \
  scripts/run_evidence_selection_review_calibration_gate.py \
  tests/unit/test_run_evidence_selection_review_calibration_gate.py
```

Result: `All checks passed!`

Evidence API service gate:

```bash
make artana-evidence-api-service-checks
```

Result: passed. The first run caught an architecture-structure failure because
the initial implementation added a new root `evidence_selection_*` module. The
root-cause fix moved the calibration gate into the existing
`evidence_selection_validation.py` boundary; the rerun passed with
`architecture_structure: ok`.

Aggregate service gate:

```bash
make service-checks
```

Result: passed with total coverage `87.03%`.

Executable seed gate:

```bash
uv run python scripts/run_evidence_selection_review_calibration_gate.py \
  --input scripts/validation/evidence_selection/fixtures/review_ranking_shadow_seed_v1.json \
  --max-expected-calibration-error 0.15 \
  --output-dir reports/evidence_selection_review_calibration/2026-07-07-pr39-seed \
  --fail-on-not-ready
```

Result:

```text
evidence_selection_review_calibration status=passed samples=10 ece=0.108 blocking_reasons=0
```

The same seed fixture fails under the production default `0.05` ECE threshold,
as expected.

Seed metrics:

| Metric | Value |
|---|---:|
| Sample count | 10 |
| Proposal decisions | 5 |
| Review-item decisions | 5 |
| Positive outcomes | 7 |
| Negative outcomes | 3 |
| Mean score | 0.642 |
| Observed positive rate | 0.700 |
| Expected calibration error | 0.108 |
| Max allowed ECE | 0.150 |
| ROC AUC | 1.000 |
| Mean positive score | 0.881429 |
| Mean negative score | 0.083333 |
| Mean score separation | 0.798096 |
| Blocking reasons | 0 |

## Interpretation

This PR makes review-ranking thresholding executable and fail-closed. The seed
fixture proves the mechanics and committed data format, but it is not
production-representative evidence. Production readiness still requires real
expert/shadow-mode decisions collected across multiple research questions and
evidence shapes.

## Adversarial Review

Initial adversarial review returned BLOCK because the runner exited `0` on a
failed gate unless `--fail-on-not-ready` was provided, and because the default
ECE threshold was looser than the tracker target. PR39 fixed both blockers:
failed gates now exit nonzero by default, and the production default
`max_expected_calibration_error` is `0.05`.

Second adversarial review returned BLOCK because an ECE-only gate could pass a
constant base-rate score distribution and because the runner accepted missing or
wrong study schema versions. PR39 fixed both blockers: the gate now requires ROC
AUC and positive-vs-negative mean score separation, and the runner validates a
strict `evidence_selection_review_ranking_calibration.v1` study envelope with
extra fields forbidden.
