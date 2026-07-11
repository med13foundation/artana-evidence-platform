# PR51 Shadow Review Batch Suite Gate Summary

Date: 2026-07-07

Branch: `alvaro/evidence-pr51-shadow-review-batch-suite-gate`

## Goal

PR50 made completed shadow-review packets executable as a batch, but the batch
result still over-relied on per-entry pass/fail counts. A single passing packet
could be reported as a passing batch, which is not enough evidence for a
production-readiness claim.

PR51 adds a batch-level production suite gate so a study batch must be
successful, broad, independent, sufficiently sampled, and quality-clean before
`result.passed` is true.

## What Changed

- Added `EvidenceSelectionShadowReviewStudyBatchSuiteThresholds`.
- Added a suite gate with thresholds for:
  - minimum batch entry count,
  - minimum passed-entry count,
  - maximum failed-entry count,
  - minimum passed-entry rate,
  - minimum total selection reviews,
  - minimum total review-ranking decisions,
  - minimum distinct source run IDs,
  - minimum distinct study IDs,
  - minimum distinct selection goals,
  - minimum distinct review-ranking goals,
  - minimum distinct evidence shapes,
  - suite mean precision,
  - suite mean recall,
  - suite mean explanation quality,
  - maximum review-ranking expected calibration error.
- Production floors are non-relaxable. CLI threshold flags can tighten a batch
  gate but cannot lower the production floor.
- Changed batch `passed` semantics to use the suite gate instead of only
  `failed_entry_count == 0`.
- Added suite-gate JSON output under `suite_gate`.
- Added CLI controls for the new `--min-batch-*` thresholds.
- Added Suite Gate rendering to the aggregate Markdown report.
- Kept rounded values for report display while comparing raw quality values for
  blocking decisions.

## Test Evidence

RED tests:

- A one-entry batch with a passing per-entry expert-study gate was incorrectly
  reported as passing.
- The CLI rejected the new `--min-batch-*` threshold controls.
- Failed entries could contribute diversity to a passing suite.
- Punctuation-only variants such as `drug_resistance`, `drug-resistance`, and
  `drug resistance` could spoof distinct evidence shapes.
- Rounded pass rates and rounded quality metrics could pass values that were
  below the raw production floor.
- Three cloned packets with the same underlying source run could count as three
  independent entries.
- Three distinct but thin entries could pass with only six total ranking
  decisions.
- Relaxed per-entry quality thresholds could turn low-precision, low-recall,
  low-explanation entries into a top-level passing batch.

GREEN tests run:

```bash
uv run --python python3.13 --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py -q
```

Result: `14 passed` during the first suite-gate pass; final focused batch/CLI
coverage below includes all adversarial regressions.

```bash
uv run --python python3.13 --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py -q
```

Result: included in the final focused batch/CLI command below.

```bash
uv run --python python3.13 --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py -q
```

Result: `22 passed`

```bash
uv run --python python3.13 --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_source_export_writer.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_source_export_writer_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_validation.py \
  tests/unit/test_run_evidence_selection_expert_study_gate.py \
  tests/unit/test_ci_service_check_planner.py \
  tests/unit/test_makefile_type_gate_contract.py -q
```

Result: `160 passed`

```bash
uv run --python python3.13 --with ruff ruff check \
  services/artana_evidence_api/evidence_selection/shadow_review_study_batch.py \
  scripts/build_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py
```

Result: `All checks passed!`

```bash
make artana-evidence-api-type-check
```

Result: success across the Evidence API package and evidence-selection scripts.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Static gates, boundary/contract checks, architecture checks,
and the isolated Postgres pytest suite completed successfully.

## Adversarial Review

Independent adversarial review repeatedly found real overclaim paths. PR51 fixed
all production-overclaim blockers found:

- relaxed CLI suite thresholds,
- failed-entry diversity padding,
- punctuation-spoofed labels,
- rounded pass-rate comparison,
- cloned source-run evidence,
- relaxed per-entry sample floors,
- relaxed per-entry quality floors,
- rounded quality-floor comparison.

Final adversarial verdict: PASS on production-overclaim correctness.

## Safety Invariant

A completed shadow-review batch cannot support production study evidence merely
because every entry passed locally. It must also prove minimum sample size,
successful entry rate, independent source/study identity, cross-batch diversity,
and aggregate quality using raw comparison values.

## Remaining Risk

- `--allow-failed-gate` still intentionally permits diagnostic exit success
  after reports are written; operators must read the report status when using
  that flag.
- Markdown could expose `requested_thresholds` and `production_floor_applied`
  more prominently as a follow-up usability improvement. JSON already carries
  those fields.
