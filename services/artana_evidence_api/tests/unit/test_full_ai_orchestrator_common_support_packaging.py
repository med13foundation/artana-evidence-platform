"""Packaging compatibility tests for full-AI common support helpers."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[4]
_COMMON_SUPPORT_FACADE_PATH = (
    "services/artana_evidence_api/full_ai_orchestrator_common_support.py"
)
_COMMON_SUPPORT_MODULE = "artana_evidence_api.full_ai_orchestrator_common_support"


def test_common_support_facade_is_registered() -> None:
    raw = json.loads(
        (_REPO_ROOT / "architecture_structure_overrides.json").read_text(
            encoding="utf-8",
        ),
    )
    registered_paths = {
        str(entry["path"])
        for entry in raw["compatibility_facades"]
        if str(entry["module"]) == _COMMON_SUPPORT_MODULE
    }

    assert _COMMON_SUPPORT_FACADE_PATH in registered_paths


def test_common_support_facade_reexports_focused_canonical_modules() -> None:
    facade = importlib.import_module(_COMMON_SUPPORT_MODULE)
    action_registry = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.action_registry",
    )
    workspace_support = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.workspace_support",
    )
    runtime_constants = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.runtime_constants",
    )
    runtime_models = importlib.import_module(
        "artana_evidence_api.full_ai_orchestrator.runtime_models",
    )

    _assert_symbols_match(
        facade=facade,
        canonical=action_registry,
        names=(
            "_ACTION_REGISTRY",
            "_ACTION_SPEC_BY_TYPE",
            "_CONTROL_ACTIONS",
            "_SOURCE_ACTIONS",
            "build_step_key",
            "is_control_action",
            "is_source_action",
            "orchestrator_action_registry",
            "require_action_enabled_for_sources",
        ),
    )
    _assert_symbols_match(
        facade=facade,
        canonical=workspace_support,
        names=(
            "_chase_round_action_input_from_workspace",
            "_chase_round_metadata_from_workspace",
            "_chase_round_stop_reason",
            "_guarded_structured_verification_payload",
            "_normalized_source_key_list",
            "_planner_mode_value",
            "_source_decision_status",
            "_workspace_list",
            "_workspace_object",
        ),
    )
    _assert_symbols_match(
        facade=facade,
        canonical=runtime_constants,
        names=(
            "_HARNESS_ID",
            "_SHADOW_PLANNER_CHECKPOINT_ORDER",
            "_STEP_KEY_VERSION",
            "_STRUCTURED_ENRICHMENT_SOURCES",
        ),
    )
    _assert_symbols_match(
        facade=facade,
        canonical=runtime_models,
        names=("FullAIOrchestratorExecutionResult",),
    )


def _assert_symbols_match(
    *,
    facade: ModuleType,
    canonical: ModuleType,
    names: tuple[str, ...],
) -> None:
    for name in names:
        assert getattr(facade, name) is getattr(canonical, name)


def test_full_ai_modules_do_not_import_common_support_facade() -> None:
    implementation_root = (
        _REPO_ROOT / "services" / "artana_evidence_api" / "full_ai_orchestrator"
    )

    for implementation_file in implementation_root.rglob("*.py"):
        imported_modules = _imported_modules(implementation_file)
        assert _COMMON_SUPPORT_MODULE not in imported_modules


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.add(node.module)
    return imported_modules
