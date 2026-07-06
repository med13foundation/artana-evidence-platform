#!/usr/bin/env python3
"""Build a model-comparison report from relation feasibility run artifacts."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from scripts.validation.relation_feasibility.model_comparison import (  # noqa: E402
    build_model_comparison_report,
    write_model_comparison_report,
)
from scripts.validation.relation_feasibility.readiness import (  # noqa: E402
    build_readiness_report,
)

_DEFAULT_REPORT_ROOT = _REPO_ROOT / "reports" / "relation_model_comparison"


@dataclass(frozen=True, slots=True)
class _AuditRunFailure:
    model_label: str
    run_index: int
    exit_code: int
    command: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _AuditGroupResult:
    report_paths: tuple[Path, ...]
    failures: tuple[_AuditRunFailure, ...]


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Compare current and candidate model relation-feasibility reports "
            "using repeated-run readiness gates."
        ),
    )
    parser.add_argument(
        "--current-model-label",
        required=True,
        help="Label for the current model report group.",
    )
    parser.add_argument(
        "--candidate-model-label",
        required=True,
        help="Label for the candidate model report group.",
    )
    parser.add_argument(
        "--current-report",
        action="append",
        type=Path,
        help=(
            "Current-model relation_feasibility_report.json, or a directory "
            "containing that file. Repeat once per run."
        ),
    )
    parser.add_argument(
        "--candidate-report",
        action="append",
        type=Path,
        help=(
            "Candidate-model relation_feasibility_report.json, or a directory "
            "containing that file. Repeat once per run."
        ),
    )
    parser.add_argument(
        "--run-audits",
        action="store_true",
        help=(
            "Run repeated strict live-agent audits before building the comparison. "
            "When omitted, --current-report and --candidate-report provide already "
            "written reports."
        ),
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=None,
        help=(
            "Benchmark JSON file to pass to each live audit when --run-audits is "
            "used. When omitted, the audit script uses its own default fixture."
        ),
    )
    parser.add_argument(
        "--candidate-model-env-var",
        default="ARTANA_STRONGER_MODEL_CANDIDATE",
        help="Environment variable containing the candidate extraction model id.",
    )
    parser.add_argument(
        "--runs-per-model",
        type=int,
        default=3,
        help="Required report count for each model.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. Defaults to "
            "reports/relation_model_comparison/<timestamp>."
        ),
    )
    parser.add_argument(
        "--fail-on-keep-current",
        action="store_true",
        help="Exit nonzero when the candidate model is not adopted.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build a model comparison report and write artifacts."""

    args = parse_args(argv)
    output_dir = args.output_dir or _timestamped_output_dir()
    if args.run_audits:
        current_group, candidate_group = _run_audit_group_reports(
            output_dir=output_dir,
            runs_per_model=args.runs_per_model,
            candidate_model_env_var=args.candidate_model_env_var,
            cases_path=args.cases,
        )
        current_reports = current_group.report_paths
        candidate_reports = candidate_group.report_paths
        audit_failures = current_group.failures + candidate_group.failures
    else:
        current_reports = tuple(args.current_report or ())
        candidate_reports = tuple(args.candidate_report or ())
        audit_failures = ()
    resolved_current_reports = tuple(_resolve_report_path(path) for path in current_reports)
    resolved_candidate_reports = tuple(
        _resolve_report_path(path) for path in candidate_reports
    )
    if audit_failures:
        report = _build_failed_audit_comparison_report(
            current_model_label=args.current_model_label,
            candidate_model_label=args.candidate_model_label,
            current_report_paths=resolved_current_reports,
            candidate_report_paths=resolved_candidate_reports,
            audit_failures=audit_failures,
            min_runs=args.runs_per_model,
        )
    else:
        _validate_report_count(
            label="current",
            report_paths=resolved_current_reports,
            runs_per_model=args.runs_per_model,
        )
        _validate_report_count(
            label="candidate",
            report_paths=resolved_candidate_reports,
            runs_per_model=args.runs_per_model,
        )
        report = build_model_comparison_report(
            current_model_label=args.current_model_label,
            candidate_model_label=args.candidate_model_label,
            current_report_paths=resolved_current_reports,
            candidate_report_paths=resolved_candidate_reports,
            min_runs=args.runs_per_model,
        )
    manifest = write_model_comparison_report(report=report, output_dir=output_dir)
    decision = report["decision"]
    adopted_model_label = (
        decision.get("adopted_model_label") if isinstance(decision, dict) else None
    )
    decision_status = "adopt_candidate" if adopted_model_label else "keep_current"
    print(
        "relation_model_comparison "
        f"decision={decision_status} "
        f"current={report['current_model_label']} "
        f"candidate={report['candidate_model_label']} "
        f"blocking_reasons={_decision_count(decision, 'blocking_reasons')} "
        f"safety_failures={_decision_count(decision, 'safety_failures')}",
    )
    print(f"Wrote JSON report: {manifest['json_path']}")
    print(f"Wrote Markdown report: {manifest['markdown_path']}")
    if args.fail_on_keep_current and adopted_model_label is None:
        return 1
    return 0


