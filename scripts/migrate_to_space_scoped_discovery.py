#!/usr/bin/env python3
"""Data migration utility for space-scoped discovery.

This script enforces the production rollout requirements described in
``docs/sandboxing_plan.md`` Phase 6:

* Every research space receives deterministic source permissions.
* Existing discovery sessions without a `research_space_id` are aligned to
  the default Artana research space (a safe fallback space).
* Admin teams gain a repeatable process for preparing lower environments
  before enabling the feature flag in production.

Usage examples::

    # Apply the migration with default settings (clinvar available, others blocked)
    ./scripts/migrate_to_space_scoped_discovery.py

    # Preview changes without persisting them
    ./scripts/migrate_to_space_scoped_discovery.py --dry-run

    # Allow additional sources by default
    ./scripts/migrate_to_space_scoped_discovery.py --available-source clinvar --available-source hpo
"""

from __future__ import annotations

import argparse
import logging
from typing import TYPE_CHECKING, Final

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from src.database.seed import (
    DEFAULT_RESEARCH_SPACE_ID_STR,
    SYSTEM_USER_ID_STR,
    ensure_default_research_space_seeded,
)
from src.database.session import SessionLocal
from src.models.database.data_discovery import (
    DataDiscoverySessionModel,
    SourceCatalogEntryModel,
)
from src.models.database.data_source_activation import (
    ActivationScopeEnum,
    DataSourceActivationModel,
    PermissionLevelEnum,
)
from src.models.database.research_space import ResearchSpaceModel

if TYPE_CHECKING:
    from collections.abc import Iterable

    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Conservative default: only ClinVar is available everywhere out of the gate.
DEFAULT_AVAILABLE_SOURCES: Final[frozenset[str]] = frozenset({"clinvar"})


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the migration."""

    parser = argparse.ArgumentParser(
        description="Prepare existing data for space-scoped discovery rollout.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the migration without persisting any changes.",
    )
    parser.add_argument(
        "--available-source",
        action="append",
        default=None,
        help=(
            "Catalog entry ID that should default to 'available' for all spaces. "
            "May be specified multiple times. Defaults to only 'clinvar'."
        ),
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Configure console logging verbosity (default: INFO).",
    )
    return parser.parse_args()


def _resolve_available_sources(args: argparse.Namespace) -> frozenset[str]:
    if args.available_source:
        normalized = {
            source_id.strip() for source_id in args.available_source if source_id
        }
        return frozenset(source for source in normalized if source)
    return DEFAULT_AVAILABLE_SOURCES


def _assign_missing_session_spaces(session: Session) -> int:
    """Assign legacy sessions (if any) to the default research space."""

    pending_sessions = (
        session.query(DataDiscoverySessionModel)
        .filter(DataDiscoverySessionModel.research_space_id.is_(None))
        .all()
    )
    for session_model in pending_sessions:
        session_model.research_space_id = DEFAULT_RESEARCH_SPACE_ID_STR
    return len(pending_sessions)


def _list_active_source_ids(session: Session) -> list[str]:
    """Return active catalog entry identifiers."""

    result = session.execute(
        select(SourceCatalogEntryModel.id).where(
            SourceCatalogEntryModel.is_active.is_(True),
        ),
    )
    return [row[0] for row in result]


def _list_research_space_ids(session: Session) -> list[str]:
    """Return identifiers for all research spaces."""

    result = session.execute(select(ResearchSpaceModel.id))
    return [row[0] for row in result]


def _ensure_space_permissions(
    session: Session,
    *,
    space_ids: Iterable[str],
    source_ids: Iterable[str],
    default_available: frozenset[str],
) -> int:
    """Create per-space activation policies when none exist."""

    created_rules = 0
    for space_id in space_ids:
        existing_rules = {
            rule.catalog_entry_id
            for rule in session.query(DataSourceActivationModel)
            .filter(
                DataSourceActivationModel.scope == ActivationScopeEnum.RESEARCH_SPACE,
            )
            .filter(DataSourceActivationModel.research_space_id == space_id)
            .all()
        }

        for source_id in source_ids:
            if source_id in existing_rules:
                continue

            permission_level = (
                PermissionLevelEnum.AVAILABLE
                if source_id in default_available
                else PermissionLevelEnum.BLOCKED
            )
            session.add(
                DataSourceActivationModel(
                    catalog_entry_id=source_id,
                    scope=ActivationScopeEnum.RESEARCH_SPACE,
                    research_space_id=space_id,
                    permission_level=permission_level,
                    is_active=permission_level != PermissionLevelEnum.BLOCKED,
                    updated_by=SYSTEM_USER_ID_STR,
                ),
            )
            created_rules += 1
    return created_rules


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))
    available_sources = _resolve_available_sources(args)

    session: Session | None = None
    try:
        session = SessionLocal()
        ensure_default_research_space_seeded(session)

        reassigned_sessions = _assign_missing_session_spaces(session)
        space_ids = _list_research_space_ids(session)
        source_ids = _list_active_source_ids(session)
        created_rules = _ensure_space_permissions(
            session,
            space_ids=space_ids,
            source_ids=source_ids,
            default_available=available_sources,
        )

        if args.dry_run:
            session.rollback()
            logger.info(
                "[DRY RUN] Prepared %d session updates and %d new permission rules. "
                "No changes were committed.",
                reassigned_sessions,
                created_rules,
            )
            return

        session.commit()
        logger.info(
            "Migration complete: %d sessions aligned to the default research space, "
            "%d new permission rules created across %d spaces (default-available sources: %s).",
            reassigned_sessions,
            created_rules,
            len(space_ids),
            ", ".join(sorted(available_sources)) or "none",
        )
    except SQLAlchemyError as exc:
        if session is not None:
            session.rollback()
        logger.exception("Migration failed due to a database error")
        raise SystemExit(1) from exc
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    main()
