"""Deferred MONDO loading helpers for research-init runs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from threading import Thread
from typing import TYPE_CHECKING, Protocol
from uuid import UUID

from artana_evidence_api.ontology_runtime_bridges import (
    MondoIngestionServiceProtocol,
    build_mondo_ingestion_service,
)
from artana_evidence_api.ontology_runtime_bridges import (
    build_mondo_writer as build_mondo_writer_bridge,
)
from artana_evidence_api.research_init_source_execution import (
    refresh_research_init_source_outputs,
)
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.harness_runtime import HarnessExecutionServices


class MondoIngestionServiceBuilder(Protocol):
    """Factory signature for building the MONDO ingestion service."""

    def __call__(
        self,
        *,
        graph_api_gateway: object,
        space_id: UUID,
        entity_writer: object | None,
    ) -> MondoIngestionServiceProtocol: ...


class MondoWriterBuilder(Protocol):
    """Factory signature for the optional ontology graph writer."""

    def __call__(
        self,
        *,
        graph_api_gateway: object,
        space_id: UUID,
    ) -> object | None: ...


class SourceOutputRefresher(Protocol):
    """Callback used to patch research-init source outputs."""

    def __call__(
        self,
        *,
        artifact_store: HarnessArtifactStore,
        space_id: UUID,
        run_id: str,
        source_key: str,
        source_result: JSONObject,
        error_message: str | None = None,
    ) -> None: ...


def empty_mondo_source_result(*, selected: bool, status: str) -> JSONObject:
    """Return the normalized MONDO source result shape."""
    return {
        "selected": selected,
        "status": status,
        "terms_loaded": 0,
        "hierarchy_edges": 0,
        "alias_candidates_count": 0,
        "aliases_registered": 0,
        "aliases_persisted": 0,
        "aliases_skipped": 0,
        "alias_entities_touched": 0,
        "alias_errors": [],
    }


async def execute_deferred_mondo_load(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    mondo_writer_builder: MondoWriterBuilder = build_mondo_writer_bridge,
    mondo_ingestion_service_builder: MondoIngestionServiceBuilder = (
        build_mondo_ingestion_service
    ),
    source_output_refresher: SourceOutputRefresher = (
        refresh_research_init_source_outputs
    ),
) -> None:
    """Load MONDO after the main run completes and patch the stored outputs."""
    graph_api_gateway = services.graph_api_gateway_factory()
    error_message: str | None = None
    mondo_source_result = empty_mondo_source_result(selected=True, status="background")

    try:
        mondo_writer = mondo_writer_builder(
            graph_api_gateway=graph_api_gateway,
            space_id=space_id,
        )
        mondo_service = mondo_ingestion_service_builder(
            graph_api_gateway=graph_api_gateway,
            space_id=space_id,
            entity_writer=mondo_writer,
        )
        mondo_summary = await mondo_service.ingest(
            source_id=run_id,
            research_space_id=str(space_id),
        )
        mondo_source_result = empty_mondo_source_result(
            selected=True,
            status="completed",
        )
        mondo_source_result["terms_loaded"] = mondo_summary.terms_imported
        mondo_source_result["hierarchy_edges"] = mondo_summary.hierarchy_edges_created
        mondo_source_result["alias_candidates_count"] = (
            mondo_summary.alias_candidates_count
        )
        mondo_source_result["aliases_registered"] = mondo_summary.aliases_registered
        mondo_source_result["aliases_persisted"] = mondo_summary.aliases_persisted
        mondo_source_result["aliases_skipped"] = mondo_summary.aliases_skipped
        mondo_source_result["alias_entities_touched"] = (
            mondo_summary.alias_entities_touched
        )
        mondo_source_result["alias_errors"] = list(mondo_summary.alias_errors)
        if mondo_summary.aliases_persisted_by_namespace_entity_type:
            mondo_source_result["aliases_persisted_by_namespace_entity_type"] = dict(
                mondo_summary.aliases_persisted_by_namespace_entity_type,
            )
        logging.getLogger(__name__).info(
            "Deferred MONDO loading completed: %d terms, %d hierarchy edges for space %s",
            mondo_summary.terms_imported,
            mondo_summary.hierarchy_edges_created,
            space_id,
        )
        if mondo_writer is not None:
            _log_ontology_ai_sentence_stats(
                mondo_writer=mondo_writer,
                space_id=space_id,
            )
    except Exception as exc:  # noqa: BLE001
        error_message = f"MONDO loading failed: {type(exc).__name__}: {exc}"
        mondo_source_result["status"] = "failed"
        logging.getLogger(__name__).warning(
            "Deferred MONDO loading failed for space %s: %s",
            space_id,
            exc,
        )
    finally:
        graph_api_gateway.close()

    source_output_refresher(
        artifact_store=services.artifact_store,
        space_id=space_id,
        run_id=run_id,
        source_key="mondo",
        source_result=mondo_source_result,
        error_message=error_message,
    )


def start_deferred_mondo_load(
    *,
    services: HarnessExecutionServices,
    space_id: UUID,
    run_id: str,
    load_runner: Callable[
        ...,
        Coroutine[object, object, None],
    ] = execute_deferred_mondo_load,
) -> None:
    """Launch deferred MONDO loading without blocking the main run."""

    def _runner() -> None:
        try:
            asyncio.run(
                load_runner(
                    services=services,
                    space_id=space_id,
                    run_id=run_id,
                ),
            )
        except Exception:  # noqa: BLE001
            logging.getLogger(__name__).exception(
                "Deferred MONDO loader crashed for space %s run %s",
                space_id,
                run_id,
            )

    Thread(
        target=_runner,
        name=f"research-init-mondo-{run_id}",
        daemon=True,
    ).start()


def _log_ontology_ai_sentence_stats(
    *,
    mondo_writer: object,
    space_id: UUID,
) -> None:
    """Log per-namespace ontology AI sentence stats when available."""
    if not hasattr(mondo_writer, "get_ai_sentence_stats"):
        return
    ai_stats = mondo_writer.get_ai_sentence_stats()
    for namespace, counters in ai_stats.items():
        requested = counters.get("requested", 0)
        generated = counters.get("generated", 0)
        fallback = counters.get("fallback", 0)
        cache_hit = counters.get("cache_hit", 0)
        total_chars = counters.get("total_sentence_chars", 0)
        avg_chars = (total_chars // generated) if generated else 0
        logging.getLogger(__name__).info(
            "AI evidence sentence stats for ontology=%s "
            "(space %s): requested=%d generated=%d "
            "fallback=%d cache_hit=%d avg_sentence_chars=%d",
            namespace,
            space_id,
            requested,
            generated,
            fallback,
            cache_hit,
            avg_chars,
        )


__all__ = [
    "empty_mondo_source_result",
    "execute_deferred_mondo_load",
    "start_deferred_mondo_load",
]
