"""Typed source adapter registry for direct evidence sources."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchError,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSourcePlugin,
    SourceCandidateContext,
    SourceQueryIntent,
)
from artana_evidence_api.source_plugins.registry import source_plugin
from artana_evidence_api.source_registry import (
    SourceDefinition,
    direct_search_source_keys,
    get_source_definition,
    normalize_source_key,
)
from artana_evidence_api.types.common import JSONObject


class SourceAdapterRegistryError(RuntimeError):
    """Raised when the source adapter registry is internally inconsistent."""


class EvidenceSourceAdapter(Protocol):
    """Source-owned behavior needed by evidence-selection source workflows."""

    @property
    def source_key(self) -> str:
        """Return the canonical source key."""
        ...

    @property
    def source_family(self) -> str:
        """Return the public source family."""
        ...

    @property
    def display_name(self) -> str:
        """Return the public display name for this source."""
        ...

    @property
    def direct_search_supported(self) -> bool:
        """Return whether direct source-search is supported."""
        ...

    @property
    def handoff_target_kind(self) -> str:
        """Return the downstream handoff target kind."""
        ...

    @property
    def request_schema_ref(self) -> str | None:
        """Return the request schema reference exposed by this source."""
        ...

    @property
    def result_schema_ref(self) -> str | None:
        """Return the result schema reference exposed by this source."""
        ...

    @property
    def proposal_type(self) -> str:
        """Return the proposal type used for selected records."""
        ...

    @property
    def review_type(self) -> str:
        """Return the review item type used for selected records."""
        ...

    @property
    def evidence_role(self) -> str:
        """Return the reviewer-facing evidence role."""
        ...

    @property
    def limitations(self) -> tuple[str, ...]:
        """Return source-specific review limitations."""
        ...

    @property
    def normalized_fields(self) -> tuple[str, ...]:
        """Return fields included in normalized extraction payloads."""
        ...

    @property
    def supported_objective_intents(self) -> tuple[str, ...]:
        """Return objective intents supported by source planning."""
        ...

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        """Return result interpretation hints for planning."""
        ...

    @property
    def non_goals(self) -> tuple[str, ...]:
        """Return source planning non-goals."""
        ...

    @property
    def handoff_eligible(self) -> bool:
        """Return whether planned searches can be handed off."""
        ...

    def build_query_payload(self, intent: SourceQueryIntent) -> JSONObject:
        """Build a validated direct-source query payload for one intent."""
        ...

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return this source's normalized record payload."""
        ...

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable provider identifier for one record when present."""
        ...

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """Return whether a selected record should use variant-aware handling."""
        ...

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return source-specific normalized extraction metadata."""
        ...

    def proposal_summary(self, selection_reason: str) -> str:
        """Return a source-specific proposal summary."""
        ...

    def review_item_summary(self, selection_reason: str) -> str:
        """Return a source-specific review-item summary."""
        ...

    def validate_live_search(self, search: EvidenceSelectionLiveSourceSearch) -> None:
        """Validate one live source-search payload for this source."""
        ...

    def build_candidate_context(self, record: JSONObject) -> SourceCandidateContext:
        """Return normalized source context for candidate screening and handoff."""
        ...


@dataclass(frozen=True, slots=True)
class _PluginSourceAdapter:
    """Concrete adapter backed by one source plugin."""

    _plugin: EvidenceSourcePlugin

    @property
    def source_key(self) -> str:
        """Return the canonical source key."""

        return self._plugin.source_key

    @property
    def source_family(self) -> str:
        """Return the public source family."""

        return self._plugin.source_family

    @property
    def display_name(self) -> str:
        """Return the public display name for this source."""

        return self._plugin.display_name

    @property
    def direct_search_supported(self) -> bool:
        """Return whether direct source-search is supported."""

        return self._plugin.direct_search_supported

    @property
    def handoff_target_kind(self) -> str:
        """Return the downstream handoff target kind."""

        return self._plugin.handoff_target_kind

    @property
    def request_schema_ref(self) -> str | None:
        """Return the request schema reference exposed by this source."""

        return self._plugin.request_schema_ref

    @property
    def result_schema_ref(self) -> str | None:
        """Return the result schema reference exposed by this source."""

        return self._plugin.result_schema_ref

    @property
    def proposal_type(self) -> str:
        """Return the proposal type used for selected records."""

        return self._plugin.review_policy.proposal_type

    @property
    def review_type(self) -> str:
        """Return the review item type used for selected records."""

        return self._plugin.review_policy.review_type

    @property
    def evidence_role(self) -> str:
        """Return the reviewer-facing evidence role."""

        return self._plugin.review_policy.evidence_role

    @property
    def limitations(self) -> tuple[str, ...]:
        """Return source-specific review limitations."""

        return self._plugin.review_policy.limitations

    @property
    def normalized_fields(self) -> tuple[str, ...]:
        """Return fields included in normalized extraction payloads."""

        return self._plugin.review_policy.normalized_fields

    @property
    def supported_objective_intents(self) -> tuple[str, ...]:
        """Return objective intents supported by source planning."""

        return self._plugin.supported_objective_intents

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        """Return result interpretation hints for planning."""

        return self._plugin.result_interpretation_hints

    @property
    def non_goals(self) -> tuple[str, ...]:
        """Return source planning non-goals."""

        return self._plugin.non_goals

    @property
    def handoff_eligible(self) -> bool:
        """Return whether planned searches can be handed off."""

        return self._plugin.handoff_eligible

    def build_query_payload(self, intent: SourceQueryIntent) -> JSONObject:
        """Build a validated direct-source query payload for one intent."""

        return self._plugin.build_query_payload(intent)

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return this source's normalized record payload."""

        return self._plugin.normalize_record(record)

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable provider identifier for one record when present."""

        return self._plugin.provider_external_id(record)

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """Return whether a selected record should use variant-aware handling."""

        return self._plugin.recommends_variant_aware(record)

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return source-specific normalized extraction metadata."""

        return self._plugin.normalized_extraction_payload(record)

    def proposal_summary(self, selection_reason: str) -> str:
        """Return a source-specific proposal summary."""

        return self._plugin.proposal_summary(selection_reason)

    def review_item_summary(self, selection_reason: str) -> str:
        """Return a source-specific review-item summary."""

        return self._plugin.review_item_summary(selection_reason)

    def validate_live_search(self, search: EvidenceSelectionLiveSourceSearch) -> None:
        """Validate one live source-search payload for this source."""

        normalized_source_key = normalize_source_key(search.source_key)
        if normalized_source_key != self.source_key:
            msg = (
                f"Adapter for '{self.source_key}' cannot validate "
                f"'{search.source_key}' live source search."
            )
            raise EvidenceSelectionSourceSearchError(msg)
        if search.source_key != self.source_key:
            msg = (
                f"Live source search for '{self.source_key}' must use canonical "
                f"source_key '{self.source_key}', got '{search.source_key}'."
            )
            raise EvidenceSelectionSourceSearchError(msg)
        self._plugin.validate_live_search(search)

    def build_candidate_context(self, record: JSONObject) -> SourceCandidateContext:
        """Return normalized source context for candidate screening and handoff."""

        return self._plugin.build_candidate_context(record)


