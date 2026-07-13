#!/usr/bin/env python3
"""Build and gate a batch of completed shadow-review study packets."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.evidence_selection.cli_errors import (
    cli_error_message,  # noqa: E402
)
from artana_evidence_api.evidence_selection.output_paths import (
    paths_alias,  # noqa: E402
    paths_nested,  # noqa: E402
)
from artana_evidence_api.evidence_selection.shadow_review_study_batch import (  # noqa: E402
    EvidenceSelectionShadowReviewStudyBatchManifest,
    EvidenceSelectionShadowReviewStudyBatchRequest,
    EvidenceSelectionShadowReviewStudyBatchResult,
    EvidenceSelectionShadowReviewStudyBatchSuiteThresholds,
    EvidenceSelectionShadowReviewStudyBatchThresholds,
    build_evidence_selection_shadow_review_study_batch,
    collect_evidence_selection_shadow_review_study_batch_source_paths,
    load_evidence_selection_shadow_review_study_batch_manifest,
)
from artana_evidence_api.evidence_selection.shadow_review_study_batch_outputs import (  # noqa: E402
    rollback_published_batch_outputs,
)

from scripts.run_evidence_selection_expert_study_gate import (  # noqa: E402
    write_evidence_selection_expert_study_gate_report,
)

if TYPE_CHECKING:
    from artana_evidence_api.types.common import JSONObject as ServiceJSONObject

JSONObject = dict[str, object]

_BATCH_REPORT_JSON_FILENAME = "shadow-review-study-batch.json"
_BATCH_REPORT_MARKDOWN_FILENAME = "shadow-review-study-batch.md"
_GATE_REPORT_JSON_FILENAME = "evidence_selection_expert_study_gate.json"
_GATE_REPORT_MARKDOWN_FILENAME = "evidence_selection_expert_study_gate.md"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Run completed evidence-selection shadow-review packets through the "
            "source-export, expert-study bundle, and gate pipeline as a batch."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="evidence_selection_shadow_review_study_batch.v1 manifest JSON.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for per-entry artifacts and aggregate batch reports.",
    )
    parser.add_argument(
        "--allow-failed-gate",
        action="store_true",
        help=(
            "Return success after writing reports even if an entry or suite gate fails."
        ),
    )
    _add_gate_threshold_args(parser)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the batch pipeline and return a process exit code."""

    args = parse_args(argv)
    try:
        manifest = load_evidence_selection_shadow_review_study_batch_manifest(
            args.manifest,
        )
        _validate_report_output_paths(
            output_dir=args.output_dir,
            manifest=manifest,
            manifest_path=args.manifest,
            source_paths=collect_evidence_selection_shadow_review_study_batch_source_paths(
                manifest=manifest,
                manifest_path=args.manifest,
            ),
        )
        result = build_evidence_selection_shadow_review_study_batch(
            EvidenceSelectionShadowReviewStudyBatchRequest(
                manifest=manifest,
                manifest_path=args.manifest,
                output_dir=args.output_dir,
                thresholds=_thresholds_from_args(args),
                suite_thresholds=_suite_thresholds_from_args(args),
            ),
        )
        gate_report_manifests, batch_manifest = _write_reports_transactionally(
            result=result,
            output_dir=args.output_dir,
        )
    except (OSError, RuntimeError, ValueError, TypeError, ValidationError) as exc:
        print(f"error: {cli_error_message(exc)}", file=sys.stderr)
        return 1

    print(
        "evidence_selection_shadow_review_study_batch "
        f"batch_id={result.batch_id} "
        f"status={'passed' if result.passed else 'failed'} "
        f"suite_gate={result.suite_gate.get('status')} "
        f"entries={result.entry_count} "
        f"passed={result.passed_entry_count} "
        f"failed={result.failed_entry_count}",
    )
    print(f"Wrote batch JSON report: {batch_manifest['json_path']}")
    print(f"Wrote batch Markdown report: {batch_manifest['markdown_path']}")
    if not result.passed and not args.allow_failed_gate:
        return 1
    return 0


