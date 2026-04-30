"""Packaging compatibility tests for full-AI shadow checkpoint modules."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from artana_evidence_api.full_ai_orchestrator.shadow_planner import (
    ShadowPlannerRecommendationResult,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SHADOW_CANONICAL_PREFIX = "artana_evidence_api.full_ai_orchestrator.shadow."
_SHADOW_FACADE_PATHS = frozenset(
    {
        "services/artana_evidence_api/full_ai_orchestrator_shadow_checkpoints.py",
        "services/artana_evidence_api/full_ai_orchestrator_shadow_support.py",
    },
)
_RECOMMENDATION_SENTINEL = cast("ShadowPlannerRecommendationResult", object())


def _shadow_facade_modules() -> tuple[tuple[str, str], ...]:
    return tuple(
        (str(entry["module"]), str(entry["canonical_package"]))
        for entry in _shadow_facade_entries()
    )


def _shadow_facade_entries() -> tuple[dict[str, object], ...]:
    raw = json.loads(
        (_REPO_ROOT / "architecture_structure_overrides.json").read_text(
            encoding="utf-8",
        ),
    )
    return tuple(
        entry
        for entry in raw["compatibility_facades"]
        if str(entry["canonical_package"]).startswith(_SHADOW_CANONICAL_PREFIX)
    )


@pytest.mark.parametrize(("facade_name", "canonical_name"), _shadow_facade_modules())
def test_shadow_facades_reexport_canonical_symbols(
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


def test_shadow_root_facades_are_registered() -> None:
    registered_paths = {str(entry["path"]) for entry in _shadow_facade_entries()}

    assert registered_paths >= _SHADOW_FACADE_PATHS


def test_full_ai_entrypoints_do_not_import_shadow_facades() -> None:
    facade_modules = {str(entry["module"]) for entry in _shadow_facade_entries()}
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
        _REPO_ROOT
        / "services"
        / "artana_evidence_api"
        / "full_ai_orchestrator"
        / "progress"
        / "observer.py",
        _REPO_ROOT
        / "services"
        / "artana_evidence_api"
        / "full_ai_orchestrator"
        / "guarded"
        / "selection.py",
        _REPO_ROOT
        / "services"
        / "artana_evidence_api"
        / "full_ai_orchestrator"
        / "shadow"
        / "checkpoints.py",
    )

    for implementation_file in implementation_files:
        imported_modules = _imported_modules(implementation_file)
        assert facade_modules.isdisjoint(imported_modules)


@pytest.mark.asyncio
async def test_runtime_shadow_recommendation_monkeypatch_seam_reaches_checkpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_facade = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator_runtime",
    )
    checkpoints = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.shadow.checkpoints",
    )
    calls: list[dict[str, object]] = []

    async def replacement(**kwargs: object) -> ShadowPlannerRecommendationResult:
        calls.append(dict(kwargs))
        return _RECOMMENDATION_SENTINEL

    monkeypatch.setattr(
        runtime_facade,
        "recommend_shadow_planner_action",
        replacement,
    )

    result = await checkpoints.recommend_shadow_planner_action(
        checkpoint_key="after_bootstrap",
        objective="Investigate MED13 syndrome",
    )

    assert result is _RECOMMENDATION_SENTINEL
    assert calls == [
        {
            "checkpoint_key": "after_bootstrap",
            "objective": "Investigate MED13 syndrome",
        },
    ]


def test_shadow_support_policy_constants_stay_in_sync_while_duplication_remains() -> (
    None
):
    shadow_support = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.shadow.support",
    )
    guarded_support = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.guarded.support",
    )
    runtime_constants = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.runtime_constants",
    )
    guarded_support_names = (
        "_ACTION_REGISTRY",
        "_GUARDED_PROFILE_ALLOWED_STRATEGIES",
        "_GUARDED_PROFILE_CHASE_ONLY",
        "_GUARDED_PROFILE_DRY_RUN",
        "_GUARDED_PROFILE_LOW_RISK",
        "_GUARDED_PROFILE_SHADOW_ONLY",
        "_GUARDED_PROFILE_SOURCE_CHASE",
    )
    runtime_constant_names = (
        "_GUARDED_PROFILE_ALLOWED_STRATEGIES",
        "_GUARDED_PROFILE_CHASE_ONLY",
        "_GUARDED_PROFILE_DRY_RUN",
        "_GUARDED_PROFILE_LOW_RISK",
        "_GUARDED_PROFILE_SHADOW_ONLY",
        "_GUARDED_PROFILE_SOURCE_CHASE",
        "_SHADOW_PLANNER_COMPARISON_ARTIFACT_KEY",
        "_SHADOW_PLANNER_RECOMMENDATION_ARTIFACT_KEY",
        "_SHADOW_PLANNER_TIMELINE_ARTIFACT_KEY",
        "_SHADOW_PLANNER_WORKSPACE_ARTIFACT_KEY",
    )

    for name in guarded_support_names:
        assert getattr(shadow_support, name) == getattr(guarded_support, name)
    for name in runtime_constant_names:
        assert getattr(shadow_support, name) == getattr(runtime_constants, name)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    return imported_modules
