"""Reconcile platform research spaces into the standalone graph service."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID


def _ensure_repo_root_on_path(script_path: str | Path | None = None) -> None:
    """Allow direct script execution without relying on editable installs."""
    resolved_script_path = Path(script_path) if script_path else Path(__file__)
    repo_root = resolved_script_path.resolve().parent.parent
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)


_ensure_repo_root_on_path()

from src.application.services.space_lifecycle_sync_service import (
    SpaceLifecycleSyncService,
)
from src.database.session import SessionLocal
from src.domain.entities.research_space import SpaceStatus
from src.infrastructure.platform_graph.graph_service.space_lifecycle_sync import (
    GraphServiceSpaceLifecycleSync,
)
from src.infrastructure.repositories import SqlAlchemyResearchSpaceRepository
from src.infrastructure.repositories.research_space_membership_repository import (
    SqlAlchemyResearchSpaceMembershipRepository,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def _parse_statuses(values: list[str] | None) -> tuple[SpaceStatus, ...]:
    if not values:
        return (
            SpaceStatus.ACTIVE,
            SpaceStatus.INACTIVE,
            SpaceStatus.ARCHIVED,
            SpaceStatus.SUSPENDED,
        )

    return tuple(SpaceStatus(value.lower()) for value in values)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync platform space and membership state into the graph service.",
    )
    parser.add_argument(
        "--space-id",
        type=str,
        default=None,
        help="Optional single space ID to sync.",
    )
    parser.add_argument(
        "--status",
        action="append",
        default=None,
        help=(
            "Restrict bulk sync to one lifecycle status. "
            "Repeat to include multiple statuses."
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of spaces to load per status page during bulk sync.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    return parser.parse_args()


def _build_service() -> SpaceLifecycleSyncService:
    session = SessionLocal()
    return SpaceLifecycleSyncService(
        research_space_repository=SqlAlchemyResearchSpaceRepository(session=session),
        space_lifecycle_sync=GraphServiceSpaceLifecycleSync(
            membership_repository=SqlAlchemyResearchSpaceMembershipRepository(
                session=session,
            ),
        ),
    )


def run_sync(
    args: argparse.Namespace,
    *,
    service_factory: Callable[[], SpaceLifecycleSyncService] | None = None,
) -> int:
    effective_service_factory = service_factory or _build_service
    service = effective_service_factory()
    statuses = _parse_statuses(args.status)
    try:
        summary = service.sync_spaces(
            space_id=UUID(args.space_id) if args.space_id else None,
            statuses=statuses,
            batch_size=max(1, int(args.batch_size)),
        )
    finally:
        session = getattr(getattr(service, "_space_repository", None), "session", None)
        if session is not None:
            session.close()

    payload = {
        "total_spaces": summary.total_spaces,
        "synced_space_ids": [str(space_id) for space_id in summary.synced_space_ids],
        "statuses": list(summary.statuses),
        "batch_size": summary.batch_size,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "spaces="
            f"{payload['total_spaces']} "
            f"statuses={','.join(payload['statuses'])} "
            f"batch_size={payload['batch_size']}",
        )
        for space_id in payload["synced_space_ids"]:
            print(f"  - space={space_id}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    args = _parse_args()
    return run_sync(args)


if __name__ == "__main__":
    raise SystemExit(main())
