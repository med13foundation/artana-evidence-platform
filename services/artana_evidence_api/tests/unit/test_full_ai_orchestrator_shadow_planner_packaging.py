"""Packaging compatibility tests for the full-AI shadow planner."""

from __future__ import annotations

import importlib
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from artana_evidence_api.full_ai_orchestrator_runtime import (
    orchestrator_action_registry,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SHADOW_PLANNER_CANONICAL_PREFIX = (
    "artana_evidence_api.full_ai_orchestrator.shadow_planner"
)
_REGISTRY_SENTINEL = object()
_STORE_SENTINEL = object()


def _shadow_planner_facade_modules() -> tuple[tuple[str, str], ...]:
    raw = json.loads(
        (_REPO_ROOT / "architecture_structure_overrides.json").read_text(
            encoding="utf-8",
        ),
    )
    return tuple(
        (str(entry["module"]), str(entry["canonical_package"]))
        for entry in raw["compatibility_facades"]
        if str(entry["canonical_package"]).startswith(
            _SHADOW_PLANNER_CANONICAL_PREFIX,
        )
    )


@pytest.mark.parametrize(
    ("facade_name", "canonical_name"), _shadow_planner_facade_modules()
)
def test_shadow_planner_facades_reexport_canonical_symbols(
    facade_name: str,
    canonical_name: str,
) -> None:
    facade = importlib.import_module(facade_name)
    canonical = importlib.import_module(canonical_name)
    exported_names = getattr(facade, "__all__", None)

    assert isinstance(exported_names, list)
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


@pytest.mark.parametrize(
    ("name", "replacement", "expected"),
    [
        ("has_configured_openai_api_key", lambda: False, False),
        ("get_model_registry", lambda: _REGISTRY_SENTINEL, _REGISTRY_SENTINEL),
        ("create_artana_postgres_store", lambda: _STORE_SENTINEL, _STORE_SENTINEL),
    ],
)
def test_old_shadow_planner_monkeypatch_seams_still_reach_canonical_runtime(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    replacement: Callable[[], Any],
    expected: object | None,
) -> None:
    facade = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner",
    )
    runtime = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.shadow_planner.runtime",
    )

    monkeypatch.setattr(facade, name, replacement)
    result = getattr(runtime, name)()

    assert result is expected


@pytest.mark.asyncio
async def test_old_shadow_planner_openai_key_seam_reaches_recommendation_callsite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    facade = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator_shadow_planner",
    )
    runtime = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.shadow_planner.runtime",
    )

    monkeypatch.setattr(facade, "has_configured_openai_api_key", lambda: False)

    result = await runtime.recommend_shadow_planner_action(
        checkpoint_key="before_first_action",
        objective="Investigate MED13 syndrome",
        workspace_summary={"objective": "Investigate MED13 syndrome", "counts": {}},
        sources={"pubmed": True, "clinvar": True},
        action_registry=orchestrator_action_registry(),
        harness_id="full-ai-orchestrator",
        step_key_version="v1",
    )

    assert result.planner_status == "unavailable"
    assert result.used_fallback is True
