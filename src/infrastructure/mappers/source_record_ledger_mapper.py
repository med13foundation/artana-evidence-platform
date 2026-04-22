"""Mapper utilities for source record ledger entries."""

from __future__ import annotations

from uuid import UUID

from src.domain.entities.source_record_ledger import SourceRecordLedgerEntry
from src.models.database.source_record_ledger import SourceRecordLedgerModel


class SourceRecordLedgerMapper:
    """Bidirectional mapper between ledger entities and SQLAlchemy models."""

    @staticmethod
    def to_domain(model: SourceRecordLedgerModel) -> SourceRecordLedgerEntry:
        return SourceRecordLedgerEntry(
            source_id=UUID(model.source_id),
            external_record_id=model.external_record_id,
            payload_hash=model.payload_hash,
            source_updated_at=model.source_updated_at,
            first_seen_job_id=(
                UUID(model.first_seen_job_id) if model.first_seen_job_id else None
            ),
            last_seen_job_id=(
                UUID(model.last_seen_job_id) if model.last_seen_job_id else None
            ),
            last_changed_job_id=(
                UUID(model.last_changed_job_id) if model.last_changed_job_id else None
            ),
            last_processed_at=model.last_processed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )

    @staticmethod
    def to_model(entity: SourceRecordLedgerEntry) -> SourceRecordLedgerModel:
        return SourceRecordLedgerModel(
            source_id=str(entity.source_id),
            external_record_id=entity.external_record_id,
            payload_hash=entity.payload_hash,
            source_updated_at=entity.source_updated_at,
            first_seen_job_id=(
                str(entity.first_seen_job_id) if entity.first_seen_job_id else None
            ),
            last_seen_job_id=(
                str(entity.last_seen_job_id) if entity.last_seen_job_id else None
            ),
            last_changed_job_id=(
                str(entity.last_changed_job_id) if entity.last_changed_job_id else None
            ),
            last_processed_at=entity.last_processed_at,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
        )
