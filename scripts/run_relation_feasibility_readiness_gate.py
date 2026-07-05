#!/usr/bin/env python3
"""Build a repeatability readiness gate from relation feasibility reports."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from scripts.validation.relation_feasibility.readiness import (  # noqa: E402
    build_readiness_report,
    write_readiness_report,
)

_DEFAULT_REPORT_ROOT = _REPO_ROOT / "reports" / "relation_feasibility_readiness"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Aggregate repeated strict live-agent relation feasibility reports "
            "into a trusted-graph readiness gate."
        ),
    )
    parser.add_argument(
        "--report",
        action="append",
        type=Path,
        required=True,
        help=(
            "Path to relation_feasibility_report.json, or a directory containing "
            "that file. Repeat for each strict live-agent run."
        ),
    )
    parser.add_argument(
        "--min-runs",
        type=int,
        default=3,
        help="Minimum repeated strict runs required for readiness.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to reports/relation_feasibility_readiness/<timestamp>.",
    )
    parser.add_argument(
        "--fail-on-not-ready",
        action="store_true",
        help="Exit nonzero when the readiness gate is not ready.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the readiness gate and write artifacts."""

    args = parse_args(argv)
    report_paths = tuple(_resolve_report_path(path) for path in args.report)
    output_dir = args.output_dir or _timestamped_output_dir()
    report = build_readiness_report(
        report_paths=report_paths,
        min_runs=args.min_runs,
    )
    manifest = write_readiness_report(report=report, output_dir=output_dir)
    status = report["readiness_status"]
    print(
        "relation_feasibility_readiness "
        f"status={status} "
        f"runs={report['run_count']}/{report['required_run_count']} "
        f"blocking_reasons={len(report['blocking_reasons'])}",
    )
    print(f"Wrote JSON report: {manifest['json_path']}")
    print(f"Wrote Markdown report: {manifest['markdown_path']}")
    if args.fail_on_not_ready and report.get("trusted_graph_ready") is not True:
        return 1
    return 0


def _resolve_report_path(path: Path) -> Path:
    if path.is_dir():
        return path / "relation_feasibility_report.json"
    return path


def _timestamped_output_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _DEFAULT_REPORT_ROOT / timestamp


if __name__ == "__main__":
    raise SystemExit(main())
