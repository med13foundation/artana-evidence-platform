# PR-10 CI Quality Gate Evidence Snapshot

Date: 2026-07-03

Branch: planned `alvaro/evidence-pr10-ci-quality-gate`; currently stacked in
worktree branch `alvaro/evidence-pr0-quality-harness` until earlier slices are
split.

## Scope

PR-10 makes relation-quality regressions visible in local and GitHub CI gates:

- Adds `relation-feasibility-quality-gate` to the Makefile.
- Runs that gate from normal `make service-checks`.
- Routes relation-feasibility audit-methodology changes through the Evidence API
  and repo-control CI paths.
- Adds `tests/unit/test_relation_feasibility_audit.py` to both repo-control
  workflow jobs.
- Cleans machine-specific absolute paths from validation docs so repo-control
  checks pass.

## Focused Result

| Scenario | Result |
|---|---|
| Change under `scripts/validation/relation_feasibility/` | Plans Evidence API and repo-control checks |
| Local normal gate | Runs `relation-feasibility-quality-gate` |
| GitHub repo-control jobs | Run relation-feasibility audit tests |
| Docs reusable-path hygiene | No developer-home absolute paths remain under docs |

## Validation

- RED/GREEN PR-10 tests:
  - `test_relation_feasibility_quality_code_runs_evidence_api_and_repo_control`
  - `test_relation_feasibility_quality_gate_is_part_of_service_checks`
  - `test_ci_repo_control_jobs_run_relation_feasibility_quality_tests`
- `make relation-feasibility-quality-gate` passed.
- `ruff check` on touched PR-10 Python files passed.
- Repo-control bundle passed after docs path cleanup:
  - `tests/unit/test_ci_service_check_planner.py`
  - `tests/unit/test_control_files.py`
  - `tests/unit/test_coverage_enforcement_contract.py`
  - `tests/unit/test_makefile_type_gate_contract.py`
  - `tests/unit/test_relation_feasibility_audit.py`

## Known Remaining Risk

The CI quality gate covers deterministic audit-methodology regressions. The
strict live-agent audit still requires model credentials and remains opt-in.
