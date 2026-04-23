"""Service-owned bridges for optional ontology runtime dependencies."""

from __future__ import annotations

import importlib
from typing import Protocol, cast
from uuid import UUID


class MondoIngestionServiceProtocol(Protocol):
    """Minimal MONDO ingestion service contract used by research-init."""

    async def ingest(
        self,
        *,
        source_id: str,
        research_space_id: str,
    ) -> object: ...


def _load_attr(module_path: str, attribute_name: str) -> object:
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        msg = f"Unavailable runtime dependency: {module_path}"
        raise RuntimeError(msg) from exc
    resolved = getattr(module, attribute_name, None)
    if resolved is None:
        msg = f"Missing runtime dependency: {module_path}.{attribute_name}"
        raise RuntimeError(msg)
    return resolved


def build_mondo_writer(
    *,
    graph_api_gateway: object,
    space_id: UUID,
) -> object | None:
    """Construct the optional ontology graph writer for MONDO loading."""
    try:
        graph_writer_factory = _load_attr(
            "src.infrastructure.ingest.graph_ontology_entity_writer",
            "GraphOntologyEntityWriter",
        )
        if not callable(graph_writer_factory):
            return None

        mondo_ai_harness: object | None = None
        try:
            harness_factory = _load_attr(
                "src.infrastructure.llm.adapters",
                "ArtanaEvidenceSentenceHarnessAdapter",
            )
            if callable(harness_factory):
                mondo_ai_harness = harness_factory()
        except RuntimeError:
            mondo_ai_harness = None

        return graph_writer_factory(
            graph_api_gateway=graph_api_gateway,
            research_space_id=space_id,
            evidence_sentence_harness=mondo_ai_harness,
        )
    except RuntimeError:
        return None


def build_mondo_ingestion_service(
    *,
    graph_api_gateway: object,
    space_id: UUID,
    entity_writer: object | None = None,
) -> MondoIngestionServiceProtocol:
    """Construct the shared MONDO ingestion service lazily."""
    ontology_service_factory = _load_attr(
        "src.application.services.ontology_ingestion_service",
        "OntologyIngestionService",
    )
    mondo_gateway_factory = _load_attr(
        "src.infrastructure.ingest.mondo_gateway",
        "MondoGateway",
    )
    if not callable(ontology_service_factory):
        msg = "Ontology ingestion service factory is not callable"
        raise TypeError(msg)
    if not callable(mondo_gateway_factory):
        msg = "MONDO gateway factory is not callable"
        raise TypeError(msg)

    mondo_service = ontology_service_factory(
        gateway=mondo_gateway_factory(),
        entity_writer=(
            entity_writer
            if entity_writer is not None
            else build_mondo_writer(
                graph_api_gateway=graph_api_gateway,
                space_id=space_id,
            )
        ),
    )
    return cast("MondoIngestionServiceProtocol", mondo_service)


__all__ = ["build_mondo_ingestion_service", "build_mondo_writer"]
