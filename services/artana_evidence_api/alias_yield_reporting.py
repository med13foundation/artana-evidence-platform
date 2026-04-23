"""Service-local alias-yield reporting helpers for research-init surfaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from artana_evidence_api.types.common import JSONObject
from pydantic import BaseModel, ConfigDict, Field


class AliasYieldSourceMetadata(BaseModel):
    """Backend-derived alias persistence counts for one source run."""

    model_config = ConfigDict(extra="forbid")

    source_key: str
    alias_candidates_count: int = Field(default=0, ge=0)
    aliases_registered: int | None = Field(default=None, ge=0)
    aliases_persisted: int = Field(default=0, ge=0)
    aliases_skipped: int = Field(default=0, ge=0)
    alias_entities_touched: int = Field(default=0, ge=0)
    alias_errors: list[str] = Field(default_factory=list)
    aliases_persisted_by_namespace_entity_type: dict[str, int] = Field(
        default_factory=dict,
    )

    def to_json_object(self) -> JSONObject:
        """Serialize to a JSON-safe object for run/reporting metadata."""
        payload: JSONObject = {
            "source_key": self.source_key,
            "alias_candidates_count": self.alias_candidates_count,
            "aliases_persisted": self.aliases_persisted,
            "aliases_skipped": self.aliases_skipped,
            "alias_entities_touched": self.alias_entities_touched,
            "alias_errors": list(self.alias_errors),
        }
        if self.aliases_registered is not None:
            payload["aliases_registered"] = self.aliases_registered
        if self.aliases_persisted_by_namespace_entity_type:
            payload["aliases_persisted_by_namespace_entity_type"] = dict(
                sorted(self.aliases_persisted_by_namespace_entity_type.items()),
            )
        return payload


class AliasYieldTotalsMetadata(BaseModel):
    """Backend-derived alias persistence totals across source runs."""

    model_config = ConfigDict(extra="forbid")

    source_count: int = Field(default=0, ge=0)
    alias_candidates_count: int = Field(default=0, ge=0)
    aliases_registered: int = Field(default=0, ge=0)
    aliases_persisted: int = Field(default=0, ge=0)
    aliases_skipped: int = Field(default=0, ge=0)
    alias_entities_touched: int = Field(default=0, ge=0)
    alias_error_count: int = Field(default=0, ge=0)

    def to_json_object(self) -> JSONObject:
        """Serialize to a JSON-safe object for run/reporting metadata."""
        return {
            "source_count": self.source_count,
            "alias_candidates_count": self.alias_candidates_count,
            "aliases_registered": self.aliases_registered,
            "aliases_persisted": self.aliases_persisted,
            "aliases_skipped": self.aliases_skipped,
            "alias_entities_touched": self.alias_entities_touched,
            "alias_error_count": self.alias_error_count,
        }


class AliasYieldRollupMetadata(BaseModel):
    """Backend-derived alias persistence rollup across source runs."""

    model_config = ConfigDict(extra="forbid")

    sources: dict[str, AliasYieldSourceMetadata] = Field(default_factory=dict)
    totals: AliasYieldTotalsMetadata = Field(default_factory=AliasYieldTotalsMetadata)

    def to_json_object(self) -> JSONObject:
        """Serialize to a JSON-safe object for run/reporting metadata."""
        return {
            "sources": {
                key: source.to_json_object()
                for key, source in sorted(self.sources.items())
            },
            "totals": self.totals.to_json_object(),
        }


def build_alias_yield_source_metadata(
    *,
    source_key: str,
    raw_summary: object,
) -> AliasYieldSourceMetadata | None:
    """Build one normalized alias-yield row from a summary or JSON payload."""
    alias_candidates_count = _int_field(raw_summary, "alias_candidates_count")
    aliases_registered = _optional_int_field(raw_summary, "aliases_registered")
    if alias_candidates_count == 0 and aliases_registered is not None:
        alias_candidates_count = aliases_registered

    aliases_persisted = _int_field(raw_summary, "aliases_persisted")
    aliases_skipped = _int_field(raw_summary, "aliases_skipped")
    if not _has_field(raw_summary, "aliases_skipped"):
        attempted_count = (
            aliases_registered
            if aliases_registered is not None
            else alias_candidates_count
        )
        aliases_skipped = max(attempted_count - aliases_persisted, 0)

    alias_entities_touched = _int_field(raw_summary, "alias_entities_touched")
    alias_errors = _string_sequence_field(raw_summary, "alias_errors")
    namespace_metrics = _namespace_entity_type_metrics(raw_summary)

    has_signal = any(
        value > 0
        for value in (
            alias_candidates_count,
            aliases_registered or 0,
            aliases_persisted,
            aliases_skipped,
            alias_entities_touched,
        )
    )
    has_signal = has_signal or bool(alias_errors) or bool(namespace_metrics)
    if not has_signal:
        return None

    return AliasYieldSourceMetadata(
        source_key=source_key,
        alias_candidates_count=alias_candidates_count,
        aliases_registered=aliases_registered,
        aliases_persisted=aliases_persisted,
        aliases_skipped=aliases_skipped,
        alias_entities_touched=alias_entities_touched,
        alias_errors=alias_errors,
        aliases_persisted_by_namespace_entity_type=namespace_metrics,
    )


def build_alias_yield_rollup(
    source_results: Mapping[str, object],
) -> AliasYieldRollupMetadata | None:
    """Build a normalized alias-yield rollup from source result payloads."""
    source_summaries: dict[str, AliasYieldSourceMetadata] = {}
    for source_key, raw_summary in source_results.items():
        if source_key == "alias_yield":
            continue
        source_summary = build_alias_yield_source_metadata(
            source_key=source_key,
            raw_summary=raw_summary,
        )
        if source_summary is not None:
            source_summaries[source_key] = source_summary

    if not source_summaries:
        return None

    totals = AliasYieldTotalsMetadata(
        source_count=len(source_summaries),
        alias_candidates_count=sum(
            summary.alias_candidates_count for summary in source_summaries.values()
        ),
        aliases_registered=sum(
            summary.aliases_registered or 0 for summary in source_summaries.values()
        ),
        aliases_persisted=sum(
            summary.aliases_persisted for summary in source_summaries.values()
        ),
        aliases_skipped=sum(
            summary.aliases_skipped for summary in source_summaries.values()
        ),
        alias_entities_touched=sum(
            summary.alias_entities_touched for summary in source_summaries.values()
        ),
        alias_error_count=sum(
            len(summary.alias_errors) for summary in source_summaries.values()
        ),
    )
    return AliasYieldRollupMetadata(sources=source_summaries, totals=totals)


def attach_alias_yield_rollup(
    source_results: dict[str, JSONObject],
) -> AliasYieldRollupMetadata | None:
    """Attach the normalized alias-yield rollup to source_results in place."""
    rollup = build_alias_yield_rollup(source_results)
    if rollup is None:
        source_results.pop("alias_yield", None)
        return None
    source_results["alias_yield"] = rollup.to_json_object()
    return rollup


def source_results_with_alias_yield(
    source_results: Mapping[str, JSONObject],
) -> dict[str, JSONObject]:
    """Return a JSON-safe source-results copy with alias-yield rollup attached."""
    copied: dict[str, JSONObject] = {
        source_key: dict(source_payload)
        for source_key, source_payload in source_results.items()
        if source_key != "alias_yield"
    }
    attach_alias_yield_rollup(copied)
    return copied


def _read_field(raw_summary: object, field_name: str) -> object:
    if isinstance(raw_summary, Mapping):
        return raw_summary.get(field_name)
    return getattr(raw_summary, field_name, None)


def _has_field(raw_summary: object, field_name: str) -> bool:
    if isinstance(raw_summary, Mapping):
        return field_name in raw_summary
    return hasattr(raw_summary, field_name)


def _int_field(raw_summary: object, field_name: str) -> int:
    value = _read_field(raw_summary, field_name)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _optional_int_field(raw_summary: object, field_name: str) -> int | None:
    if not _has_field(raw_summary, field_name):
        return None
    value = _read_field(raw_summary, field_name)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _string_sequence_field(raw_summary: object, field_name: str) -> list[str]:
    value = _read_field(raw_summary, field_name)
    if isinstance(value, str) or not isinstance(value, Sequence):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _namespace_entity_type_metrics(raw_summary: object) -> dict[str, int]:
    value = _read_field(
        raw_summary,
        "aliases_persisted_by_namespace_entity_type",
    )
    if not isinstance(value, Mapping):
        return {}
    metrics: dict[str, int] = {}
    for raw_key, raw_count in value.items():
        if not isinstance(raw_key, str):
            continue
        if not isinstance(raw_count, int) or isinstance(raw_count, bool):
            continue
        if raw_count > 0:
            metrics[raw_key] = raw_count
    return metrics


__all__ = [
    "AliasYieldRollupMetadata",
    "AliasYieldSourceMetadata",
    "AliasYieldTotalsMetadata",
    "attach_alias_yield_rollup",
    "build_alias_yield_rollup",
    "build_alias_yield_source_metadata",
    "source_results_with_alias_yield",
]
