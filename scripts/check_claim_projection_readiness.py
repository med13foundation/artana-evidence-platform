"""Audit and optionally repair claim-backed projection readiness."""

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
        description=(
            "Check global readiness for claim-backed canonical relation projections."
        ),
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=10,
        help="Maximum number of sampled rows per readiness issue.",
    )
    parser.add_argument(
        "--repair",
        action="store_true",
        help="Attempt automatic repair before evaluating final readiness.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="When combined with --repair, perform repair logic without committing.",
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


def run_readiness_check(
    args: argparse.Namespace,
    *,
    client_factory: Callable[[argparse.Namespace], GraphServiceClient] | None = None,
) -> int:
    effective_client_factory = client_factory or _build_client
    client = effective_client_factory(args)
    try:
        repair_summary = None
        if args.repair:
            repair_summary = client.repair_projections(dry_run=args.dry_run)
        report = client.get_projection_readiness(
            sample_limit=max(1, int(args.sample_limit)),
        )
    finally:
        client.close()

    payload = report.model_dump(mode="json")
    payload["repair_summary"] = (
        repair_summary.model_dump(mode="json") if repair_summary is not None else None
    )

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"ready={payload['ready']}")
        for key in (
            "orphan_relations",
            "missing_claim_participants",
            "missing_claim_evidence",
            "linked_relation_mismatches",
            "invalid_projection_relations",
        ):
            issue = payload[key]
            print(f"{key}={issue['count']}")
            for sample in issue["samples"]:
                print(
                    "  - "
                    f"space={sample['research_space_id']} "
                    f"claim={sample['claim_id']} "
                    f"relation={sample['relation_id']} "
                    f"detail={sample['detail']}",
                )
        if payload["repair_summary"] is not None:
            repair = payload["repair_summary"]
            print(
                "repair="
                f"dry_run={repair['dry_run']} "
                f"materialized={repair['materialized_claims']} "
                f"detached={repair['detached_claims']} "
                f"unresolved={repair['unresolved_claims']}",
            )
    return 0 if report.ready else 1


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    args = _parse_args()
    return run_readiness_check(args)


if __name__ == "__main__":
    raise SystemExit(main())
