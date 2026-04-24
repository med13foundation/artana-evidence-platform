"""Service-owned bridges for optional ontology runtime dependencies."""

from __future__ import annotations

from typing import Protocol, cast
from uuid import UUID

from artana_evidence_api.mondo_runtime import (
    MondoGateway,
    MondoIngestionService,
    MondoIngestionSummary,
    OntologyEntityWriterProtocol,
    ServiceGraphOntologyEntityWriter,
)


class MondoIngestionServiceProtocol(Protocol):
    """Minimal MONDO ingestion service contract used by research-init."""

    async def ingest(
        self,
        *,
        source_id: str,
        research_space_id: str,
    ) -> MondoIngestionSummary: ...


def build_mondo_writer(
    *,
    graph_api_gateway: object,
    space_id: UUID,
) -> object | None:
    """Return the service-local MONDO graph writer."""
    return ServiceGraphOntologyEntityWriter(
        graph_api_gateway=graph_api_gateway,
        research_space_id=space_id,
    )


def build_mondo_ingestion_service(
    *,
    graph_api_gateway: object,
    space_id: UUID,
    entity_writer: object | None = None,
) -> MondoIngestionServiceProtocol:
    """Return the service-local MONDO ingestion service."""
    del graph_api_gateway, space_id
    return MondoIngestionService(
        gateway=MondoGateway(),
        entity_writer=cast("OntologyEntityWriterProtocol | None", entity_writer),
    )


__all__ = ["build_mondo_ingestion_service", "build_mondo_writer"]
