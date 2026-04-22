"""Rebuild the entity-neighbors read model."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

from artana_evidence_db.database import SessionLocal
from artana_evidence_db.entity_neighbors_projector import (
    KernelEntityNeighborsProjector,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from sqlalchemy.orm import Session


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild the entity_neighbors read model.",
    )
    parser.add_argument(
        "--space-id",
        type=str,
        default=None,
        help="Optional research space ID to rebuild. Rebuild all spaces when omitted.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    return parser.parse_args()


def _build_projector(session: Session) -> KernelEntityNeighborsProjector:
    return KernelEntityNeighborsProjector(session)


def run_rebuild(
    args: argparse.Namespace,
    *,
    session_factory: Callable[[], Session] | None = None,
    projector_factory: (
        Callable[[Session], KernelEntityNeighborsProjector] | None
    ) = None,
) -> int:
    effective_session_factory = session_factory or SessionLocal
    effective_projector_factory = projector_factory or _build_projector

    session = effective_session_factory()
    try:
        projector = effective_projector_factory(session)
        rebuilt_rows = projector.rebuild(space_id=args.space_id)
        session.commit()
    finally:
        session.close()

    payload = {
        "model_name": "entity_neighbors",
        "research_space_id": args.space_id,
        "rebuilt_rows": rebuilt_rows,
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            "model="
            f"{payload['model_name']} "
            f"space={payload['research_space_id'] or 'ALL'} "
            f"rebuilt_rows={payload['rebuilt_rows']}",
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    args = _parse_args()
    return run_rebuild(args)


if __name__ == "__main__":
    raise SystemExit(main())
