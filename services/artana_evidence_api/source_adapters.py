"""Typed source adapter registry for direct evidence sources."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from artana_evidence_api.evidence_selection_extraction_policy import (
    EvidenceSelectionExtractionPolicy,
    adapter_extraction_policy_for_source,
    adapter_normalized_extraction_payload,
    adapter_proposal_summary,
    adapter_review_item_summary,
)
from artana_evidence_api.evidence_selection_source_playbooks import (
    SourceQueryIntent,
    SourceQueryPlaybook,
    adapter_source_query_playbook,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchError,
    adapter_validate_live_source_search,
)
from artana_evidence_api.source_policies import (
    SourceRecordPolicy,
    adapter_source_record_policy,
)
from artana_evidence_api.source_registry import (
    SourceDefinition,
    direct_search_source_keys,
    get_source_definition,
    normalize_source_key,
)
from artana_evidence_api.types.common import JSONObject

LiveSourceSearchValidator = Callable[[EvidenceSelectionLiveSourceSearch], None]


class SourceAdapterRegistryError(RuntimeError):
    """Raised when the source adapter registry is internally inconsistent."""


@dataclass(frozen=True, slots=True)
class SourceCandidateContext:
    """Typed source context used by candidate screening and handoff artifacts."""

    source_key: str
    source_family: str
    display_name: str
    normalized_record: JSONObject
    variant_aware_recommended: bool
    handoff_target_kind: str
    provider_external_id: str | None
    proposal_type: str
    review_type: str
    evidence_role: str
    limitations: tuple[str, ...]
    normalized_fields: tuple[str, ...]

    def to_json(self) -> JSONObject:
        """Return the JSON payload shape stored in candidate artifacts."""

        return {
            "source_key": self.source_key,
            "source_family": self.source_family,
            "display_name": self.display_name,
            "normalized_record": self.normalized_record,
            "variant_aware_recommended": self.variant_aware_recommended,
            "handoff_target_kind": self.handoff_target_kind,
            "provider_external_id": self.provider_external_id,
            "extraction_policy": {
                "proposal_type": self.proposal_type,
                "review_type": self.review_type,
                "evidence_role": self.evidence_role,
                "limitations": list(self.limitations),
                "normalized_fields": list(self.normalized_fields),
            },
        }


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
class _SourceAdapter:
    """Concrete adapter that composes existing source-owned contracts."""

    _definition: SourceDefinition
    _query_playbook: SourceQueryPlaybook
    _record_policy: SourceRecordPolicy
    _extraction_policy: EvidenceSelectionExtractionPolicy
    _live_search_validator: LiveSourceSearchValidator

    @property
    def source_key(self) -> str:
        """Return the canonical source key."""

        return self._definition.source_key

    @property
    def source_family(self) -> str:
        """Return the public source family."""

        return self._definition.source_family

    @property
    def display_name(self) -> str:
        """Return the public display name for this source."""

        return self._definition.display_name

    @property
    def direct_search_supported(self) -> bool:
        """Return whether direct source-search is supported."""

        return self._record_policy.direct_search_supported

    @property
    def handoff_target_kind(self) -> str:
        """Return the downstream handoff target kind."""

        return self._record_policy.handoff_target_kind

    @property
    def request_schema_ref(self) -> str | None:
        """Return the request schema reference exposed by this source."""

        return self._record_policy.request_schema_ref

    @property
    def result_schema_ref(self) -> str | None:
        """Return the result schema reference exposed by this source."""

        return self._record_policy.result_schema_ref

    @property
    def proposal_type(self) -> str:
        """Return the proposal type used for selected records."""

        return self._extraction_policy.proposal_type

    @property
    def review_type(self) -> str:
        """Return the review item type used for selected records."""

        return self._extraction_policy.review_type

    @property
    def evidence_role(self) -> str:
        """Return the reviewer-facing evidence role."""

        return self._extraction_policy.evidence_role

    @property
    def limitations(self) -> tuple[str, ...]:
        """Return source-specific review limitations."""

        return self._extraction_policy.limitations

    @property
    def normalized_fields(self) -> tuple[str, ...]:
        """Return fields included in normalized extraction payloads."""

        return self._extraction_policy.normalized_fields

    @property
    def supported_objective_intents(self) -> tuple[str, ...]:
        """Return objective intents supported by source planning."""

        return self._query_playbook.supported_objective_intents

    @property
    def result_interpretation_hints(self) -> tuple[str, ...]:
        """Return result interpretation hints for planning."""

        return self._query_playbook.result_interpretation_hints

    @property
    def non_goals(self) -> tuple[str, ...]:
        """Return source planning non-goals."""

        return self._query_playbook.non_goals

    @property
    def handoff_eligible(self) -> bool:
        """Return whether planned searches can be handed off."""

        return self._query_playbook.handoff_eligible

    def build_query_payload(self, intent: SourceQueryIntent) -> JSONObject:
        """Build a validated direct-source query payload for one intent."""

        return self._query_playbook.build_payload(intent)

    def normalize_record(self, record: JSONObject) -> JSONObject:
        """Return this source's normalized record payload."""

        return self._record_policy.normalize_record(record)

    def provider_external_id(self, record: JSONObject) -> str | None:
        """Return the stable provider identifier for one record when present."""

        return self._record_policy.provider_external_id(record)

    def recommends_variant_aware(self, record: JSONObject) -> bool:
        """Return whether a selected record should use variant-aware handling."""

        return self._record_policy.recommends_variant_aware(record)

    def normalized_extraction_payload(self, record: JSONObject) -> JSONObject:
        """Return source-specific normalized extraction metadata."""

        return adapter_normalized_extraction_payload(
            source_key=self.source_key,
            record=record,
        )

    def proposal_summary(self, selection_reason: str) -> str:
        """Return a source-specific proposal summary."""

        return adapter_proposal_summary(
            source_key=self.source_key,
            selection_reason=selection_reason,
        )

    def review_item_summary(self, selection_reason: str) -> str:
        """Return a source-specific review-item summary."""

        return adapter_review_item_summary(
            source_key=self.source_key,
            selection_reason=selection_reason,
        )

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
        self._live_search_validator(search)

    def build_candidate_context(self, record: JSONObject) -> SourceCandidateContext:
        """Return normalized source context for candidate screening and handoff."""

        return SourceCandidateContext(
            source_key=self.source_key,
            source_family=self.source_family,
            display_name=self.display_name,
            normalized_record=self.normalize_record(record),
            variant_aware_recommended=self.recommends_variant_aware(record),
            handoff_target_kind=self.handoff_target_kind,
            provider_external_id=self.provider_external_id(record),
            proposal_type=self.proposal_type,
            review_type=self.review_type,
            evidence_role=self.evidence_role,
            limitations=self.limitations,
            normalized_fields=self.normalized_fields,
        )


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


