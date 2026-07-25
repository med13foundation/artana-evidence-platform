"""Formal runs name their model, and refuse to guess when they cannot.

D8 asks formal runs to pin a dated snapshot. None exists for this project's
models -- the provider publishes `gpt-5.6-luna`, `-sol` and `-terra` as floating
aliases only -- so the strongest available guarantee is a different one: the
model is named explicitly rather than inherited from a `default_*` entry, so
editing the defaults cannot silently change what a sealed result was produced
with.

The gap that remains is recorded, not papered over. Comparability rests on
replication and on observing the model the provider actually returned (#206),
not on the model being frozen.

See ART-MODEL-004 / #198.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from artana_evidence_api.runtime.model_registry import (
    ArtanaModelRegistry,
    ModelCapability,
)

_REGISTERED = """
[models]
allow_runtime_model_overrides = false

[models.formal]
model = "openai:gpt-5.6-luna"
snapshot_pinned = false

[models.registry."openai:gpt-5.6-luna"]
capabilities = ["query_generation", "evidence_extraction", "curation", "judge"]
is_enabled = true
"""


def _registry(tmp_path: Path, config: str) -> ArtanaModelRegistry:
    path = tmp_path / "artana.toml"
    path.write_text(textwrap.dedent(config), encoding="utf-8")
    return ArtanaModelRegistry(config_path=path)


def test_the_shipped_config_declares_a_formal_model() -> None:
    """The real artana.toml, not a fixture -- this is the live guarantee."""

    registry = ArtanaModelRegistry()
    model = registry.formal_model()

    assert model.model_id == "openai:gpt-5.6-luna"
    assert model.is_enabled
    assert model.supports_capability(ModelCapability.EVIDENCE_EXTRACTION)


def test_the_shipped_config_admits_the_snapshot_is_not_pinned() -> None:
    """Recording the gap honestly is the point; it must not claim otherwise."""

    assert ArtanaModelRegistry().formal_snapshot_is_pinned() is False


def test_an_unregistered_formal_model_refuses(tmp_path: Path) -> None:
    """A formal run that quietly used another model is worse than one that stops."""

    registry = _registry(
        tmp_path,
        _REGISTERED.replace('model = "openai:gpt-5.6-luna"', 'model = "openai:typo"'),
    )

    with pytest.raises(ValueError, match="not in the registry"):
        registry.formal_model()


def test_a_missing_formal_section_refuses(tmp_path: Path) -> None:
    """Silence must not fall back to a default_* entry."""

    registry = _registry(
        tmp_path,
        """
        [models]
        default_evidence_extraction = "openai:gpt-5.6-luna"

        [models.registry."openai:gpt-5.6-luna"]
        capabilities = ["evidence_extraction"]
        """,
    )

    with pytest.raises(ValueError, match="no \\[models.formal\\] model"):
        registry.formal_model()


def test_a_disabled_formal_model_refuses(tmp_path: Path) -> None:
    registry = _registry(
        tmp_path,
        _REGISTERED.replace("is_enabled = true", "is_enabled = false"),
    )

    with pytest.raises(ValueError, match="disabled"):
        registry.formal_model()


def test_the_formal_model_does_not_follow_the_defaults(tmp_path: Path) -> None:
    """The property the explicit section exists to provide.

    Changing `default_evidence_extraction` must not move what a formal run uses,
    or a defaults edit silently reinterprets every sealed result.
    """

    registry = _registry(
        tmp_path,
        """
        [models]
        default_evidence_extraction = "openai:gpt-5.6-sol"

        [models.formal]
        model = "openai:gpt-5.6-luna"

        [models.registry."openai:gpt-5.6-luna"]
        capabilities = ["evidence_extraction"]

        [models.registry."openai:gpt-5.6-sol"]
        capabilities = ["evidence_extraction"]
        """,
    )

    assert registry.formal_model().model_id == "openai:gpt-5.6-luna"
    assert (
        registry.get_default_model(ModelCapability.EVIDENCE_EXTRACTION).model_id
        == "openai:gpt-5.6-sol"
    )
