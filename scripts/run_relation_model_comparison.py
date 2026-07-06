#!/usr/bin/env python3
"""Build a model-comparison report from relation feasibility run artifacts."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
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

_DEFAULT_REPORT_ROOT = _REPO_ROOT / "reports" / "relation_model_comparison"


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
        current_reports, candidate_reports = _run_audit_group_reports(
            output_dir=output_dir,
            runs_per_model=args.runs_per_model,
            candidate_model_env_var=args.candidate_model_env_var,
        )
    else:
        current_reports = tuple(args.current_report or ())
        candidate_reports = tuple(args.candidate_report or ())
    _validate_report_count(
        label="current",
        report_paths=current_reports,
        runs_per_model=args.runs_per_model,
    )
    _validate_report_count(
        label="candidate",
        report_paths=candidate_reports,
        runs_per_model=args.runs_per_model,
    )
    report = build_model_comparison_report(
        current_model_label=args.current_model_label,
        candidate_model_label=args.candidate_model_label,
        current_report_paths=tuple(_resolve_report_path(path) for path in current_reports),
        candidate_report_paths=tuple(
            _resolve_report_path(path) for path in candidate_reports
        ),
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
) -> tuple[tuple[Path, ...], tuple[Path, ...]]:
    candidate_model = os.environ.get(candidate_model_env_var)
    if not candidate_model:
        msg = f"{candidate_model_env_var} must be set when --run-audits is used"
        raise SystemExit(msg)
    original_model = os.environ.get("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL")
    current_reports = _run_model_audits(
        output_dir=output_dir / "runs" / "current",
        runs_per_model=runs_per_model,
        model_id=original_model,
    )
    candidate_reports = _run_model_audits(
        output_dir=output_dir / "runs" / "candidate",
        runs_per_model=runs_per_model,
        model_id=candidate_model,
    )
    return current_reports, candidate_reports


def _run_model_audits(
    *,
    output_dir: Path,
    runs_per_model: int,
    model_id: str | None,
) -> tuple[Path, ...]:
    reports: list[Path] = []
    for run_index in range(1, runs_per_model + 1):
        run_dir = output_dir / f"run{run_index}"
        run_dir.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        if model_id is not None:
            env["ARTANA_AI_EVIDENCE_EXTRACTION_MODEL"] = model_id
        else:
            env.pop("ARTANA_AI_EVIDENCE_EXTRACTION_MODEL", None)
        _run_single_audit(output_dir=run_dir, env=env)
        reports.append(run_dir / "relation_feasibility_report.json")
    return tuple(reports)


def _run_single_audit(*, output_dir: Path, env: Mapping[str, str]) -> None:
    command = [
        sys.executable,
        str(_REPO_ROOT / "scripts" / "run_relation_feasibility_audit.py"),
        "--extractor",
        "agent",
        "--output-dir",
        str(output_dir),
    ]
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
