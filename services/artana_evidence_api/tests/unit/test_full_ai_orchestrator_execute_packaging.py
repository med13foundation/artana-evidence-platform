"""Packaging compatibility tests for the full-AI execute module."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from artana_evidence_api.research_init_runtime import ResearchInitExecutionResult

_REPO_ROOT = Path(__file__).resolve().parents[4]
_EXECUTE_CANONICAL_MODULE = "artana_evidence_api.full_ai_orchestrator.execute"
_EXECUTE_FACADE_PATH = "services/artana_evidence_api/full_ai_orchestrator_execute.py"
_RESEARCH_INIT_SENTINEL = cast("ResearchInitExecutionResult", object())


def _execute_facade_entries() -> tuple[dict[str, object], ...]:
    raw = json.loads(
        (_REPO_ROOT / "architecture_structure_overrides.json").read_text(
            encoding="utf-8",
        ),
    )
    return tuple(
        entry
        for entry in raw["compatibility_facades"]
        if str(entry["canonical_package"]) == _EXECUTE_CANONICAL_MODULE
    )


def test_execute_facade_reexports_canonical_symbols() -> None:
    entries = _execute_facade_entries()
    assert entries
    facade = importlib.import_module(str(entries[0]["module"]))
    canonical = importlib.import_module(_EXECUTE_CANONICAL_MODULE)
    exported_names = getattr(facade, "__all__", None)

    assert isinstance(exported_names, list | tuple)
    assert exported_names
    canonical_exported_names = getattr(canonical, "__all__", ())
    assert set(canonical_exported_names) <= set(exported_names)
    for name in exported_names:
        assert isinstance(name, str)
        assert _facade_symbol_matches_canonical(
            facade=facade,
            canonical=canonical,
            name=name,
        ), f"execute facade {name} does not resolve to canonical execute module"


def _facade_symbol_matches_canonical(
    *,
    facade: ModuleType,
    canonical: ModuleType,
    name: str,
) -> bool:
    return hasattr(canonical, name) and getattr(facade, name) is getattr(
        canonical,
        name,
    )


def test_execute_root_facade_is_registered() -> None:
    registered_paths = {str(entry["path"]) for entry in _execute_facade_entries()}

    assert _EXECUTE_FACADE_PATH in registered_paths


def test_runtime_facade_imports_canonical_execute_module() -> None:
    runtime_path = (
        _REPO_ROOT
        / "services"
        / "artana_evidence_api"
        / "full_ai_orchestrator_runtime.py"
    )
    imported_modules = _imported_modules(runtime_path)

    assert "artana_evidence_api.full_ai_orchestrator.execute" in imported_modules
    assert "artana_evidence_api.full_ai_orchestrator_execute" not in imported_modules


@pytest.mark.asyncio
async def test_runtime_research_init_monkeypatch_seam_reaches_canonical_execute(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_facade = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator_runtime",
    )
    execute = importlib.import_module(_EXECUTE_CANONICAL_MODULE)
    calls: list[dict[str, object]] = []

    async def replacement(**kwargs: object) -> ResearchInitExecutionResult:
        calls.append(dict(kwargs))
        return _RESEARCH_INIT_SENTINEL

    monkeypatch.setattr(runtime_facade, "execute_research_init_run", replacement)

    result = await execute.execute_research_init_run(
        space_id="space-1",
        existing_run="run-1",
    )

    assert result is _RESEARCH_INIT_SENTINEL
    assert calls == [{"space_id": "space-1", "existing_run": "run-1"}]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    return imported_modules
