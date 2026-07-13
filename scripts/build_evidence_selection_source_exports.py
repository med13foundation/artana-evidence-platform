#!/usr/bin/env python3
"""Build self-describing evidence-selection source export files."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
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
from artana_evidence_api.evidence_selection.source_export_writer import (  # noqa: E402
    EvidenceSelectionReviewExportWriteRequest,
    EvidenceSelectionSourceExportWriteRequest,
    EvidenceSelectionSourceExportWriterError,
    write_evidence_selection_review_export,
    write_evidence_selection_source_exports,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Build self-describing source exports for a selection-only or "
            "selection-and-review-ranking expert/shadow study."
        ),
    )
    parser.add_argument(
        "--study-type",
        choices=("selection_relevance", "selection_and_review_ranking"),
        required=True,
    )
    parser.add_argument(
        "--selection-reviews",
        type=Path,
        required=True,
        help="JSON input with a selection_reviews array.",
    )
    parser.add_argument(
        "--review-ranking",
        type=Path,
        default=None,
        help="Required only for selection_and_review_ranking studies.",
    )
    parser.add_argument(
        "--selection-export-output",
        type=Path,
        required=True,
        help="Output path for the self-describing selection-review export.",
    )
    parser.add_argument(
        "--review-ranking-export-output",
        type=Path,
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
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Write source exports and return a process-style exit code."""

    args = parse_args(argv)
    try:
        selection_review_count, review_ranking_decision_count = _write_exports(args)
    except (EvidenceSelectionSourceExportWriterError, ValidationError) as exc:
        print(f"error: {cli_error_message(exc)}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_source_exports "
        f"selection_reviews={selection_review_count} "
        f"review_ranking_decisions={review_ranking_decision_count}",
    )
    print(f"Wrote selection-review export: {args.selection_export_output}")
    if args.review_ranking_export_output is not None:
        print(f"Wrote review-ranking export: {args.review_ranking_export_output}")
    return 0


def _write_exports(args: argparse.Namespace) -> tuple[int, int]:
    if args.study_type == "selection_relevance":
        if (
            args.review_ranking is not None
            or args.review_ranking_export_output is not None
        ):
            msg = "selection_relevance studies must not set review-ranking paths."
            raise EvidenceSelectionSourceExportWriterError(msg)
        selection_result = write_evidence_selection_review_export(
            EvidenceSelectionReviewExportWriteRequest(
                selection_reviews_path=args.selection_reviews,
                selection_export_path=args.selection_export_output,
                source_system=args.source_system,
                export_id=args.export_id,
                exported_at=args.exported_at,
                exporter_id=args.exporter_id,
                redaction_statement=args.redaction_statement,
            ),
        )
        return selection_result.selection_review_count, 0
    if args.review_ranking is None or args.review_ranking_export_output is None:
        msg = (
            "selection_and_review_ranking studies require --review-ranking and "
            "--review-ranking-export-output."
        )
        raise EvidenceSelectionSourceExportWriterError(msg)
    combined_result = write_evidence_selection_source_exports(
        EvidenceSelectionSourceExportWriteRequest(
            selection_reviews_path=args.selection_reviews,
            review_ranking_path=args.review_ranking,
            selection_export_path=args.selection_export_output,
            review_ranking_export_path=args.review_ranking_export_output,
            source_system=args.source_system,
            export_id=args.export_id,
            exported_at=args.exported_at,
            exporter_id=args.exporter_id,
            redaction_statement=args.redaction_statement,
        ),
    )
    return (
        combined_result.selection_review_count,
        combined_result.review_ranking_decision_count,
    )


if __name__ == "__main__":
    raise SystemExit(main())