def _run_audit_group_reports(
    *,
    output_dir: Path,
    runs_per_model: int,
    candidate_model_env_var: str,
    cases_path: Path | None,
) -> tuple[_AuditGroupResult, _AuditGroupResult]:
    candidate_model = os.environ.get(candidate_model_env_var)
    if not candidate_model:
        msg = f"{candidate_model_env_var} must be set when --run-audits is used"
        raise SystemExit(msg)
    original_model = os.environ.get("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL")
    current_reports = _run_model_audits(
        model_label="current",
        output_dir=output_dir / "runs" / "current",
        runs_per_model=runs_per_model,
        model_id=original_model,
        cases_path=cases_path,
    )
    candidate_reports = _run_model_audits(
        model_label="candidate",
        output_dir=output_dir / "runs" / "candidate",
        runs_per_model=runs_per_model,
        model_id=candidate_model,
        cases_path=cases_path,
    )
    return current_reports, candidate_reports


def _run_model_audits(
    *,
    model_label: str,
    output_dir: Path,
    runs_per_model: int,
    model_id: str | None,
    cases_path: Path | None,
) -> _AuditGroupResult:
    reports: list[Path] = []
    failures: list[_AuditRunFailure] = []
    for run_index in range(1, runs_per_model + 1):
        run_dir = output_dir / f"run{run_index}"
        run_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        if model_id is not None:
            env["ARTANA_AI_EVIDENCE_EXTRACTION_MODEL"] = model_id
        else:
            env.pop("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL", None)
        try:
            if cases_path is None:
                _run_single_audit(output_dir=run_dir, env=env)
            else:
                _run_single_audit(output_dir=run_dir, env=env, cases_path=cases_path)
        except subprocess.CalledProcessError as exc:
            failures.append(
                _AuditRunFailure(
                    model_label=model_label,
                    run_index=run_index,
                    exit_code=exc.returncode,
                    command=tuple(str(part) for part in exc.cmd),
                ),
            )
            break
        reports.append(run_dir / "relation_feasibility_report.json")
    return _AuditGroupResult(report_paths=tuple(reports), failures=tuple(failures))


def _run_single_audit(
    *,
    output_dir: Path,
    env: Mapping[str, str],
    cases_path: Path | None = None,
) -> None:
    command = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "run_relation_feasibility_audit.py"),
        "--extractor",
        "agent",
        "--output-dir",
        str(output_dir),
    ]
    if cases_path is not None:
        command.extend(("--cases", str(cases_path)))
    subprocess.run(  # noqa: S603
        command,
        cwd=_REPO_ROOT,
        env=dict(env),
        check=True,
    )


