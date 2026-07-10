# PR43 Expert Study Bundle Builder Summary

## Run Context

- Branch: `alvaro/evidence-pr43-expert-study-bundle-builder`
- Base branch: `alvaro/evidence-pr42-expert-study-provenance-gate`
- Scope: Evidence API expert/shadow study validation

## Goal

Make PR42 source-manifest provenance reproducible from source export files
instead of relying on hand-authored study bundles.

## Root Cause

PR42 made the expert-study gate fail closed unless a bundle included hashed
source artifacts and exact study coverage metadata. That raised the proof bar,
but users still had to assemble the manifest manually. Manual assembly can
create false confidence through stale hashes, omitted rows, accidental
deduplication, or synthetic fixtures mislabeled as real shadow-review evidence.

## Code Changes

- Added `artana_evidence_api.evidence_selection.study_bundle` as the service
  builder for `evidence_selection_expert_study.v1` bundles.
- Added `scripts/build_evidence_selection_expert_study_bundle.py` as a thin CLI
  wrapper around the service builder.
- The builder reads selection-review, review-ranking, and optional adjudication
  source artifacts once as bytes, computes SHA-256 from those bytes, and parses
  JSON from the same bytes.
- The source manifest derives selection-review run IDs, review-ranking
  `source_kind:item_id` keys, and reviewer roster from validated inputs.
- Duplicate selection run IDs and duplicate review-ranking decision keys are
  preserved so the existing gate can block them instead of having the builder
  hide them.
- The CLI rejects output paths that would overwrite any source artifact before
  building the bundle.
- The CLI rejects invalid or timezone-naive `--exported-at` values and returns
  concise stderr errors for missing sources, malformed JSON, validation errors,
  and write failures.
- The new CLI script is included in Evidence API lint/type gates and in the CI
  service-check planner's Evidence API file set.

## Validation

RED tests observed:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle_cli.py \
  -q
```

Initial result: the builder module and CLI script were missing.

Adversarial RED results:

- Synthetic mechanics fixtures were initially labeled `real_shadow_review` and
  asserted as passing production gates.
- Duplicate review-ranking decision-key preservation was not tested.
- Source JSON and source hashes came from separate file reads.
- CLI output could overwrite source artifacts.
- CLI errors could escape as raw tracebacks.
- Timezone-naive export timestamps were accepted.
- The service-check planner did not run Evidence API checks for script-only
  changes to the new builder CLI.

GREEN focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle_cli.py \
  tests/unit/test_ci_service_check_planner.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_validation.py \
  tests/unit/test_run_evidence_selection_expert_study_gate.py \
  -q
```

Result: `46 passed`.

Additional checks:

```bash
make artana-evidence-api-lint
```

Result: passed.

```bash
make artana-evidence-api-type-check
```

Result: passed for the Evidence API package and the new builder CLI script.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Static checks, OpenAPI contract, architecture size,
architecture structure, migrations, pytest, and database teardown completed.

```bash
make service-checks
```

Result: passed with coverage `87.03%` against the `86%` gate.

```bash
uv run pre-commit run --all-files
```

Result: passed.

Final adversarial re-review: PASS. Reviewers re-probed synthetic-real false
confidence, duplicate ranking keys, read-once hashing, destructive output
paths, write-error handling, and CI planner coverage.

## Interpretation

PR43 still does not make synthetic labels production evidence. Its value is
operational: real expert/shadow studies can now be assembled from source export
files with computed hashes, derived coverage metadata, and safety checks that
prevent the builder from hiding the same provenance gaps the gate is supposed
to catch.
