"""Reject production model calls that bypass agent-output schema governance."""

from __future__ import annotations

import argparse
import ast
import json
from dataclasses import dataclass
from pathlib import Path

from artana_evidence_api.runtime.agent_output_report import (
    build_agent_output_registry_report,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SERVICE_ROOT = REPO_ROOT / "services" / "artana_evidence_api"
GUARDED_RUNTIME_FILE = SERVICE_ROOT / "step_helpers.py"
_REGISTERED_CALLS = frozenset(
    {
        "run_registered_agent",
        "run_registered_harness_agent",
        "run_single_step_with_policy",
        "step_runner",
    },
)
_DIRECT_MODEL_METHODS = frozenset({"run", "run_agent", "step"})


@dataclass(frozen=True, slots=True)
class AgentOutputBoundaryViolation:
    """One direct or incompletely registered model-output boundary."""

    path: Path
    line: int
    message: str

    def render(self) -> str:
        """Return a stable CI diagnostic."""

        relative_path = self.path.relative_to(REPO_ROOT)
        return f"{relative_path}:{self.line}: {self.message}"


def find_agent_output_boundary_violations(
    paths: tuple[Path, ...] | None = None,
) -> tuple[AgentOutputBoundaryViolation, ...]:
    """Return every production model call that bypasses the registered wrappers."""

    source_paths = paths or tuple(sorted(SERVICE_ROOT.rglob("*.py")))
    violations: list[AgentOutputBoundaryViolation] = []
    for path in source_paths:
        if "tests" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            keywords = {keyword.arg for keyword in node.keywords if keyword.arg}
            if "output_schema" not in keywords:
                continue
            call_name = _call_name(node.func)
            leaf_name = call_name.rsplit(".", maxsplit=1)[-1]
            if leaf_name in _DIRECT_MODEL_METHODS and path != GUARDED_RUNTIME_FILE:
                violations.append(
                    AgentOutputBoundaryViolation(
                        path=path,
                        line=node.lineno,
                        message=(
                            f"direct {call_name}(output_schema=...) bypasses the "
                            "registered agent-output wrapper"
                        ),
                    ),
                )
                continue
            if leaf_name in _REGISTERED_CALLS and "schema_id" not in keywords:
                violations.append(
                    AgentOutputBoundaryViolation(
                        path=path,
                        line=node.lineno,
                        message=f"{call_name}(...) is missing required schema_id",
                    ),
                )
    return tuple(violations)


def _call_name(function: ast.expr) -> str:
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        prefix = _call_name(function.value)
        return f"{prefix}.{function.attr}" if prefix else function.attr
    return "<dynamic-call>"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate registered model boundaries and registry evidence.",
    )
    parser.add_argument("--check-report", type=Path)
    parser.add_argument("--write-report", type=Path)
    return parser.parse_args()


def _render_report() -> str:
    return json.dumps(
        build_agent_output_registry_report(),
        indent=2,
        sort_keys=True,
    ) + "\n"


def main() -> None:
    args = _parse_args()
    violations = find_agent_output_boundary_violations()
    if violations:
        rendered = "\n".join(violation.render() for violation in violations)
        raise SystemExit(f"Agent output boundary validation failed:\n{rendered}")
    report = _render_report()
    if args.write_report is not None:
        args.write_report.parent.mkdir(parents=True, exist_ok=True)
        args.write_report.write_text(report, encoding="utf-8")
    if args.check_report is not None:
        if not args.check_report.exists():
            raise SystemExit(f"Agent output registry report is missing: {args.check_report}")
        if args.check_report.read_text(encoding="utf-8") != report:
            raise SystemExit(
                f"Agent output registry report is stale: {args.check_report}",
            )
    print("Agent output boundary validation passed.")


if __name__ == "__main__":
    main()
