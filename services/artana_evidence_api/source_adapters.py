"""Typed source adapter registry for direct evidence sources."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from typing import Protocol

from artana_evidence_api.evidence_selection_extraction_policy import (
    EvidenceSelectionExtractionPolicy,
    extraction_policy_for_source,
)
from artana_evidence_api.evidence_selection_source_playbooks import (
    SourceQueryPlaybook,
    source_query_playbook,
)
from artana_evidence_api.evidence_selection_source_search import (
    EvidenceSelectionLiveSourceSearch,
    EvidenceSelectionSourceSearchError,
    validate_live_source_search,
)
from artana_evidence_api.source_policies import (
    SourceRecordPolicy,
    source_record_policy,
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

    def definition(self) -> SourceDefinition:
        """Return public source metadata and capability flags."""
        ...

    def query_playbook(self) -> SourceQueryPlaybook:
        """Return the source-specific query planning contract."""
        ...

    def record_policy(self) -> SourceRecordPolicy:
        """Return the source-specific record normalization policy."""
        ...

    def extraction_policy(self) -> EvidenceSelectionExtractionPolicy:
        """Return the source-specific extraction and review staging policy."""
        ...

    def validate_live_search(self, search: EvidenceSelectionLiveSourceSearch) -> None:
        """Validate one live source-search payload for this source."""
        ...

    def build_candidate_context(self, record: JSONObject) -> JSONObject:
        """Return normalized source context for candidate screening and handoff."""
        ...


@dataclass(frozen=True, slots=True)
class SourceAdapter:
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

    def definition(self) -> SourceDefinition:
        """Return public source metadata and capability flags."""

        return self._definition

    def query_playbook(self) -> SourceQueryPlaybook:
        """Return the source-specific query planning contract."""

        return self._query_playbook

    def record_policy(self) -> SourceRecordPolicy:
        """Return the source-specific record normalization policy."""

        return self._record_policy

    def extraction_policy(self) -> EvidenceSelectionExtractionPolicy:
        """Return the source-specific extraction and review staging policy."""

        return self._extraction_policy

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

    def build_candidate_context(self, record: JSONObject) -> JSONObject:
        """Return normalized source context for candidate screening and handoff."""

        provider_external_id = self._record_policy.provider_external_id(record)
        context: JSONObject = {
            "source_key": self.source_key,
            "source_family": self.source_family,
            "display_name": self._definition.display_name,
            "normalized_record": self._record_policy.normalize_record(record),
            "variant_aware_recommended": self._record_policy.recommends_variant_aware(
                record,
            ),
            "handoff_target_kind": self._record_policy.handoff_target_kind,
            "provider_external_id": provider_external_id,
            "extraction_policy": {
                "proposal_type": self._extraction_policy.proposal_type,
                "review_type": self._extraction_policy.review_type,
                "evidence_role": self._extraction_policy.evidence_role,
                "limitations": list(self._extraction_policy.limitations),
                "normalized_fields": list(self._extraction_policy.normalized_fields),
            },
        }
        return context


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


def _build_source_adapters() -> tuple[SourceAdapter, ...]:
    return tuple(
        _build_source_adapter(source_key) for source_key in direct_search_source_keys()
    )


def _build_source_adapter(source_key: str) -> SourceAdapter:
    definition = get_source_definition(source_key)
    if definition is None:
        msg = f"Direct-search source '{source_key}' has no source definition."
        raise SourceAdapterRegistryError(msg)
    query_playbook = source_query_playbook(source_key)
    if query_playbook is None:
        msg = f"Direct-search source '{source_key}' has no query playbook."
        raise SourceAdapterRegistryError(msg)
    record_policy = source_record_policy(source_key)
    if record_policy is None:
        msg = f"Direct-search source '{source_key}' has no record policy."
        raise SourceAdapterRegistryError(msg)
    extraction_policy = extraction_policy_for_source(source_key)
    _validate_adapter_contracts(
        definition=definition,
        query_playbook=query_playbook,
        record_policy=record_policy,
        extraction_policy=extraction_policy,
    )
    return SourceAdapter(
        _definition=definition,
        _query_playbook=query_playbook,
        _record_policy=record_policy,
        _extraction_policy=extraction_policy,
        _live_search_validator=validate_live_source_search,
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
def _source_adapters_tuple() -> tuple[SourceAdapter, ...]:
    return _build_source_adapters()


@lru_cache(maxsize=1)
def _source_adapters_by_key() -> dict[str, SourceAdapter]:
    return {adapter.source_key: adapter for adapter in _source_adapters_tuple()}


__all__ = [
    "EvidenceSourceAdapter",
    "SourceAdapter",
    "SourceAdapterRegistryError",
    "source_adapter",
    "source_adapter_keys",
    "source_adapters",
    "require_source_adapter",
]
