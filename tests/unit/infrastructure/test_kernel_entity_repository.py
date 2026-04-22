"""Unit tests for SQLAlchemy kernel entity repository adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import pytest
from artana_evidence_db.entity_lookup_models import EntityIdentifierModel
from artana_evidence_db.entity_repository import (
    SqlAlchemyKernelEntityRepository,
)
from artana_evidence_db.kernel_entity_errors import (
    KernelEntityConflictError,
)
from artana_evidence_db.kernel_entity_models import EntityModel
from sqlalchemy import select

from src.domain.value_objects.entity_resolution import normalize_entity_match_text
from src.infrastructure.security.key_provider import PHIKeyMaterial
from src.infrastructure.security.phi_encryption import PHIEncryptionService
from tests.graph_seed_helpers import ensure_entity_types

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


@dataclass(slots=True)
class StaticKeyProvider:
    key_material: PHIKeyMaterial

    def get_key_material(self) -> PHIKeyMaterial:
        return self.key_material


def _build_phi_encryption_service() -> PHIEncryptionService:
    provider = StaticKeyProvider(
        PHIKeyMaterial(
            encryption_key=bytes([9]) * 32,
            blind_index_key=bytes([10]) * 32,
            key_version="v1",
            blind_index_version="v1",
        ),
    )
    return PHIEncryptionService(provider)


def _seed_space_and_entity(
    db_session: Session,
    *,
    entity_type: str = "PATIENT",
    display_label: str = "Patient 1",
) -> tuple[UUID, UUID]:
    ensure_entity_types(db_session, entity_type)
    research_space_id = uuid4()

    entity_id = uuid4()
    db_session.add(
        EntityModel(
            id=entity_id,
            research_space_id=research_space_id,
            entity_type=entity_type,
            display_label=display_label,
            display_label_normalized=normalize_entity_match_text(display_label),
            metadata_payload={},
        ),
    )
    db_session.flush()
    return research_space_id, entity_id


def test_add_phi_identifier_encrypts_and_resolves(db_session: Session) -> None:
    research_space_id, entity_id = _seed_space_and_entity(db_session)
    encryption_service = _build_phi_encryption_service()
    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=encryption_service,
        enable_phi_encryption=True,
    )

    created = repository.add_identifier(
        entity_id=str(entity_id),
        namespace="MRN",
        identifier_value="MRN-123",
        sensitivity="PHI",
    )

    assert created.identifier_value == "MRN-123"
    assert created.identifier_blind_index is not None
    assert created.encryption_key_version == "v1"
    assert created.blind_index_version == "v1"

    persisted = db_session.scalars(
        select(EntityIdentifierModel).where(
            EntityIdentifierModel.entity_id == entity_id,
            EntityIdentifierModel.namespace == "MRN",
        ),
    ).one()
    assert persisted.identifier_value != "MRN-123"
    assert persisted.identifier_blind_index == encryption_service.blind_index("MRN-123")

    resolved = repository.find_by_identifier(
        namespace="MRN",
        identifier_value="MRN-123",
        research_space_id=str(research_space_id),
    )
    assert resolved is not None
    assert str(resolved.id) == str(entity_id)


def test_add_phi_identifier_is_idempotent_by_blind_index(db_session: Session) -> None:
    _research_space_id, entity_id = _seed_space_and_entity(db_session)
    encryption_service = _build_phi_encryption_service()
    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=encryption_service,
        enable_phi_encryption=True,
    )

    first = repository.add_identifier(
        entity_id=str(entity_id),
        namespace="MRN",
        identifier_value="MRN-456",
        sensitivity="PHI",
    )
    second = repository.add_identifier(
        entity_id=str(entity_id),
        namespace="MRN",
        identifier_value="MRN-456",
        sensitivity="PHI",
    )

    assert first.id == second.id

    rows = db_session.scalars(
        select(EntityIdentifierModel).where(
            EntityIdentifierModel.entity_id == entity_id,
            EntityIdentifierModel.namespace == "MRN",
        ),
    ).all()
    assert len(rows) == 1


def test_non_phi_identifier_passthrough_when_encryption_enabled(
    db_session: Session,
) -> None:
    _research_space_id, entity_id = _seed_space_and_entity(db_session)
    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=_build_phi_encryption_service(),
        enable_phi_encryption=True,
    )

    created = repository.add_identifier(
        entity_id=str(entity_id),
        namespace="HGNC",
        identifier_value="HGNC:1234",
        sensitivity="INTERNAL",
    )

    assert created.identifier_value == "HGNC:1234"
    assert created.identifier_blind_index is None

    persisted = db_session.scalars(
        select(EntityIdentifierModel).where(
            EntityIdentifierModel.entity_id == entity_id,
            EntityIdentifierModel.namespace == "HGNC",
        ),
    ).one()
    assert persisted.identifier_value == "HGNC:1234"
    assert persisted.identifier_blind_index is None


def test_find_by_identifier_supports_legacy_plaintext_phi_rows(
    db_session: Session,
) -> None:
    research_space_id, entity_id = _seed_space_and_entity(db_session)
    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=_build_phi_encryption_service(),
        enable_phi_encryption=True,
    )

    db_session.add(
        EntityIdentifierModel(
            entity_id=entity_id,
            research_space_id=research_space_id,
            namespace="MRN",
            identifier_value="LEGACY-MRN-001",
            identifier_blind_index=None,
            sensitivity="PHI",
        ),
    )
    db_session.flush()

    resolved = repository.find_by_identifier(
        namespace="MRN",
        identifier_value="LEGACY-MRN-001",
        research_space_id=str(research_space_id),
    )
    assert resolved is not None
    assert str(resolved.id) == str(entity_id)


def test_find_by_display_label_matches_casefolded_labels(db_session: Session) -> None:
    research_space_id, entity_id = _seed_space_and_entity(
        db_session,
        entity_type="GENE",
        display_label="MED13",
    )
    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=None,
        enable_phi_encryption=False,
    )

    resolved = repository.find_by_display_label(
        research_space_id=str(research_space_id),
        entity_type="GENE",
        display_label=" med13 ",
    )

    assert resolved is not None
    assert str(resolved.id) == str(entity_id)


def test_add_alias_supports_exact_alias_lookup_and_search(
    db_session: Session,
) -> None:
    research_space_id, entity_id = _seed_space_and_entity(
        db_session,
        entity_type="GENE",
        display_label="MED13",
    )
    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=None,
        enable_phi_encryption=False,
    )

    repository.add_alias(
        entity_id=str(entity_id),
        alias_label="THRAP1",
        source="unit-test",
    )

    resolved = repository.find_by_alias(
        research_space_id=str(research_space_id),
        entity_type="GENE",
        alias_label="thrap1",
    )

    assert resolved is not None
    assert str(resolved.id) == str(entity_id)
    assert "THRAP1" in resolved.aliases

    search_results = repository.search(str(research_space_id), "thrap1")
    assert len(search_results) == 1
    assert str(search_results[0].id) == str(entity_id)


def test_add_identifier_conflicts_across_entities_in_same_space(
    db_session: Session,
) -> None:
    research_space_id, entity_id = _seed_space_and_entity(
        db_session,
        entity_type="GENE",
        display_label="MED13",
    )
    other_entity_id = uuid4()
    db_session.add(
        EntityModel(
            id=other_entity_id,
            research_space_id=research_space_id,
            entity_type="GENE",
            display_label="THRAP1",
            display_label_normalized=normalize_entity_match_text("THRAP1"),
            metadata_payload={},
        ),
    )
    db_session.flush()

    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=None,
        enable_phi_encryption=False,
    )
    repository.add_identifier(
        entity_id=str(entity_id),
        namespace="HGNC",
        identifier_value="HGNC:1234",
    )

    with pytest.raises(KernelEntityConflictError, match="already assigned"):
        repository.add_identifier(
            entity_id=str(other_entity_id),
            namespace="HGNC",
            identifier_value=" hgnc:1234 ",
        )


def test_resolve_candidates_aggregates_conflicting_identifier_anchors(
    db_session: Session,
) -> None:
    research_space_id, first_entity_id = _seed_space_and_entity(
        db_session,
        entity_type="GENE",
        display_label="MED13",
    )
    second_entity_id = uuid4()
    db_session.add(
        EntityModel(
            id=second_entity_id,
            research_space_id=research_space_id,
            entity_type="GENE",
            display_label="THRAP1",
            display_label_normalized=normalize_entity_match_text("THRAP1"),
            metadata_payload={},
        ),
    )
    db_session.flush()

    repository = SqlAlchemyKernelEntityRepository(
        db_session,
        phi_encryption_service=None,
        enable_phi_encryption=False,
    )
    repository.add_identifier(
        entity_id=str(first_entity_id),
        namespace="HGNC",
        identifier_value="HGNC:1234",
    )
    repository.add_identifier(
        entity_id=str(second_entity_id),
        namespace="ENSEMBL",
        identifier_value="ENSG00000123066",
    )

    candidates = repository.resolve_candidates(
        research_space_id=str(research_space_id),
        entity_type="GENE",
        identifiers={
            "HGNC": " hgnc:1234 ",
            "ENSEMBL": "ensg00000123066",
        },
    )

    assert {str(candidate.id) for candidate in candidates} == {
        str(first_entity_id),
        str(second_entity_id),
    }

    with pytest.raises(KernelEntityConflictError, match="Ambiguous exact match"):
        repository.resolve(
            research_space_id=str(research_space_id),
            entity_type="GENE",
            identifiers={
                "HGNC": "HGNC:1234",
                "ENSEMBL": "ENSG00000123066",
            },
        )
