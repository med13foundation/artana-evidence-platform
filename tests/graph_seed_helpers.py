"""Shared test helpers for seeding graph dictionary primitives."""

from __future__ import annotations

from collections.abc import Iterable

from artana_evidence_db.kernel_dictionary_models import (
    DictionaryDataTypeModel,
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
    DictionarySensitivityLevelModel,
    RelationConstraintModel,
)
from sqlalchemy.orm import Session


def _humanize(identifier: str) -> str:
    return " ".join(part.capitalize() for part in identifier.replace("_", " ").split())


def _has_pending_id(
    db_session: Session,
    *,
    model_type: type[object],
    identifier: str,
) -> bool:
    return any(
        isinstance(instance, model_type) and getattr(instance, "id", None) == identifier
        for instance in db_session.new
    )


def _normalize_identifiers(values: Iterable[str]) -> list[str]:
    return [value.strip().upper() for value in values if value.strip()]


def ensure_domain_context(
    db_session: Session,
    *,
    domain_context: str = "general",
) -> None:
    normalized = domain_context.strip().lower()
    if db_session.get(
        DictionaryDomainContextModel,
        normalized,
    ) is not None or _has_pending_id(
        db_session,
        model_type=DictionaryDomainContextModel,
        identifier=normalized,
    ):
        return
    db_session.add(
        DictionaryDomainContextModel(
            id=normalized,
            display_name=_humanize(normalized),
            description="Graph test seed domain context",
            is_active=True,
        ),
    )
    db_session.flush()


def ensure_data_type(
    db_session: Session,
    *,
    data_type: str = "STRING",
) -> None:
    normalized = data_type.strip().upper()
    if db_session.get(
        DictionaryDataTypeModel,
        normalized,
    ) is not None or _has_pending_id(
        db_session,
        model_type=DictionaryDataTypeModel,
        identifier=normalized,
    ):
        return
    db_session.add(
        DictionaryDataTypeModel(
            id=normalized,
            display_name=_humanize(normalized),
            python_type_hint="str",
            description="Graph test seed data type",
            constraint_schema={},
        ),
    )
    db_session.flush()


def ensure_sensitivity_level(
    db_session: Session,
    *,
    sensitivity: str = "INTERNAL",
) -> None:
    normalized = sensitivity.strip().upper()
    if db_session.get(
        DictionarySensitivityLevelModel,
        normalized,
    ) is not None or _has_pending_id(
        db_session,
        model_type=DictionarySensitivityLevelModel,
        identifier=normalized,
    ):
        return
    db_session.add(
        DictionarySensitivityLevelModel(
            id=normalized,
            display_name=_humanize(normalized),
            description="Graph test seed sensitivity",
            is_active=True,
        ),
    )
    db_session.flush()


def ensure_entity_types(
    db_session: Session,
    *entity_types: str,
    domain_context: str = "general",
) -> None:
    ensure_domain_context(db_session, domain_context=domain_context)
    for normalized in _normalize_identifiers(entity_types):
        if db_session.get(
            DictionaryEntityTypeModel,
            normalized,
        ) is not None or _has_pending_id(
            db_session,
            model_type=DictionaryEntityTypeModel,
            identifier=normalized,
        ):
            continue
        db_session.add(
            DictionaryEntityTypeModel(
                id=normalized,
                display_name=_humanize(normalized),
                description="Graph test seed entity type",
                domain_context=domain_context,
                expected_properties={},
                created_by="test-seed",
                is_active=True,
                review_status="ACTIVE",
            ),
        )
    db_session.flush()


def ensure_relation_types(
    db_session: Session,
    *relation_types: str,
    domain_context: str = "general",
) -> None:
    ensure_domain_context(db_session, domain_context=domain_context)
    for normalized in _normalize_identifiers(relation_types):
        if db_session.get(
            DictionaryRelationTypeModel,
            normalized,
        ) is not None or _has_pending_id(
            db_session,
            model_type=DictionaryRelationTypeModel,
            identifier=normalized,
        ):
            continue
        db_session.add(
            DictionaryRelationTypeModel(
                id=normalized,
                display_name=_humanize(normalized),
                description="Graph test seed relation type",
                domain_context=domain_context,
                is_directional=True,
                created_by="test-seed",
                is_active=True,
                review_status="ACTIVE",
            ),
        )
    db_session.flush()


def ensure_relation_constraint(
    db_session: Session,
    *,
    source_type: str,
    relation_type: str,
    target_type: str,
    domain_context: str = "general",
    is_allowed: bool = True,
    requires_evidence: bool = True,
) -> None:
    normalized_source = source_type.strip().upper()
    normalized_relation = relation_type.strip().upper()
    normalized_target = target_type.strip().upper()
    ensure_entity_types(
        db_session,
        normalized_source,
        normalized_target,
        domain_context=domain_context,
    )
    ensure_relation_types(
        db_session,
        normalized_relation,
        domain_context=domain_context,
    )
    existing = (
        db_session.query(RelationConstraintModel)
        .filter(
            RelationConstraintModel.source_type == normalized_source,
            RelationConstraintModel.relation_type == normalized_relation,
            RelationConstraintModel.target_type == normalized_target,
        )
        .one_or_none()
    )
    if existing is None:
        db_session.add(
            RelationConstraintModel(
                source_type=normalized_source,
                relation_type=normalized_relation,
                target_type=normalized_target,
                is_allowed=is_allowed,
                requires_evidence=requires_evidence,
                created_by="test-seed",
                is_active=True,
                review_status="ACTIVE",
            ),
        )
        db_session.flush()


def build_dense_vector(
    values: list[float],
    *,
    dimensions: int = 1536,
) -> list[float]:
    """Pad or truncate a sparse test vector to the pgvector column dimension."""
    if len(values) >= dimensions:
        return values[:dimensions]
    return values + [0.0] * (dimensions - len(values))


__all__ = [
    "build_dense_vector",
    "ensure_data_type",
    "ensure_domain_context",
    "ensure_entity_types",
    "ensure_relation_constraint",
    "ensure_relation_types",
    "ensure_sensitivity_level",
]
