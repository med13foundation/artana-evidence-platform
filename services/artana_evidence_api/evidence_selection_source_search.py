"""Tool-backed source-search runner for evidence-selection harness runs."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from uuid import UUID

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    DirectSourceSearchStore,
)
from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
from artana_evidence_api.source_enrichment_bridges import (
    MarrvelDiscoveryServiceProtocol,
    build_marrvel_discovery_service,
)
from artana_evidence_api.source_plugins.contracts import (
    EvidenceSelectionSourceSearchError,
    SourceSearchExecutionContext,
)
from artana_evidence_api.source_plugins.registry import (
    source_plugin,
    source_plugin_for_execution,
)
from artana_evidence_api.source_registry import normalize_source_key
from artana_evidence_api.types.common import JSONObject


@dataclass(frozen=True, slots=True)
class EvidenceSelectionLiveSourceSearch:
    """One source search the harness should create before screening records."""

    source_key: str
    query_payload: JSONObject
    max_records: int | None = None
    timeout_seconds: float | None = None


class EvidenceSelectionSourceSearchRunner:
    """Create durable direct-source searches for the evidence-selection harness."""

    def __init__(
        self,
        *,
        pubmed_discovery_service_factory: (
            Callable[[], AbstractContextManager[PubMedDiscoveryService]] | None
        ) = None,
        marrvel_discovery_service_factory: (
            Callable[[], MarrvelDiscoveryServiceProtocol | None]
        ) = build_marrvel_discovery_service,
    ) -> None:
        self._pubmed_discovery_service_factory = pubmed_discovery_service_factory
        self._marrvel_discovery_service_factory = marrvel_discovery_service_factory

    async def run_search(
        self,
        *,
        space_id: UUID,
        created_by: UUID | str,
        source_search: EvidenceSelectionLiveSourceSearch,
        store: DirectSourceSearchStore,
    ) -> DirectSourceSearchRecord:
        """Run and store one source-specific search."""

        normalized_source_key = normalize_source_key(source_search.source_key)
        if normalized_source_key != source_search.source_key:
            msg = (
                "Evidence-selection live source searches must use canonical "
                f"source keys; got '{source_search.source_key}', expected "
                f"'{normalized_source_key}'."
            )
            raise EvidenceSelectionSourceSearchError(msg)

        plugin = source_plugin_for_execution(
            normalized_source_key,
            pubmed_discovery_service_factory=self._pubmed_discovery_service_factory,
            marrvel_discovery_service_factory=self._marrvel_discovery_service_factory,
        )
        if plugin is not None:
            return await plugin.run_direct_search(
                context=SourceSearchExecutionContext(
                    space_id=space_id,
                    created_by=created_by,
                    store=store,
                ),
                search=source_search,
            )

        raise EvidenceSelectionSourceSearchError(
            "Evidence-selection live source search does not support "
            f"'{source_search.source_key}'.",
        )


def adapter_validate_live_source_search(
    source_search: EvidenceSelectionLiveSourceSearch,
) -> None:
    """Validate a live source-search payload before external source side effects."""

    plugin = source_plugin(source_search.source_key)
    if plugin is not None:
        plugin.validate_live_search(source_search)
        return
    raise EvidenceSelectionSourceSearchError(
        "Evidence-selection live source search does not support "
        f"'{source_search.source_key}'.",
    )


__all__ = [
    "EvidenceSelectionLiveSourceSearch",
    "EvidenceSelectionSourceSearchError",
    "EvidenceSelectionSourceSearchRunner",
]
