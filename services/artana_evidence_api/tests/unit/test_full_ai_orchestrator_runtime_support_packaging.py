"""Packaging compatibility tests for full-AI runtime-support modules."""

from __future__ import annotations

import ast
import importlib
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_RUNTIME_SUPPORT_CANONICAL_MODULES = frozenset(
    {
        "artana_evidence_api.full_ai_orchestrator.initial_decisions",
        "artana_evidence_api.full_ai_orchestrator.queue",
        "artana_evidence_api.full_ai_orchestrator.runtime_artifacts",
        "artana_evidence_api.full_ai_orchestrator.runtime_constants",
        "artana_evidence_api.full_ai_orchestrator.runtime_models",
    },
)
_RUNTIME_SUPPORT_FACADE_PATHS = frozenset(
    {
        "services/artana_evidence_api/full_ai_orchestrator_initial_decisions.py",
        "services/artana_evidence_api/full_ai_orchestrator_queue.py",
        "services/artana_evidence_api/full_ai_orchestrator_runtime_artifacts.py",
        "services/artana_evidence_api/full_ai_orchestrator_runtime_constants.py",
        "services/artana_evidence_api/full_ai_orchestrator_runtime_models.py",
    },
)


def _runtime_support_facade_modules() -> tuple[tuple[str, str], ...]:
    return tuple(
        (str(entry["module"]), str(entry["canonical_package"]))
        for entry in _runtime_support_facade_entries()
    )


def _runtime_support_facade_entries() -> tuple[dict[str, object], ...]:
    raw = json.loads(
        (_REPO_ROOT / "architecture_structure_overrides.json").read_text(
            encoding="utf-8",
        ),
    )
    return tuple(
        entry
        for entry in raw["compatibility_facades"]
        if str(entry["canonical_package"]) in _RUNTIME_SUPPORT_CANONICAL_MODULES
    )


@pytest.mark.parametrize(
    ("facade_name", "canonical_name"),
    _runtime_support_facade_modules(),
)
def test_runtime_support_facades_reexport_canonical_symbols(
    facade_name: str,
    canonical_name: str,
) -> None:
    facade = importlib.import_module(facade_name)
    canonical = importlib.import_module(canonical_name)
    exported_names = getattr(facade, "__all__", None)

    assert isinstance(exported_names, list | tuple)
    assert exported_names
    canonical_exported_names = getattr(canonical, "__all__", ())
    if canonical_exported_names:
        assert set(canonical_exported_names) <= set(exported_names)
    for name in exported_names:
        assert isinstance(name, str)
        assert _facade_symbol_matches_canonical(
            facade=facade,
            canonical=canonical,
            name=name,
        ), f"{facade_name}.{name} does not resolve to {canonical_name}.{name}"


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


def test_runtime_support_root_facades_are_registered() -> None:
    registered_paths = {
        str(entry["path"]) for entry in _runtime_support_facade_entries()
    }

    assert registered_paths >= _RUNTIME_SUPPORT_FACADE_PATHS


def test_runtime_entrypoints_do_not_import_runtime_support_facades() -> None:
    facade_modules = {
        str(entry["module"]) for entry in _runtime_support_facade_entries()
    }
    implementation_files = (
        _REPO_ROOT
        / "services"
        / "artana_evidence_api"
        / "full_ai_orchestrator_runtime.py",
        _REPO_ROOT
        / "services"
        / "artana_evidence_api"
        / "full_ai_orchestrator"
        / "execute.py",
    )

    for implementation_file in implementation_files:
        imported_modules = _imported_modules(implementation_file)
        assert facade_modules.isdisjoint(imported_modules)


@pytest.mark.parametrize(
    "facade_name",
    [
        "artana_evidence_api.full_ai_orchestrator_queue",
        "artana_evidence_api.full_ai_orchestrator_runtime",
    ],
)
def test_old_transparency_monkeypatch_seams_reach_canonical_queue(
    monkeypatch: pytest.MonkeyPatch,
    facade_name: str,
) -> None:
    facade = importlib.import_module(facade_name)
    queue = importlib.import_module("artana_evidence_api.full_ai_orchestrator.queue")
    calls: list[dict[str, object]] = []

    def replacement(**kwargs: object) -> None:
        calls.append(dict(kwargs))

    monkeypatch.setattr(facade, "ensure_run_transparency_seed", replacement)
    cast_replacement = queue.ensure_run_transparency_seed
    assert isinstance(cast_replacement, Callable)

    cast_replacement(space_id="space-1", run_id="run-1")

    assert calls == [{"space_id": "space-1", "run_id": "run-1"}]


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    return imported_modules
