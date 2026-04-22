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
        description="Run a graph search in the caller's personal default space.",
    )
    add_base_url_argument(parser)
    add_api_key_argument(parser)
    parser.add_argument(
        "--question",
        default="What is known about MED13 and cardiomyopathy?",
        help="Natural-language question to send to graph search.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=10,
        help="Maximum number of graph-search results to request.",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=2,
        help="Graph traversal depth.",
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

    with create_client(base_url=base_url, api_key=api_key) as client:
        personal_space = client.spaces.ensure_default()
        response = client.graph.search(
            question=args.question,
            top_k=args.top_k,
            max_depth=args.max_depth,
        )

    print_heading("Default Space")
    print(f"space_id: {personal_space.id}")
    print(f"space_name: {personal_space.name}")

    print_heading("Graph Search")
    print(f"run_id: {response.run.id}")
    print(f"decision: {response.result.decision}")
    print(f"total_results: {response.result.total_results}")
    if response.result.results:
        top_result = response.result.results[0]
        print(f"top_entity_id: {top_result.entity_id}")
        print(f"top_entity_type: {top_result.entity_type}")
        print(f"top_label: {top_result.display_label}")
        print(f"top_summary: {top_result.support_summary}")


if __name__ == "__main__":
    main()
