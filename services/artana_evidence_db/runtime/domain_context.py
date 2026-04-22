"""Graph runtime domain-context helpers owned by the standalone graph service."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from artana_evidence_db.runtime.contracts import GraphDomainContextPolicy

GENERAL_DEFAULT_DOMAIN = "general"
_METADATA_KEYS = ("domain_context", "domain")


def _normalize_domain_context(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _domain_context_from_metadata(
    metadata: Mapping[str, object] | None,
) -> str | None:
    if metadata is None:
        return None
    for key in _METADATA_KEYS:
        raw_value = metadata.get(key)
        if not isinstance(raw_value, str):
            continue
        normalized = _normalize_domain_context(raw_value)
        if normalized is not None:
            return normalized
    return None


def default_graph_domain_context_for_source_type(
    source_type: str | None,
    *,
    domain_context_policy: GraphDomainContextPolicy,
    fallback: str | None = GENERAL_DEFAULT_DOMAIN,
) -> str | None:
    """Return the provided-pack default domain context for one source type."""
    normalized_source_type = _normalize_domain_context(source_type)
    if normalized_source_type is not None:
        for definition in domain_context_policy.source_type_defaults:
            if definition.source_type == normalized_source_type:
                return definition.domain_context
    return _normalize_domain_context(fallback)


def resolve_graph_domain_context(  # noqa: PLR0913
    *,
    domain_context_policy: GraphDomainContextPolicy,
    explicit_domain_context: str | None = None,
    metadata: Mapping[str, object] | None = None,
    source_type: str | None = None,
    ai_inference: Callable[[], str | None] | None = None,
    fallback: str | None = None,
) -> str | None:
    """Resolve graph domain context using the provided-pack source defaults."""
    explicit = _normalize_domain_context(explicit_domain_context)
    if explicit is not None:
        return explicit

    from_metadata = _domain_context_from_metadata(metadata)
    if from_metadata is not None:
        return from_metadata

    from_source_type = default_graph_domain_context_for_source_type(
        source_type,
        domain_context_policy=domain_context_policy,
        fallback=None,
    )
    if from_source_type is not None:
        return from_source_type

    if ai_inference is not None:
        ai_inferred = _normalize_domain_context(ai_inference())
        if ai_inferred is not None:
            return ai_inferred

    return _normalize_domain_context(fallback)


__all__ = [
    "GENERAL_DEFAULT_DOMAIN",
    "default_graph_domain_context_for_source_type",
    "resolve_graph_domain_context",
]
