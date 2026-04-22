"""Boundary tests for standalone graph-service external examples."""

from __future__ import annotations

import ast
from pathlib import Path


def test_http_only_example_imports_no_artana_internals() -> None:
    example_path = Path(
        "services/artana_evidence_db/examples/http_only_client_flow.py",
    )
    tree = ast.parse(example_path.read_text(encoding="utf-8"))

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)

    forbidden_prefixes = ("artana_evidence_db", "artana_evidence_api", "src.")
    assert [
        module
        for module in imported_modules
        if module == "src" or module.startswith(forbidden_prefixes)
    ] == []
