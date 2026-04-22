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
        description="Check service health and inspect the current Artana identity.",
    )
    add_base_url_argument(parser)
    add_api_key_argument(parser)
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
        health = client.health()
        auth_context = client.auth.me()

    print_heading("Service Health")
    print(f"status: {health.status}")
    print(f"version: {health.version}")

    print_heading("Current Identity")
    print(f"user_id: {auth_context.user.id}")
    print(f"email: {auth_context.user.email}")
    print(f"role: {auth_context.user.role}")
    if auth_context.default_space is not None:
        print(f"default_space_id: {auth_context.default_space.id}")
        print(f"default_space_name: {auth_context.default_space.name}")


if __name__ == "__main__":
    main()
