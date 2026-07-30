from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

DOC_EXTENSIONS = {".md", ".mdx", ".rst", ".txt"}
REPO_CONTROL_FILES = {
    ".env.postgres.example",
    "Makefile",
    "architecture_overrides.json",
    "docker-compose.postgres.yml",
    "pyproject.toml",
    "pytest.ini",
    "scripts/run_qa_report.sh",
    "tests/unit/test_control_files.py",
    "tests/unit/test_coverage_enforcement_contract.py",
    "tests/unit/test_makefile_type_gate_contract.py",
    "tests/unit/test_agent_output_boundary_validator.py",
    "services/artana_evidence_api/tests/unit/test_agent_output_schema_registry.py",
}
QUALITY_GATE_PREFIXES = (
    "scripts/validation/relation_feasibility/",
    "scripts/validation/claim_events/",
)
QUALITY_GATE_FILES = {
    "scripts/run_relation_feasibility_audit.py",
    "tests/unit/test_relation_feasibility_audit.py",
}
HIGH_RISK_PREFIXES = (
    ".github/workflows/",
    "services/artana_evidence_api/alembic/",
    "services/artana_evidence_db/alembic/",
)
EVIDENCE_API_PREFIXES = (
    "services/artana_evidence_api/",
    "scripts/validation/evidence_selection/",
    "docs/validation/reports/semantic-model-comparisons/",
    "tests/e2e/artana_evidence_api/",
)
EVIDENCE_API_FILES = (
    "docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.json",
    "docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.md",
    "docs/validation/reports/pr-semantic-pr2-agent-selector-evaluation.json",
    "docs/validation/reports/pr-semantic-pr2-agent-selector-evaluation.md",
    "scripts/build_evidence_selection_shadow_review_packet.py",
    "scripts/build_evidence_selection_expert_pilot_packets.py",
    "scripts/import_evidence_selection_expert_pilot_reviews.py",
    "scripts/build_evidence_selection_shadow_review_source_inputs.py",
    "scripts/build_evidence_selection_shadow_review_study_batch_manifest.py",
    "scripts/build_evidence_selection_shadow_review_study_batch.py",
    "scripts/build_evidence_selection_shadow_review_study_artifacts.py",
    "scripts/build_evidence_selection_source_exports.py",
    "scripts/build_evidence_selection_expert_study_bundle.py",
    "scripts/generate_evidence_selection_semantic_baseline.py",
    "scripts/ci/validate_agent_output_boundaries.py",
    "scripts/run_evidence_selection_semantic_agent_evaluation.py",
    "scripts/run_evidence_selection_semantic_model_comparison.py",
    "scripts/export_artana_evidence_api_openapi.py",
    "scripts/run_evidence_selection_expert_study_gate.py",
    "scripts/run_evidence_selection_review_calibration_gate.py",
    "scripts/validate_artana_evidence_api_service_boundary.py",
)
GRAPH_SERVICE_PREFIXES = (
    "services/artana_evidence_db/",
    "tests/e2e/graph_service/",
)
GRAPH_SERVICE_FILES = (
    "scripts/export_graph_openapi.py",
    "scripts/generate_ts_types.py",
    "scripts/validate_graph_phase6_release_contract.py",
    "scripts/validate_graph_service_boundary.py",
    # Reads graph models and the graph schema, and its output is meant to be
    # attached to readiness decisions. Without this entry a change touching only
    # the script planned every gate false, so it had no lint, no type check and
    # no test run at all.
    "scripts/measure_governance_invariants.py",
)
TEST_PREFIXES = (
    "services/artana_evidence_api/tests/",
    "services/artana_evidence_db/tests/",
    "tests/unit/",
)
FORCE_STATIC_TEST_FILES = {
    "services/artana_evidence_api/tests/unit/test_agent_output_schema_registry.py",
    "tests/unit/test_agent_output_boundary_validator.py",
}
INTEGRATION_TEST_PARTS = (
    "/integration/",
    "/e2e/",
    "tests/e2e/",
    "database/",
)


@dataclass(frozen=True)
class CheckPlan:
    docs_only: bool
    evidence_api: bool
    graph_service: bool
    repo_control: bool
    full: bool
    targeted_test_paths: tuple[str, ...]


