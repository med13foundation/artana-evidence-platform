"""Guardrails that keep harness execution out of API routers."""

from __future__ import annotations

import ast
from pathlib import Path

ROUTERS_DIR = Path(__file__).resolve().parents[2] / "routers"
_BANNED_IMPORT_NAMES = frozenset(
    {
        "execute_inline_worker_run",
        "get_graph_search_runner",
        "get_graph_connection_runner",
        "get_research_onboarding_runner",
        "execute_graph_search_run",
        "execute_graph_connection_run",
        "execute_hypothesis_run",
        "execute_research_onboarding_run",
        "execute_research_onboarding_continuation",
    },
)
_BANNED_CALL_NAMES = _BANNED_IMPORT_NAMES


def _iter_router_modules() -> list[Path]:
    return sorted(
        path for path in ROUTERS_DIR.glob("*.py") if path.name != "__init__.py"
    )


def _called_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def test_router_modules_do_not_import_legacy_execution_helpers() -> None:
    offending_imports: list[str] = []
    offending_calls: list[str] = []

    for path in _iter_router_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                offending_imports.extend(
                    f"{path.name}: {alias.name}"
                    for alias in node.names
                    if alias.name in _BANNED_IMPORT_NAMES
                )
            if isinstance(node, ast.Call):
                called_name = _called_name(node)
                if called_name in _BANNED_CALL_NAMES:
                    offending_calls.append(f"{path.name}: {called_name}")

    assert offending_imports == []
    assert offending_calls == []
