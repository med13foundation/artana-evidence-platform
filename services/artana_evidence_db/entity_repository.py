"""Service-local SQLAlchemy implementation of the kernel entity repository."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from artana_evidence_db.entity_lookup_models import (
    EntityAliasModel,
    EntityIdentifierModel,
)
from artana_evidence_db.entity_resolution import (
    canonicalize_entity_match_text,
    normalize_entity_match_text,
)
from artana_evidence_db.graph_core_models import (
    KernelEntity,
    KernelEntityAlias,
    KernelEntityIdentifier,
)
from artana_evidence_db.kernel_entity_errors import (
    KernelEntityConflictError,
    KernelEntityValidationError,
)
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.phi_encryption_support import (
    PHIEncryptionService,
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)
from sqlalchemy import and_, func, or_, select
from sqlalchemy import insert as sa_insert
from sqlalchemy.dialects.postgresql import insert as pg_insert

if TYPE_CHECKING:
    from artana_evidence_db.common_types import JSONObject
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def _as_uuid(value: str | UUID) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


class SqlAlchemyKernelEntityRepository:
    """SQLAlchemy implementation of the kernel entity repository."""

    def __init__(
        self,
        session: Session,
        *,
        phi_encryption_service: PHIEncryptionService | None = None,
        enable_phi_encryption: bool | None = None,
    ) -> None:
        self._session = session
        self._phi_encryption_enabled = (
            enable_phi_encryption
            if enable_phi_encryption is not None
            else is_phi_encryption_enabled()
        )
        self._phi_encryption_service = phi_encryption_service
        if self._phi_encryption_enabled and self._phi_encryption_service is None:
            self._phi_encryption_service = build_phi_encryption_service_from_env()

    def create(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity:
        canonical_label, normalized_label = self._normalize_display_label(display_label)
        entity = EntityModel(
            id=uuid4(),
            research_space_id=_as_uuid(research_space_id),
            entity_type=entity_type,
            display_label=canonical_label,
            display_label_normalized=normalized_label,
            metadata_payload=metadata or {},
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_domain_entity(entity)

    def get_by_id(self, entity_id: str) -> KernelEntity | None:
        model = self._session.get(EntityModel, _as_uuid(entity_id))
        return self._to_domain_entity(model) if model is not None else None

    def update(
        self,
        entity_id: str,
        *,
        display_label: str | None = None,
        metadata: JSONObject | None = None,
    ) -> KernelEntity | None:
        entity_model = self._session.get(EntityModel, _as_uuid(entity_id))
        if entity_model is None:
            return None

        if display_label is not None:
            canonical_label, normalized_label = self._normalize_display_label(
                display_label,
            )
            entity_model.display_label = canonical_label
            entity_model.display_label_normalized = normalized_label

        if metadata is not None:
            merged = dict(entity_model.metadata_payload or {})
            merged.update(metadata)
            entity_model.metadata_payload = merged

        self._session.flush()
        return self._to_domain_entity(entity_model)

    def find_by_type(
        self,
        research_space_id: str,
        entity_type: str,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        stmt = (
            select(EntityModel)
            .where(
                EntityModel.research_space_id == _as_uuid(research_space_id),
                EntityModel.entity_type == entity_type,
            )
            .order_by(EntityModel.created_at.desc())
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return self._to_domain_entities(self._session.scalars(stmt).all())

    def find_by_research_space(
        self,
        research_space_id: str,
        *,
        entity_type: str | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[KernelEntity]:
        stmt = select(EntityModel).where(
            EntityModel.research_space_id == _as_uuid(research_space_id),
        )
        if entity_type is not None:
            stmt = stmt.where(EntityModel.entity_type == entity_type)
        stmt = stmt.order_by(EntityModel.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(limit)
        if offset is not None:
            stmt = stmt.offset(offset)
        return self._to_domain_entities(self._session.scalars(stmt).all())

    def search(
        self,
        research_space_id: str,
        query: str,
        *,
        entity_type: str | None = None,
        limit: int = 20,
    ) -> list[KernelEntity]:
        canonical_query = canonicalize_entity_match_text(query)
        if not canonical_query:
            return []
        normalized_query = normalize_entity_match_text(canonical_query)
        stmt = (
            select(EntityModel.id)
            .outerjoin(
                EntityAliasModel,
                and_(
                    EntityAliasModel.entity_id == EntityModel.id,
                    EntityAliasModel.is_active.is_(True),
                ),
            )
            .where(
                EntityModel.research_space_id == _as_uuid(research_space_id),
                or_(
                    EntityModel.display_label.ilike(f"%{canonical_query}%"),
                    EntityModel.display_label_normalized.like(f"%{normalized_query}%"),
                    EntityAliasModel.alias_label.ilike(f"%{canonical_query}%"),
                    EntityAliasModel.alias_normalized.like(f"%{normalized_query}%"),
                ),
            )
            .order_by(EntityModel.created_at.desc())
        )
        if entity_type is not None:
            stmt = stmt.where(EntityModel.entity_type == entity_type)
        entity_ids = self._dedupe_entity_ids(self._session.scalars(stmt).all())[:limit]
        if not entity_ids:
            return []
        models = self._session.scalars(
            select(EntityModel)
            .where(EntityModel.id.in_(entity_ids))
            .order_by(EntityModel.created_at.desc()),
        ).all()
        return self._to_domain_entities(models)

    def count_by_type(self, research_space_id: str) -> dict[str, int]:
        rows = self._session.execute(
            select(EntityModel.entity_type, func.count())
            .where(EntityModel.research_space_id == _as_uuid(research_space_id))
            .group_by(EntityModel.entity_type),
        ).all()
        return {row[0]: row[1] for row in rows}

    def count_global_by_type(self) -> dict[str, int]:
        rows = self._session.execute(
            select(EntityModel.entity_type, func.count()).group_by(
                EntityModel.entity_type,
            ),
        ).all()
        return {row[0]: row[1] for row in rows}

    def delete(self, entity_id: str) -> bool:
        entity_model = self._session.get(EntityModel, _as_uuid(entity_id))
        if entity_model is None:
            return False
        self._session.delete(entity_model)
        self._session.flush()
        return True

    def add_identifier(  # noqa: C901, PLR0912, PLR0915
        self,
        *,
        entity_id: str,
        namespace: str,
        identifier_value: str,
        sensitivity: str = "INTERNAL",
    ) -> KernelEntityIdentifier:
        entity_uuid = _as_uuid(entity_id)
        entity_model = self._session.get(EntityModel, entity_uuid)
        if entity_model is None:
            msg = f"Entity '{entity_id}' does not exist."
            raise KernelEntityValidationError(msg)

        normalized_namespace = namespace.strip()
        if not normalized_namespace:
            msg = "namespace is required"
            raise KernelEntityValidationError(msg)
        canonical_identifier_value = canonicalize_entity_match_text(identifier_value)
        if not canonical_identifier_value:
            msg = "identifier_value is required"
            raise KernelEntityValidationError(msg)

        normalized_sensitivity = sensitivity.strip().upper() or "INTERNAL"
        uses_phi_encryption = self._uses_phi_encryption(normalized_sensitivity)
        blind_index: str | None = None
        normalized_identifier: str | None = None
        stored_identifier_value = canonical_identifier_value
        encryption_key_version: str | None = None
        blind_index_version: str | None = None

        if uses_phi_encryption:
            if self._phi_encryption_service is None:
                message = "PHI encryption is enabled but encryption service is missing"
                raise RuntimeError(message)
            blind_index = self._phi_encryption_service.blind_index(
                canonical_identifier_value,
            )
            stored_identifier_value = self._phi_encryption_service.encrypt(
                canonical_identifier_value,
            )
            encryption_key_version = self._phi_encryption_service.key_version
            blind_index_version = self._phi_encryption_service.blind_index_version
        else:
            normalized_identifier = normalize_entity_match_text(
                canonical_identifier_value,
            )

        existing_row = self._find_identifier_conflict(
            entity_id=entity_uuid,
            research_space_id=entity_model.research_space_id,
            namespace=normalized_namespace,
            canonical_identifier_value=canonical_identifier_value,
            normalized_identifier=normalized_identifier,
            blind_index=blind_index,
        )
        if existing_row is not None:
            if existing_row.entity_id == entity_uuid:
                return self._to_domain_identifier(existing_row)
            msg = (
                f"Identifier '{canonical_identifier_value}' in namespace "
                f"'{normalized_namespace}' is already assigned to another entity."
            )
            raise KernelEntityConflictError(msg)

        bind = self._session.get_bind()
        dialect_name = getattr(bind.dialect, "name", "")
        values = {
            "entity_id": entity_uuid,
            "research_space_id": entity_model.research_space_id,
            "namespace": normalized_namespace,
            "identifier_value": stored_identifier_value,
            "identifier_blind_index": blind_index,
            "identifier_normalized": normalized_identifier,
            "encryption_key_version": encryption_key_version,
            "blind_index_version": blind_index_version,
            "sensitivity": normalized_sensitivity,
        }
        if dialect_name == "postgresql":
            index_elements = (
                ["entity_id", "namespace", "identifier_blind_index"]
                if uses_phi_encryption
                else ["entity_id", "namespace", "identifier_value"]
            )
            self._session.execute(
                pg_insert(EntityIdentifierModel)
                .values(**values)
                .on_conflict_do_nothing(index_elements=index_elements),
            )
        else:
            self._session.execute(sa_insert(EntityIdentifierModel).values(**values))
        self._session.flush()

        if uses_phi_encryption:
            if blind_index is None:
                message = (
                    "PHI blind index was not computed for PHI identifier upsert lookup"
                )
                raise RuntimeError(message)
            lookup = select(EntityIdentifierModel).where(
                EntityIdentifierModel.entity_id == entity_uuid,
                EntityIdentifierModel.namespace == normalized_namespace,
                EntityIdentifierModel.identifier_blind_index == blind_index,
                EntityIdentifierModel.sensitivity == "PHI",
            )
        else:
            lookup = select(EntityIdentifierModel).where(
                EntityIdentifierModel.entity_id == entity_uuid,
                EntityIdentifierModel.namespace == normalized_namespace,
                EntityIdentifierModel.identifier_normalized == normalized_identifier,
            )
        model = self._session.scalars(lookup).one()
        return self._to_domain_identifier(model)

    def find_by_identifier(
        self,
        *,
        namespace: str,
        identifier_value: str,
        research_space_id: str | None = None,
    ) -> KernelEntity | None:
        candidates = self.find_identifier_candidates(
            namespace=namespace,
            identifier_value=identifier_value,
            research_space_id=research_space_id,
        )
        return self._resolve_single_candidate(
            candidates,
            match_description=(
                f"identifier '{identifier_value}' in namespace '{namespace.strip()}'"
            ),
        )

    def find_identifier_candidates(
        self,
        *,
        namespace: str,
        identifier_value: str,
        research_space_id: str | None = None,
        entity_type: str | None = None,
    ) -> list[KernelEntity]:
        normalized_namespace = namespace.strip()
        if not normalized_namespace:
            return []
        models = self._find_identifier_matches(
            namespace=normalized_namespace,
            identifier_value=identifier_value,
            research_space_id=research_space_id,
            entity_type=entity_type,
        )
        return self._to_domain_entities(models)

    def find_by_display_label(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str,
    ) -> KernelEntity | None:
        candidates = self.find_display_label_candidates(
            research_space_id=research_space_id,
            entity_type=entity_type,
            display_label=display_label,
        )
        return self._resolve_single_candidate(
            candidates,
            match_description=f"display label '{display_label}'",
        )

    def find_display_label_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        display_label: str,
    ) -> list[KernelEntity]:
        normalized_display_label = normalize_entity_match_text(display_label)
        if not normalized_display_label:
            return []
        models = self._session.scalars(
            select(EntityModel).where(
                EntityModel.research_space_id == _as_uuid(research_space_id),
                EntityModel.entity_type == entity_type,
                EntityModel.display_label_normalized == normalized_display_label,
            ),
        ).all()
        return self._to_domain_entities(self._dedupe_entity_models(models))

    def add_alias(
        self,
        *,
        entity_id: str,
        alias_label: str,
        source: str | None = None,
        review_status: str = "ACTIVE",
    ) -> KernelEntityAlias:
        entity_model = self._session.get(EntityModel, _as_uuid(entity_id))
        if entity_model is None:
            msg = f"Entity '{entity_id}' does not exist."
            raise KernelEntityValidationError(msg)

        canonical_alias = canonicalize_entity_match_text(alias_label)
        if not canonical_alias:
            msg = "alias_label is required"
            raise KernelEntityValidationError(msg)
        normalized_alias = normalize_entity_match_text(canonical_alias)
        existing_models = self._session.scalars(
            select(EntityAliasModel).where(
                EntityAliasModel.research_space_id == entity_model.research_space_id,
                EntityAliasModel.entity_type == entity_model.entity_type,
                EntityAliasModel.alias_normalized == normalized_alias,
                EntityAliasModel.is_active.is_(True),
            ),
        ).all()
        for existing_model in existing_models:
            if existing_model.entity_id == entity_model.id:
                return self._to_domain_alias(existing_model)
            msg = (
                f"Alias '{canonical_alias}' is already assigned to another "
                "entity in this research space."
            )
            raise KernelEntityConflictError(msg)

        same_entity_alias = self._session.scalars(
            select(EntityAliasModel).where(
                EntityAliasModel.entity_id == entity_model.id,
                EntityAliasModel.alias_normalized == normalized_alias,
            ),
        ).first()
        if same_entity_alias is not None:
            return self._to_domain_alias(same_entity_alias)

        alias_model = EntityAliasModel(
            entity_id=entity_model.id,
            research_space_id=entity_model.research_space_id,
            entity_type=entity_model.entity_type,
            alias_label=canonical_alias,
            alias_normalized=normalized_alias,
            source=source,
            created_by="system:kernel_entity_repository",
            review_status=review_status,
        )
        self._session.add(alias_model)
        self._session.flush()
        return self._to_domain_alias(alias_model)

    def list_aliases(
        self,
        *,
        entity_id: str,
        include_inactive: bool = False,
    ) -> list[KernelEntityAlias]:
        stmt = select(EntityAliasModel).where(
            EntityAliasModel.entity_id == _as_uuid(entity_id),
        )
        if not include_inactive:
            stmt = stmt.where(EntityAliasModel.is_active.is_(True))
        stmt = stmt.order_by(
            EntityAliasModel.created_at.asc(),
            EntityAliasModel.id.asc(),
        )
        return [self._to_domain_alias(model) for model in self._session.scalars(stmt)]

    def find_by_alias(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        alias_label: str,
    ) -> KernelEntity | None:
        candidates = self.find_alias_candidates(
            research_space_id=research_space_id,
            entity_type=entity_type,
            alias_label=alias_label,
        )
        return self._resolve_single_candidate(
            candidates,
            match_description=f"alias '{alias_label}'",
        )

    def find_alias_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        alias_label: str,
    ) -> list[KernelEntity]:
        normalized_alias = normalize_entity_match_text(alias_label)
        if not normalized_alias:
            return []
        models = self._session.scalars(
            select(EntityModel)
            .join(EntityAliasModel, EntityAliasModel.entity_id == EntityModel.id)
            .where(
                EntityAliasModel.research_space_id == _as_uuid(research_space_id),
                EntityAliasModel.entity_type == entity_type,
                EntityAliasModel.alias_normalized == normalized_alias,
                EntityAliasModel.is_active.is_(True),
            ),
        ).all()
        return self._to_domain_entities(self._dedupe_entity_models(models))

    def resolve_candidates(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str],
    ) -> list[KernelEntity]:
        candidate_by_id: dict[UUID, KernelEntity] = {}
        for namespace, value in identifiers.items():
            for candidate in self.find_identifier_candidates(
                namespace=namespace,
                identifier_value=value,
                research_space_id=research_space_id,
                entity_type=entity_type,
            ):
                candidate_by_id[candidate.id] = candidate
        return list(candidate_by_id.values())

    def resolve(
        self,
        *,
        research_space_id: str,
        entity_type: str,
        identifiers: dict[str, str],
    ) -> KernelEntity | None:
        candidates = self.resolve_candidates(
            research_space_id=research_space_id,
            entity_type=entity_type,
            identifiers=identifiers,
        )
        return self._resolve_single_candidate(
            candidates,
            match_description="identifier anchors",
        )

    @staticmethod
    def _normalize_display_label(
        display_label: str | None,
    ) -> tuple[str | None, str | None]:
        if display_label is None:
            return None, None
        canonical_label = canonicalize_entity_match_text(display_label)
        if not canonical_label:
            return None, None
        return canonical_label, normalize_entity_match_text(canonical_label)

    def _uses_phi_encryption(self, sensitivity: str) -> bool:
        return (
            self._phi_encryption_enabled
            and self._phi_encryption_service is not None
            and sensitivity == "PHI"
        )

    def _find_identifier_conflict(  # noqa: PLR0913
        self,
        *,
        entity_id: UUID,
        research_space_id: UUID,
        namespace: str,
        canonical_identifier_value: str,
        normalized_identifier: str | None,
        blind_index: str | None,
    ) -> EntityIdentifierModel | None:
        stmt = select(EntityIdentifierModel).where(
            EntityIdentifierModel.research_space_id == research_space_id,
            EntityIdentifierModel.namespace == namespace,
        )
        if blind_index is not None:
            stmt = stmt.where(
                or_(
                    and_(
                        EntityIdentifierModel.sensitivity == "PHI",
                        EntityIdentifierModel.identifier_blind_index == blind_index,
                    ),
                    and_(
                        EntityIdentifierModel.sensitivity == "PHI",
                        EntityIdentifierModel.identifier_blind_index.is_(None),
                        EntityIdentifierModel.identifier_value
                        == canonical_identifier_value,
                    ),
                ),
            )
        else:
            stmt = stmt.where(
                and_(
                    EntityIdentifierModel.sensitivity != "PHI",
                    or_(
                        EntityIdentifierModel.identifier_normalized
                        == normalized_identifier,
                        and_(
                            EntityIdentifierModel.identifier_normalized.is_(None),
                            EntityIdentifierModel.identifier_value
                            == canonical_identifier_value,
                        ),
                    ),
                ),
            )
        models = self._session.scalars(stmt).all()
        if not models:
            return None
        for model in models:
            if model.entity_id == entity_id:
                return model
        return models[0]

    def _find_identifier_matches(
        self,
        *,
        namespace: str,
        identifier_value: str,
        research_space_id: str | None = None,
        entity_type: str | None = None,
    ) -> list[EntityModel]:
        canonical_identifier_value = canonicalize_entity_match_text(identifier_value)
        if not canonical_identifier_value:
            return []
        normalized_identifier = normalize_entity_match_text(canonical_identifier_value)
        stmt = (
            select(EntityModel)
            .join(EntityIdentifierModel)
            .where(EntityIdentifierModel.namespace == namespace)
        )
        blind_index: str | None = None
        if self._phi_encryption_enabled and self._phi_encryption_service is not None:
            blind_index = self._phi_encryption_service.blind_index(
                canonical_identifier_value,
            )

        non_phi_match = and_(
            EntityIdentifierModel.sensitivity != "PHI",
            or_(
                EntityIdentifierModel.identifier_normalized == normalized_identifier,
                and_(
                    EntityIdentifierModel.identifier_normalized.is_(None),
                    EntityIdentifierModel.identifier_value
                    == canonical_identifier_value,
                ),
            ),
        )
        conditions = [
            and_(
                EntityIdentifierModel.sensitivity == "PHI",
                EntityIdentifierModel.identifier_blind_index.is_(None),
                EntityIdentifierModel.identifier_value == canonical_identifier_value,
            ),
            non_phi_match,
        ]
        if blind_index is not None:
            conditions.insert(
                0,
                and_(
                    EntityIdentifierModel.sensitivity == "PHI",
                    EntityIdentifierModel.identifier_blind_index == blind_index,
                ),
            )
        stmt = stmt.where(or_(*conditions))
        if research_space_id is not None:
            stmt = stmt.where(
                EntityModel.research_space_id == _as_uuid(research_space_id),
            )
        if entity_type is not None:
            stmt = stmt.where(EntityModel.entity_type == entity_type)
        return self._dedupe_entity_models(self._session.scalars(stmt).all())

    def _resolve_single_candidate(
        self,
        candidates: Sequence[KernelEntity],
        *,
        match_description: str,
    ) -> KernelEntity | None:
        if not candidates:
            return None
        unique_candidates = self._dedupe_domain_entities(candidates)
        if len(unique_candidates) > 1:
            msg = f"Ambiguous exact match for {match_description}."
            raise KernelEntityConflictError(msg)
        return unique_candidates[0]

    @staticmethod
    def _dedupe_entity_models(models: Sequence[EntityModel]) -> list[EntityModel]:
        deduped: list[EntityModel] = []
        seen: set[UUID] = set()
        for model in models:
            if model.id in seen:
                continue
            seen.add(model.id)
            deduped.append(model)
        return deduped

    @staticmethod
    def _dedupe_entity_ids(entity_ids: Sequence[UUID]) -> list[UUID]:
        deduped: list[UUID] = []
        seen: set[UUID] = set()
        for entity_id in entity_ids:
            if entity_id in seen:
                continue
            seen.add(entity_id)
            deduped.append(entity_id)
        return deduped

    @staticmethod
    def _dedupe_domain_entities(
        entities: Sequence[KernelEntity],
    ) -> list[KernelEntity]:
        deduped: list[KernelEntity] = []
        seen: set[UUID] = set()
        for entity in entities:
            if entity.id in seen:
                continue
            seen.add(entity.id)
            deduped.append(entity)
        return deduped

    def _alias_map_for_entity_ids(
        self,
        entity_ids: Sequence[UUID],
    ) -> dict[UUID, list[str]]:
        if not entity_ids:
            return {}
        rows = self._session.execute(
            select(EntityAliasModel.entity_id, EntityAliasModel.alias_label)
            .where(
                EntityAliasModel.entity_id.in_(entity_ids),
                EntityAliasModel.is_active.is_(True),
            )
            .order_by(EntityAliasModel.created_at.asc(), EntityAliasModel.id.asc()),
        ).all()
        alias_map: dict[UUID, list[str]] = {entity_id: [] for entity_id in entity_ids}
        for entity_id, alias_label in rows:
            labels = alias_map.setdefault(entity_id, [])
            if alias_label in labels:
                continue
            labels.append(alias_label)
        return alias_map

    def _to_domain_entity(self, model: EntityModel) -> KernelEntity:
        alias_map = self._alias_map_for_entity_ids([model.id])
        return KernelEntity.model_validate(
            {
                "id": model.id,
                "research_space_id": model.research_space_id,
                "entity_type": model.entity_type,
                "display_label": model.display_label,
                "aliases": alias_map.get(model.id, []),
                "metadata_payload": model.metadata_payload or {},
                "created_at": model.created_at,
                "updated_at": model.updated_at,
            },
        )

    def _to_domain_entities(self, models: Sequence[EntityModel]) -> list[KernelEntity]:
        entity_ids = [model.id for model in models]
        alias_map = self._alias_map_for_entity_ids(entity_ids)
        return [
            KernelEntity.model_validate(
                {
                    "id": model.id,
                    "research_space_id": model.research_space_id,
                    "entity_type": model.entity_type,
                    "display_label": model.display_label,
                    "aliases": alias_map.get(model.id, []),
                    "metadata_payload": model.metadata_payload or {},
                    "created_at": model.created_at,
                    "updated_at": model.updated_at,
                },
            )
            for model in models
        ]

    @staticmethod
    def _to_domain_alias(model: EntityAliasModel) -> KernelEntityAlias:
        return KernelEntityAlias.model_validate(model)

    def _to_domain_identifier(
        self,
        model: EntityIdentifierModel,
    ) -> KernelEntityIdentifier:
        identifier_value = model.identifier_value
        if (
            model.sensitivity == "PHI"
            and model.identifier_blind_index
            and self._phi_encryption_enabled
            and self._phi_encryption_service is not None
            and self._phi_encryption_service.is_encrypted_identifier(identifier_value)
        ):
            try:
                identifier_value = self._phi_encryption_service.decrypt(
                    identifier_value,
                )
            except ValueError:
                logger.warning(
                    "Failed to decrypt PHI identifier %s/%s; returning stored payload",
                    model.namespace,
                    model.id,
                )

        return KernelEntityIdentifier.model_validate(
            {
                "id": model.id,
                "entity_id": model.entity_id,
                "namespace": model.namespace,
                "identifier_value": identifier_value,
                "identifier_blind_index": model.identifier_blind_index,
                "encryption_key_version": model.encryption_key_version,
                "blind_index_version": model.blind_index_version,
                "sensitivity": model.sensitivity,
                "created_at": model.created_at,
                "updated_at": model.created_at,
            },
        )


__all__ = ["SqlAlchemyKernelEntityRepository"]
