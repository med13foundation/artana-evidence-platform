"""Plugin-backed compatibility helpers for captured source records."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.source_plugins.registry import source_plugin, source_plugins
from artana_evidence_api.types.common import JSONObject

SourceHandoffTargetKind = Literal["source_document"]


@dataclass(frozen=True, slots=True)
class SourceRecordPolicy:
    """Compatibility facade for source-specific record behavior.

    Source plugins are the source of truth. This object is kept only for older
    tests and public helper imports that still expect a record-policy shape.
    """

    source_key: str
    source_family: str
    provider_external_id: Callable[[JSONObject], str | None]
    normalize_record: Callable[[JSONObject], JSONObject]
    recommends_variant_aware: Callable[[JSONObject], bool]
    handoff_target_kind: SourceHandoffTargetKind = "source_document"
    direct_search_supported: bool = True
    request_schema_ref: str | None = None
    result_schema_ref: str | None = None


def _source_document_handoff_kind(value: str) -> SourceHandoffTargetKind:
    if value != "source_document":
        msg = f"unsupported source handoff target kind: {value!r}"
        raise ValueError(msg)
    return "source_document"


def adapter_source_record_policy(source_key: str) -> SourceRecordPolicy | None:
    """Return a plugin-backed source record policy for one source key."""

    plugin = source_plugin(source_key)
    if plugin is None:
        return None
    return SourceRecordPolicy(
        source_key=plugin.source_key,
        source_family=plugin.source_family,
        provider_external_id=plugin.provider_external_id,
        normalize_record=plugin.normalize_record,
        recommends_variant_aware=plugin.recommends_variant_aware,
        handoff_target_kind=_source_document_handoff_kind(plugin.handoff_target_kind),
        direct_search_supported=plugin.direct_search_supported,
        request_schema_ref=plugin.request_schema_ref,
        result_schema_ref=plugin.result_schema_ref,
    )


def adapter_source_record_policies() -> tuple[SourceRecordPolicy, ...]:
    """Return plugin-backed source record policies in registry order."""

    return tuple(
        SourceRecordPolicy(
            source_key=plugin.source_key,
            source_family=plugin.source_family,
            provider_external_id=plugin.provider_external_id,
            normalize_record=plugin.normalize_record,
            recommends_variant_aware=plugin.recommends_variant_aware,
            handoff_target_kind=_source_document_handoff_kind(
                plugin.handoff_target_kind
            ),
            direct_search_supported=plugin.direct_search_supported,
            request_schema_ref=plugin.request_schema_ref,
            result_schema_ref=plugin.result_schema_ref,
        )
        for plugin in source_plugins()
    )


__all__ = [
    "SourceHandoffTargetKind",
    "SourceRecordPolicy",
    "adapter_source_record_policies",
    "adapter_source_record_policy",
]
