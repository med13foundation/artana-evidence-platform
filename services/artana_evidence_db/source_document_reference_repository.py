"""Service-local SQLAlchemy adapter for graph-local source-document references."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.kernel_domain_ports import SourceDocumentReferencePort
from artana_evidence_db.source_document_model import SourceDocumentModel
from artana_evidence_db.source_document_reference_model import (
    KernelSourceDocumentReference,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


class SqlAlchemyKernelSourceDocumentReferenceRepository(
    SourceDocumentReferencePort,
):
    """Resolve graph-local document references from the shared document store."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(
        self,
        document_id: UUID,
    ) -> KernelSourceDocumentReference | None:
        model = self._session.get(SourceDocumentModel, str(document_id))
        if model is None:
            return None
        return KernelSourceDocumentReference(
            id=UUID(str(model.id)),
            research_space_id=(
                UUID(str(model.research_space_id))
                if model.research_space_id is not None
                else None
            ),
            source_id=UUID(str(model.source_id)),
            external_record_id=model.external_record_id,
            source_type=model.source_type,
            document_format=model.document_format,
            enrichment_status=model.enrichment_status,
            extraction_status=model.extraction_status,
            metadata=dict(model.metadata_payload or {}),
            created_at=getattr(model, "created_at", None),
            updated_at=getattr(model, "updated_at", None),
        )


__all__ = ["SqlAlchemyKernelSourceDocumentReferenceRepository"]
