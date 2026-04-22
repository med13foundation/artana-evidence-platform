#!/usr/bin/env python3
"""Backfill legacy plaintext PHI identifiers into encrypted+blind-index form."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.database.session import SessionLocal
from src.infrastructure.security.phi_backfill import PHIIdentifierBackfillRunner
from src.infrastructure.security.phi_encryption import (
    build_phi_encryption_service_from_env,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Backfill legacy PHI identifier rows by encrypting identifier_value and "
            "computing identifier_blind_index in batches."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Rows to process per batch (default: 500)",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional cap on total scanned rows",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Persist changes (default is dry-run with rollback)",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    try:
        encryption_service = build_phi_encryption_service_from_env()
        runner = PHIIdentifierBackfillRunner(
            session_factory=SessionLocal,
            encryption_service=encryption_service,
        )
        summary = runner.run(
            batch_size=args.batch_size,
            max_rows=args.max_rows,
            dry_run=not args.commit,
        )
    except Exception:
        logger.exception("PHI backfill failed")
        sys.exit(1)

    mode = "COMMIT" if args.commit else "DRY-RUN"
    logger.info("PHI backfill completed [%s]", mode)
    logger.info("  batches_processed=%d", summary.batches_processed)
    logger.info("  scanned_rows=%d", summary.scanned_rows)
    logger.info("  updated_rows=%d", summary.updated_rows)
    logger.info("  skipped_rows=%d", summary.skipped_rows)
    logger.info("  failed_rows=%d", summary.failed_rows)

    if summary.failed_rows > 0:
        logger.error("Backfill completed with failures")
        sys.exit(2)


if __name__ == "__main__":  # pragma: no cover - script entrypoint
    main()
