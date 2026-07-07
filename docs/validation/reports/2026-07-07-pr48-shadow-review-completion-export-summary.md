# PR48 Shadow Review Completion Export Summary

## Run Context

- Branch: `alvaro/evidence-pr48-shadow-review-completion-export`
- Base branch: `alvaro/evidence-pr47-shadow-review-packet-export`
- Scope: Evidence API evidence-selection shadow-review completion conversion

## Goal

Close the gap between a human-filled shadow-review packet and the strict raw
source inputs consumed by the PR45 source-export writer.

## Root Cause

PR47 made reviewer-facing packets reproducible, but those packets are
intentionally incomplete and do not validate as completed expert evidence. Once
reviewers fill the blank fields, the repo still needed a strict, repeatable
conversion step that creates:

- `selection-review-labels.json` with a `selection_reviews` array;
- `review-ranking-study.json` with
  `schema_version: "evidence_selection_review_ranking_calibration.v1"`.

Without this step, teams would have to hand-author those raw source inputs,
which risks drift from the reviewed packet and can silently package incomplete
review labels.

## Code Changes

- Added `artana_evidence_api.evidence_selection.shadow_review_completion`.
- Added strict completed-packet models separate from the intentionally
  incomplete PR47 packet models.
- Converted completed selection-review forms into
  `EvidenceSelectionReviewInput` objects.
- Converted completed ranking forms into
  `ReviewRankingCalibrationStudyInput` decisions.
- Required stripped, nonblank reviewer IDs, explanation-quality scores,
  high-severity-overclaim counts, ranking outcomes, and adjudication notes.
- Rejected human-selected, duplicate, selected, skipped, or deferred record IDs
  that do not exist in the packet candidate record roster.
- Kept deferred candidates out of `harness_skipped_record_ids`, so human
  selection of a deferred candidate becomes a measurable false negative.
- Added JSON-list parsing for packet candidate-record term arrays so
  packet JSON can round-trip through completed conversion.
- Added `scripts/build_evidence_selection_shadow_review_source_inputs.py`.
- Added output collision checks so converter outputs cannot overwrite the
  source packet or each other.
- Added output path preflight so converter outputs cannot replace directories
  or write beneath non-directory parents.
- Added paired temp-file writes and rollback cleanup so a failed second output
  does not leave half-converted source inputs, and successful overwrites do not
  leave backup artifacts.
- Registered the CLI with the path-aware CI planner and Makefile lint/type
  gates.

## Validation

RED tests observed:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_source_input_script_pr_runs_evidence_api_gate \
  tests/unit/test_makefile_type_gate_contract.py::test_evidence_api_gates_cover_shadow_review_source_input_cli_script \
  -q
```

Initial result: nine failures because the completion module, CLI, CI planner
registration, and Makefile script coverage did not exist.

Additional RED regression:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py::test_shadow_review_completion_cli_keeps_paired_outputs_all_or_nothing \
  -q
```

Initial result: failed because a simulated second-output write failure left the
selection-review output on disk.

Adversarial RED regressions after independent review:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py \
  -q
```

Initial result: four expected failures because whitespace-only reviewer IDs
validated as present, an output directory could be replaced by JSON, and
successful overwrites left `.bak-*` artifacts.

GREEN focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_source_input_script_pr_runs_evidence_api_gate \
  tests/unit/test_makefile_type_gate_contract.py::test_evidence_api_gates_cover_shadow_review_source_input_cli_script \
  -q
```

Result before adversarial review: `10 passed`.

Post-adversarial result for the completion converter and CLI:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py \
  -q
```

Result: `12 passed`.

Adjacent workflow check:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_source_export_writer.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_source_export_writer_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_source_input_script_pr_runs_evidence_api_gate \
  tests/unit/test_makefile_type_gate_contract.py::test_evidence_api_gates_cover_shadow_review_source_input_cli_script \
  -q
```

Result after adversarial fixes: `31 passed`.

```bash
uv run ruff check \
  services/artana_evidence_api/evidence_selection/shadow_review_completion.py \
  scripts/build_evidence_selection_shadow_review_source_inputs.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py \
  tests/unit/test_ci_service_check_planner.py \
  tests/unit/test_makefile_type_gate_contract.py
```

Result: passed.

```bash
make artana-evidence-api-lint
```

Result: passed via the post-adversarial service gate.

```bash
make artana-evidence-api-type-check
```

Result: passed.

```bash
make artana-evidence-api-service-checks
```

Result: passed after adversarial fixes. Live external API, running-service, and
OpenAI-key integration tests remained explicitly skipped by their environment
guards.

```bash
make service-checks
```

Result: passed after adversarial fixes with total coverage `87.03%`. Live
external API, running-service, and OpenAI-key integration tests remained
explicitly skipped by their environment guards.

Adversarial review:

- Initial verdict: BLOCK.
- Findings fixed: whitespace-only reviewer IDs, directory outputs being
  replaceable, and leaked `.bak-*` artifacts after successful overwrites.
- The review also confirmed deferred records are not copied into
  `harness_skipped_record_ids`, unknown candidate references are rejected, and
  the docs avoid claiming production readiness.

## Interpretation

PR48 does not create source exports and does not claim trusted-graph readiness.
It creates the strict bridge from a completed human packet to the raw source
inputs that PR45 can wrap as self-describing source exports. The final readiness
loop still needs real reviewed packets, source export generation, expert-study
bundle creation, and the expert-study gate.
