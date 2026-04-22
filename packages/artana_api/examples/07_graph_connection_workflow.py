from __future__ import annotations

import argparse

from _example_support import (
    add_api_key_argument,
    add_base_url_argument,
    create_client,
    print_heading,
    require_value,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a graph connection workflow from one seed entity.",
    )
    add_base_url_argument(parser)
    add_api_key_argument(parser)
    parser.add_argument(
        "--seed-entity-id",
        default="11111111-1111-1111-1111-111111111111",
        help="UUID of the seed entity to explore from.",
    )
    parser.add_argument(
        "--source-type",
        default="pubmed",
        help="Source type to send to the graph-connection workflow.",
    )
    parser.add_argument(
        "--relation-type",
        action="append",
        dest="relation_types",
        default=["ASSOCIATED_WITH"],
        help=(
            "Relation type filter. Repeat the flag for multiple values. "
            "Defaults to ASSOCIATED_WITH."
        ),
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Graph traversal depth for relation discovery.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    base_url = require_value(
        args.base_url,
        env_name="ARTANA_API_BASE_URL",
        help_text="This example needs a reachable Artana API URL.",
    )
    api_key = require_value(
        args.api_key,
        env_name="ARTANA_API_KEY",
        help_text="Run the bootstrap example first if you do not have an API key.",
    )

    relation_types = list(dict.fromkeys(args.relation_types))

    with create_client(base_url=base_url, api_key=api_key) as client:
        response = client.graph.connect(
            seed_entity_ids=[args.seed_entity_id],
            source_type=args.source_type,
            relation_types=relation_types,
            max_depth=args.max_depth,
        )

    print_heading("Graph Connection")
    print(f"run_id: {response.run.id}")
    print(f"run_space_id: {response.run.space_id}")
    print(f"outcome_count: {len(response.outcomes)}")

    if response.outcomes:
        outcome = response.outcomes[0]
        print(f"seed_entity_id: {outcome.seed_entity_id}")
        print(f"decision: {outcome.decision}")
        print(f"proposed_relation_count: {len(outcome.proposed_relations)}")
        if outcome.proposed_relations:
            relation = outcome.proposed_relations[0]
            print(f"relation_type: {relation.relation_type}")
            print(f"target_id: {relation.target_id}")
            print(f"confidence: {relation.confidence}")


if __name__ == "__main__":
    main()