def _build_source_adapters() -> tuple[_SourceAdapter, ...]:
    return tuple(
        _build_source_adapter(source_key) for source_key in direct_search_source_keys()
    )


def _build_source_adapter(source_key: str) -> _SourceAdapter:
    definition = get_source_definition(source_key)
    if definition is None:
        msg = f"Direct-search source '{source_key}' has no source definition."
        raise SourceAdapterRegistryError(msg)
    query_playbook = adapter_source_query_playbook(source_key)
    if query_playbook is None:
        msg = f"Direct-search source '{source_key}' has no query playbook."
        raise SourceAdapterRegistryError(msg)
    record_policy = adapter_source_record_policy(source_key)
    if record_policy is None:
        msg = f"Direct-search source '{source_key}' has no record policy."
        raise SourceAdapterRegistryError(msg)
    try:
        extraction_policy = adapter_extraction_policy_for_source(source_key)
    except KeyError as exc:
        msg = f"Direct-search source '{source_key}' has no extraction policy."
        raise SourceAdapterRegistryError(msg) from exc
    _validate_adapter_contracts(
        definition=definition,
        query_playbook=query_playbook,
        record_policy=record_policy,
        extraction_policy=extraction_policy,
    )
    return _SourceAdapter(
        _definition=definition,
        _query_playbook=query_playbook,
        _record_policy=record_policy,
        _extraction_policy=extraction_policy,
        _live_search_validator=adapter_validate_live_source_search,
    )


def _validate_adapter_contracts(
    *,
    definition: SourceDefinition,
    query_playbook: SourceQueryPlaybook,
    record_policy: SourceRecordPolicy,
    extraction_policy: EvidenceSelectionExtractionPolicy,
) -> None:
    source_key = definition.source_key
    mismatches: list[str] = []
    if not definition.direct_search_enabled:
        mismatches.append("definition.direct_search_enabled is false")
    if query_playbook.source_key != source_key:
        mismatches.append("query playbook source_key mismatch")
    if record_policy.source_key != source_key:
        mismatches.append("record policy source_key mismatch")
    if record_policy.source_family != definition.source_family:
        mismatches.append("record policy source_family mismatch")
    if record_policy.request_schema_ref != definition.request_schema_ref:
        mismatches.append("record policy request_schema_ref mismatch")
    if record_policy.result_schema_ref != definition.result_schema_ref:
        mismatches.append("record policy result_schema_ref mismatch")
    if extraction_policy.source_key != source_key:
        mismatches.append("extraction policy source_key mismatch")
    if mismatches:
        msg = (
            f"Source adapter contract for '{source_key}' is inconsistent: "
            f"{'; '.join(mismatches)}."
        )
        raise SourceAdapterRegistryError(msg)


@lru_cache(maxsize=1)
def _source_adapters_tuple() -> tuple[_SourceAdapter, ...]:
    return _build_source_adapters()


@lru_cache(maxsize=1)
def _source_adapters_by_key() -> dict[str, _SourceAdapter]:
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
