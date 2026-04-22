"""Report relation curation-status normalization state.

Usage:
    ./venv/bin/python scripts/report_relation_status_normalization.py
    ./venv/bin/python scripts/report_relation_status_normalization.py --json-out /tmp/report.json

Exit code:
    0 when no relation row remains in PENDING_REVIEW
    1 when one or more rows remain in PENDING_REVIEW
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sqlalchemy import text

from src.database.session import SessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a relation-status normalization report "
            "(PENDING_REVIEW -> DRAFT migration verification)."
        ),
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Optional output path for a JSON report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    session = SessionLocal()
    try:
        status_rows = session.execute(
            text(
                """
                SELECT curation_status, COUNT(*) AS count
                FROM relations
                GROUP BY curation_status
                ORDER BY curation_status
                """,
            ),
        ).all()
        pending_review_count = int(
            session.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM relations
                    WHERE curation_status = 'PENDING_REVIEW'
                    """,
                ),
            ).scalar_one(),
        )
    finally:
        session.close()

    by_status: dict[str, int] = {
        str(row[0]): int(row[1]) for row in status_rows if row[0] is not None
    }
    report = {
        "status_counts": by_status,
        "pending_review_count": pending_review_count,
        "normalization_complete": pending_review_count == 0,
    }

    print("Relation status normalization report")
    print("-----------------------------------")
    for status, count in sorted(by_status.items(), key=lambda item: item[0]):
        print(f"{status}: {count}")
    print(f"PENDING_REVIEW remaining: {pending_review_count}")
    print(f"Normalization complete: {report['normalization_complete']}")

    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2, sort_keys=True))
        print(f"JSON report written to: {args.json_out}")

    return 0 if pending_review_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
