"""Model selection cannot be re-opened from the environment.

`artana.toml` sets `allow_runtime_model_overrides = false`, and four
`ARTANA_CLAIM_*_MODEL` variables selected verifier models with no registry check
at all.  Both were reachable from the environment, so the configured intent was
advisory: a deployment that had deliberately locked model choice down could
have it unlocked, and a typo could silently send formal traffic to a model
nobody chose.

That matters more than it looks.  No dated snapshot exists for the model this
lane runs, so the only thing keeping runs comparable is that the configured id
is the one actually used.  See ART-MODEL-004 / #198.
"""

from __future__ import annotations

import pytest
from artana_evidence_api.document_extraction_support.llm_extraction.verification_loop import (
    _model_from_environment,
)
from artana_evidence_api.runtime.model_registry import get_model_registry

_OVERRIDE_FLAG = "ARTANA_AI_ALLOW_RUNTIME_MODEL_OVERRIDES"
_VERIFIER_VAR = "ARTANA_CLAIM_VERIFICATION_MODEL"
_DEFAULT_MODEL = "openai:gpt-5.6-luna"


@pytest.mark.parametrize("enabling_value", ["true", "1", "on", "yes", "TRUE"])
def test_environment_cannot_re_enable_locked_model_overrides(
    monkeypatch: pytest.MonkeyPatch,
    enabling_value: str,
) -> None:
    """The environment may tighten this setting, never relax it."""

    monkeypatch.setenv(_OVERRIDE_FLAG, enabling_value)

    assert get_model_registry().allow_runtime_model_overrides() is False


def test_environment_may_still_tighten(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(_OVERRIDE_FLAG, "false")

    assert get_model_registry().allow_runtime_model_overrides() is False


def test_unset_verifier_variable_uses_the_configured_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(_VERIFIER_VAR, raising=False)

    assert _model_from_environment(_VERIFIER_VAR, _DEFAULT_MODEL) == (
        "openai/gpt-5.6-luna"
    )


def test_a_registered_override_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real override must still work; this is a guard, not a lockout."""

    monkeypatch.setenv(_VERIFIER_VAR, "openai:gpt-5.6-sol")

    assert _model_from_environment(_VERIFIER_VAR, _DEFAULT_MODEL) == (
        "openai/gpt-5.6-sol"
    )


@pytest.mark.parametrize(
    "unknown",
    [
        "openai:gpt-5.6-lunar",  # one-character typo for the default
        "gpt-4o-mini-typo",
        "not-a-model",
        "",
    ],
)
def test_an_unregistered_override_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    unknown: str,
) -> None:
    monkeypatch.setenv(_VERIFIER_VAR, unknown)

    with pytest.raises(ValueError, match="not a registered model"):
        _model_from_environment(_VERIFIER_VAR, _DEFAULT_MODEL)


def test_registry_lookup_uses_the_configured_id_form() -> None:
    """Registry keys are `provider:model`; the client wants `provider/model`.

    Validating the normalised form against colon-keyed entries rejects every
    valid override, so the lookup must use the raw configured id.
    """

    registry = get_model_registry()

    assert registry.get_model(_DEFAULT_MODEL) is not None
    with pytest.raises(KeyError):
        registry.get_model("openai/gpt-5.6-luna")