def source_adapter(source_key: str) -> EvidenceSourceAdapter | None:
    """Return one direct-search source adapter by public or canonical key."""

    return _source_adapters_by_key().get(normalize_source_key(source_key))


def require_source_adapter(source_key: str) -> EvidenceSourceAdapter:
    """Return one direct-search source adapter or raise a registry error."""

    normalized_source_key = normalize_source_key(source_key)
    adapter = _source_adapters_by_key().get(normalized_source_key)
    if adapter is not None:
        return adapter
    msg = f"No source adapter is registered for '{source_key}'."
    raise SourceAdapterRegistryError(msg)


def source_adapters() -> tuple[EvidenceSourceAdapter, ...]:
    """Return direct-search source adapters in source-registry order."""

    return _source_adapters_tuple()


def source_adapter_keys() -> tuple[str, ...]:
    """Return canonical source keys with direct-search adapters."""

    return tuple(adapter.source_key for adapter in _source_adapters_tuple())


def _build_source_adapters() -> tuple[EvidenceSourceAdapter, ...]:
    return tuple(
        _build_source_adapter(source_key) for source_key in direct_search_source_keys()
    )


def _build_source_adapter(source_key: str) -> EvidenceSourceAdapter:
    plugin = source_plugin(source_key)
    definition = get_source_definition(source_key)
    if definition is None:
        msg = f"Direct-search source '{source_key}' has no source definition."
        raise SourceAdapterRegistryError(msg)
    if plugin is None:
        msg = f"Direct-search source '{source_key}' has no source plugin."
        raise SourceAdapterRegistryError(msg)
    _validate_plugin_adapter_contracts(definition=definition, plugin=plugin)
    return _PluginSourceAdapter(_plugin=plugin)


def _validate_plugin_adapter_contracts(
    *,
    definition: SourceDefinition,
    plugin: EvidenceSourcePlugin,
) -> None:
    source_key = definition.source_key
    plugin_definition = plugin.source_definition()
    mismatches: list[str] = []
    if not definition.direct_search_enabled:
        mismatches.append("definition.direct_search_enabled is false")
    if plugin.source_key != source_key:
        mismatches.append("plugin source_key mismatch")
    if plugin_definition != definition:
        mismatches.append("plugin source definition mismatch")
    if plugin.source_family != definition.source_family:
        mismatches.append("plugin source_family mismatch")
    if plugin.request_schema_ref != definition.request_schema_ref:
        mismatches.append("plugin request_schema_ref mismatch")
    if plugin.result_schema_ref != definition.result_schema_ref:
        mismatches.append("plugin result_schema_ref mismatch")
    if plugin.review_policy.source_key != source_key:
        mismatches.append("plugin review policy source_key mismatch")
    if mismatches:
        msg = (
            f"Source plugin contract for '{source_key}' is inconsistent: "
            f"{'; '.join(mismatches)}."
        )
        raise SourceAdapterRegistryError(msg)


@lru_cache(maxsize=1)
def _source_adapters_tuple() -> tuple[EvidenceSourceAdapter, ...]:
    return _build_source_adapters()


@lru_cache(maxsize=1)
def _source_adapters_by_key() -> dict[str, EvidenceSourceAdapter]:
    return {adapter.source_key: adapter for adapter in _source_adapters_tuple()}


__all__ = [
    "EvidenceSourceAdapter",
    "SourceCandidateContext",
    "SourceAdapterRegistryError",
    "source_adapter",
    "source_adapter_keys",
    "source_adapters",
    "require_source_adapter",
]
