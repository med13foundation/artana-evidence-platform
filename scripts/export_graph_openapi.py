#!/usr/bin/env python3
"""Export the standalone graph-service OpenAPI schema."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from types import TracebackType
from typing import Self


def _skip_dictionary_seed(*_args: object, **_kwargs: object) -> None:
    """Disable runtime dictionary seeding while exporting OpenAPI."""


class _NoopSession:
    """Lightweight session stub for OpenAPI export."""

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc, traceback

    def commit(self) -> None:
        """No-op commit for schema export."""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export the standalone graph-service OpenAPI schema.",
    )
    parser.add_argument(
        "--output",
        default="services/artana_evidence_db/openapi.json",
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
    graph_service_root = repo_root / "services" / "artana_evidence_db"
    services_root = repo_root / "services"
    for path in (repo_root, services_root, graph_service_root):
        resolved = str(path)
        if resolved not in sys.path:
            sys.path.append(resolved)
    os.environ.setdefault(
        "GRAPH_DATABASE_URL",
        "postgresql://graph-openapi:graph-openapi@localhost:5432/graph_openapi",
    )

    import artana_evidence_db.app as graph_app_module

    graph_app_module.SessionLocal = _NoopSession
    graph_app_module.seed_builtin_dictionary_entries = _skip_dictionary_seed
    graph_app_module.seed_biomedical_starter_concepts_for_existing_spaces = (
        _skip_dictionary_seed
    )
    create_app = graph_app_module.create_app

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
                "Graph-service OpenAPI schema is out of date. "
                f"Run scripts/export_graph_openapi.py --output {display_path}"
            )
            raise SystemExit(msg)
        print(f"✅ Graph-service OpenAPI is up to date at {display_path}")  # noqa: T201
        return

    output_path.write_text(rendered, encoding="utf-8")
    print(f"✅ Wrote graph-service OpenAPI to {display_path}")  # noqa: T201


if __name__ == "__main__":
    main()
