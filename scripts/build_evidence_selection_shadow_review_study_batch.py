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

from artana_evidence_api.evidence_selection.shadow_review_study_batch import (  # noqa: E402
    EvidenceSelectionShadowReviewStudyBatchManifest,
    EvidenceSelectionShadowReviewStudyBatchRequest,
    EvidenceSelectionShadowReviewStudyBatchResult,
    EvidenceSelectionShadowReviewStudyBatchThresholds,
    build_evidence_selection_shadow_review_study_batch,
    collect_evidence_selection_shadow_review_study_batch_source_paths,
    load_evidence_selection_shadow_review_study_batch_manifest,
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
        help="Return success after writing reports even if one or more entries fail.",
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
            ),
        )
        gate_report_manifests = _write_entry_gate_reports(result)
        batch_manifest = write_evidence_selection_shadow_review_study_batch_report(
            result=result,
            output_dir=args.output_dir,
            gate_report_manifests=gate_report_manifests,
        )
    except (OSError, ValueError, TypeError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        "evidence_selection_shadow_review_study_batch "
        f"batch_id={result.batch_id} "
        f"status={'passed' if result.passed else 'failed'} "
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

    resolved_outputs = [path.resolve(strict=False) for path in output_paths]
    if len(set(resolved_outputs)) != len(resolved_outputs):
        msg = "Shadow-review batch report output paths must be unique."
        raise ValueError(msg)
    for source_path in source_paths:
        resolved_source = source_path.resolve(strict=False)
        for output_path, resolved_output in zip(
            output_paths,
            resolved_outputs,
            strict=True,
        ):
            if resolved_output == resolved_source:
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
        if output_path.exists() and output_path.is_dir():
            msg = f"Report output path must be a file: {output_path}"
            raise ValueError(msg)
        if output_path.parent.exists() and not output_path.parent.is_dir():
            msg = f"Report output parent must be a directory: {output_path.parent}"
            raise ValueError(msg)


def _add_gate_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-selection-review-count", type=int, default=3)
    parser.add_argument("--min-distinct-selection-goals", type=int, default=3)
    parser.add_argument("--min-selection-reviewer-count", type=int, default=1)
    parser.add_argument("--min-mean-precision", type=float, default=0.8)
    parser.add_argument("--min-mean-recall", type=float, default=0.8)
    parser.add_argument("--min-mean-explanation-quality", type=float, default=3.0)
    parser.add_argument("--min-source-artifact-count", type=int, default=2)
    parser.add_argument("--min-review-ranking-sample-count", type=int, default=10)
    parser.add_argument("--max-expected-calibration-error", type=float, default=0.05)
    parser.add_argument("--min-distinct-ranking-goals", type=int, default=3)
    parser.add_argument("--min-distinct-evidence-shapes", type=int, default=3)


def _thresholds_from_args(
    args: argparse.Namespace,
) -> EvidenceSelectionShadowReviewStudyBatchThresholds:
    return EvidenceSelectionShadowReviewStudyBatchThresholds(
        min_selection_review_count=args.min_selection_review_count,
        min_distinct_selection_goals=args.min_distinct_selection_goals,
        min_selection_reviewer_count=args.min_selection_reviewer_count,
        min_mean_precision=args.min_mean_precision,
        min_mean_recall=args.min_mean_recall,
        min_mean_explanation_quality=args.min_mean_explanation_quality,
        min_source_artifact_count=args.min_source_artifact_count,
        min_review_ranking_sample_count=args.min_review_ranking_sample_count,
        max_expected_calibration_error=args.max_expected_calibration_error,
        min_distinct_ranking_goals=args.min_distinct_ranking_goals,
        min_distinct_evidence_shapes=args.min_distinct_evidence_shapes,
    )


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
    if (
        manifest_path is not None
        and source_path.resolve(strict=False) == manifest_path.resolve(strict=False)
    ):
        return "manifest"
    return "source packet"


if __name__ == "__main__":
    raise SystemExit(main())
