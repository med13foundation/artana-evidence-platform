# PR52 Shadow Review Batch Report Transparency Summary

Date: 2026-07-07

Branch: `alvaro/evidence-pr52-shadow-review-batch-report-transparency`

Base: `alvaro/evidence-pr51-shadow-review-batch-suite-gate`

## Goal

PR51 made the shadow-review batch suite gate non-relaxable, but its Markdown
report did not make the requested-vs-enforced threshold decision visible enough
for operators. The JSON already carried the audit fields, but a reviewer reading
only the Markdown report could miss that production floors were applied.

PR52 makes the existing suite-gate decision easier to audit without changing the
gate math.

## What Changed

- The aggregate Markdown report now states whether the production floor was
  applied.
- The aggregate Markdown report now includes a Suite Thresholds table showing
  requested thresholds next to enforced thresholds.
- The CLI help for `--allow-failed-gate` now says the override can apply to an
  entry gate or a suite gate failure.
- Old or malformed reports with a suite gate but no production-floor field now
  render the production-floor status as `unknown` instead of implying `no`.
- Regression tests cover both the Markdown transparency output and the CLI help
  text.

## Test Evidence

RED tests:

- A relaxed CLI threshold run did not render `production_floor_applied` in the
  Markdown report.
- The Markdown report did not expose requested-vs-enforced suite thresholds.
- `--allow-failed-gate --help` only mentioned entry failures, even though PR51
  made the suite gate the top-level pass/fail decision.
- A malformed/old report with the suite gate present but no
  `production_floor_applied` field rendered as `no` instead of `unknown`.

GREEN tests run:

```bash
uv run --python python3.13 --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py::test_shadow_review_study_batch_markdown_marks_missing_production_floor_unknown \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py::test_shadow_review_study_batch_cli_does_not_relax_production_suite_floor \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py::test_shadow_review_study_batch_cli_help_mentions_suite_gate_override -q
```

Result: `3 passed`

```bash
uv run --python python3.13 --with pytest --with pytest-asyncio \
  pytest services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py -q
```

Result: `24 passed`

```bash
uv run --python python3.13 --with ruff ruff check \
  scripts/build_evidence_selection_shadow_review_study_batch.py \
  services/artana_evidence_api/tests/unit/test_evidence_selection_shadow_review_study_batch_cli.py
```

Result: `All checks passed!`

```bash
make artana-evidence-api-type-check
```

Result: success across the Evidence API package and evidence-selection scripts.

## Adversarial Review

Independent adversarial review reported PASS for draft-PR readiness and confirmed
that the change materially improves operator transparency for PR51 suite-gate
reports. The review found one non-blocking defensive nit: missing
`production_floor_applied` fields should render as `unknown` instead of `no`.
PR52 includes that fix and regression coverage.

## Safety Invariant

The batch suite gate still fails closed using PR51's JSON gate semantics. PR52
does not weaken or reinterpret thresholds; it only makes non-relaxable
production-floor enforcement visible in the human-readable report.

## Remaining Risk

- This improves report transparency only. It does not collect new real
  shadow-review labels and does not move the trusted-graph quality metrics by
  itself.
- The next product-quality proof still requires completed real shadow-review
  packets, source export generation, expert-study bundle generation, and a
  passing batch suite gate over a sufficiently broad suite.
