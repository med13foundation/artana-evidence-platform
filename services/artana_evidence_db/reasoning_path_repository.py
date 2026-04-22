"""Service-local SQLAlchemy persistence for derived reasoning paths."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.kernel_domain_ports import (
    ReasoningPathKind,
    ReasoningPathStatus,
    ReasoningPathStepWrite,
    ReasoningPathWriteBundle,
)
from artana_evidence_db.reasoning_path_models import (
    KernelReasoningPath,
    KernelReasoningPathStep,
)
from artana_evidence_db.reasoning_path_persistence_models import (
    ReasoningPathModel,
    ReasoningPathStepModel,
)
from sqlalchemy import func, or_, select, update

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from sqlalchemy.sql import Select


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class SqlAlchemyKernelReasoningPathRepository:
    """Persist rebuildable reasoning paths and their ordered steps."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def replace_for_space(
        self,
        *,
        research_space_id: str,
        bundles: list[ReasoningPathWriteBundle],
        replace_existing: bool,
    ) -> list[KernelReasoningPath]:
        space_uuid = _as_uuid(research_space_id)
        if replace_existing:
            existing_stmt = select(ReasoningPathModel).where(
                ReasoningPathModel.research_space_id == space_uuid,
            )
            for model in self._session.scalars(existing_stmt).all():
                self._session.delete(model)
            self._session.flush()

        created: list[KernelReasoningPath] = []
        for bundle in bundles:
            path_payload = bundle.path
            model = ReasoningPathModel(
                id=uuid4(),
                research_space_id=space_uuid,
                path_kind=path_payload.path_kind,
                status=path_payload.status,
                start_entity_id=_as_uuid(path_payload.start_entity_id),
                end_entity_id=_as_uuid(path_payload.end_entity_id),
                root_claim_id=_as_uuid(path_payload.root_claim_id),
                path_length=path_payload.path_length,
                confidence=path_payload.confidence,
                path_signature_hash=path_payload.path_signature_hash,
                generated_by=path_payload.generated_by,
                generated_at=datetime.now(UTC),
                metadata_payload=path_payload.metadata,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            self._session.add(model)
            self._session.flush()
            self._create_steps(path_id=model.id, steps=bundle.steps)
            created.append(KernelReasoningPath.model_validate(model))

        return created

    def list_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: ReasoningPathStatus | None = None,
        path_kind: ReasoningPathKind | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelReasoningPath]:
        stmt = self._build_path_stmt(
            research_space_id=research_space_id,
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            status=status,
            path_kind=path_kind,
        ).order_by(
            ReasoningPathModel.confidence.desc(),
            ReasoningPathModel.path_length.asc(),
            ReasoningPathModel.updated_at.desc(),
            ReasoningPathModel.id.asc(),
        )
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return [
            KernelReasoningPath.model_validate(model)
            for model in self._session.scalars(stmt).all()
        ]

    def count_paths(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None = None,
        end_entity_id: str | None = None,
        status: ReasoningPathStatus | None = None,
        path_kind: ReasoningPathKind | None = None,
    ) -> int:
        subquery = self._build_path_stmt(
            research_space_id=research_space_id,
            start_entity_id=start_entity_id,
            end_entity_id=end_entity_id,
            status=status,
            path_kind=path_kind,
        ).subquery()
        return int(
            self._session.execute(
                select(func.count()).select_from(subquery),
            ).scalar_one(),
        )

    def get_path(
        self,
        *,
        path_id: str,
        research_space_id: str,
    ) -> KernelReasoningPath | None:
        stmt = (
            select(ReasoningPathModel)
            .where(
                ReasoningPathModel.id == _as_uuid(path_id),
                ReasoningPathModel.research_space_id == _as_uuid(research_space_id),
            )
            .limit(1)
        )
        model = self._session.scalars(stmt).first()
        if model is None:
            return None
        return KernelReasoningPath.model_validate(model)

    def list_steps_for_path_ids(
        self,
        *,
        path_ids: list[str],
    ) -> dict[str, list[KernelReasoningPathStep]]:
        normalized_ids = [_as_uuid(path_id) for path_id in path_ids]
        if not normalized_ids:
            return {}
        stmt = (
            select(ReasoningPathStepModel)
            .where(ReasoningPathStepModel.path_id.in_(normalized_ids))
            .order_by(
                ReasoningPathStepModel.path_id.asc(),
                ReasoningPathStepModel.step_index.asc(),
            )
        )
        result: dict[str, list[KernelReasoningPathStep]] = {
            str(path_id): [] for path_id in normalized_ids
        }
        for model in self._session.scalars(stmt).all():
            result.setdefault(str(model.path_id), []).append(
                KernelReasoningPathStep.model_validate(model),
            )
        return result

    def mark_stale_for_claim_ids(
        self,
        *,
        research_space_id: str,
        claim_ids: list[str],
    ) -> int:
        normalized_ids = [_as_uuid(claim_id) for claim_id in claim_ids]
        if not normalized_ids:
            return 0
        path_ids = select(ReasoningPathStepModel.path_id).where(
            or_(
                ReasoningPathStepModel.source_claim_id.in_(normalized_ids),
                ReasoningPathStepModel.target_claim_id.in_(normalized_ids),
            ),
        )
        stmt = (
            update(ReasoningPathModel)
            .where(
                ReasoningPathModel.research_space_id == _as_uuid(research_space_id),
                or_(
                    ReasoningPathModel.root_claim_id.in_(normalized_ids),
                    ReasoningPathModel.id.in_(path_ids),
                ),
            )
            .values(status="STALE", updated_at=datetime.now(UTC))
        )
        result = self._session.execute(stmt)
        rowcount = getattr(result, "rowcount", None)
        return int(rowcount or 0)

    def mark_stale_for_claim_relation_ids(
        self,
        *,
        research_space_id: str,
        relation_ids: list[str],
    ) -> int:
        normalized_ids = [_as_uuid(relation_id) for relation_id in relation_ids]
        if not normalized_ids:
            return 0
        path_ids = select(ReasoningPathStepModel.path_id).where(
            ReasoningPathStepModel.claim_relation_id.in_(normalized_ids),
        )
        stmt = (
            update(ReasoningPathModel)
            .where(
                ReasoningPathModel.research_space_id == _as_uuid(research_space_id),
                ReasoningPathModel.id.in_(path_ids),
            )
            .values(status="STALE", updated_at=datetime.now(UTC))
        )
        result = self._session.execute(stmt)
        rowcount = getattr(result, "rowcount", None)
        return int(rowcount or 0)

    def _build_path_stmt(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        start_entity_id: str | None,
        end_entity_id: str | None,
        status: ReasoningPathStatus | None,
        path_kind: ReasoningPathKind | None,
    ) -> Select[tuple[ReasoningPathModel]]:
        stmt = select(ReasoningPathModel).where(
            ReasoningPathModel.research_space_id == _as_uuid(research_space_id),
        )
        if start_entity_id is not None:
            stmt = stmt.where(
                ReasoningPathModel.start_entity_id == _as_uuid(start_entity_id),
            )
        if end_entity_id is not None:
            stmt = stmt.where(
                ReasoningPathModel.end_entity_id == _as_uuid(end_entity_id),
            )
        if status is not None:
            stmt = stmt.where(ReasoningPathModel.status == status)
        if path_kind is not None:
            stmt = stmt.where(ReasoningPathModel.path_kind == path_kind)
        return stmt

    def _create_steps(
        self,
        *,
        path_id: UUID,
        steps: tuple[ReasoningPathStepWrite, ...],
    ) -> None:
        for step in steps:
            model = ReasoningPathStepModel(
                id=uuid4(),
                path_id=path_id,
                step_index=step.step_index,
                source_claim_id=_as_uuid(step.source_claim_id),
                target_claim_id=_as_uuid(step.target_claim_id),
                claim_relation_id=_as_uuid(step.claim_relation_id),
                canonical_relation_id=(
                    _as_uuid(step.canonical_relation_id)
                    if step.canonical_relation_id is not None
                    else None
                ),
                metadata_payload=step.metadata,
                created_at=datetime.now(UTC),
            )
            self._session.add(model)
        self._session.flush()


__all__ = ["SqlAlchemyKernelReasoningPathRepository"]
