"""Service-owned bridges for optional ontology runtime dependencies."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class MondoIngestionServiceProtocol(Protocol):
    """Minimal MONDO ingestion service contract used by research-init."""

    async def ingest(
        self,
        *,
        source_id: str,
        research_space_id: str,
    ) -> object: ...


class _UnavailableMondoIngestionService:
    """Fail closed until MONDO ingestion is ported into this service."""

    async def ingest(
        self,
        *,
        source_id: str,
        research_space_id: str,
    ) -> object:
        del source_id, research_space_id
        msg = "MONDO ontology runtime is not available in this service"
        raise RuntimeError(msg)


def build_mondo_writer(
    *,
    graph_api_gateway: object,
    space_id: UUID,
) -> object | None:
    """Return the service-local MONDO writer when implemented."""
    del graph_api_gateway, space_id
    return None


def build_mondo_ingestion_service(
    *,
    graph_api_gateway: object,
    space_id: UUID,
    entity_writer: object | None = None,
) -> MondoIngestionServiceProtocol:
    """Return a fail-closed MONDO ingestion service until ported locally."""
    del graph_api_gateway, space_id, entity_writer
    return _UnavailableMondoIngestionService()


__all__ = ["build_mondo_ingestion_service", "build_mondo_writer"]