def plan_checks(
    changed_files: list[str],
    *,
    event_name: str,
    ref: str,
) -> CheckPlan:
    normalized_paths = sorted(_normalize_path(path) for path in changed_files if path)
    if _must_run_full(event_name=event_name, ref=ref) or not normalized_paths:
        return _full_plan()

    docs_only = all(_is_docs_path(path) for path in normalized_paths)
    test_paths = tuple(
        path for path in normalized_paths if _is_targeted_unit_test(path)
    )
    force_static = any(path in FORCE_STATIC_TEST_FILES for path in normalized_paths)
    tests_only = (
        bool(test_paths)
        and len(test_paths) == len(normalized_paths)
        and not force_static
    )
    high_risk = any(_is_high_risk_path(path) for path in normalized_paths)
    repo_control = any(_is_repo_control_path(path) for path in normalized_paths)
    quality_gate = any(_is_quality_gate_path(path) for path in normalized_paths)
    evidence_api = any(_is_evidence_api_path(path) for path in normalized_paths)
    graph_service = any(_is_graph_service_path(path) for path in normalized_paths)

    return CheckPlan(
        docs_only=docs_only,
        evidence_api=(evidence_api or high_risk or quality_gate) and not tests_only,
        graph_service=(graph_service or high_risk) and not tests_only,
        repo_control=(repo_control or high_risk or quality_gate)
        and not docs_only
        and not tests_only,
        full=high_risk,
        targeted_test_paths=test_paths if tests_only else (),
    )


def emit_github_outputs(plan: CheckPlan) -> str:
    return "\n".join(
        (
            f"docs_only={_bool_output(value=plan.docs_only)}",
            f"evidence_api={_bool_output(value=plan.evidence_api)}",
            f"graph_service={_bool_output(value=plan.graph_service)}",
            f"repo_control={_bool_output(value=plan.repo_control)}",
            f"full={_bool_output(value=plan.full)}",
            f"targeted_tests={_bool_output(value=bool(plan.targeted_test_paths))}",
            f"targeted_test_paths={' '.join(plan.targeted_test_paths)}",
        ),
    )


def _full_plan() -> CheckPlan:
    return CheckPlan(
        docs_only=False,
        evidence_api=True,
        graph_service=True,
        repo_control=True,
        full=True,
        targeted_test_paths=(),
    )


def _normalize_path(path: str) -> str:
    return path.strip().removeprefix("./")


def _must_run_full(*, event_name: str, ref: str) -> bool:
    return event_name in {"workflow_dispatch", "merge_group"} or ref in {
        "refs/heads/main",
        "refs/heads/develop",
    }


def _is_docs_path(path: str) -> bool:
    path_obj = Path(path)
    return (
        path.startswith("docs/")
        or path_obj.name in {"README.md", "AGENTS.md"}
        or path_obj.suffix in DOC_EXTENSIONS
    )


def _is_high_risk_path(path: str) -> bool:
    return path.startswith(HIGH_RISK_PREFIXES) or path in {
        "pyproject.toml",
        "pytest.ini",
    }


def _is_repo_control_path(path: str) -> bool:
    return path in REPO_CONTROL_FILES or path.startswith(
        ("scripts/ci/", "scripts/deploy/"),
    )


def _is_quality_gate_path(path: str) -> bool:
    return path in QUALITY_GATE_FILES or path.startswith(QUALITY_GATE_PREFIXES)


def _is_evidence_api_path(path: str) -> bool:
    return path.startswith(EVIDENCE_API_PREFIXES) or path in EVIDENCE_API_FILES


def _is_graph_service_path(path: str) -> bool:
    return path.startswith(GRAPH_SERVICE_PREFIXES) or path in GRAPH_SERVICE_FILES


def _is_targeted_unit_test(path: str) -> bool:
    if not path.endswith(".py") or not Path(path).name.startswith("test_"):
        return False
    if not path.startswith(TEST_PREFIXES):
        return False
    return not any(part in path for part in INTEGRATION_TEST_PARTS)


def _bool_output(*, value: bool) -> str:
    return "true" if value else "false"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Plan path-aware Artana Evidence Platform CI checks.",
    )
    parser.add_argument("--changed-files", required=True, type=Path)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--ref", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    changed_files = args.changed_files.read_text(encoding="utf-8").splitlines()
    print(
        emit_github_outputs(
            plan_checks(changed_files, event_name=args.event_name, ref=args.ref),
        ),
    )


if __name__ == "__main__":
    main()
