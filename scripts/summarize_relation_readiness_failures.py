#!/usr/bin/env python3
"""Summarize failure patterns across relation feasibility reports."""

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

from scripts.validation.relation_feasibility.failure_analysis import (  # noqa: E402
    FailureAnalysisInput,
    build_failure_analysis_report,
    write_failure_analysis_report,
)

_DEFAULT_REPORT_ROOT = _REPO_ROOT / "reports" / "relation_feasibility_failure_analysis"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Summarize repeated misses, false positives, CURIE gaps, proposal "
            "capture, and model comparison for relation feasibility reports."
        ),
    )
    parser.add_argument(
        "--report",
        action="append",
        required=True,
        help=(
            "Report path or MODEL_LABEL=report path. A directory is resolved to "
            "relation_feasibility_report.json."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Output directory. Defaults to "
            "reports/relation_feasibility_failure_analysis/<timestamp>."
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run failure analysis and write artifacts."""

    args = parse_args(argv)
    inputs = tuple(_parse_report_arg(raw_report) for raw_report in args.report)
    output_dir = args.output_dir or _timestamped_output_dir()
    report = build_failure_analysis_report(inputs)
    manifest = write_failure_analysis_report(report=report, output_dir=output_dir)
    print(
        "relation_feasibility_failure_analysis "
        f"runs={report['run_count']} "
        f"missed={len(report['repeated_missed_gold_relations'])} "
        f"false_positives={len(report['repeated_false_positive_candidates'])} "
        f"curie_gaps={len(report['curie_gaps'])}",
    )
    print(f"Wrote JSON report: {manifest['json_path']}")
    print(f"Wrote Markdown report: {manifest['markdown_path']}")
    return 0


def _parse_report_arg(raw_report: str) -> FailureAnalysisInput:
    model_label: str | None = None
    report_path_text = raw_report
    if "=" in raw_report:
        maybe_label, maybe_path = raw_report.split("=", 1)
        if maybe_label.strip() and maybe_path.strip():
            model_label = maybe_label.strip()
            report_path_text = maybe_path.strip()
    path = Path(report_path_text)
    return FailureAnalysisInput(path=path, model_label=model_label)


def _timestamped_output_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return _DEFAULT_REPORT_ROOT / timestamp


if __name__ == "__main__":
    raise SystemExit(main())
