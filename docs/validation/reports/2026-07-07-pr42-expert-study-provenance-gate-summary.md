# PR42 Expert Study Provenance Gate Summary

## Run Context

- Branch: `alvaro/evidence-pr42-expert-study-provenance-gate`
- Base branch: `alvaro/evidence-pr41-expert-study-gate`
- Scope: Evidence API expert/shadow study validation

## Goal

Close the PR41 provenance caveat by making a real-shadow study pass only when
the bundle includes an auditable source manifest.

## Root Cause

PR41 correctly blocked synthetic fixtures and incomplete study labels, but the
`study_evidence_kind` value was still declared by the bundle. A mislabeled or
hand-assembled JSON file could say `real_shadow_review` without preserving
enough source evidence to audit where the labels came from.

## Code Changes

- Added typed source artifacts with strict artifact kind, URI, and lowercase
  SHA-256 hash validation.
- Added `EvidenceSelectionExpertStudySourceManifest` for source system,
  export ID, export timestamp, exporter ID, redaction statement, source
  artifacts, selection-review run IDs, review-ranking decision keys, and
  reviewer roster.
- Added provenance summary output to the expert-study gate report.
- Added fail-closed checks for missing manifest, too few source artifacts,
  duplicate source artifact IDs, selection-review run ID drift,
  review-ranking decision-key drift, and reviewer IDs missing from the manifest
  roster.
- Added Source Manifest output to the expert-study Markdown report.
- Added `--min-source-artifact-count` to the expert-study gate runner.
- Updated validation docs and the review template with the required manifest
  shape.
- After adversarial review, added duplicate-aware coverage checks so repeated
  selection run IDs, repeated manifest run IDs, repeated review-ranking keys,
  repeated manifest ranking keys, duplicate artifact URIs, and duplicate
  artifact hashes cannot inflate provenance coverage.
- After adversarial review, required at least one `selection_review_export` and
  one `review_ranking_export` artifact instead of accepting any artifact count.
- Added normalized nonblank validation for manifest identity fields so
  whitespace-only source system, export ID, exporter ID, or redaction statement
  cannot pass as provenance.
- Split provenance models and blocker logic into
  `artana_evidence_api.evidence_selection.provenance` after the service gate
  found `evidence_selection_validation.py` exceeded the architecture size
  budget.

## Validation

RED tests observed:

```bash
uv run pytest services/artana_evidence_api/tests/unit/test_evidence_selection_validation.py -q
```

Initial result: `source_manifest` was rejected as an unknown field, and a
real-shadow bundle without source provenance still passed.

```bash
uv run pytest tests/unit/test_run_evidence_selection_expert_study_gate.py -q
```

Initial runner result: the balanced JSON fixture failed without a manifest, and
the Markdown report did not expose source-manifest evidence.

Adversarial RED results:

- Duplicate selection-review run IDs could collapse through set comparison and
  still pass.
- Source artifact coverage was count-based and did not require
  `selection_review_export` or `review_ranking_export`.
- Whitespace-only manifest identity fields could pass validation.
- Duplicate artifact URI or hash values could inflate artifact count.

GREEN focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_validation.py \
  tests/unit/test_run_evidence_selection_expert_study_gate.py \
  -q
```

Result after adversarial fixes: `42 passed`.

Additional checks:

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

Initial result: failed on architecture size because
`evidence_selection_validation.py` reached 1413 lines. The first-principles fix
was to move source-manifest responsibility into
`services/artana_evidence_api/evidence_selection/provenance.py` instead of
adding an override.

Final result: passed. Static checks, OpenAPI contract, architecture size,
architecture structure, migrations, pytest, and database teardown completed.

```bash
make service-checks
```

Result: passed with coverage `87.03%` against the `86%` gate.

Final adversarial re-review: PASS. Both reviewers re-probed the prior bypasses:
duplicate run IDs, missing export artifact kinds, duplicate artifact URI/hash
inflation, duplicate ranking keys, and blank manifest identity now fail closed.

## Interpretation

PR42 still does not make expert/shadow study data appear automatically. It
raises the proof bar: a production-style passing study must now preserve the
source export identity, hashed artifacts, exact study-row coverage, and reviewer
roster coverage needed for audit.
