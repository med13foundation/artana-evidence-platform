"""Focused regressions for production model registry configuration."""

from __future__ import annotations

import tomllib
from pathlib import Path

from artana_evidence_api.runtime.model_registry import (
    ArtanaModelRegistry,
    ModelCapability,
)

_CONFIG_PATH = Path(__file__).resolve().parents[2] / "artana.toml"


def test_gpt_5_6_sol_is_enabled_for_every_luna_capability() -> None:
    registry = ArtanaModelRegistry(_CONFIG_PATH)
    sol = registry.get_model("openai:gpt-5.6-sol")
    luna = registry.get_model("openai:gpt-5.6-luna")

    assert sol.capabilities == luna.capabilities == frozenset(ModelCapability)
    assert sol.timeout_seconds == luna.timeout_seconds == 900.0
    assert sol.is_enabled is luna.is_enabled is True
    assert all(
        registry.validate_model_for_capability(sol.model_id, capability)
        for capability in ModelCapability
    )


def test_gpt_5_6_sol_matches_luna_reasoning_and_retry_settings() -> None:
    with _CONFIG_PATH.open("rb") as config_file:
        registry = tomllib.load(config_file)["models"]["registry"]

    sol = registry["openai:gpt-5.6-sol"]
    luna = registry["openai:gpt-5.6-luna"]

    for setting in (
        "provider",
        "capabilities",
        "cost_tier",
        "is_reasoning_model",
        "max_retries",
        "timeout_seconds",
        "is_enabled",
        "is_default",
        "default_reasoning_settings",
    ):
        assert sol[setting] == luna[setting]
