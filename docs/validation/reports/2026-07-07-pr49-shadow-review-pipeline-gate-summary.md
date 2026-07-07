# PR49 Shadow Review Pipeline Gate Summary

## Run Context

- Branch: `alvaro/evidence-pr49-shadow-review-pipeline-gate`
- Base branch: `alvaro/evidence-pr48-shadow-review-completion-export`
- Scope: Evidence API evidence-selection shadow-review study artifact pipeline

## Goal

Close the manual handoff gap after PR48. A completed human shadow-review packet
should produce the full set of auditable study artifacts:

- raw PR48 source inputs:
  - `selection-review-labels.json`
  - `review-ranking-study.json`
- PR45 self-describing source exports:
  - `selection-review-export.json`
  - `review-ranking-export.json`
- PR43 expert-study bundle:
  - `evidence-selection-expert-study.json`
- PR41 expert-study gate report:
  - `gate/evidence_selection_expert_study_gate.json`
  - `gate/evidence_selection_expert_study_gate.md`

## Root Cause

PR48 made completed reviewer packets convertible into strict raw source inputs,
but operators still had to manually chain multiple commands to wrap those
inputs as source exports, build the expert-study bundle, and run the study gate.
That manual stitching increases the chance that reviewed labels are packaged
with mismatched identity, missing provenance, or no gate report.

## Code Changes

- Added `artana_evidence_api.evidence_selection.shadow_review_study_pipeline`.
- Added `scripts/build_evidence_selection_shadow_review_study_artifacts.py`.
- Composed existing builders instead of duplicating their domain logic:
  - PR48 completed-packet source-input conversion.
  - PR45 self-describing source-export writer.
  - PR43 expert-study bundle builder.
  - PR41 expert-study gate report writer.
- Kept the CLI fail-closed by default when the expert-study gate fails.
- Preserved failed gate JSON/Markdown reports so reviewers can inspect blockers.
- Added `--allow-failed-gate` for mechanics/debug runs where nonzero exit would
  interrupt artifact inspection.
- Added output-directory and source-packet collision preflight before writing
  any generated artifacts.
- Registered the new script in Makefile lint/type gates and path-aware CI
  planning.
- Fixed a type-shadowing issue in `scripts/run_evidence_selection_expert_study_gate.py`
  exposed by importing the runner helper from the new CLI.

## Validation

RED tests observed:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline_cli.py \
  -q
```

Initial result: five failures because the pipeline module and CLI did not exist.

Gate-registration RED tests observed:

```bash
uv run pytest \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_study_pipeline_script_pr_runs_evidence_api_gate \
  tests/unit/test_makefile_type_gate_contract.py::test_evidence_api_gates_cover_shadow_review_study_pipeline_cli_script \
  -q
```

Initial result: two failures because script-only PR49 changes were not routed
through Evidence API gates and the script was not type checked by the Makefile.

Adversarial RED regression:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline.py::test_shadow_review_study_pipeline_rejects_packet_output_collision \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline_cli.py::test_shadow_review_study_pipeline_cli_rejects_packet_output_collision \
  -q
```

Initial result: failed because `packet_path` was not represented in the service
request and the CLI could overwrite the source packet before failing the gate.

GREEN focused/adjacent checks after the adversarial fix:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_source_export_writer.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_source_export_writer_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle_cli.py \
  tests/unit/test_run_evidence_selection_expert_study_gate.py \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_study_pipeline_script_pr_runs_evidence_api_gate \
  tests/unit/test_makefile_type_gate_contract.py::test_evidence_api_gates_cover_shadow_review_study_pipeline_cli_script \
  -q
```

Result: `85 passed`.

```bash
uv run ruff check \
  services/artana_evidence_api/evidence_selection/shadow_review_study_pipeline.py \
  scripts/build_evidence_selection_shadow_review_study_artifacts.py \
  scripts/run_evidence_selection_expert_study_gate.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline_cli.py \
  tests/unit/test_ci_service_check_planner.py \
  tests/unit/test_makefile_type_gate_contract.py
```

Result: passed.

```bash
make artana-evidence-api-type-check
```

Result: passed.

Pre-adversarial baseline:

```bash
make artana-evidence-api-service-checks
```

Result: passed before the packet-collision fix. The post-fix service gate still
supersedes this baseline as the merge-relevant service-gate result.

Post-adversarial service gate:

```bash
make artana-evidence-api-service-checks
```

Result: passed. Live external API, running-service, and OpenAI-key integration
tests remained explicitly skipped by their environment guards.

Aggregate service gate:

```bash
make service-checks
```

Result: passed with total coverage `87.03%`. Live external API,
running-service, and OpenAI-key integration tests remained explicitly skipped by
their environment guards.

## Adversarial Review

- Initial verdict: BLOCK.
- Finding fixed: source packet could be overwritten when the packet path was
  inside the output directory and matched a generated artifact filename.
- Current fix: request carries `packet_path`; the pipeline computes all fixed
  output paths, verifies uniqueness, rejects output/source-packet collisions,
  and checks output file safety before any artifact write.

## Interpretation

PR49 does not claim the live agent is trusted-graph ready. It removes another
manual gap in the measurement loop: a completed human review can now become a
source-exported, provenance-backed, gate-scored expert-study artifact set in one
reproducible command.
