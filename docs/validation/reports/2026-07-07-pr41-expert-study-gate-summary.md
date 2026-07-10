# PR41 Expert Study Gate Summary

## Run Context

- Branch: `alvaro/evidence-pr41-expert-study-gate`
- Base branch: `alvaro/evidence-pr40-review-ranking-study-design-gate`
- Scope: Evidence API expert/shadow study validation

## Goal

Make a complete evidence-selection expert/shadow study executable and
fail-closed before it can support production-readiness claims.

## Root Cause

PR38 through PR40 made review-ranking calibration observable, thresholded, and
hard to fake through shallow study design. The remaining process gap was that
selection-review quality and review-ranking calibration were still separate
artifacts. A study could pass one lane while missing the other, and the typed
selection-review input did not preserve reviewer IDs even though the review
template asked reviewers to provide them.

## Code Changes

- Added `reviewer_id` preservation to `EvidenceSelectionReviewInput` and
  `EvidenceSelectionReviewReport`.
- Added JSON-friendly parsing for selection-review `run_id` and record-ID
  arrays so normal study JSON files validate without weakening strict typing.
- Added strict nested selection-review schemas so unknown selection-review fields
  cannot be silently dropped.
- Added `EvidenceSelectionExpertStudyInput` with schema version
  `evidence_selection_expert_study.v1`.
- Added `study_evidence_kind`; production-style gates only pass
  `real_shadow_review`, while synthetic fixtures are blocked.
- Added study-level thresholds and report output for:
  - minimum selection review count;
  - minimum distinct selection goals;
  - minimum selection reviewer count;
  - missing reviewer IDs and missing goals on every selection review;
  - unmeasurable precision and recall;
  - missing explanation-quality scores;
  - mean precision;
  - mean recall;
  - mean explanation quality;
  - zero high-severity overclaims;
  - nested review-ranking calibration gate pass.
- Added per-selection-review JSON audit evidence to the study-gate report.
- Added `scripts/run_evidence_selection_expert_study_gate.py` to emit JSON and
  Markdown study-gate artifacts and exit nonzero on failed gates.
- Updated validation docs and review templates with the full study-bundle shape.

## Validation

RED tests observed:

```bash
uv run pytest services/artana_evidence_api/tests/unit/test_evidence_selection_validation.py -q
```

Initial result: import failure for the missing expert-study gate API.

```bash
uv run pytest tests/unit/test_run_evidence_selection_expert_study_gate.py -q
```

Initial result: import failure for the missing expert-study runner.

Post-runner RED result: normal JSON study files failed because selection-review
UUIDs and record-ID arrays were not accepted from JSON.

Adversarial RED results:

- Synthetic fixtures could pass the production-style gate.
- Partially unlabeled selection reviews could pass through aggregate reviewer
  count.
- Unmeasurable precision/recall and missing explanation scores were excluded
  from averages.
- Extra fields inside selection reviews were silently dropped.
- JSON artifacts omitted per-review reviewer evidence.

GREEN focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_validation.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_review_calibration.py \
  tests/unit/test_run_evidence_selection_review_calibration_gate.py \
  tests/unit/test_run_evidence_selection_expert_study_gate.py \
  -q
```

Result after adversarial fixes: `35 passed`.

Final gates:

```bash
uv run ruff check \
  services/artana_evidence_api/evidence_selection_validation.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_validation.py \
  scripts/run_evidence_selection_expert_study_gate.py \
  tests/unit/test_run_evidence_selection_expert_study_gate.py
```

Result: passed.

```bash
make artana-evidence-api-type-check
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed.

```bash
make service-checks
```

Result: passed with coverage `87.03%` against the `86%` gate.

Final adversarial re-review: PASS after the generated root `uv.lock` artifact
was removed. The reviewer caveat is intentionally non-blocking: the declared
`study_evidence_kind` is provenance metadata, so production use still requires
the study bundle to be populated from the real shadow-review process.

## Interpretation

PR41 still does not claim production readiness. It makes the required
expert/shadow evidence bundle executable and fail-closed: real
production-readiness evidence must now prove selection quality and
review-ranking calibration together, with real-shadow provenance, complete
per-review labels, and reviewer evidence preserved in the emitted artifact.