def _validate_report_count(
    *,
    label: str,
    report_paths: Sequence[Path],
    runs_per_model: int,
) -> None:
    if len(report_paths) != runs_per_model:
        msg = (
            f"{label} report count must match --runs-per-model; "
            f"expected {runs_per_model}, got {len(report_paths)}"
        )
        raise SystemExit(msg)


def _resolve_report_path(path: Path) -> Path:
    if path.is_dir():
        return path / "relation_feasibility_report.json"
    return path


def _build_failed_audit_comparison_report(  # noqa: PLR0913
    *,
    current_model_label: str,
    candidate_model_label: str,
    current_report_paths: Sequence[Path],
    candidate_report_paths: Sequence[Path],
    audit_failures: Sequence[_AuditRunFailure],
    min_runs: int,
) -> dict[str, object]:
    return {
        "current_model_label": current_model_label,
        "candidate_model_label": candidate_model_label,
        "current_readiness": _readiness_or_incomplete_placeholder(
            label="current",
            report_paths=current_report_paths,
            min_runs=min_runs,
        ),
        "candidate_readiness": _readiness_or_incomplete_placeholder(
            label="candidate",
            report_paths=candidate_report_paths,
            min_runs=min_runs,
        ),
        "audit_failures": [_audit_failure_to_json(failure) for failure in audit_failures],
        "decision": {
            "adopted_model_label": None,
            "blocking_reasons": _audit_failure_blocking_reasons(
                current_report_count=len(current_report_paths),
                candidate_report_count=len(candidate_report_paths),
                audit_failures=audit_failures,
                min_runs=min_runs,
            ),
            "metric_deltas": {},
            "safety_failures": [
                (
                    f"{failure.model_label} run{failure.run_index} "
                    f"exited {failure.exit_code}"
                )
                for failure in audit_failures
            ],
        },
    }


def _readiness_or_incomplete_placeholder(
    *,
    label: str,
    report_paths: Sequence[Path],
    min_runs: int,
) -> dict[str, object]:
    if len(report_paths) >= min_runs:
        return build_readiness_report(report_paths=report_paths, min_runs=min_runs)
    return {
        "readiness_status": "not_ready",
        "trusted_graph_ready": False,
        "blocking_reasons": [
            _report_count_reason(
                label=label,
                report_count=len(report_paths),
                min_runs=min_runs,
            ),
        ],
        "worst_metrics": {},
        "hard_failure_counts": {},
    }


def _audit_failure_blocking_reasons(
    *,
    current_report_count: int,
    candidate_report_count: int,
    audit_failures: Sequence[_AuditRunFailure],
    min_runs: int,
) -> list[str]:
    reasons: list[str] = []
    failed_labels = {failure.model_label for failure in audit_failures}
    reasons.extend(f"{label} audit run failed." for label in sorted(failed_labels))
    if current_report_count != min_runs:
        reasons.append(
            _report_count_reason(
                label="current",
                report_count=current_report_count,
                min_runs=min_runs,
            ),
        )
    if candidate_report_count != min_runs:
        reasons.append(
            _report_count_reason(
                label="candidate",
                report_count=candidate_report_count,
                min_runs=min_runs,
            ),
        )
    return reasons


def _report_count_reason(*, label: str, report_count: int, min_runs: int) -> str:
    return (
        f"{label} report count must match --runs-per-model; "
        f"expected {min_runs}, got {report_count}."
    )


def _audit_failure_to_json(failure: _AuditRunFailure) -> dict[str, object]:
    return {
        "model_label": failure.model_label,
        "run_index": failure.run_index,
        "exit_code": failure.exit_code,
        "command": " ".join(failure.command),
    }


def _decision_count(decision: object, key: str) -> int:
    if not isinstance(decision, dict):
        return 0
    value = decision.get(key)
    return len(value) if isinstance(value, list) else 0


def _timestamped_output_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _DEFAULT_REPORT_ROOT / timestamp


if __name__ == "__main__":
    raise SystemExit(main())
