# PR44 Expert Source Export Metadata Summary

## Run Context

- Branch: `alvaro/evidence-pr44-expert-source-export-metadata`
- Base branch: `alvaro/evidence-pr43-expert-study-bundle-builder`
- Scope: Evidence API expert/shadow study source-export provenance

## Goal

Make expert-study source identity self-describing and literal so the bundle
builder cannot create provenance false confidence from manually supplied CLI
metadata.

## Root Cause

PR43 made source artifact hashing reproducible, but source identity was still
provided out of band through builder request fields and CLI flags. That meant a
caller could accidentally retype stale metadata, use a timestamp spelling that
normalized to the same instant, or provide fields that did not match the source
files. The stronger fix is for the source exports themselves to carry identity
and for the builder to derive the final source manifest from those exports.

## Code Changes

- Added `artana_evidence_api.evidence_selection.source_exports` with strict
  self-describing export envelopes:
  `evidence_selection_review_export.v1` and
  `evidence_selection_review_ranking_export.v1`.
- The bundle builder now loads typed selection-review and review-ranking source
  exports and derives `source_manifest` identity from matching embedded
  `source_system`, `export_id`, `exported_at`, `exporter_id`, and
  `redaction_statement` fields.
- Optional request and CLI source-identity fields are now compatibility checks
  only. If one is supplied, all must be supplied, and the supplied identity must
  exactly match the identity embedded in both source exports.
- Source-export timestamps are parsed through one canonical helper. JSON source
  exports must use exact `YYYY-MM-DDTHH:MM:SSZ`; timezone-naive timestamps,
  offset spellings such as `+00:00` or `+01:00`, fractional seconds, space
  separators, and omitted seconds are rejected.
- Source identity text fields are compared literally. Leading or trailing
  whitespace is rejected instead of stripped.
- The builder CLI can now build from source exports without manual identity
  flags, while still allowing exact-match compatibility checks for operators
  that want an additional guard.
- Validation docs now document the self-describing source-export shapes,
  canonical UTC timestamp rule, and optional compatibility-check behavior.

## Validation

RED tests observed:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle_cli.py \
  -q
```

Initial adversarial result: eight failures showed that timezone-naive source
export timestamps were accepted as mismatched identity instead of being rejected
for the real timestamp defect, same-instant offset spellings could be accepted,
and CLI/source-identity override mismatch paths were not covered.

Second adversarial RED result: fourteen failures showed that same-instant
alternate UTC spellings such as `.000Z`, `+00:00`, a space separator, and
omitted seconds were still accepted, and that leading/trailing whitespace in
identity text fields was stripped instead of rejected.

GREEN focused checks:

```bash
uv run pytest \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle_cli.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_validation.py \
  tests/unit/test_run_evidence_selection_expert_study_gate.py \
  -q
```

Result: `73 passed`.

```bash
uv run ruff check \
  services/artana_evidence_api/evidence_selection/source_exports.py \
  services/artana_evidence_api/evidence_selection/study_bundle.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_study_bundle_cli.py \
  scripts/build_evidence_selection_expert_study_bundle.py
```

Result: passed.

```bash
make artana-evidence-api-type-check
```

Result: passed for the Evidence API package and the bundle builder CLI.

```bash
make artana-evidence-api-service-checks
```

Result: passed. Static checks, OpenAPI contract, architecture size,
architecture structure, migrations, pytest, and database teardown completed.

```bash
make service-checks
```

Result: passed with coverage `87.03%` against the `86%` gate.

Final adversarial re-review: PASS for code and spec behavior after exact
timestamp grammar and whitespace rejection were added. The remaining packaging
note was to include the new source-export module and this report in the PR set
while leaving unrelated `uv.lock` out.

## Interpretation

PR44 does not make synthetic expert studies production evidence. It closes a
provenance gap: source identity now travels with the source exports, must match
across the two expert-study inputs, and cannot be replaced by manually supplied
CLI metadata. That makes the PR43 bundle builder safer to use for real
expert/shadow review studies.
