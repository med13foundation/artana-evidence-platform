"""Regression tests for live endpoint contract coverage scope."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _load_live_contract_module() -> ModuleType:
    module_path = (
        Path(__file__).resolve().parents[1]
        / "e2e"
        / "artana_evidence_api"
        / "test_live_endpoint_contract.py"
    )
    spec = importlib.util.spec_from_file_location(
        "test_live_endpoint_contract",
        module_path,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load live endpoint contract module.")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_direct_live_operation_set_tracks_canonical_runtime_routes() -> None:
    module = _load_live_contract_module()
    spec: dict[str, object] = {
        "paths": {
            "/health": {"get": {}},
            "/v1/spaces": {"get": {}, "post": {}},
            "/v2/spaces": {"get": {}, "post": {}},
        },
    }

    assert module._direct_live_operation_set(spec) == {
        ("get", "/health"),
        ("get", "/v1/spaces"),
        ("post", "/v1/spaces"),
    }


def test_redacted_created_ids_removes_generated_api_key_values() -> None:
    module = _load_live_contract_module()

    assert module._redacted_created_ids(
        {
            "api_key": "art_sk_secret",
            "api_key_id": "key-id",
            "secondary_api_key": "art_sk_secondary",
            "secondary_api_key_id": "secondary-id",
            "space_id": "space-id",
        },
    ) == {
        "api_key": "<redacted>",
        "api_key_id": "key-id",
        "secondary_api_key": "<redacted>",
        "secondary_api_key_id": "secondary-id",
        "space_id": "space-id",
    }
