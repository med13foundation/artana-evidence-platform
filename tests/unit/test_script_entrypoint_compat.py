"""Compatibility tests for packaged script entrypoints."""

from __future__ import annotations

import importlib
from types import ModuleType


def _assert_facade_symbols_resolve_to_canonical_modules(
    *,
    facade_name: str,
    canonical_module_names: tuple[str, ...],
) -> None:
    facade = importlib.import_module(facade_name)
    canonical_modules = tuple(
        importlib.import_module(module_name) for module_name in canonical_module_names
    )

    exported_names = getattr(facade, "__all__", None)

    assert isinstance(exported_names, list | tuple)
    assert exported_names
    for name in exported_names:
        assert isinstance(name, str)
        assert hasattr(facade, name), f"{facade_name}.{name} is missing"
        assert _canonical_symbol_matches(
            facade=facade,
            canonical_modules=canonical_modules,
            name=name,
        ), f"{facade_name}.{name} does not resolve to a canonical package symbol"


def _canonical_symbol_matches(
    *,
    facade: ModuleType,
    canonical_modules: tuple[ModuleType, ...],
    name: str,
) -> bool:
    facade_value = getattr(facade, name)
    return any(
        hasattr(module, name) and getattr(module, name) is facade_value
        for module in canonical_modules
    )


def test_full_ai_real_space_canary_entrypoint_facade_reexports_canonical_symbols() -> None:
    _assert_facade_symbols_resolve_to_canonical_modules(
        facade_name="scripts.run_full_ai_real_space_canary",
        canonical_module_names=(
            "scripts.full_ai_real_space_canary.runner",
            "scripts.full_ai_real_space_canary.reporting",
            "scripts.full_ai_real_space_canary.utils",
        ),
    )


def test_live_evidence_session_audit_entrypoint_facade_reexports_canonical_symbols() -> None:
    _assert_facade_symbols_resolve_to_canonical_modules(
        facade_name="scripts.run_live_evidence_session_audit",
        canonical_module_names=(
            "scripts.live_evidence_session_audit.runner",
            "scripts.live_evidence_session_audit.support",
        ),
    )


def test_phase1_guarded_eval_entrypoint_facade_reexports_canonical_symbols() -> None:
    _assert_facade_symbols_resolve_to_canonical_modules(
        facade_name="scripts.run_phase1_guarded_eval",
        canonical_module_names=(
            "scripts.phase1_guarded_eval.runner",
            "scripts.phase1_guarded_eval.render",
            "scripts.phase1_guarded_eval.report",
            "scripts.phase1_guarded_eval.review",
        ),
    )
