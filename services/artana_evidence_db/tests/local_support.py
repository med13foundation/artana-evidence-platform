"""Service-local reset and seed helpers for standalone artana-evidence-db tests."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from artana_evidence_db.kernel_dictionary_models import (
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
    EntityResolutionPolicyModel,
    RelationConstraintModel,
)
from artana_evidence_db.schema_support import graph_schema_name
from sqlalchemy import inspect, select, text

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine
    from sqlalchemy.orm import Session
    from sqlalchemy.sql.schema import MetaData

_ENTITY_RESOLUTION_POLICY_ROWS: tuple[tuple[str, str, tuple[str, ...], float], ...] = (
    ("GENE", "LOOKUP", ("hgnc_id",), 1.0),
    ("VARIANT", "STRICT_MATCH", ("hgvs_notation", "gene_symbol"), 1.0),
    ("PHENOTYPE", "LOOKUP", ("hpo_id",), 1.0),
    ("PUBLICATION", "FUZZY", ("doi", "title"), 0.95),
    ("DRUG", "LOOKUP", ("drugbank_id",), 1.0),
    ("PATHWAY", "LOOKUP", ("reactome_id",), 1.0),
    ("MECHANISM", "NONE", (), 1.0),
    ("PATIENT", "STRICT_MATCH", ("mrn", "issuer"), 1.0),
)

_RELATION_CONSTRAINT_ROWS: tuple[tuple[str, str, str, bool, bool], ...] = (
    ("VARIANT", "LOCATED_IN", "GENE", True, False),
    ("VARIANT", "CAUSES", "PHENOTYPE", True, True),
    ("VARIANT", "LOCATED_IN_DOMAIN", "GENE", True, False),
    ("GENE", "ASSOCIATED_WITH", "PHENOTYPE", True, True),
    ("GENE", "INTERACTS_WITH", "GENE", True, True),
    ("GENE", "PARTICIPATES_IN", "PATHWAY", True, True),
    ("MECHANISM", "EXPLAINS", "PHENOTYPE", True, True),
    ("MECHANISM", "INVOLVES", "GENE", True, True),
    ("DRUG", "TARGETS", "PATHWAY", True, True),
    ("DRUG", "TARGETS", "GENE", True, True),
    ("DRUG", "TREATS", "PHENOTYPE", True, True),
    ("PUBLICATION", "SUPPORTS", "VARIANT", True, False),
    ("PUBLICATION", "SUPPORTS", "MECHANISM", True, False),
    ("PUBLICATION", "SUPPORTS", "GENE", True, False),
    ("PUBLICATION", "MENTIONS", "PHENOTYPE", True, False),
    ("PUBLICATION", "MENTIONS", "DRUG", True, False),
    ("PUBLICATION", "MENTIONS", "GENE", True, False),
    ("PUBLICATION", "MENTIONS", "PROTEIN", True, False),
    ("PUBLICATION", "MENTIONS", "VARIANT", True, False),
    ("PUBLICATION", "CITES", "PUBLICATION", True, False),
    ("PUBLICATION", "HAS_AUTHOR", "AUTHOR", True, False),
    ("PUBLICATION", "HAS_KEYWORD", "KEYWORD", True, False),
    ("PATIENT", "HAS_VARIANT", "VARIANT", True, False),
    ("PATIENT", "EXHIBITS", "PHENOTYPE", True, False),
)


def _humanize(identifier: str) -> str:
    return " ".join(part.capitalize() for part in identifier.replace("_", " ").split())


def _escape_identifier(identifier: str) -> str:
    return identifier.replace('"', '""')


def _qualified_tables_for_schema(*, inspector: object, schema: str) -> list[str]:
    table_names = inspect(inspector).get_table_names(schema=schema)
    tables = [
        table_name
        for table_name in table_names
        if not (schema == "public" and table_name == "alembic_version")
    ]
    escaped_schema = _escape_identifier(schema)
    return [f'"{escaped_schema}"."{_escape_identifier(table)}"' for table in tables]


def reset_database(engine: Engine, metadata: MetaData) -> None:
    """Reset the graph-service test database contents."""
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            schemas = ["public"]
            configured_graph_schema = graph_schema_name(os.getenv("GRAPH_DB_SCHEMA"))
            if configured_graph_schema is not None:
                schemas.append(configured_graph_schema)
            qualified_tables: list[str] = []
            for schema in schemas:
                qualified_tables.extend(
                    _qualified_tables_for_schema(inspector=connection, schema=schema),
                )
            if qualified_tables:
                connection.execute(
                    text(
                        "TRUNCATE TABLE "
                        + ", ".join(qualified_tables)
                        + " RESTART IDENTITY CASCADE",
                    ),
                )
            if configured_graph_schema is not None:
                escaped_schema = _escape_identifier(configured_graph_schema)
                connection.execute(
                    text(f'CREATE SCHEMA IF NOT EXISTS "{escaped_schema}"'),
                )
            connection.execute(
                text("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public"),
            )
            metadata.create_all(bind=connection, checkfirst=True)
            return

    metadata.drop_all(bind=engine)
    metadata.create_all(bind=engine)


def _ensure_domain_context_reference(
    session: Session,
    *,
    domain_context: str,
) -> None:
    normalized_domain_context = domain_context.strip().lower()
    if not normalized_domain_context:
        return
    if session.get(DictionaryDomainContextModel, normalized_domain_context) is not None:
        return
    session.add(
        DictionaryDomainContextModel(
            id=normalized_domain_context,
            display_name=_humanize(normalized_domain_context),
            description="Autogenerated graph-service test domain context",
            is_active=True,
        ),
    )
    session.flush()


def _ensure_entity_type_reference(
    session: Session,
    *,
    entity_type: str,
    domain_context: str = "genomics",
) -> None:
    normalized_entity_type = entity_type.strip().upper()
    if not normalized_entity_type:
        return
    _ensure_domain_context_reference(session, domain_context=domain_context)
    if session.get(DictionaryEntityTypeModel, normalized_entity_type) is not None:
        return
    session.add(
        DictionaryEntityTypeModel(
            id=normalized_entity_type,
            display_name=_humanize(normalized_entity_type),
            description="Autogenerated entity type from graph-service test seed input",
            domain_context=domain_context,
            expected_properties={},
            created_by="test-seed",
            review_status="ACTIVE",
            is_active=True,
        ),
    )
    session.flush()


def _ensure_relation_type_reference(
    session: Session,
    *,
    relation_type: str,
    domain_context: str = "genomics",
) -> None:
    normalized_relation_type = relation_type.strip().upper()
    if not normalized_relation_type:
        return
    _ensure_domain_context_reference(session, domain_context=domain_context)
    if session.get(DictionaryRelationTypeModel, normalized_relation_type) is not None:
        return
    session.add(
        DictionaryRelationTypeModel(
            id=normalized_relation_type,
            display_name=_humanize(normalized_relation_type),
            description="Autogenerated relation type from graph-service test seed input",
            domain_context=domain_context,
            is_directional=True,
            created_by="test-seed",
            review_status="ACTIVE",
            is_active=True,
        ),
    )
    session.flush()


def seed_entity_resolution_policies(session: Session) -> int:
    """Seed deterministic entity-resolution policies for standalone tests."""
    count = 0
    for (
        entity_type,
        policy_strategy,
        required_anchors,
        auto_merge_threshold,
    ) in _ENTITY_RESOLUTION_POLICY_ROWS:
        _ensure_entity_type_reference(
            session,
            entity_type=entity_type,
            domain_context="genomics",
        )
        if session.get(EntityResolutionPolicyModel, entity_type) is not None:
            continue
        session.add(
            EntityResolutionPolicyModel(
                entity_type=entity_type,
                policy_strategy=policy_strategy,
                required_anchors=list(required_anchors),
                auto_merge_threshold=auto_merge_threshold,
                created_by="test-seed",
                review_status="ACTIVE",
                is_active=True,
            ),
        )
        count += 1
    session.flush()
    return count


def seed_relation_constraints(session: Session) -> int:
    """Seed deterministic relation constraints for standalone tests."""
    count = 0
    for (
        source_type,
        relation_type,
        target_type,
        is_allowed,
        requires_evidence,
    ) in _RELATION_CONSTRAINT_ROWS:
        _ensure_entity_type_reference(
            session,
            entity_type=source_type,
            domain_context="genomics",
        )
        _ensure_entity_type_reference(
            session,
            entity_type=target_type,
            domain_context="genomics",
        )
        _ensure_relation_type_reference(
            session,
            relation_type=relation_type,
            domain_context="genomics",
        )
        existing_constraint = session.scalars(
            select(RelationConstraintModel).where(
                RelationConstraintModel.source_type == source_type,
                RelationConstraintModel.relation_type == relation_type,
                RelationConstraintModel.target_type == target_type,
            ),
        ).first()
        if existing_constraint is not None:
            continue
        session.add(
            RelationConstraintModel(
                source_type=source_type,
                relation_type=relation_type,
                target_type=target_type,
                is_allowed=is_allowed,
                requires_evidence=requires_evidence,
                created_by="test-seed",
                review_status="ACTIVE",
                is_active=True,
            ),
        )
        count += 1
    session.flush()
    return count


__all__ = [
    "reset_database",
    "seed_entity_resolution_policies",
    "seed_relation_constraints",
]
