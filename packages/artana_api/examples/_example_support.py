from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import NoReturn

EXAMPLES_DIR = Path(__file__).resolve().parent
SDK_SRC = EXAMPLES_DIR.parent / "src"

if str(SDK_SRC) not in sys.path:
    sys.path.insert(0, str(SDK_SRC))

from artana_api import ArtanaClient


def require_value(value: str | None, *, env_name: str, help_text: str) -> str:
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    message = (
        f"Missing required value. Set {env_name} or pass it explicitly. {help_text}"
    )
    raise SystemExit(message)


def add_base_url_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--base-url",
        default=os.getenv("ARTANA_API_BASE_URL") or os.getenv("ARTANA_BASE_URL"),
        help="Artana API base URL. Defaults to ARTANA_API_BASE_URL.",
    )


def add_api_key_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--api-key",
        default=os.getenv("ARTANA_API_KEY"),
        help="Artana API key. Defaults to ARTANA_API_KEY.",
    )


def add_bootstrap_key_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--bootstrap-key",
        default=os.getenv("ARTANA_BOOTSTRAP_KEY")
        or os.getenv("ARTANA_EVIDENCE_API_BOOTSTRAP_KEY"),
        help=(
            "Bootstrap secret for first-time self-hosted key issuance. "
            "Defaults to ARTANA_BOOTSTRAP_KEY."
        ),
    )


def create_client(*, base_url: str, api_key: str | None = None) -> ArtanaClient:
    if api_key is None:
        return ArtanaClient(base_url=base_url)
    return ArtanaClient(base_url=base_url, api_key=api_key)


def print_heading(title: str) -> None:
    print(f"\n=== {title} ===")


def exit_with_error(message: str) -> NoReturn:
    raise SystemExit(message)
