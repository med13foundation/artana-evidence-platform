#!/usr/bin/env python3
"""Build a reproducible evidence-selection expert/shadow study bundle."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVICES_ROOT = _REPO_ROOT / "services"
for _path in (_REPO_ROOT, _SERVICES_ROOT):
    _path_text = str(_path)
    if _path_text not in sys.path:
        sys.path.insert(0, _path_text)

from artana_evidence_api.evidence_selection.source_exports import (  # noqa: E402
    parse_canonical_source_exported_at,
)
from artana_evidence_api.evidence_selection.study_bundle import (  # noqa: E402
    EvidenceSelectionExpertStudyBundleError,
    EvidenceSelectionExpertStudyBundleRequest,
    build_evidence_selection_expert_study_bundle,
    validate_evidence_selection_expert_study_bundle_output_path,
    write_evidence_selection_expert_study_bundle,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Build an evidence-selection expert/shadow study JSON bundle from "
            "selection-review and review-ranking source exports."
        ),
    )
    parser.add_argument("--study-id", required=True)
    parser.add_argument(
        "--study-evidence-kind",
        choices=("real_shadow_review", "synthetic_fixture"),
        required=True,
    )
    parser.add_argument(
        "--selection-reviews",
        type=Path,
        required=True,
        help="JSON export with a selection_reviews array.",
    )
    parser.add_argument(
        "--review-ranking",
        type=Path,
        required=True,
        help="JSON review-ranking calibration export.",
    )
    parser.add_argument(
        "--adjudication-log",
        type=Path,
        default=None,
        help="Optional adjudication log artifact to hash into the source manifest.",
    )
    parser.add_argument(
        "--source-system",
        default=None,
        help="Optional compatibility check; source exports are authoritative.",
    )
    parser.add_argument(
        "--export-id",
        default=None,
        help="Optional compatibility check; source exports are authoritative.",
    )
    parser.add_argument(
        "--exported-at",
        default=None,
        help=(
            "Optional compatibility check as ISO-8601, for example "
            "2026-07-07T07:00:00Z. Source exports are authoritative."
        ),
    )
    parser.add_argument(
        "--exporter-id",
        default=None,
        help="Optional compatibility check; source exports are authoritative.",
    )
    parser.add_argument(
        "--redaction-statement",
        default=None,
        help="Optional compatibility check; source exports are authoritative.",
    )
    parser.add_argument("--description", default=None)
    parser.add_argument("--selection-reviews-uri", default=None)
    parser.add_argument("--review-ranking-uri", default=None)
    parser.add_argument("--adjudication-log-uri", default=None)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output path for the expert/shadow study JSON bundle.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Build and write an expert/shadow study bundle."""

    args = parse_args(argv)
    try:
        validate_evidence_selection_expert_study_bundle_output_path(
            output_path=args.output,
            source_paths=_source_paths_from_args(args),
        )
        bundle = build_evidence_selection_expert_study_bundle(
            EvidenceSelectionExpertStudyBundleRequest(
                study_id=args.study_id,
                study_evidence_kind=args.study_evidence_kind,
                selection_reviews_path=args.selection_reviews,
                review_ranking_path=args.review_ranking,
                adjudication_log_path=args.adjudication_log,
                source_system=args.source_system,
                export_id=args.export_id,
                exported_at=(
                    _parse_exported_at(args.exported_at)
                    if args.exported_at is not None
                    else None
                ),
                exporter_id=args.exporter_id,
                redaction_statement=args.redaction_statement,
                description=args.description,
                selection_reviews_uri=args.selection_reviews_uri,
                review_ranking_uri=args.review_ranking_uri,
                adjudication_log_uri=args.adjudication_log_uri,
            ),
        )
        write_evidence_selection_expert_study_bundle(
            bundle=bundle,
            output_path=args.output,
        )
    except (EvidenceSelectionExpertStudyBundleError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    source_manifest = bundle.source_manifest
    artifact_count = (
        0 if source_manifest is None else len(source_manifest.source_artifacts)
    )
    print(
        "evidence_selection_expert_study_bundle "
        f"selection_reviews={len(bundle.selection_reviews)} "
        f"review_ranking_decisions={len(bundle.review_ranking.decisions)} "
        f"source_artifacts={artifact_count}",
    )
    print(f"Wrote bundle: {args.output}")
    return 0


def _parse_exported_at(value: str) -> datetime:
    try:
        return parse_canonical_source_exported_at(
            value,
            field_name="--exported-at",
        )
    except ValueError as exc:
        raise EvidenceSelectionExpertStudyBundleError(str(exc)) from exc


def _source_paths_from_args(args: argparse.Namespace) -> tuple[Path, ...]:
    paths = [args.selection_reviews, args.review_ranking]
    if args.adjudication_log is not None:
        paths.append(args.adjudication_log)
    return tuple(paths)


if __name__ == "__main__":
    raise SystemExit(main())
