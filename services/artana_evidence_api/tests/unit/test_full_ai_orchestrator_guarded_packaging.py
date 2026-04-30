"""Packaging compatibility tests for full-AI guarded planner modules."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_GUARDED_CANONICAL_PREFIX = "artana_evidence_api.full_ai_orchestrator.guarded."
_GUARDED_FACADE_GLOB = "full_ai_orchestrator_guarded_*.py"


def _guarded_facade_modules() -> tuple[tuple[str, str], ...]:
    return tuple(
        (str(entry["module"]), str(entry["canonical_package"]))
        for entry in _guarded_facade_entries()
    )


def _guarded_facade_entries() -> tuple[dict[str, object], ...]:
    raw = json.loads(
        (_REPO_ROOT / "architecture_structure_overrides.json").read_text(
            encoding="utf-8",
        ),
    )
    return tuple(
        entry
        for entry in raw["compatibility_facades"]
        if str(entry["canonical_package"]).startswith(_GUARDED_CANONICAL_PREFIX)
    )


@pytest.mark.parametrize(("facade_name", "canonical_name"), _guarded_facade_modules())
def test_guarded_facades_reexport_canonical_symbols(
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


def test_all_guarded_root_facades_are_registered() -> None:
    guarded_facade_paths = {
        path.relative_to(_REPO_ROOT).as_posix()
        for path in (_REPO_ROOT / "services" / "artana_evidence_api").glob(
            _GUARDED_FACADE_GLOB,
        )
    }
    registered_paths = {str(entry["path"]) for entry in _guarded_facade_entries()}

    assert guarded_facade_paths
    assert guarded_facade_paths <= registered_paths


def test_full_ai_entrypoints_do_not_import_guarded_facades() -> None:
    facade_modules = {str(entry["module"]) for entry in _guarded_facade_entries()}
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
        _REPO_ROOT / "services" / "artana_evidence_api" / "phase1_compare.py",
        _REPO_ROOT / "services" / "artana_evidence_api" / "phase1_compare_progress.py",
    )

    for implementation_file in implementation_files:
        imported_modules = _imported_modules(implementation_file)
        assert facade_modules.isdisjoint(imported_modules)


def test_guarded_policy_constants_stay_in_sync_while_duplication_remains() -> None:
    rollout = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.guarded.rollout",
    )
    support = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.guarded.support",
    )
    runtime_constants = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.runtime_constants",
    )
    shared_names = (
        "_GUARDED_CHASE_ROLLOUT_ENV",
        "_GUARDED_PROFILE_ALLOWED_STRATEGIES",
        "_GUARDED_PROFILE_CHASE_ONLY",
        "_GUARDED_PROFILE_DRY_RUN",
        "_GUARDED_PROFILE_LOW_RISK",
        "_GUARDED_PROFILE_SHADOW_ONLY",
        "_GUARDED_PROFILE_SOURCE_CHASE",
        "_GUARDED_ROLLOUT_POLICY_VERSION",
        "_GUARDED_ROLLOUT_PROFILE_ENV",
        "_GUARDED_SKIP_CHASE_ROUND_NUMBER",
        "_GUARDED_STRATEGY_BRIEF_GENERATION",
        "_GUARDED_STRATEGY_CHASE_SELECTION",
        "_GUARDED_STRATEGY_STRUCTURED_SOURCE",
        "_GUARDED_STRATEGY_TERMINAL_CONTROL",
        "_TRUE_ENV_VALUES",
        "_VALID_GUARDED_ROLLOUT_PROFILES",
    )

    for name in shared_names:
        assert getattr(rollout, name) == getattr(support, name)
        assert getattr(rollout, name) == getattr(runtime_constants, name)
    assert rollout._ACTION_REGISTRY == support._ACTION_REGISTRY


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    return imported_modules
