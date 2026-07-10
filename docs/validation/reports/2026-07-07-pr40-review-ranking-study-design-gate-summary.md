# PR40 Review-Ranking Study-Design Gate Summary

## Run Context

- Branch: `alvaro/evidence-pr40-review-ranking-study-design-gate`
- Base branch: `alvaro/evidence-pr39-review-ranking-threshold-gate`
- Scope: Evidence API review-ranking calibration study-design coverage

## Goal

Make production review-ranking calibration studies prove expert/shadow coverage
across research goals, evidence shapes, reviewer labels, and adjudication notes.

## Root Cause

PR39 made the review-ranking threshold gate executable and fail-closed for score
quality, but a narrow study with one research question and one evidence shape
could still be treated as a gate input. That would overstate production
readiness because calibration quality from a small homogeneous review set does
not prove that ranking works across the workflows where reviewers will actually
use it.

## Code Changes

- Added `evidence_shape` to review-ranking calibration decisions.
- Added study-level `adjudication_note` to calibration studies while keeping
  v1 study files parseable so missing notes become gate blockers instead of
  schema-version drift.
- Added study-design metrics to gate reports:
  - distinct research goal count;
  - distinct evidence-shape count;
  - reviewer count;
  - missing goal/evidence-shape/reviewer counts;
  - adjudication note presence.
- Made the core helper and runner default to production study-design thresholds:
  - at least three distinct research goals;
  - at least three distinct evidence shapes;
  - reviewer IDs required on every decision;
  - study-level adjudication note required.
- Normalized study labels before counting distinct goals and evidence shapes so
  case, whitespace, and punctuation variants cannot inflate coverage.
- Updated the seed fixture to remain an honest single-goal MED13 mechanics
  fixture that fails production study-design defaults.
- Updated validation docs and reviewer template.

## Validation

RED tests observed:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_review_calibration.py \
  tests/unit/test_run_evidence_selection_review_calibration_gate.py \
  -q
```

Initial result: failures showed missing `evidence_shape`, missing
`study_design` report metrics, and missing `adjudication_note` support.
Post-adversarial RED tests also proved that the core helper could be bypassed
without study metadata, missing reviewer IDs were not blocked by default, blank
adjudication notes counted as present, raw label variants counted as distinct,
the seed could be mistaken for production coverage, and missing adjudication
notes broke schema parsing instead of producing gate blockers.

GREEN focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_review_calibration.py \
  tests/unit/test_run_evidence_selection_review_calibration_gate.py \
  -q
```

Result after post-adversarial fixes: `20 passed`.

Touched-file Ruff:

```bash
uv run ruff check \
  services/artana_evidence_api/evidence_selection_validation.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_review_calibration.py \
  scripts/run_evidence_selection_review_calibration_gate.py \
  tests/unit/test_run_evidence_selection_review_calibration_gate.py
```

Result: `All checks passed!`

Type check:

```bash
make artana-evidence-api-type-check
```

Result: passed.

Evidence API service gate:

```bash
make artana-evidence-api-service-checks
```

Result: passed with `architecture_structure: ok`.

Aggregate service gate:

```bash
make service-checks
```

Result: passed with total coverage `87.03%`.

Production-default seed gate. This is expected to fail because the seed is
single-goal mechanics data:

```bash
uv run python scripts/run_evidence_selection_review_calibration_gate.py \
  --input scripts/validation/evidence_selection/fixtures/review_ranking_shadow_seed_v1.json \
  --max-expected-calibration-error 0.15 \
  --output-dir reports/evidence_selection_review_calibration/2026-07-07-pr40-seed-production-default
```

Result:

```text
evidence_selection_review_calibration status=failed samples=10 ece=0.108 blocking_reasons=2
```

Seed study-design metrics:

| Metric | Value |
|---|---:|
| Distinct goals | 1 |
| Distinct evidence shapes | 1 |
| Reviewer count | 1 |
| Missing goal count | 0 |
| Missing evidence-shape count | 0 |
| Missing reviewer-ID count | 0 |
| Adjudication note present | true |

Mechanics-only seed smoke. This intentionally relaxes study diversity to prove
report rendering and threshold math only:

```bash
uv run python scripts/run_evidence_selection_review_calibration_gate.py \
  --input scripts/validation/evidence_selection/fixtures/review_ranking_shadow_seed_v1.json \
  --max-expected-calibration-error 0.15 \
  --min-distinct-goals 1 \
  --min-distinct-evidence-shapes 1 \
  --output-dir reports/evidence_selection_review_calibration/2026-07-07-pr40-seed-mechanics
```

Result:

```text
evidence_selection_review_calibration status=passed samples=10 ece=0.108 blocking_reasons=0
```

## Interpretation

PR40 does not claim the seed fixture is production-representative. It makes the
production gate reject undercovered calibration studies so real expert/shadow
data must span multiple research questions and evidence shapes before ranking
thresholds can be trusted.
