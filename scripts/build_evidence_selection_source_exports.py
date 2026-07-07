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

from artana_evidence_api.evidence_selection.source_export_writer import (  # noqa: E402
    EvidenceSelectionSourceExportWriteRequest,
    EvidenceSelectionSourceExportWriterError,
    write_evidence_selection_source_exports,
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Build self-describing selection-review and review-ranking source "
            "exports for an evidence-selection expert/shadow study."
        ),
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
        required=True,
        help="JSON review-ranking calibration study input.",
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
        required=True,
        help="Output path for the self-describing review-ranking export.",
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
        result = write_evidence_selection_source_exports(
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
    except (EvidenceSelectionSourceExportWriterError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        "evidence_selection_source_exports "
        f"selection_reviews={result.selection_review_count} "
        f"review_ranking_decisions={result.review_ranking_decision_count}",
    )
    print(f"Wrote selection-review export: {result.selection_export_path}")
    print(f"Wrote review-ranking export: {result.review_ranking_export_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
