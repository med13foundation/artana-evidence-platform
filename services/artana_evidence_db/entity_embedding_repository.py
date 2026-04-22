"""Service-local repository for entity embeddings and nearest-neighbor lookup."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import sqlalchemy as sa
from artana_evidence_db.embedding_models import (
    KernelEntityEmbedding,
    KernelEntitySimilarityCandidate,
)
from artana_evidence_db.entity_embedding_model import EntityEmbeddingModel
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.kernel_relation_models import RelationModel
from sqlalchemy import or_, select

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _clamp_score(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot_product = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for left_value, right_value in zip(left, right, strict=False):
        dot_product += left_value * right_value
        left_norm += left_value * left_value
        right_norm += right_value * right_value
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return _clamp_score(dot_product / (math.sqrt(left_norm) * math.sqrt(right_norm)))


class SqlAlchemyEntityEmbeddingRepository:
    """Persistence adapter for entity embeddings and similarity lookup."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def upsert_embedding(  # noqa: PLR0913
        self,
        *,
        research_space_id: str,
        entity_id: str,
        embedding: list[float],
        embedding_model: str,
        embedding_version: int,
        source_fingerprint: str,
    ) -> KernelEntityEmbedding:
        space_uuid = _as_uuid(research_space_id)
        entity_uuid = _as_uuid(entity_id)

        existing = self._session.scalars(
            select(EntityEmbeddingModel).where(
                EntityEmbeddingModel.entity_id == entity_uuid,
            ),
        ).first()
        if existing is None:
            model = EntityEmbeddingModel(
                id=uuid4(),
                research_space_id=space_uuid,
                entity_id=entity_uuid,
                embedding=[float(item) for item in embedding],
                embedding_model=embedding_model,
                embedding_version=embedding_version,
                source_fingerprint=source_fingerprint,
            )
            self._session.add(model)
            self._session.flush()
            return KernelEntityEmbedding.model_validate(model)

        existing.research_space_id = space_uuid
        existing.embedding = [float(item) for item in embedding]
        existing.embedding_model = embedding_model
        existing.embedding_version = embedding_version
        existing.source_fingerprint = source_fingerprint
        self._session.flush()
        return KernelEntityEmbedding.model_validate(existing)

    def get_embedding(
        self,
        *,
        entity_id: str,
    ) -> KernelEntityEmbedding | None:
        entity_uuid = _as_uuid(entity_id)
        model = self._session.scalars(
            select(EntityEmbeddingModel).where(
                EntityEmbeddingModel.entity_id == entity_uuid,
            ),
        ).first()
        return (
            KernelEntityEmbedding.model_validate(model) if model is not None else None
        )

    def find_similar_entities(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int,
        min_similarity: float,
        target_entity_types: list[str] | None = None,
    ) -> list[KernelEntitySimilarityCandidate]:
        normalized_limit = max(1, min(limit, 500))
        normalized_min_similarity = _clamp_score(min_similarity)
        normalized_target_types = self._normalize_target_entity_types(
            target_entity_types,
        )

        space_uuid = _as_uuid(research_space_id)
        source_uuid = _as_uuid(entity_id)
        source_embedding = self._session.scalars(
            select(EntityEmbeddingModel.embedding).where(
                EntityEmbeddingModel.research_space_id == space_uuid,
                EntityEmbeddingModel.entity_id == source_uuid,
            ),
        ).first()
        if source_embedding is None:
            return []

        dialect_name = self._session.get_bind().dialect.name
        if dialect_name == "postgresql":
            return self._find_similar_entities_postgres(
                research_space_id=space_uuid,
                entity_id=source_uuid,
                limit=normalized_limit,
                min_similarity=normalized_min_similarity,
                target_entity_types=normalized_target_types,
            )
        return self._find_similar_entities_python(
            research_space_id=space_uuid,
            entity_id=source_uuid,
            source_embedding=[float(item) for item in source_embedding],
            limit=normalized_limit,
            min_similarity=normalized_min_similarity,
            target_entity_types=normalized_target_types,
        )

    def _find_similar_entities_postgres(
        self,
        *,
        research_space_id: UUID,
        entity_id: UUID,
        limit: int,
        min_similarity: float,
        target_entity_types: list[str] | None,
    ) -> list[KernelEntitySimilarityCandidate]:
        source_embedding_subquery = (
            select(EntityEmbeddingModel.embedding)
            .where(
                EntityEmbeddingModel.research_space_id == research_space_id,
                EntityEmbeddingModel.entity_id == entity_id,
            )
            .scalar_subquery()
        )
        distance_expr = EntityEmbeddingModel.embedding.op("<=>")(
            source_embedding_subquery,
        )
        distance_expr_float = sa.cast(distance_expr, sa.Float())
        similarity_expr = sa.func.greatest(
            sa.literal(0.0),
            sa.func.least(sa.literal(1.0), sa.literal(1.0) - distance_expr_float),
        )

        stmt = (
            select(
                EntityModel.id,
                EntityModel.entity_type,
                EntityModel.display_label,
                similarity_expr.label("vector_score"),
            )
            .join(EntityModel, EntityModel.id == EntityEmbeddingModel.entity_id)
            .where(
                EntityEmbeddingModel.research_space_id == research_space_id,
                EntityEmbeddingModel.entity_id != entity_id,
                similarity_expr >= min_similarity,
            )
            .order_by(distance_expr.asc())
            .limit(limit)
        )
        if target_entity_types:
            stmt = stmt.where(EntityModel.entity_type.in_(target_entity_types))

        rows = self._session.execute(stmt).all()
        candidates: list[KernelEntitySimilarityCandidate] = []
        for row in rows:
            entity_id_value = row[0]
            entity_type_value = row[1]
            display_label_value = row[2]
            vector_score_value = row[3]
            if not isinstance(entity_id_value, UUID):
                continue
            if not isinstance(entity_type_value, str):
                continue
            if display_label_value is not None and not isinstance(
                display_label_value,
                str,
            ):
                continue
            try:
                vector_score = float(vector_score_value)
            except (TypeError, ValueError):
                continue
            candidates.append(
                KernelEntitySimilarityCandidate(
                    entity_id=entity_id_value,
                    entity_type=entity_type_value,
                    display_label=display_label_value,
                    vector_score=_clamp_score(vector_score),
                ),
            )
        return candidates

    def _find_similar_entities_python(  # noqa: PLR0913
        self,
        *,
        research_space_id: UUID,
        entity_id: UUID,
        source_embedding: list[float],
        limit: int,
        min_similarity: float,
        target_entity_types: list[str] | None,
    ) -> list[KernelEntitySimilarityCandidate]:
        stmt = (
            select(EntityEmbeddingModel, EntityModel)
            .join(EntityModel, EntityModel.id == EntityEmbeddingModel.entity_id)
            .where(
                EntityEmbeddingModel.research_space_id == research_space_id,
                EntityEmbeddingModel.entity_id != entity_id,
            )
        )
        if target_entity_types:
            stmt = stmt.where(EntityModel.entity_type.in_(target_entity_types))

        rows = self._session.execute(stmt).all()
        candidates: list[KernelEntitySimilarityCandidate] = []
        for embedding_model, entity_model in rows:
            vector_score = _cosine_similarity(
                source_embedding,
                [float(item) for item in embedding_model.embedding],
            )
            if vector_score < min_similarity:
                continue
            candidates.append(
                KernelEntitySimilarityCandidate(
                    entity_id=entity_model.id,
                    entity_type=str(entity_model.entity_type),
                    display_label=(
                        str(entity_model.display_label)
                        if entity_model.display_label is not None
                        else None
                    ),
                    vector_score=vector_score,
                ),
            )

        candidates.sort(key=lambda item: item.vector_score, reverse=True)
        return candidates[:limit]

    def list_neighbor_ids_for_overlap(
        self,
        *,
        research_space_id: str,
        entity_id: str,
    ) -> list[str]:
        space_uuid = _as_uuid(research_space_id)
        entity_uuid = _as_uuid(entity_id)

        rows = self._session.execute(
            select(RelationModel.source_id, RelationModel.target_id).where(
                RelationModel.research_space_id == space_uuid,
                or_(
                    RelationModel.source_id == entity_uuid,
                    RelationModel.target_id == entity_uuid,
                ),
            ),
        ).all()

        neighbor_ids: set[str] = set()
        for source_id, target_id in rows:
            if not isinstance(source_id, UUID):
                continue
            if not isinstance(target_id, UUID):
                continue
            if source_id == entity_uuid:
                neighbor_ids.add(str(target_id))
            if target_id == entity_uuid:
                neighbor_ids.add(str(source_id))

        return sorted(neighbor_ids)

    @staticmethod
    def _normalize_target_entity_types(
        target_entity_types: list[str] | None,
    ) -> list[str] | None:
        if target_entity_types is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for raw in target_entity_types:
            value = raw.strip().upper()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized if normalized else None


__all__ = ["SqlAlchemyEntityEmbeddingRepository"]
