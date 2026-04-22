from __future__ import annotations

import argparse
import os

from _example_support import (
    add_base_url_argument,
    add_bootstrap_key_argument,
    create_client,
    print_heading,
    require_value,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Bootstrap a first Artana API key on a self-hosted deployment.",
    )
    add_base_url_argument(parser)
    add_bootstrap_key_argument(parser)
    parser.add_argument(
        "--email",
        default=os.getenv("ARTANA_EXAMPLE_EMAIL") or "developer@example.com",
        help="User email to create or resolve.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("ARTANA_EXAMPLE_USERNAME") or "developer",
        help="Username for the bootstrap user.",
    )
    parser.add_argument(
        "--full-name",
        default=os.getenv("ARTANA_EXAMPLE_FULL_NAME") or "Developer Example",
        help="Full name for the bootstrap user.",
    )
    parser.add_argument(
        "--api-key-name",
        default="Default SDK Key",
        help="Label for the newly issued API key.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    base_url = require_value(
        args.base_url,
        env_name="ARTANA_API_BASE_URL",
        help_text="Point this example at your Artana Evidence API deployment.",
    )
    bootstrap_key = require_value(
        args.bootstrap_key,
        env_name="ARTANA_BOOTSTRAP_KEY",
        help_text="Ask your self-hosted operator for the bootstrap secret.",
    )

    with create_client(base_url=base_url) as client:
        response = client.auth.bootstrap_api_key(
            bootstrap_key=bootstrap_key,
            email=args.email,
            username=args.username,
            full_name=args.full_name,
            api_key_name=args.api_key_name,
        )

    print_heading("Bootstrap Complete")
    print(f"user_email: {response.user.email}")
    print(f"api_key: {response.api_key.api_key}")
    if response.default_space is not None:
        print(f"default_space_id: {response.default_space.id}")
        print(f"default_space_slug: {response.default_space.slug}")


if __name__ == "__main__":
    main()
