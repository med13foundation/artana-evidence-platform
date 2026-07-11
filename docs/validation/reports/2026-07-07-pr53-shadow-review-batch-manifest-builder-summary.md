# PR53 Shadow Review Batch Manifest Builder Summary

Date: 2026-07-07

Branch: `alvaro/evidence-pr53-shadow-review-batch-manifest-builder`

Base: `alvaro/evidence-pr52-shadow-review-batch-report-transparency`

## Goal

PR50 through PR52 made completed shadow-review packets executable as a strict
batch gate, but operators still had to hand-author the batch manifest. That
manual step is a practical blocker for the next real proof loop because copy
errors can create source-identity drift before the batch gate runs.

PR53 adds a strict manifest builder that turns completed human-labeled packets
into the `evidence_selection_shadow_review_study_batch.v1` manifest consumed by
the existing batch runner.

## What Changed

- Added `artana_evidence_api.evidence_selection.shadow_review_study_batch_manifest`.
- Added `scripts/build_evidence_selection_shadow_review_study_batch_manifest.py`.
- The builder validates every packet with the completed-packet contract already
  used by the source-input converter.
- Entry IDs, output subdirectories, and per-entry export IDs are derived
  predictably from packet study IDs and a caller-supplied export prefix.
- Packet paths are written relative to the output manifest path.
- Duplicate packet paths are rejected.
- The CLI refuses to overwrite source packets and writes the manifest through a
  temporary sibling file.
- Evidence-selection validation docs and the reviewer template now include the
  batch-manifest and batch-gate commands.
- CI planning and Makefile type-check coverage now include the new script.

## Test Evidence

RED tests:

- The service-level manifest builder module was missing.
- The CLI script was missing.
- CI planning did not route the new script through the Evidence API gate.
- Makefile type-check coverage did not include the new script.

GREEN tests run:

```bash
uv run --python python3.13 --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_manifest.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_manifest_cli.py -q
```

Result: `4 passed`

```bash
uv run --python python3.13 --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_packet_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_completion_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_pipeline_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_manifest.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_manifest_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py \
  tests/unit/test_ci_service_check_planner.py::test_evidence_api_shadow_review_study_batch_manifest_script_pr_runs_evidence_api_gate \
  tests/unit/test_makefile_type_gate_contract.py::test_evidence_api_gates_cover_shadow_review_study_batch_manifest_cli_script -q
```

Result: `58 passed`

```bash
uv run --python python3.13 --with ruff ruff check \
  services/artana_evidence_api/evidence_selection/shadow_review_study_batch_manifest.py \
  scripts/build_evidence_selection_shadow_review_study_batch_manifest.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_manifest.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_manifest_cli.py \
  tests/unit/test_ci_service_check_planner.py \
  tests/unit/test_makefile_type_gate_contract.py
```

Result: `All checks passed!`

```bash
make artana-evidence-api-type-check
```

Result: success across the Evidence API package and evidence-selection scripts,
including the new manifest-builder CLI.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Static checks, boundary checks, contract checks, architecture
checks, OpenAPI check, isolated Postgres migrations, and the Evidence API pytest
suite completed successfully. Live external API/service tests that require
explicit environment flags or running local services were skipped by their
existing guards.

## Adversarial Review

Independent adversarial review reported PASS with no blocking findings. The
review confirmed that PR53 removes the manual manifest-authoring gap, validates
packets through the completed-packet converter, writes manifest-relative packet
paths, derives entry/output/export IDs consistently, protects source packets
from overwrite, and wires CI/type gates. Non-blocking notes: keep unrelated
`uv.lock` out of the PR, and remember that derived IDs are stable for the
explicit packet order rather than order-independent unordered globs.

## Safety Invariant

Completed shadow-review packets should become batch evidence through one
validated builder path, not through hand-authored manifests. The builder does
not make any production-readiness claim by itself; the existing batch suite gate
still decides whether the completed packet suite is broad and accurate enough.

## Remaining Risk

- This still does not create real human labels. It removes a manual assembly
  risk after those labels exist.
- The trusted-graph quality proof still requires a real completed batch to pass
  the PR51 suite gate without using diagnostic `--allow-failed-gate`.