def render_evidence_selection_shadow_review_study_batch_markdown(
    report: JSONObject,
) -> str:
    """Render a completed shadow-review batch report as Markdown."""

    passed = report.get("passed") is True
    status = "PASSED" if passed else "FAILED"
    lines = [
        "# Evidence Selection Shadow Review Study Batch",
        "",
        f"- Batch: `{report.get('batch_id')}`",
        f"- Status: **{status}**",
        f"- Entry count: {report.get('entry_count')}",
        f"- Passed entries: {report.get('passed_entry_count')}",
        f"- Failed entries: {report.get('failed_entry_count')}",
        "",
        "## Suite Gate",
        "",
        f"- Status: **{_suite_gate_status(report)}**",
        f"- Blocking reasons: {_suite_gate_blocking_reason_text(report)}",
        f"- Production floor applied: {_suite_gate_production_floor_applied(report)}",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        *_suite_gate_summary_rows(report),
        "",
        "## Suite Thresholds",
        "",
        "| Threshold | Requested | Enforced |",
        "| --- | ---: | ---: |",
        *_suite_gate_threshold_rows(report),
        "",
        "## Entries",
        "",
        "| Entry | Gate | Blocking Reasons | Bundle |",
        "| --- | --- | --- | --- |",
    ]
    for entry in _entry_reports(report):
        gate_status = "PASSED" if entry.get("gate_passed") is True else "FAILED"
        blocking_reasons = _string_list(entry.get("blocking_reasons"))
        reason_text = "; ".join(blocking_reasons) if blocking_reasons else "none"
        paths = entry.get("paths")
        bundle_path = ""
        if isinstance(paths, dict):
            bundle = paths.get("bundle")
            if isinstance(bundle, str):
                bundle_path = bundle
        lines.append(
            "| "
            f"{_table_text(entry.get('entry_id'))} | "
            f"{gate_status} | "
            f"{_table_text(reason_text)} | "
            f"`{bundle_path}` |",
        )
    return "\n".join(lines) + "\n"


def write_evidence_selection_shadow_review_study_batch_report(
    *,
    result: EvidenceSelectionShadowReviewStudyBatchResult,
    output_dir: Path,
    gate_report_manifests: dict[str, JSONObject],
) -> JSONObject:
    """Write aggregate JSON and Markdown reports for the batch."""

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / _BATCH_REPORT_JSON_FILENAME
    markdown_path = output_dir / _BATCH_REPORT_MARKDOWN_FILENAME
    service_gate_report_manifests = cast(
        "Mapping[str, ServiceJSONObject]",
        gate_report_manifests,
    )
    report = cast(
        "JSONObject",
        result.to_json(gate_report_manifests=service_gate_report_manifests),
    )
    json_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(
        render_evidence_selection_shadow_review_study_batch_markdown(report),
        encoding="utf-8",
    )
    return {
        "json_path": str(json_path),
        "markdown_path": str(markdown_path),
    }


def _write_reports_transactionally(
    *,
    result: EvidenceSelectionShadowReviewStudyBatchResult,
    output_dir: Path,
) -> tuple[dict[str, JSONObject], JSONObject]:
    try:
        gate_report_manifests = _write_entry_gate_reports(result)
        batch_manifest = write_evidence_selection_shadow_review_study_batch_report(
            result=result,
            output_dir=output_dir,
            gate_report_manifests=gate_report_manifests,
        )
    except Exception:
        try:
            _remove_batch_report_outputs(output_dir)
            rollback_published_batch_outputs(
                entry_output_dirs=tuple(entry.output_dir for entry in result.entries),
                batch_output_dir=output_dir,
                remove_empty_batch_output_dir=False,
            )
        except OSError as cleanup_error:
            msg = (
                "Shadow-review batch report publication failed and published "
                "outputs could not be rolled back."
            )
            raise RuntimeError(msg) from cleanup_error
        raise
    return gate_report_manifests, batch_manifest


