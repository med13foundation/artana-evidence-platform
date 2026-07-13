#!/usr/bin/env python3
"""Build source exports, bundle, and gate report from a completed packet."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

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
from artana_evidence_api.evidence_selection.shadow_review_completion import (  # noqa: E402
    machine_packet_sidecar_path,
)
from artana_evidence_api.evidence_selection.shadow_review_study_pipeline import (  # noqa: E402
    EvidenceSelectionShadowReviewStudyArtifactRequest,
    build_evidence_selection_shadow_review_study_artifacts,
)
from artana_evidence_api.types.common import JSONObject, json_object  # noqa: E402

from scripts.run_evidence_selection_expert_study_gate import (  # noqa: E402
    EvidenceSelectionExpertStudyRunnerThresholds,
    build_evidence_selection_expert_study_gate_report,
    write_evidence_selection_expert_study_gate_report,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Build source-export, expert-study bundle, and gate artifacts from "
            "a human-completed shadow-review packet bound to its immutable "
            "machine packet."
        ),
    )
    parser.add_argument(
        "--machine-packet",
        type=Path,
        default=None,
        help="Original machine packet JSON; defaults to <packet>.machine.json.",
    )
    parser.add_argument(
        "--packet",
        type=Path,
        required=True,
        help="Human-completed copy of the machine packet JSON file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for raw inputs, source exports, bundle, and gate report.",
    )
    parser.add_argument(
        "--adjudication-note",
        default=None,
        help="Required only for selection_and_review_ranking studies.",
    )
    parser.add_argument("--source-system", required=True)
    parser.add_argument("--export-id", required=True)
    parser.add_argument(
        "--exported-at",
        required=True,
        help="Canonical UTC timestamp in YYYY-MM-DDTHH:MM:SSZ format.",
    )
    parser.add_argument("--exporter-id", required=True)
    parser.add_argument("--redaction-statement", required=True)
    parser.add_argument(
        "--study-evidence-kind",
        choices=(
            "real_shadow_review",
            "ai_reviewer_simulation",
            "synthetic_fixture",
        ),
        required=True,
        help="Explicit origin of the completed review labels.",
    )
    parser.add_argument("--description", default=None)
    parser.add_argument(
        "--allow-failed-gate",
        action="store_true",
        help="Return success after writing artifacts even if the study gate fails.",
    )
    _add_gate_threshold_args(parser)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build artifacts, run the study gate, and return a process exit code."""

    args = parse_args(argv)
    machine_packet_path = args.machine_packet or machine_packet_sidecar_path(
        args.packet,
    )
    published_artifacts = False
    try:
        result = build_evidence_selection_shadow_review_study_artifacts(
            EvidenceSelectionShadowReviewStudyArtifactRequest(
                machine_packet=_load_json_object(machine_packet_path),
                packet=_load_json_object(args.packet),
                output_dir=args.output_dir,
                adjudication_note=args.adjudication_note,
                source_system=args.source_system,
                export_id=args.export_id,
                exported_at=args.exported_at,
                exporter_id=args.exporter_id,
                redaction_statement=args.redaction_statement,
                study_evidence_kind=args.study_evidence_kind,
                machine_packet_path=machine_packet_path,
                packet_path=args.packet,
                description=args.description,
            ),
        )
        published_artifacts = True
        gate_report = build_evidence_selection_expert_study_gate_report(
            input_path=result.bundle_path,
            thresholds=_thresholds_from_args(args),
        )
        gate_manifest = write_evidence_selection_expert_study_gate_report(
            report=gate_report,
            output_dir=args.output_dir / "gate",
        )
    except (OSError, ValueError, TypeError, ValidationError) as exc:
        if published_artifacts:
            _remove_published_study_output(args.output_dir)
        print(f"error: {cli_error_message(exc)}", file=sys.stderr)
        return 1
    gate = _object_value(gate_report, "gate")
    gate_passed = gate.get("passed") is True
    blocking_reasons = _string_list(gate.get("blocking_reasons"))
    print(
        "evidence_selection_shadow_review_study_artifacts "
        f"selection_reviews={result.selection_review_count} "
        f"review_ranking_decisions={result.review_ranking_decision_count} "
        f"source_artifacts={result.source_artifact_count} "
        f"gate_status={gate.get('status')} "
        f"blocking_reasons={len(blocking_reasons)}",
    )
    print(f"Wrote selection-review labels: {result.selection_reviews_path}")
    if result.review_ranking_path is not None:
        print(f"Wrote review-ranking study: {result.review_ranking_path}")
    print(f"Wrote selection-review export: {result.selection_export_path}")
    if result.review_ranking_export_path is not None:
        print(f"Wrote review-ranking export: {result.review_ranking_export_path}")
    print(f"Wrote expert-study bundle: {result.bundle_path}")
    print(f"Wrote gate JSON report: {gate_manifest['json_path']}")
    print(f"Wrote gate Markdown report: {gate_manifest['markdown_path']}")
    if not gate_passed and not args.allow_failed_gate:
        return 1
    return 0


def _add_gate_threshold_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--min-selection-review-count", type=int, default=3)
    parser.add_argument("--min-distinct-selection-goals", type=int, default=3)
    parser.add_argument("--min-selection-reviewer-count", type=int, default=1)
    parser.add_argument("--min-mean-precision", type=float, default=0.8)
    parser.add_argument("--min-mean-recall", type=float, default=0.8)
    parser.add_argument("--min-explanation-adequacy-rate", type=float, default=0.8)
    parser.add_argument("--min-source-artifact-count", type=int, default=1)
    parser.add_argument("--min-review-ranking-sample-count", type=int, default=10)
    parser.add_argument("--max-expected-calibration-error", type=float, default=0.05)
    parser.add_argument("--min-distinct-ranking-goals", type=int, default=3)
    parser.add_argument("--min-distinct-evidence-shapes", type=int, default=3)


def _thresholds_from_args(
    args: argparse.Namespace,
) -> EvidenceSelectionExpertStudyRunnerThresholds:
    return EvidenceSelectionExpertStudyRunnerThresholds(
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


def _load_json_object(path: Path) -> JSONObject:
    source_text = path.read_text(encoding="utf-8")
    try:
        payload = json.loads(source_text)
    except json.JSONDecodeError as exc:
        msg = f"{path} is not valid JSON: {exc.msg}."
        raise ValueError(msg) from exc
    result = json_object(payload)
    if result is None:
        msg = f"{path} does not contain a JSON object."
        raise ValueError(msg)
    return result


def _object_value(payload: Mapping[str, object], key: str) -> JSONObject:
    value = payload.get(key)
    if isinstance(value, dict):
        return dict(value)
    return {}


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _remove_published_study_output(output_dir: Path) -> None:
    """Remove an artifact handoff when its gate report could not be published."""

    shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
