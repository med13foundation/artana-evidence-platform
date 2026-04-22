"""Projector for the graph-owned entity embedding readiness read model."""

from __future__ import annotations

from artana_evidence_db.entity_embedding_status_service import (
    KernelEntityEmbeddingStatusService,
)
from artana_evidence_db.read_model_support import (
    ENTITY_EMBEDDING_STATUS_READ_MODEL,
    GraphReadModelDefinition,
    GraphReadModelUpdate,
)


class KernelEntityEmbeddingStatusProjector:
    """Rebuild and incrementally refresh entity embedding readiness state."""

    def __init__(self, service: KernelEntityEmbeddingStatusService) -> None:
        self._service = service

    @property
    def definition(self) -> GraphReadModelDefinition:
        return ENTITY_EMBEDDING_STATUS_READ_MODEL

    def rebuild(self, *, space_id: str | None = None) -> int:
        return self._service.rebuild_statuses(research_space_id=space_id)

    def apply_update(self, update: GraphReadModelUpdate) -> int:
        if update.model_name != self.definition.name:
            return 0
        return self._service.rebuild_statuses(
            research_space_id=update.space_id,
            entity_ids=update.entity_ids,
        )


__all__ = ["KernelEntityEmbeddingStatusProjector"]
