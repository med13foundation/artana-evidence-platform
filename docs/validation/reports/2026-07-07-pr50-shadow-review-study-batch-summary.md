# PR50 Shadow-Review Study Batch Summary

## Purpose

PR50 turns the PR49 one-packet shadow-review study pipeline into a manifest-driven
batch loop. This matters because trusted-graph readiness cannot be argued from a
single completed reviewer packet. The system needs repeated packets, preserved
per-packet gate reports, and an aggregate pass/fail summary that makes scale
visible.

## Scope

Branch:

```text
alvaro/evidence-pr50-shadow-review-study-batch
```

Stack base:

```text
alvaro/evidence-pr49-shadow-review-pipeline-gate
```

Added:

- `artana_evidence_api.evidence_selection.shadow_review_study_batch`
- `scripts/build_evidence_selection_shadow_review_study_batch.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py`
- `services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py`

Updated:

- `services/artana_evidence_api/evidence_selection/shadow_review_study_pipeline.py`
- `scripts/ci/plan_service_checks.py`
- `Makefile`
- `tests/unit/test_ci_service_check_planner.py`
- `tests/unit/test_makefile_type_gate_contract.py`
- `docs/validation/evidence-excellence-progress-tracker.md`

## Behavior Added

- Strict `evidence_selection_shadow_review_study_batch.v1` manifest validation.
- Duplicate `entry_id`, `output_subdir`, and `export_id` rejection.
- Relative-only batch output subdirectories.
- Per-entry execution through the PR49 artifact pipeline.
- Per-entry expert/shadow study gate evaluation.
- Per-entry gate JSON/Markdown report preservation.
- Aggregate batch JSON/Markdown report writing.
- Nonzero CLI exit by default when any entry gate fails.
- `--allow-failed-gate` for report-generation workflows that intentionally
  collect failed packet evidence.
- Manifest and packet collision protection for both per-entry artifacts and
  batch reports.
- CI planner and Makefile wiring so script-only changes run Evidence API gates.

## TDD Evidence

RED command:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_study_batch_script_pr_runs_evidence_api_gate \
  tests/unit/test_makefile_type_gate_contract.py::test_evidence_api_gates_cover_shadow_review_study_batch_cli_script
```

Initial RED result:

```text
9 failed
```

Expected missing surfaces:

- Missing batch module.
- Missing batch CLI.
- Missing CI planner script classification.
- Missing Makefile lint/type-check coverage.

GREEN command:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_study_batch_script_pr_runs_evidence_api_gate \
  tests/unit/test_makefile_type_gate_contract.py::test_evidence_api_gates_cover_shadow_review_study_batch_cli_script
```

GREEN result:

```text
9 passed
```

## Adversarial Review

Initial adversarial review status:

```text
BLOCK
```

Blocking finding:

```text
Cross-entry source packet overwrite was possible because only the current entry
packet and the manifest path were protected during per-entry artifact writes.
Aggregate report writes also protected the manifest only, so a report path could
overwrite a packet path after that packet had been read.
```

Fix:

- Compute one protected source-path set from the manifest path plus every entry
  packet path.
- Resolve relative packet paths against the manifest directory when a manifest
  path is available.
- Validate every fixed per-entry artifact path against that whole protected set
  before any artifact write.
- Pass the whole protected set into each PR49 single-packet pipeline call.
- Validate aggregate batch report and per-entry gate-report paths against the
  same protected set before report writes.
- Add regressions for cross-entry packet/artifact collision and packet/report
  collision.
- Add explicit regressions for duplicate `output_subdir` and duplicate
  `export_id`.

Post-fix focused PR50 command:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_study_batch_script_pr_runs_evidence_api_gate \
  tests/unit/test_makefile_type_gate_contract.py::test_evidence_api_gates_cover_shadow_review_study_batch_cli_script
```

Post-fix focused PR50 result:

```text
13 passed
```

## Validation So Far

Focused/adjacent workflow suite:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py \
  tests/unit/test_run_evidence_selection_expert_study_gate.py \
  tests/unit/test_ci_service_check_planner.py \
  tests/unit/test_makefile_type_gate_contract.py
```

Result:

```text
63 passed
```

Touched-file Ruff:

```bash
uv run ruff check \
  services/artana_evidence_api/evidence_selection/shadow_review_study_batch.py \
  services/artana_evidence_api/evidence_selection/shadow_review_study_pipeline.py \
  scripts/build_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py \
  tests/unit/test_ci_service_check_planner.py \
  tests/unit/test_makefile_type_gate_contract.py
```

Result:

```text
All checks passed!
```

Type gate:

```bash
make artana-evidence-api-type-check
```

Result:

```text
Success: no issues found in 492 source files
Success: no issues found in 1 source file
Success: no issues found in 1 source file
Success: no issues found in 1 source file
Success: no issues found in 1 source file
Success: no issues found in 1 source file
Success: no issues found in 1 source file
```

Evidence API service gate:

```bash
make artana-evidence-api-service-checks
```

Result:

```text
passed
```

Notes:

- OpenAPI check passed.
- Architecture checks passed.
- Ephemeral PostgreSQL migration/test database was created and dropped.
- Live external/API endpoint suites were skipped because their service/runtime
  preconditions were not enabled in this gate.

Full aggregate service gate:

```bash
make service-checks
```

Result:

```text
passed; total coverage 87.03%
```

Note: this full aggregate gate was run before the adversarial overwrite fix.
Post-fix aggregate gates are rerun before PR50 closeout.

Post-fix Evidence API service gate:

```bash
make artana-evidence-api-service-checks
```

Result:

```text
passed
```

Post-fix full aggregate service gate:

```bash
make service-checks
```

Result:

```text
passed; total coverage 87.03%
```

Adversarial re-review:

```text
PASS
```

Reviewer confirmation:

```text
The previous overwrite BLOCK is closed. The old cross-entry overwrite repro now
raises ValueError and leaves the source packet unchanged.
```

## Pending Before PR50 Is Done

- Commit, push, and open the stacked draft PR.
