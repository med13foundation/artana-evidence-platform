"""Domain-context resolution helpers for dictionary records."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


class DomainContextResolver:
    """Resolve domain context from explicit input, metadata, or source defaults."""

    PUBMED_DEFAULT_DOMAIN: ClassVar[str] = "clinical"
    CLINVAR_DEFAULT_DOMAIN: ClassVar[str] = "genomics"
    GENERAL_DEFAULT_DOMAIN: ClassVar[str] = "general"

    _SOURCE_TYPE_DEFAULTS: ClassVar[dict[str, str]] = {
        "pubmed": PUBMED_DEFAULT_DOMAIN,
        "clinvar": CLINVAR_DEFAULT_DOMAIN,
    }
    _METADATA_KEYS: ClassVar[tuple[str, ...]] = ("domain_context", "domain")

    @classmethod
    def normalize(cls, value: str | None) -> str | None:
        """Normalize a domain context value into a canonical lower-case token."""
        if value is None:
            return None
        normalized = value.strip().lower()
        return normalized or None

    @classmethod
    def from_metadata(cls, metadata: Mapping[str, object] | None) -> str | None:
        """Extract a normalized domain context from metadata payload."""
        if metadata is None:
            return None
        for key in cls._METADATA_KEYS:
            raw_value = metadata.get(key)
            if not isinstance(raw_value, str):
                continue
            normalized = cls.normalize(raw_value)
            if normalized is not None:
                return normalized
        return None

    @classmethod
    def default_for_source_type(
        cls,
        source_type: str | None,
        *,
        fallback: str | None = GENERAL_DEFAULT_DOMAIN,
    ) -> str | None:
        """Return the default domain context for a source type."""
        normalized_source_type = cls.normalize(source_type)
        if normalized_source_type is None:
            return cls.normalize(fallback)
        source_default = cls._SOURCE_TYPE_DEFAULTS.get(normalized_source_type)
        if source_default is not None:
            return source_default
        return cls.normalize(fallback)

    @classmethod
    def resolve(
        cls,
        *,
        explicit_domain_context: str | None = None,
        metadata: Mapping[str, object] | None = None,
        source_type: str | None = None,
        ai_inference: Callable[[], str | None] | None = None,
        fallback: str | None = None,
    ) -> str | None:
        """Resolve a domain context via deterministic precedence rules."""
        explicit = cls.normalize(explicit_domain_context)
        if explicit is not None:
            return explicit

        from_metadata = cls.from_metadata(metadata)
        if from_metadata is not None:
            return from_metadata

        from_source_type = cls.default_for_source_type(source_type, fallback=None)
        if from_source_type is not None:
            return from_source_type

        if ai_inference is not None:
            ai_inferred = cls.normalize(ai_inference())
            if ai_inferred is not None:
                return ai_inferred

        return cls.normalize(fallback)


__all__ = ["DomainContextResolver"]
