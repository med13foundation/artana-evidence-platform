#!/usr/bin/env python3
"""Rollback utility for the space-scoped discovery migration."""

from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING

from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError

from src.database.seed import (
    DEFAULT_RESEARCH_SPACE_ID_STR,
    ensure_default_research_space_seeded,
)
from src.database.session import SessionLocal
from src.models.database.data_discovery import DataDiscoverySessionModel
from src.models.database.data_source_activation import (
    ActivationScopeEnum,
    DataSourceActivationModel,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line options."""

    parser = argparse.ArgumentParser(
        description="Rollback helper that collapses space-scoped discovery artifacts.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview deletions/updates without persisting them.",
    )
    parser.add_argument(
        "--fallback-space-id",
        default=DEFAULT_RESEARCH_SPACE_ID_STR,
        help=(
            "Research space ID that will own all discovery sessions after rollback "
            "(default: Artana core space)."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console logging verbosity (default: INFO).",
    )
    return parser.parse_args()


def _delete_space_rules(session: Session) -> int:
    """Remove research-space scoped activation rules."""

    deleted = (
        session.query(DataSourceActivationModel)
        .filter(DataSourceActivationModel.scope == ActivationScopeEnum.RESEARCH_SPACE)
        .delete(synchronize_session=False)
    )
    return int(deleted or 0)


def _collapse_sessions_to_space(session: Session, fallback_space_id: str) -> int:
    """Reassign all discovery sessions to a single research space."""

    statement = (
        update(DataDiscoverySessionModel)
        .where(DataDiscoverySessionModel.research_space_id != fallback_space_id)
        .values(research_space_id=fallback_space_id)
    )
    result = session.execute(statement)
    return int(result.rowcount or 0)


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))

    session: Session | None = None
    try:
        session = SessionLocal()
        ensure_default_research_space_seeded(session)

        deleted_rules = _delete_space_rules(session)
        reassigned_sessions = _collapse_sessions_to_space(
            session,
            args.fallback_space_id,
        )

        if args.dry_run:
            session.rollback()
            logger.info(
                "[DRY RUN] Would remove %d research-space rules and reassign %d sessions "
                "to %s. No changes committed.",
                deleted_rules,
                reassigned_sessions,
                args.fallback_space_id,
            )
            return

        session.commit()
        logger.info(
            "Rollback complete: removed %d research-space rules and reassigned %d sessions "
            "to fallback space %s.",
            deleted_rules,
            reassigned_sessions,
            args.fallback_space_id,
        )
    except SQLAlchemyError as exc:
        if session is not None:
            session.rollback()
        logger.exception("Rollback failed due to database error")
        raise SystemExit(1) from exc
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    main()
