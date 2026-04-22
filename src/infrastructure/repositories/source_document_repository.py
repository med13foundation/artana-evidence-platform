"""SQLAlchemy repository for source document lifecycle state."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from src.domain.entities.source_document import (
    DocumentExtractionStatus,
    EnrichmentStatus,
    SourceDocument,
)
from src.domain.repositories.source_document_repository import SourceDocumentRepository
from src.infrastructure.mappers.source_document_mapper import SourceDocumentMapper
from src.models.database.source_document import SourceDocumentModel

if TYPE_CHECKING:
    from uuid import UUID

    from sqlalchemy.orm import Session


class SqlAlchemySourceDocumentRepository(SourceDocumentRepository):
    """Persist and query source document lifecycle records."""

    def __init__(self, session: Session | None = None) -> None:
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            message = "Session not provided"
            raise ValueError(message)
        return self._session

    @staticmethod
    def _rowcount(result: object) -> int:
        count = getattr(result, "rowcount", None)
        return int(count) if isinstance(count, int) else 0

    @staticmethod
    def _apply_entity_to_model(
        model: SourceDocumentModel,
        entity: SourceDocument,
    ) -> None:
        model.research_space_id = (
            str(entity.research_space_id) if entity.research_space_id else None
        )
        model.ingestion_job_id = (
            str(entity.ingestion_job_id) if entity.ingestion_job_id else None
        )
        model.source_type = entity.source_type.value
        model.document_format = entity.document_format.value
        model.raw_storage_key = entity.raw_storage_key
        model.enriched_storage_key = entity.enriched_storage_key
        model.content_hash = entity.content_hash
        model.content_length_chars = entity.content_length_chars
        model.enrichment_status = entity.enrichment_status.value
        model.enrichment_method = entity.enrichment_method
        model.enrichment_agent_run_id = (
            str(entity.enrichment_agent_run_id)
            if entity.enrichment_agent_run_id
            else None
        )
        model.extraction_status = entity.extraction_status.value
        model.extraction_agent_run_id = (
            str(entity.extraction_agent_run_id)
            if entity.extraction_agent_run_id
            else None
        )
        model.metadata_payload = dict(entity.metadata)
        model.updated_at = entity.updated_at

    def get_by_id(self, document_id: UUID) -> SourceDocument | None:
        model = self.session.get(SourceDocumentModel, str(document_id))
        return SourceDocumentMapper.to_domain(model) if model else None

    def get_by_source_external_record(
        self,
        *,
        source_id: UUID,
        external_record_id: str,
    ) -> SourceDocument | None:
        stmt = select(SourceDocumentModel).where(
            SourceDocumentModel.source_id == str(source_id),
            SourceDocumentModel.external_record_id == external_record_id,
        )
        model = self.session.execute(stmt).scalars().first()
        return SourceDocumentMapper.to_domain(model) if model else None

    def upsert(self, document: SourceDocument) -> SourceDocument:
        persisted = self.upsert_many([document])
        if not persisted:
            message = "Failed to upsert source document"
            raise RuntimeError(message)
        return persisted[0]

    def upsert_many(
        self,
        documents: list[SourceDocument],
    ) -> list[SourceDocument]:
        if not documents:
            return []
        persisted_models: list[SourceDocumentModel] = []
        for document in documents:
            existing_stmt = select(SourceDocumentModel).where(
                SourceDocumentModel.source_id == str(document.source_id),
                SourceDocumentModel.external_record_id == document.external_record_id,
            )
            model = self.session.execute(existing_stmt).scalars().first()
            if model is None:
                model = SourceDocumentMapper.to_model(document)
                self.session.add(model)
            else:
                self._apply_entity_to_model(model, document)
            persisted_models.append(model)

        self.session.commit()
        for model in persisted_models:
            self.session.refresh(model)
        return [SourceDocumentMapper.to_domain(model) for model in persisted_models]

    def list_pending_enrichment(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> list[SourceDocument]:
        stmt = select(SourceDocumentModel).where(
            SourceDocumentModel.enrichment_status == EnrichmentStatus.PENDING.value,
        )
        if source_id is not None:
            stmt = stmt.where(SourceDocumentModel.source_id == str(source_id))
        if research_space_id is not None:
            stmt = stmt.where(
                SourceDocumentModel.research_space_id == str(research_space_id),
            )
        if ingestion_job_id is not None:
            stmt = stmt.where(
                SourceDocumentModel.ingestion_job_id == str(ingestion_job_id),
            )
        if isinstance(source_type, str):
            normalized_source_type = source_type.strip().lower()
            if normalized_source_type:
                stmt = stmt.where(
                    func.lower(SourceDocumentModel.source_type)
                    == normalized_source_type,
                )
        stmt = stmt.order_by(SourceDocumentModel.created_at.asc()).limit(max(limit, 1))
        models = self.session.execute(stmt).scalars().all()
        return [SourceDocumentMapper.to_domain(model) for model in models]

    def list_pending_extraction(
        self,
        *,
        limit: int = 100,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        source_type: str | None = None,
    ) -> list[SourceDocument]:
        stmt = select(SourceDocumentModel).where(
            SourceDocumentModel.extraction_status
            == DocumentExtractionStatus.PENDING.value,
        )
        if source_id is not None:
            stmt = stmt.where(SourceDocumentModel.source_id == str(source_id))
        if research_space_id is not None:
            stmt = stmt.where(
                SourceDocumentModel.research_space_id == str(research_space_id),
            )
        if ingestion_job_id is not None:
            stmt = stmt.where(
                SourceDocumentModel.ingestion_job_id == str(ingestion_job_id),
            )
        if isinstance(source_type, str):
            normalized_source_type = source_type.strip().lower()
            if normalized_source_type:
                stmt = stmt.where(
                    func.lower(SourceDocumentModel.source_type)
                    == normalized_source_type,
                )
        stmt = stmt.order_by(SourceDocumentModel.created_at.asc()).limit(max(limit, 1))
        models = self.session.execute(stmt).scalars().all()
        return [SourceDocumentMapper.to_domain(model) for model in models]

    def recover_stale_in_progress_extraction(
        self,
        *,
        stale_before: datetime,
        source_id: UUID | None = None,
        research_space_id: UUID | None = None,
        ingestion_job_id: UUID | None = None,
        limit: int = 500,
    ) -> int:
        stmt = select(SourceDocumentModel).where(
            SourceDocumentModel.extraction_status
            == DocumentExtractionStatus.IN_PROGRESS.value,
            SourceDocumentModel.updated_at < stale_before,
        )
        if source_id is not None:
            stmt = stmt.where(SourceDocumentModel.source_id == str(source_id))
        if research_space_id is not None:
            stmt = stmt.where(
                SourceDocumentModel.research_space_id == str(research_space_id),
            )
        if ingestion_job_id is not None:
            stmt = stmt.where(
                SourceDocumentModel.ingestion_job_id == str(ingestion_job_id),
            )
        stale_models = (
            self.session.execute(
                stmt.order_by(SourceDocumentModel.updated_at.asc()).limit(
                    max(limit, 1),
                ),
            )
            .scalars()
            .all()
        )
        if not stale_models:
            return 0

        now = datetime.now(UTC)
        recovered = 0
        for model in stale_models:
            metadata = (
                dict(model.metadata_payload)
                if isinstance(model.metadata_payload, dict)
                else {}
            )
            metadata["extraction_stale_recovered_at"] = now.isoformat()
            metadata["extraction_stale_previous_status"] = (
                DocumentExtractionStatus.IN_PROGRESS.value
            )
            metadata["extraction_stale_recovery_reason"] = (
                "in_progress_timeout_recovered_to_pending"
            )
            model.metadata_payload = metadata
            model.extraction_status = DocumentExtractionStatus.PENDING.value
            model.extraction_agent_run_id = None
            model.updated_at = now
            recovered += 1

        self.session.commit()
        return recovered

    def delete_by_source(self, source_id: UUID) -> int:
        stmt = delete(SourceDocumentModel).where(
            SourceDocumentModel.source_id == str(source_id),
        )
        result = self.session.execute(stmt)
        self.session.commit()
        return self._rowcount(result)

    def count_for_source(self, source_id: UUID) -> int:
        stmt = select(func.count()).where(
            SourceDocumentModel.source_id == str(source_id),
        )
        return int(self.session.execute(stmt).scalar_one())
