"""Compatibility tests for support-module package facades."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUPPORT_FACADE_MODULES = frozenset(
    {
        "artana_evidence_api.queued_run_support",
        "artana_evidence_api.runtime_support",
        "artana_evidence_db.dictionary_support",
    },
)
_EXPECTED_FACADE_PATHS = frozenset(
    {
        "services/artana_evidence_api/queued_run_support.py",
        "services/artana_evidence_api/runtime_support.py",
        "services/artana_evidence_db/dictionary_support.py",
    },
)
_RUNTIME_COMPAT_WRAPPER_NAMES = frozenset(
    {
        "create_artana_postgres_store",
        "get_artana_model_health",
        "get_shared_artana_postgres_store",
    },
)


def _support_facade_entries() -> tuple[dict[str, object], ...]:
    raw = json.loads(
        (_REPO_ROOT / "architecture_structure_overrides.json").read_text(
            encoding="utf-8",
        ),
    )
    return tuple(
        entry
        for entry in raw["compatibility_facades"]
        if str(entry["module"]) in _SUPPORT_FACADE_MODULES
    )


def _support_facade_modules() -> tuple[tuple[str, str], ...]:
    return tuple(
        (str(entry["module"]), str(entry["canonical_package"]))
        for entry in _support_facade_entries()
    )


@pytest.mark.parametrize(
    ("facade_name", "canonical_name"),
    _support_facade_modules(),
)
def test_support_facades_export_canonical_package_symbols(
    facade_name: str,
    canonical_name: str,
) -> None:
    facade = importlib.import_module(facade_name)
    canonical = importlib.import_module(canonical_name)
    facade_exported_names = getattr(facade, "__all__", None)
    canonical_exported_names = getattr(canonical, "__all__", None)

    assert isinstance(facade_exported_names, list | tuple)
    assert isinstance(canonical_exported_names, list | tuple)
    assert set(facade_exported_names) == set(canonical_exported_names)

    for name in facade_exported_names:
        assert isinstance(name, str)
        assert _facade_symbol_matches_canonical(
            facade=facade,
            canonical=canonical,
            facade_name=facade_name,
            name=name,
        ), f"{facade_name}.{name} does not match {canonical_name}.{name}"


def _facade_symbol_matches_canonical(
    *,
    facade: ModuleType,
    canonical: ModuleType,
    facade_name: str,
    name: str,
) -> bool:
    if not hasattr(canonical, name):
        return False
    facade_value = getattr(facade, name)
    canonical_value = getattr(canonical, name)
    if (
        facade_name == "artana_evidence_api.runtime_support"
        and name in _RUNTIME_COMPAT_WRAPPER_NAMES
    ):
        return callable(facade_value) and callable(canonical_value)
    return facade_value is canonical_value


def test_support_facades_are_registered() -> None:
    registered_paths = {str(entry["path"]) for entry in _support_facade_entries()}

    assert registered_paths == _EXPECTED_FACADE_PATHS
