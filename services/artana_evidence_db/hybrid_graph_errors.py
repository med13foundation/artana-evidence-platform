"""Typed application errors for hybrid graph + embeddings workflows."""

from __future__ import annotations


class HybridGraphError(Exception):
    """Base error for hybrid graph application services."""

    code = "HYBRID_GRAPH_ERROR"

    def __init__(
        self,
        message: str,
        *,
        detail_payload: object | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail_payload = detail_payload


class FeatureDisabledError(HybridGraphError):
    """Raised when a feature-flagged endpoint is disabled."""

    code = "FEATURE_DISABLED"


class EmbeddingNotReadyError(HybridGraphError):
    """Raised when an entity embedding is required but missing."""

    code = "EMBEDDING_NOT_READY"


class ConstraintConfigMissingError(HybridGraphError):
    """Raised when relation suggestion has no eligible dictionary constraints."""

    code = "CONSTRAINT_CONFIG_MISSING"


__all__ = [
    "ConstraintConfigMissingError",
    "EmbeddingNotReadyError",
    "FeatureDisabledError",
    "HybridGraphError",
]
