"""Rebuild persisted derived reasoning paths."""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from src.infrastructure.platform_graph.graph_service import GraphServiceClient

from scripts._graph_service_client_support import (
    add_graph_service_connection_args,
    build_graph_service_client,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild derived reasoning paths from grounded claim chains.",
    )
    parser.add_argument(
        "--space-id",
        type=str,
        default=None,
        help="Optional research space ID to rebuild. Rebuild all spaces when omitted.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=4,
        help="Maximum number of claim-relation edges per persisted path.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON output.",
    )
    add_graph_service_connection_args(parser)
    return parser.parse_args()


def _build_client(args: argparse.Namespace) -> GraphServiceClient:
    return build_graph_service_client(args)


def run_rebuild(
    args: argparse.Namespace,
    *,
    client_factory: Callable[[argparse.Namespace], GraphServiceClient] | None = None,
) -> int:
    effective_client_factory = client_factory or _build_client
    client = effective_client_factory(args)
    try:
        response = client.rebuild_reasoning_paths(
            space_id=args.space_id,
            max_depth=max(1, min(4, int(args.max_depth))),
            replace_existing=True,
        )
    finally:
        client.close()

    payload = response.model_dump(mode="json")["summaries"]
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        for summary in payload:
            print(
                "space="
                f"{summary['research_space_id']} "
                f"eligible_claims={summary['eligible_claims']} "
                f"accepted_claim_relations={summary['accepted_claim_relations']} "
                f"rebuilt_paths={summary['rebuilt_paths']} "
                f"max_depth={summary['max_depth']}",
            )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    args = _parse_args()
    return run_rebuild(args)


if __name__ == "__main__":
    raise SystemExit(main())
