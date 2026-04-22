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
        description="Trigger a run, then inspect runs, artifacts, and workspace state.",
    )
    add_base_url_argument(parser)
    add_api_key_argument(parser)
    parser.add_argument(
        "--question",
        default="What is known about MED13?",
        help="Question to use for the graph-search run.",
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
        search = client.graph.search(question=args.question)
        runs = client.runs.list()
        run = client.runs.get(run_id=search.run.id)
        artifacts = client.artifacts.list(run_id=search.run.id)
        workspace = client.artifacts.workspace(run_id=search.run.id)

    print_heading("Run")
    print(f"run_id: {run.id}")
    print(f"harness_id: {run.harness_id}")
    print(f"status: {run.status}")
    print(f"total_runs_in_space: {runs.total}")

    print_heading("Artifacts")
    print(f"artifact_count: {artifacts.total}")
    print("artifact_keys:")
    for artifact in artifacts.artifacts:
        print(f"- {artifact.key}")

    print_heading("Workspace Snapshot Keys")
    for key in sorted(workspace.snapshot.keys()):
        print(f"- {key}")


if __name__ == "__main__":
    main()