def _remove_batch_report_outputs(output_dir: Path) -> None:
    for filename in (_BATCH_REPORT_JSON_FILENAME, _BATCH_REPORT_MARKDOWN_FILENAME):
        path = output_dir / filename
        if path.is_file() or path.is_symlink():
            path.unlink()


def _write_entry_gate_reports(
    result: EvidenceSelectionShadowReviewStudyBatchResult,
) -> dict[str, JSONObject]:
    manifests: dict[str, JSONObject] = {}
    for entry in result.entries:
        manifests[entry.entry_id] = write_evidence_selection_expert_study_gate_report(
            report=cast("JSONObject", entry.gate_report),
            output_dir=entry.output_dir / "gate",
        )
    return manifests


def _validate_report_output_paths(
    *,
    output_dir: Path,
    manifest: EvidenceSelectionShadowReviewStudyBatchManifest,
    manifest_path: Path | None,
    source_paths: tuple[Path, ...],
) -> None:
    output_paths = [
        output_dir / _BATCH_REPORT_JSON_FILENAME,
        output_dir / _BATCH_REPORT_MARKDOWN_FILENAME,
    ]
    for entry in manifest.entries:
        gate_dir = output_dir / entry.output_subdir / "gate"
        output_paths.append(gate_dir / _GATE_REPORT_JSON_FILENAME)
        output_paths.append(gate_dir / _GATE_REPORT_MARKDOWN_FILENAME)

    if any(
        paths_alias(left, right) or paths_nested(left, right)
        for index, left in enumerate(output_paths)
        for right in output_paths[index + 1 :]
    ):
        msg = "Shadow-review batch report output paths must be unique and not nested."
        raise ValueError(msg)
    for source_path in source_paths:
        for output_path in output_paths:
            if paths_alias(output_path, source_path):
                source_label = _source_path_label(
                    source_path=source_path,
                    manifest_path=manifest_path,
                )
                msg = (
                    f"Shadow-review batch reports must not overwrite {source_label}: "
                    f"{output_path} matches {source_path}."
                )
                raise ValueError(msg)
    for output_path in output_paths:
        if output_path.exists():
            msg = (
                f"Report output path must be a file: {output_path}"
                if output_path.is_dir()
                else (
                    "Shadow-review batch reports must not overwrite existing "
                    f"output: {output_path}."
                )
            )
            raise ValueError(msg)
        if output_path.parent.exists() and not output_path.parent.is_dir():
            msg = f"Report output parent must be a directory: {output_path.parent}"
            raise ValueError(msg)


def _add_gate_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-selection-review-count", type=int, default=1)
    parser.add_argument("--min-distinct-selection-goals", type=int, default=1)
    parser.add_argument("--min-selection-reviewer-count", type=int, default=1)
    parser.add_argument("--min-mean-precision", type=float, default=0.8)
    parser.add_argument("--min-mean-recall", type=float, default=0.8)
    parser.add_argument("--min-explanation-adequacy-rate", type=float, default=0.8)
    parser.add_argument("--min-source-artifact-count", type=int, default=1)
    parser.add_argument("--min-review-ranking-sample-count", type=int, default=2)
    parser.add_argument("--max-expected-calibration-error", type=float, default=0.05)
    parser.add_argument("--min-distinct-ranking-goals", type=int, default=1)
    parser.add_argument("--min-distinct-evidence-shapes", type=int, default=1)
    parser.add_argument("--min-batch-entry-count", type=int, default=3)
    parser.add_argument("--min-batch-passed-entry-count", type=int, default=3)
    parser.add_argument("--max-batch-failed-entry-count", type=int, default=0)
    parser.add_argument("--min-batch-passed-entry-rate", type=float, default=1.0)
    parser.add_argument("--min-batch-mean-precision", type=float, default=0.8)
    parser.add_argument("--min-batch-mean-recall", type=float, default=0.8)
    parser.add_argument(
        "--min-batch-explanation-adequacy-rate",
        type=float,
        default=0.8,
    )
    parser.add_argument(
        "--max-batch-expected-calibration-error",
        type=float,
        default=0.05,
    )
    parser.add_argument("--min-batch-total-selection-review-count", type=int, default=3)
    parser.add_argument(
        "--min-batch-total-review-ranking-decision-count",
        type=int,
        default=10,
    )
    parser.add_argument("--min-batch-distinct-source-run-ids", type=int, default=3)
    parser.add_argument("--min-batch-distinct-study-ids", type=int, default=3)
    parser.add_argument("--min-batch-distinct-selection-goals", type=int, default=3)
    parser.add_argument(
        "--min-batch-distinct-review-ranking-goals",
        type=int,
        default=3,
    )
    parser.add_argument("--min-batch-distinct-evidence-shapes", type=int, default=3)


