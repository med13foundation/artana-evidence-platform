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
        description="Create a project space and run a scoped graph workflow inside it.",
    )
    add_base_url_argument(parser)
    add_api_key_argument(parser)
    parser.add_argument(
        "--space-name",
        default="MED13 Literature Review",
        help="Name of the project space to create.",
    )
    parser.add_argument(
        "--space-description",
        default="Private workspace for a focused MED13 evidence review.",
        help="Description for the project space.",
    )
    parser.add_argument(
        "--question",
        default="Summarize evidence for MED13-related cardiomyopathy findings.",
        help="Question to run inside the new project space.",
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
        before = client.spaces.list()
        project_space = client.spaces.create(
            name=args.space_name,
            description=args.space_description,
        )
        search = client.graph.search(
            space_id=project_space.id,
            question=args.question,
        )
        after = client.spaces.list()

    print_heading("Spaces")
    print(f"spaces_before: {before.total}")
    print(f"spaces_after: {after.total}")
    print(f"project_space_id: {project_space.id}")
    print(f"project_space_slug: {project_space.slug}")

    print_heading("Scoped Search")
    print(f"run_id: {search.run.id}")
    print(f"run_space_id: {search.run.space_id}")
    print(f"decision: {search.result.decision}")
    print(f"total_results: {search.result.total_results}")


if __name__ == "__main__":
    main()
