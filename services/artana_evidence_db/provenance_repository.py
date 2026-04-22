"""Service-local SQLAlchemy repository for graph provenance records."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.graph_core_models import KernelProvenanceRecord
from artana_evidence_db.provenance_model import ProvenanceModel
from sqlalchemy import select

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Session


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class SqlAlchemyProvenanceRepository:
    """SQLAlchemy implementation of the provenance repository."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        source_type: str,
        source_ref: str | None = None,
        extraction_run_id: str | None = None,
        mapping_method: str | None = None,
        mapping_confidence: float | None = None,
        agent_model: str | None = None,
        raw_input: JSONObject | None = None,
    ) -> KernelProvenanceRecord:
        prov = ProvenanceModel(
            id=uuid4(),
            research_space_id=_as_uuid(research_space_id),
            source_type=source_type,
            source_ref=source_ref,
            extraction_run_id=(
                extraction_run_id.strip()
                if isinstance(extraction_run_id, str) and extraction_run_id.strip()
                else None
            ),
            mapping_method=mapping_method,
            mapping_confidence=mapping_confidence,
            agent_model=agent_model,
            raw_input=raw_input,
        )
        self._session.add(prov)
        self._session.flush()
        return KernelProvenanceRecord.model_validate(prov)

    def get_by_id(self, provenance_id: str) -> KernelProvenanceRecord | None:
        model = self._session.get(ProvenanceModel, _as_uuid(provenance_id))
        return (
            KernelProvenanceRecord.model_validate(model) if model is not None else None
        )

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        source_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelProvenanceRecord]:
        stmt = (
            select(ProvenanceModel)
            .where(ProvenanceModel.research_space_id == _as_uuid(research_space_id))
            .order_by(ProvenanceModel.created_at.desc())
        )
        if source_type is not None:
            stmt = stmt.where(ProvenanceModel.source_type == source_type)
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return [
            KernelProvenanceRecord.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def find_by_extraction_run(
        self,
        extraction_run_id: str,
    ) -> list[KernelProvenanceRecord]:
        normalized_run_id = extraction_run_id.strip()
        if not normalized_run_id:
            return []
        stmt = (
            select(ProvenanceModel)
            .where(ProvenanceModel.extraction_run_id == normalized_run_id)
            .order_by(ProvenanceModel.created_at.desc())
        )
        return [
            KernelProvenanceRecord.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]


SqlAlchemyKernelProvenanceRepository = SqlAlchemyProvenanceRepository

__all__ = [
    "SqlAlchemyKernelProvenanceRepository",
    "SqlAlchemyProvenanceRepository",
]
