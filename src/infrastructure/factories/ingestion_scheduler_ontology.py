"""Ontology ingestion runner helpers for scheduled ingestion."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.infrastructure.ingest.graph_ontology_entity_writer import (
    GraphOntologyEntityWriter,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from src.domain.entities.user_data_source import UserDataSource
    from src.domain.services.ingestion import (
        IngestionExtractionTarget,
        IngestionRunContext,
        IngestionRunSummary,
    )
    from src.type_definitions.common import JSONObject

logger = logging.getLogger(__name__)


class OntologyRunSummaryAdapter:
    """Adapt OntologyIngestionSummary to the IngestionRunSummary protocol."""

    def __init__(self, summary: object) -> None:
        self._s = summary

    @property
    def source_id(self) -> UUID:
        return self._s.source_id  # type: ignore[no-any-return]

    @property
    def fetched_records(self) -> int:
        return getattr(self._s, "terms_fetched", 0)  # type: ignore[no-any-return]

    @property
    def parsed_publications(self) -> int:
        return getattr(self._s, "terms_imported", 0)  # type: ignore[no-any-return]

    @property
    def created_publications(self) -> int:
        return getattr(self._s, "entities_created", 0)  # type: ignore[no-any-return]

    @property
    def updated_publications(self) -> int:
        return getattr(self._s, "entities_updated", 0)  # type: ignore[no-any-return]

    @property
    def alias_candidates_count(self) -> int:
        return getattr(self._s, "alias_candidates_count", 0)  # type: ignore[no-any-return]

    @property
    def aliases_registered(self) -> int:
        return getattr(self._s, "aliases_registered", 0)  # type: ignore[no-any-return]

    @property
    def aliases_persisted(self) -> int:
        return getattr(self._s, "aliases_persisted", 0)  # type: ignore[no-any-return]

    @property
    def aliases_skipped(self) -> int:
        return getattr(self._s, "aliases_skipped", 0)  # type: ignore[no-any-return]

    @property
    def alias_entities_touched(self) -> int:
        return getattr(self._s, "alias_entities_touched", 0)  # type: ignore[no-any-return]

    @property
    def alias_errors(self) -> tuple[str, ...]:
        return getattr(self._s, "alias_errors", ())  # type: ignore[no-any-return]

    @property
    def aliases_persisted_by_namespace_entity_type(self) -> dict[str, int]:
        return getattr(
            self._s,
            "aliases_persisted_by_namespace_entity_type",
            {},
        )  # type: ignore[no-any-return]

    @property
    def extraction_targets(self) -> tuple[IngestionExtractionTarget, ...]:
        return ()

    @property
    def executed_query(self) -> str | None:
        return None

    @property
    def query_signature(self) -> str | None:
        return None

    @property
    def checkpoint_before(self) -> JSONObject | None:
        return getattr(self._s, "checkpoint_before", None)  # type: ignore[no-any-return]

    @property
    def checkpoint_after(self) -> JSONObject | None:
        return getattr(self._s, "checkpoint_after", None)  # type: ignore[no-any-return]

    @property
    def checkpoint_kind(self) -> str | None:
        return "none"

    @property
    def new_records(self) -> int:
        return getattr(self._s, "terms_imported", 0)  # type: ignore[no-any-return]

    @property
    def updated_records(self) -> int:
        return getattr(self._s, "entities_updated", 0)  # type: ignore[no-any-return]

    @property
    def unchanged_records(self) -> int:
        return 0

    @property
    def skipped_records(self) -> int:
        return getattr(self._s, "skipped_obsolete", 0)  # type: ignore[no-any-return]

    @property
    def ingestion_job_id(self) -> UUID | None:
        return getattr(self._s, "ingestion_job_id", None)  # type: ignore[no-any-return]


async def run_ontology_ingestion(
    source: UserDataSource,
    *,
    context: IngestionRunContext | None = None,
    gateway_factory: Callable[[], object] | None = None,
) -> IngestionRunSummary:
    """Run one scheduled ontology ingestion with optional graph writes."""
    from src.application.services.ontology_ingestion_service import (
        OntologyIngestionService,
    )
    from src.domain.entities.data_source_configs.ontology import OntologyQueryConfig

    if gateway_factory is None:
        from src.infrastructure.ingest.hpo_gateway import HPOGateway

        gateway_factory = HPOGateway
    gateway = gateway_factory()

    entity_writer = _create_entity_writer(source)
    ontology_service = OntologyIngestionService(
        gateway=gateway,  # type: ignore[arg-type]
        entity_writer=entity_writer,  # type: ignore[arg-type]
    )
    config_metadata = (
        source.configuration.metadata if source.configuration is not None else {}
    )
    config = OntologyQueryConfig.model_validate(config_metadata or {})
    checkpoint_before = (
        context.source_sync_state.checkpoint_payload
        if context is not None and context.source_sync_state is not None
        else None
    )
    summary = await ontology_service.ingest(
        source_id=source.id,
        research_space_id=(
            str(source.research_space_id)
            if source.research_space_id is not None
            else None
        ),
        config=config,
        checkpoint_before=checkpoint_before,
    )
    _log_alias_stats(summary)
    _log_ai_sentence_stats(entity_writer)
    return OntologyRunSummaryAdapter(summary)


def _create_entity_writer(source: UserDataSource) -> GraphOntologyEntityWriter | None:
    if source.research_space_id is None:
        return None
    try:
        from artana_evidence_api.graph_client import (  # type: ignore[import-not-found]
            GraphApiGateway,
        )

        ai_harness = _create_evidence_sentence_harness()
        return GraphOntologyEntityWriter(
            graph_api_gateway=GraphApiGateway(),
            research_space_id=source.research_space_id,
            evidence_sentence_harness=ai_harness,
        )
    except Exception:  # noqa: BLE001, S110
        return None


def _create_evidence_sentence_harness() -> object | None:
    try:
        from src.infrastructure.llm.adapters import ArtanaEvidenceSentenceHarnessAdapter

        return ArtanaEvidenceSentenceHarnessAdapter()
    except Exception:  # noqa: BLE001, S110
        return None


def _log_ai_sentence_stats(entity_writer: GraphOntologyEntityWriter | None) -> None:
    if entity_writer is None:
        return
    ai_stats = entity_writer.get_ai_sentence_stats()
    if not ai_stats:
        return
    for namespace, counters in ai_stats.items():
        requested = counters.get("requested", 0)
        generated = counters.get("generated", 0)
        fallback = counters.get("fallback", 0)
        cache_hit = counters.get("cache_hit", 0)
        total_chars = counters.get("total_sentence_chars", 0)
        avg_chars = (total_chars // generated) if generated else 0
        logger.info(
            "AI evidence sentence stats for ontology=%s: "
            "requested=%d generated=%d fallback=%d "
            "cache_hit=%d avg_sentence_chars=%d",
            namespace,
            requested,
            generated,
            fallback,
            cache_hit,
            avg_chars,
        )


def _log_alias_stats(summary: object) -> None:
    metrics = getattr(summary, "aliases_persisted_by_namespace_entity_type", {})
    if not isinstance(metrics, dict) or not metrics:
        return
    for metric_key, persisted in sorted(metrics.items()):
        if not isinstance(metric_key, str) or not isinstance(persisted, int):
            continue
        namespace, separator, entity_type = metric_key.partition(":")
        if separator == "":
            namespace = metric_key
            entity_type = "UNKNOWN"
        logger.info(
            "Ontology alias persistence stats for namespace=%s entity_type=%s: "
            "persisted=%d",
            namespace,
            entity_type,
            persisted,
        )


__all__ = ["OntologyRunSummaryAdapter", "run_ontology_ingestion"]
