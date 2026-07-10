# PR38 Review-Ranking Calibration Summary

## Run Context

- Branch: `alvaro/evidence-pr38-review-ranking-calibration`
- Base branch: `alvaro/evidence-pr37-calibration-gate`
- Scope: Evidence API review-ranking telemetry

## Goal

Make production review-ranking calibration measurable from actual human review
decisions instead of leaving it as a prose-only follow-up from PR37.

## Root Cause

PR37 made strict relation-feasibility support calibration measurable for the
trusted auto-promotion lane, but the production review queue still lacked a way
to compare `ranking_score` against real reviewer outcomes. That meant future
evidence-selection runs could see prior review decisions without knowing whether
the ranking score had historically over- or under-predicted useful work.

## Code Changes

- Added `ReviewRankingCalibrationObservation` and
  `ReviewRankingCalibrationSummary` to `services/artana_evidence_api/ranking.py`.
- Added `build_review_ranking_calibration_summary(...)` to compute mean score,
  observed positive rate, and expected calibration error over decided review
  outcomes.
- Added review-ranking calibration telemetry to evidence-selection workspace
  snapshots.
- Mapped promoted proposals and resolved review items to positive outcomes.
- Mapped rejected proposals and dismissed review items to negative outcomes.
- Ignored pending proposals and review items so calibration only reflects real
  decisions.
- Computed calibration from status-filtered decided-outcome queries instead of
  the capped display lists used for snapshot previews.

## Validation

RED tests observed:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_ranking.py::test_review_ranking_calibration_summary_uses_decided_review_outcomes \
  services/artana_evidence_api/tests/unit/test_evidence_selection_artifact_modules.py::test_workspace_snapshot_captures_prior_state_and_dedup_keys \
  -q
```

Initial result: import failure for the missing calibration observation type,
proving the behavior was absent.

GREEN focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_ranking.py::test_review_ranking_calibration_summary_uses_decided_review_outcomes \
  services/artana_evidence_api/tests/unit/test_evidence_selection_artifact_modules.py::test_workspace_snapshot_captures_prior_state_and_dedup_keys \
  -q
```

Result: `2 passed`.

Expanded focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_ranking.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_artifact_modules.py \
  -q
```

Result: `8 passed`.

Touched-file Ruff:

```bash
uv run ruff check \
  services/artana_evidence_api/ranking.py \
  services/artana_evidence_api/evidence_selection_workspace_snapshot.py \
  services/artana_evidence_api/tests/unit/test_ranking.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_artifact_modules.py
```

Result: `All checks passed!`

Adversarial review:

- Initial review returned BLOCK because calibration was computed after the
  workspace snapshot's display cap and the test suite did not prove resolved
  review items counted as positive outcomes.
- Fixed by querying decided proposals/review items separately from capped
  display lists and by adding regression coverage for resolved review items plus
  a promoted proposal outside the display cap.

## Interpretation

Production review-ranking calibration is now observable whenever prior human
review decisions exist in the workspace. This does not yet set a merge-blocking
production ECE threshold, because that threshold should come from a larger
expert or shadow-mode review set. The important change is that the system now
captures the measurement needed to tune and govern that threshold.
