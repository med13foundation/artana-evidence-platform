#!/usr/bin/env python3
"""Export the standalone artana-evidence-api-service OpenAPI schema."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the standalone artana-evidence-api-service OpenAPI schema.",
    )
    parser.add_argument(
        "--output",
        default="services/artana_evidence_api/openapi.json",
        help="Destination path for the rendered OpenAPI document.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the exported schema differs from the current file.",
    )
    return parser.parse_args()


def render_openapi_document() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    artana_evidence_api_root = repo_root / "services" / "artana_evidence_api"
    services_root = repo_root / "services"
    for path in (repo_root, services_root, artana_evidence_api_root):
        resolved = str(path)
        if resolved not in sys.path:
            sys.path.append(resolved)
    os.environ.setdefault(
        "DATABASE_URL",
        "postgresql+psycopg2://artana_dev:artana_dev_password@localhost:5432/artana_dev",
    )
    os.environ.setdefault("GRAPH_API_URL", "http://127.0.0.1:8090")

    from artana_evidence_api.main import create_app

    document = create_app().openapi()
    return json.dumps(document, indent=2, sort_keys=True) + "\n"


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    args = _parse_args()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    display_path = (
        output_path.relative_to(repo_root)
        if output_path.is_relative_to(repo_root)
        else output_path
    )

    rendered = render_openapi_document()
    if args.check:
        current = (
            output_path.read_text(encoding="utf-8") if output_path.exists() else None
        )
        if current != rendered:
            msg = (
                "Artana Evidence API OpenAPI schema is out of date. "
                f"Run scripts/export_artana_evidence_api_openapi.py --output {display_path}"
            )
            raise SystemExit(msg)
        print(  # noqa: T201
            f"✅ Artana Evidence API OpenAPI is up to date at {display_path}",
        )
        return

    output_path.write_text(rendered, encoding="utf-8")
    print(
        f"✅ Wrote artana-evidence-api-service OpenAPI to {display_path}",
    )  # noqa: T201


if __name__ == "__main__":
    main()
