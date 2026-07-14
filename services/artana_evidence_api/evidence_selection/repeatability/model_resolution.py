"""Trusted model resolution for offline semantic model comparisons."""

from __future__ import annotations

from artana_evidence_api.evidence_selection.semantic.model import (
    ArtanaEvidenceSelectionSemanticModelRunner,
    EvidenceSelectionSemanticModelRunner,
)
from artana_evidence_api.runtime.model_registry import (
    ModelCapability,
    get_model_registry,
)


def resolve_trusted_semantic_comparison_model_id(
    requested_model_id: str | None,
) -> str:
    """Resolve an exact registered judge model for a trusted offline comparison."""

    registry = get_model_registry()
    if requested_model_id is None:
        try:
            return registry.get_default_model(ModelCapability.JUDGE).model_id
        except (KeyError, ValueError) as exc:
            raise ValueError("default semantic judge model could not be resolved") from exc

    try:
        model = registry.get_model(requested_model_id)
    except KeyError as exc:
        raise ValueError(
            f"semantic comparison model '{requested_model_id}' is not registered",
        ) from exc
    if model.model_id != requested_model_id:
        raise ValueError("semantic comparison model must resolve to its exact registry ID")
    if not model.is_enabled:
        raise ValueError(
            f"semantic comparison model '{requested_model_id}' is disabled",
        )
    if not model.supports_capability(ModelCapability.JUDGE):
        raise ValueError(
            f"semantic comparison model '{requested_model_id}' is not a judge model",
        )
    return model.model_id


class TrustedSemanticComparisonModelRunner(
    ArtanaEvidenceSelectionSemanticModelRunner,
):
    """Run one prevalidated comparison model without changing runtime override policy."""

    def __init__(self, *, model_id: str) -> None:
        super().__init__()
        self._comparison_model_id = resolve_trusted_semantic_comparison_model_id(model_id)

    def _resolve_model_id(self) -> str:
        return self._comparison_model_id


def create_trusted_semantic_comparison_runner(
    model_id: str,
) -> EvidenceSelectionSemanticModelRunner:
    """Create a semantic runner pinned to one exact prevalidated comparison model."""

    return TrustedSemanticComparisonModelRunner(model_id=model_id)


__all__ = [
    "TrustedSemanticComparisonModelRunner",
    "create_trusted_semantic_comparison_runner",
    "resolve_trusted_semantic_comparison_model_id",
]