def _thresholds_from_args(
    args: argparse.Namespace,
) -> EvidenceSelectionShadowReviewStudyBatchThresholds:
    return EvidenceSelectionShadowReviewStudyBatchThresholds(
        min_selection_review_count=args.min_selection_review_count,
        min_distinct_selection_goals=args.min_distinct_selection_goals,
        min_selection_reviewer_count=args.min_selection_reviewer_count,
        min_mean_precision=args.min_mean_precision,
        min_mean_recall=args.min_mean_recall,
        min_explanation_adequacy_rate=args.min_explanation_adequacy_rate,
        min_source_artifact_count=args.min_source_artifact_count,
        min_review_ranking_sample_count=args.min_review_ranking_sample_count,
        max_expected_calibration_error=args.max_expected_calibration_error,
        min_distinct_ranking_goals=args.min_distinct_ranking_goals,
        min_distinct_evidence_shapes=args.min_distinct_evidence_shapes,
    )


def _suite_thresholds_from_args(
    args: argparse.Namespace,
) -> EvidenceSelectionShadowReviewStudyBatchSuiteThresholds:
    return EvidenceSelectionShadowReviewStudyBatchSuiteThresholds(
        min_entry_count=args.min_batch_entry_count,
        min_passed_entry_count=args.min_batch_passed_entry_count,
        max_failed_entry_count=args.max_batch_failed_entry_count,
        min_passed_entry_rate=args.min_batch_passed_entry_rate,
        min_suite_mean_precision=args.min_batch_mean_precision,
        min_suite_mean_recall=args.min_batch_mean_recall,
        min_suite_explanation_adequacy_rate=(args.min_batch_explanation_adequacy_rate),
        max_suite_expected_calibration_error=(
            args.max_batch_expected_calibration_error
        ),
        min_total_selection_review_count=(args.min_batch_total_selection_review_count),
        min_total_review_ranking_decision_count=(
            args.min_batch_total_review_ranking_decision_count
        ),
        min_distinct_source_run_ids=args.min_batch_distinct_source_run_ids,
        min_distinct_study_ids=args.min_batch_distinct_study_ids,
        min_distinct_selection_goals=args.min_batch_distinct_selection_goals,
        min_distinct_review_ranking_goals=(
            args.min_batch_distinct_review_ranking_goals
        ),
        min_distinct_evidence_shapes=args.min_batch_distinct_evidence_shapes,
    )


def _suite_gate_status(report: JSONObject) -> str:
    suite_gate = report.get("suite_gate")
    if not isinstance(suite_gate, dict):
        return "MISSING"
    return "PASSED" if suite_gate.get("passed") is True else "FAILED"


def _suite_gate_blocking_reason_text(report: JSONObject) -> str:
    suite_gate = report.get("suite_gate")
    if not isinstance(suite_gate, dict):
        return "suite gate missing"
    reasons = _string_list(suite_gate.get("blocking_reasons"))
    return "; ".join(reasons) if reasons else "none"


def _suite_gate_production_floor_applied(report: JSONObject) -> str:
    suite_gate = report.get("suite_gate")
    if not isinstance(suite_gate, dict):
        return "unknown"
    production_floor_applied = suite_gate.get("production_floor_applied")
    if production_floor_applied is True:
        return "yes"
    if production_floor_applied is False:
        return "no"
    return "unknown"


def _suite_gate_summary_rows(report: JSONObject) -> list[str]:
    suite_gate = report.get("suite_gate")
    if not isinstance(suite_gate, dict):
        return []
    summary = suite_gate.get("summary")
    if not isinstance(summary, dict):
        return []
    labels = (
        ("entry_count", "Entry count"),
        ("passed_entry_count", "Passed entries"),
        ("failed_entry_count", "Failed entries"),
        ("passed_entry_rate", "Passed-entry rate"),
        ("suite_mean_precision", "Passed-entry production mean precision"),
        ("suite_mean_recall", "Passed-entry production mean recall"),
        (
            "suite_explanation_adequacy_rate",
            "Passed-entry production explanation adequacy rate",
        ),
        (
            "max_review_ranking_expected_calibration_error",
            "Passed-entry production max ranking ECE",
        ),
        ("total_selection_review_count", "Total selection reviews"),
        (
            "total_review_ranking_decision_count",
            "Total review-ranking decisions",
        ),
        ("distinct_source_run_id_count", "Distinct source run IDs"),
        ("distinct_study_id_count", "Distinct study IDs"),
        ("distinct_selection_goal_count", "Distinct selection goals"),
        ("distinct_review_ranking_goal_count", "Distinct ranking goals"),
        ("distinct_evidence_shape_count", "Distinct evidence shapes"),
    )
    rows = [
        f"| {_table_text(label)} | {_table_text(summary.get(key))} |"
        for key, label in labels
        if key in summary
    ]
    rows.extend(
        _quality_view_rows(
            summary=summary,
            key="all_entry_observed_quality",
            label_prefix="All-entry observed",
        ),
    )
    return rows


def _quality_view_rows(
    *,
    summary: Mapping[str, object],
    key: str,
    label_prefix: str,
) -> list[str]:
    quality = summary.get(key)
    if not isinstance(quality, dict):
        return []
    labels = (
        ("suite_mean_precision", "mean precision"),
        ("suite_mean_recall", "mean recall"),
        ("suite_explanation_adequacy_rate", "explanation adequacy rate"),
        ("max_review_ranking_expected_calibration_error", "max ranking ECE"),
    )
    return [
        f"| {_table_text(f'{label_prefix} {label}')} | "
        f"{_table_text(quality.get(metric))} |"
        for metric, label in labels
        if metric in quality
    ]


def _suite_gate_threshold_rows(report: JSONObject) -> list[str]:
    suite_gate = report.get("suite_gate")
    if not isinstance(suite_gate, dict):
        return []
    requested = suite_gate.get("requested_thresholds")
    enforced = suite_gate.get("thresholds")
    if not isinstance(requested, dict) or not isinstance(enforced, dict):
        return []
    return [
        "| "
        f"{_table_text(key)} | "
        f"{_table_text(requested.get(key))} | "
        f"{_table_text(enforced.get(key))} |"
        for key in sorted(enforced)
    ]


def _entry_reports(report: JSONObject) -> list[JSONObject]:
    entries = report.get("entries")
    if not isinstance(entries, list):
        return []
    return [dict(entry) for entry in entries if isinstance(entry, dict)]


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _table_text(value: object) -> str:
    return str(value).replace("|", "\\|")


def _source_path_label(*, source_path: Path, manifest_path: Path | None) -> str:
    if manifest_path is not None and source_path.resolve(
        strict=False
    ) == manifest_path.resolve(strict=False):
        return "manifest"
    return "source packet"


if __name__ == "__main__":
    raise SystemExit(main())
