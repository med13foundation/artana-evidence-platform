"""Integration tests for the standalone graph API service."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from artana_evidence_db import database as graph_database
from artana_evidence_db.app import create_app
from artana_evidence_db.biomedical_concept_bootstrap import (
    seed_biomedical_starter_concepts,
)
from artana_evidence_db.dependencies import get_space_registry_port
from artana_evidence_db.entity_neighbors_projector import (
    KernelEntityNeighborsProjector,
)
from artana_evidence_db.graph_domain_config import (
    GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
)
from artana_evidence_db.kernel_concept_models import (
    ConceptAliasModel,
    ConceptMemberModel,
    ConceptSetModel,
)
from artana_evidence_db.kernel_dictionary_models import (
    DictionaryDomainContextModel,
    TransformRegistryModel,
)
from artana_evidence_db.kernel_entity_models import EntityModel
from artana_evidence_db.kernel_repositories import (
    SqlAlchemyDictionaryRepository,
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelClaimParticipantRepository,
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationProjectionSourceRepository,
    SqlAlchemyKernelRelationRepository,
)
from artana_evidence_db.orm_base import Base
from artana_evidence_db.product_contract import GRAPH_SERVICE_VERSION
from artana_evidence_db.provenance_model import ProvenanceModel
from artana_evidence_db.read_model_support import NullGraphReadModelUpdateDispatcher
from artana_evidence_db.read_models import EntityNeighborModel
from artana_evidence_db.relation_autopromotion_policy import AutoPromotionPolicy
from artana_evidence_db.relation_claim_service import (
    KernelRelationClaimService,
)
from artana_evidence_db.relation_projection_materialization_service import (
    KernelRelationProjectionMaterializationService,
)
from artana_evidence_db.source_document_model import (
    DocumentExtractionStatusEnum,
    DocumentFormatEnum,
    EnrichmentStatusEnum,
    SourceDocumentModel,
)
from artana_evidence_db.space_models import (
    GraphSpaceMembershipModel,
    GraphSpaceMembershipRoleEnum,
    GraphSpaceModel,
    GraphSpaceStatusEnum,
)
from artana_evidence_db.space_registry_repository import (
    SqlAlchemyKernelSpaceRegistryRepository,
)
from artana_evidence_db.tests.local_support import (
    reset_database,
    seed_entity_resolution_policies,
    seed_relation_constraints,
)
from artana_evidence_db.tests.support import build_graph_auth_headers
from artana_evidence_db.user_models import UserRole
from artana_evidence_db.workflow_persistence_models import (
    GraphWorkflowEventModel,
    GraphWorkflowModel,
)
from fastapi import Depends
from fastapi.testclient import TestClient

pytestmark = pytest.mark.graph
_TEST_SESSION_DEPENDENCY = Depends(graph_database.get_session)
_SUPPORTED_ASSESSMENT = {
    "support_band": "SUPPORTED",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Synthetic integration evidence supports this graph write.",
}
_STRONG_ASSESSMENT = {
    "support_band": "STRONG",
    "grounding_level": "SPAN",
    "mapping_status": "RESOLVED",
    "speculation_level": "DIRECT",
    "confidence_rationale": "Direct curated evidence strongly supports this AI decision.",
}
_DECISION_CONFIDENCE_ASSESSMENT = {
    "fact_assessment": _STRONG_ASSESSMENT,
    "validation_state": "VALID",
    "evidence_state": "ACCEPTED_DIRECT_EVIDENCE",
    "duplicate_conflict_state": "CLEAR",
    "source_reliability": "CURATED",
    "risk_tier": "low",
    "rationale": "Deterministic test assessment for AI authority.",
}


def _auth_headers(
    *,
    user_id: UUID,
    email: str,
    role: UserRole,
    graph_admin: bool = False,
    graph_ai_principal: str | None = None,
    graph_service_capabilities: tuple[str, ...] | list[str] | None = None,
) -> dict[str, str]:
    return build_graph_auth_headers(
        user_id=user_id,
        email=email,
        role=role,
        graph_admin=graph_admin,
        graph_ai_principal=graph_ai_principal,
        graph_service_capabilities=graph_service_capabilities,
    )


def _build_projection_materializer(
    session,
) -> KernelRelationProjectionMaterializationService:
    return KernelRelationProjectionMaterializationService(
        relation_repo=_build_relation_repository(session),
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
        claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
        entity_repo=SqlAlchemyKernelEntityRepository(
            session,
            phi_encryption_service=None,
            enable_phi_encryption=False,
        ),
        dictionary_repo=SqlAlchemyDictionaryRepository(
            session,
            builtin_domain_contexts=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG.builtin_domain_contexts,
        ),
        relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
        read_model_update_dispatcher=NullGraphReadModelUpdateDispatcher(),
    )


def _build_relation_repository(session) -> SqlAlchemyKernelRelationRepository:
    return SqlAlchemyKernelRelationRepository(
        session,
        auto_promotion_policy=AutoPromotionPolicy(),
    )


def _create_claim_backed_projection(
    session,
    *,
    space_id: UUID,
    source_id: UUID,
    target_id: UUID,
    source_document_id: UUID | None = None,
    source_document_ref: str | None = None,
) -> tuple[UUID, UUID]:
    claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
    participant_repo = SqlAlchemyKernelClaimParticipantRepository(session)
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(session)
    materializer = _build_projection_materializer(session)

    claim = claim_repo.create(
        research_space_id=str(space_id),
        source_document_id=(
            str(source_document_id) if source_document_id is not None else None
        ),
        source_document_ref=source_document_ref,
        agent_run_id="graph-service-test",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Developmental delay",
        confidence=0.88,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="RESOLVED",
        polarity="SUPPORT",
        claim_text="MED13 is associated with developmental delay.",
        claim_section="results",
        linked_relation_id=None,
        metadata={},
    )
    claim_id = str(claim.id)
    participant_repo.create(
        claim_id=claim_id,
        research_space_id=str(space_id),
        role="SUBJECT",
        label="MED13",
        entity_id=str(source_id),
        position=0,
        qualifiers={},
    )
    participant_repo.create(
        claim_id=claim_id,
        research_space_id=str(space_id),
        role="OBJECT",
        label="Developmental delay",
        entity_id=str(target_id),
        position=1,
        qualifiers={},
    )
    claim_evidence_repo.create(
        claim_id=claim_id,
        source_document_id=(
            str(source_document_id) if source_document_id is not None else None
        ),
        source_document_ref=source_document_ref,
        agent_run_id="graph-service-test",
        sentence="MED13 is associated with developmental delay.",
        sentence_source="verbatim_span",
        sentence_confidence="high",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.88,
        metadata={
            "evidence_summary": "Curated claim-backed support evidence",
            "evidence_tier": "LITERATURE",
        },
    )
    relation = materializer.materialize_support_claim(
        claim_id=claim_id,
        research_space_id=str(space_id),
        projection_origin="CLAIM_RESOLUTION",
    ).relation
    assert relation is not None
    session.commit()
    return UUID(claim_id), UUID(str(relation.id))


def _ensure_test_variable_definition(session) -> None:
    dictionary_repository = SqlAlchemyDictionaryRepository(
        session,
        builtin_domain_contexts=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG.builtin_domain_contexts,
    )
    if session.get(DictionaryDomainContextModel, "general") is None:
        session.add(
            DictionaryDomainContextModel(
                id="general",
                display_name="General",
                description="Graph service test domain context",
            ),
        )
        session.flush()
    if dictionary_repository.get_variable("VAR_TEST_NOTE") is not None:
        return
    dictionary_repository.create_variable(
        variable_id="VAR_TEST_NOTE",
        canonical_name="test_note",
        display_name="Test Note",
        data_type="STRING",
        domain_context="general",
        sensitivity="INTERNAL",
        constraints={},
        description="Graph service observation test variable",
        created_by="manual:graph-service-test",
        source_ref="test:graph-service",
    )
    session.flush()


def _create_provenance_record(
    session,
    *,
    space_id: UUID,
    source_type: str = "PUBMED",
) -> UUID:
    provenance_id = uuid4()
    session.add(
        ProvenanceModel(
            id=provenance_id,
            research_space_id=space_id,
            source_type=source_type,
            source_ref="pmid:123456",
            extraction_run_id="graph-service-provenance-test",
            mapping_method="manual",
            mapping_confidence=0.94,
            agent_model="gpt-5",
            raw_input={"title": "Graph provenance fixture"},
        ),
    )
    session.commit()
    return provenance_id


def _create_source_document_reference(
    session,
    *,
    space_id: UUID,
) -> UUID:
    source_id = uuid4()
    document_id = uuid4()
    _seed_platform_source_document_prerequisites(
        session,
        space_id=space_id,
        source_id=source_id,
    )
    session.add(
        SourceDocumentModel(
            id=str(document_id),
            research_space_id=str(space_id),
            source_id=str(source_id),
            ingestion_job_id=None,
            external_record_id="PMID:123456",
            source_type="pubmed",
            document_format=DocumentFormatEnum.TEXT.value,
            raw_storage_key=None,
            enriched_storage_key=None,
            content_hash=None,
            content_length_chars=1024,
            enrichment_status=EnrichmentStatusEnum.ENRICHED.value,
            enrichment_method=None,
            enrichment_agent_run_id=None,
            extraction_status=DocumentExtractionStatusEnum.EXTRACTED.value,
            extraction_agent_run_id="graph-service-paper-view",
            metadata_payload={"title": "MED13 and cardiomyopathy"},
        ),
    )
    session.commit()
    return document_id


def _seed_platform_source_document_prerequisites(
    session,
    *,
    space_id: UUID,
    source_id: UUID,
) -> None:
    bind = session.bind
    if bind is None or bind.dialect.name != "postgresql":
        return

    inspector = sa.inspect(bind)
    if not inspector.has_table("source_documents", schema="public"):
        public_metadata = sa.MetaData()
        SourceDocumentModel.__table__.to_metadata(
            public_metadata,
            schema="public",
        )
        public_metadata.create_all(bind=bind)
        return

    source_document_fk_targets = {
        foreign_key["referred_table"]
        for foreign_key in inspector.get_foreign_keys(
            "source_documents",
            schema="public",
        )
        if foreign_key.get("referred_table")
    }
    if "research_spaces" not in source_document_fk_targets:
        return

    metadata = sa.MetaData()
    users = sa.Table("users", metadata, schema="public", autoload_with=bind)
    research_spaces = sa.Table(
        "research_spaces",
        metadata,
        schema="public",
        autoload_with=bind,
    )
    user_data_sources = sa.Table(
        "user_data_sources",
        metadata,
        schema="public",
        autoload_with=bind,
    )

    owner_id = str(uuid4())
    now = datetime.now(UTC)
    session.execute(
        users.insert().values(
            id=owner_id,
            email=f"paper-view-{uuid4().hex[:12]}@example.org",
            username=f"paper-view-{uuid4().hex[:12]}",
            full_name="Graph Paper View Owner",
            hashed_password="graph-paper-view-test-hash",
            role="RESEARCHER",
            status="ACTIVE",
            email_verified=True,
            email_verification_token=None,
            password_reset_token=None,
            password_reset_expires=None,
            last_login=None,
            login_attempts=0,
            locked_until=None,
            created_at=now,
            updated_at=now,
        ),
    )
    session.execute(
        research_spaces.insert().values(
            id=str(space_id),
            slug=f"paper-view-{uuid4().hex[:12]}",
            name="Graph Paper View Space",
            description="Shared document-store fixture for graph paper view",
            owner_id=owner_id,
            status="active",
            settings={},
            tags=[],
            created_at=now,
            updated_at=now,
        ),
    )
    session.execute(
        user_data_sources.insert().values(
            id=str(source_id),
            owner_id=owner_id,
            research_space_id=str(space_id),
            name="Graph Paper View Source",
            description="Shared document-store fixture source",
            source_type="pubmed",
            template_id=None,
            configuration={},
            status="active",
            ingestion_schedule={},
            quality_metrics={},
            last_ingested_at=None,
            tags=[],
            version="1.0",
        ),
    )


def _create_graph_space_registry_entry(
    session,
    *,
    space_id: UUID,
    owner_id: UUID,
    slug: str,
    name: str,
    description: str,
    settings: dict[str, object] | None = None,
) -> None:
    session.add(
        GraphSpaceModel(
            id=space_id,
            slug=slug,
            name=name,
            description=description,
            owner_id=owner_id,
            status=GraphSpaceStatusEnum.ACTIVE,
            settings=settings or {},
        ),
    )


def _rebuild_entity_neighbors_read_model(*, space_id: UUID) -> int:
    with graph_database.SessionLocal() as session:
        projector = KernelEntityNeighborsProjector(session)
        rebuilt_rows = projector.rebuild(space_id=str(space_id))
        session.commit()
        return rebuilt_rows


def _create_claim(
    session,
    *,
    space_id: UUID,
    source_id: UUID,
    target_id: UUID,
    source_document_id: UUID | None = None,
    source_document_ref: str | None = None,
    claim_status: str = "OPEN",
    polarity: str = "SUPPORT",
    relation_type: str = "ASSOCIATED_WITH",
    claim_text: str = "MED13 is associated with developmental delay.",
    agent_run_id: str = "graph-service-test",
) -> UUID:
    claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
    participant_repo = SqlAlchemyKernelClaimParticipantRepository(session)
    claim_evidence_repo = SqlAlchemyKernelClaimEvidenceRepository(session)
    claim = claim_repo.create(
        research_space_id=str(space_id),
        source_document_id=(
            str(source_document_id) if source_document_id is not None else None
        ),
        source_document_ref=source_document_ref,
        agent_run_id=agent_run_id,
        source_type="GENE",
        relation_type=relation_type,
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Developmental delay",
        confidence=0.88,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status=claim_status,
        polarity=polarity,
        claim_text=claim_text,
        claim_section="results",
        linked_relation_id=None,
        metadata={},
    )
    claim_id = str(claim.id)
    participant_repo.create(
        claim_id=claim_id,
        research_space_id=str(space_id),
        role="SUBJECT",
        label="MED13",
        entity_id=str(source_id),
        position=0,
        qualifiers={},
    )
    participant_repo.create(
        claim_id=claim_id,
        research_space_id=str(space_id),
        role="OBJECT",
        label="Developmental delay",
        entity_id=str(target_id),
        position=1,
        qualifiers={},
    )
    claim_evidence_repo.create(
        claim_id=claim_id,
        source_document_id=(
            str(source_document_id) if source_document_id is not None else None
        ),
        source_document_ref=source_document_ref,
        agent_run_id=agent_run_id,
        sentence=claim_text,
        sentence_source="verbatim_span",
        sentence_confidence="high",
        sentence_rationale=None,
        figure_reference=None,
        table_reference=None,
        confidence=0.88,
        metadata={
            "evidence_summary": "Curated claim-backed support evidence",
            "evidence_tier": "LITERATURE",
        },
    )
    session.commit()
    return UUID(claim_id)


def _create_claim_without_participants(
    session,
    *,
    space_id: UUID,
    source_id: UUID,
    target_id: UUID,
    claim_text: str,
) -> UUID:
    claim_repo = SqlAlchemyKernelRelationClaimRepository(session)
    claim = claim_repo.create(
        research_space_id=str(space_id),
        source_document_id=None,
        agent_run_id="graph-service-backfill-test",
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        source_label="MED13",
        target_label="Developmental delay",
        confidence=0.88,
        validation_state="ALLOWED",
        validation_reason=None,
        persistability="PERSISTABLE",
        claim_status="OPEN",
        polarity="SUPPORT",
        claim_text=claim_text,
        claim_section="results",
        linked_relation_id=None,
        metadata={
            "source_entity_id": str(source_id),
            "target_entity_id": str(target_id),
        },
    )
    session.commit()
    return UUID(str(claim.id))


def _create_hypothesis_claim(
    session,
    *,
    space_id: UUID,
    claim_text: str,
    metadata: dict[str, object] | None = None,
):
    claim_service = KernelRelationClaimService(
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        read_model_update_dispatcher=NullGraphReadModelUpdateDispatcher(),
    )
    claim = claim_service.create_hypothesis_claim(
        research_space_id=str(space_id),
        source_type="HYPOTHESIS",
        relation_type="PROPOSES",
        target_type="HYPOTHESIS",
        source_label="Manual hypothesis",
        target_label=None,
        confidence=0.5,
        validation_state="UNDEFINED",
        validation_reason="test_hypothesis",
        persistability="NON_PERSISTABLE",
        claim_text=claim_text,
        metadata=metadata or {"origin": "manual"},
        claim_status="OPEN",
    )
    session.commit()
    return claim


@pytest.fixture(scope="function")
def graph_client() -> TestClient:
    reset_database(graph_database.engine, Base.metadata)
    with TestClient(create_app()) as client:
        yield client
    reset_database(graph_database.engine, Base.metadata)


def _seed_space_with_projection() -> dict[str, object]:
    suffix = uuid4().hex[:12]
    user_id = uuid4()
    space_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()

    with graph_database.SessionLocal() as session:
        _create_graph_space_registry_entry(
            session,
            space_id=space_id,
            owner_id=user_id,
            slug=f"graph-space-{suffix}",
            name="Graph Space",
            description="Standalone graph service test space",
        )
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        _ensure_test_variable_definition(session)
        session.add_all(
            [
                EntityModel(
                    id=source_id,
                    research_space_id=space_id,
                    entity_type="GENE",
                    display_label="MED13",
                    metadata_payload={},
                ),
                EntityModel(
                    id=target_id,
                    research_space_id=space_id,
                    entity_type="PHENOTYPE",
                    display_label="Developmental delay",
                    metadata_payload={},
                ),
            ],
        )
        _ensure_test_variable_definition(session)
        session.commit()
        _, relation_id = _create_claim_backed_projection(
            session,
            space_id=space_id,
            source_id=source_id,
            target_id=target_id,
        )

    return {
        "headers": _auth_headers(
            user_id=user_id,
            email=f"graph-owner-{suffix}@example.com",
            role=UserRole.RESEARCHER,
        ),
        "owner_id": user_id,
        "space_id": space_id,
        "source_id": source_id,
        "target_id": target_id,
        "relation_id": relation_id,
    }


def _seed_space_with_open_claims(*, claim_count: int = 1) -> dict[str, object]:
    suffix = uuid4().hex[:12]
    user_id = uuid4()
    space_id = uuid4()
    source_id = uuid4()
    target_id = uuid4()
    claim_ids: list[UUID] = []

    with graph_database.SessionLocal() as session:
        if session.get(DictionaryDomainContextModel, "general") is None:
            session.add(
                DictionaryDomainContextModel(
                    id="general",
                    display_name="General",
                    description="Graph service test domain context",
                ),
            )
            session.flush()
        _create_graph_space_registry_entry(
            session,
            space_id=space_id,
            owner_id=user_id,
            slug=f"graph-claims-{suffix}",
            name="Graph Claims Space",
            description="Standalone graph service claim test space",
        )
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        session.add_all(
            [
                EntityModel(
                    id=source_id,
                    research_space_id=space_id,
                    entity_type="GENE",
                    display_label="MED13",
                    metadata_payload={},
                ),
                EntityModel(
                    id=target_id,
                    research_space_id=space_id,
                    entity_type="PHENOTYPE",
                    display_label="Developmental delay",
                    metadata_payload={},
                ),
            ],
        )
        session.commit()
        claim_ids.extend(
            _create_claim(
                session,
                space_id=space_id,
                source_id=source_id,
                target_id=target_id,
                claim_text=(
                    "MED13 is associated with developmental delay."
                    if index == 0
                    else "Independent evidence also links MED13 to developmental delay."
                ),
                agent_run_id=f"graph-service-claim-{index}",
            )
            for index in range(claim_count)
        )

    return {
        "headers": _auth_headers(
            user_id=user_id,
            email=f"graph-curator-{suffix}@example.com",
            role=UserRole.RESEARCHER,
        ),
        "owner_id": user_id,
        "space_id": space_id,
        "source_id": source_id,
        "target_id": target_id,
        "claim_ids": claim_ids,
    }


def _add_space_member(
    *,
    space_id: UUID,
    role: GraphSpaceMembershipRoleEnum,
) -> dict[str, object]:
    suffix = uuid4().hex[:12]
    user_id = uuid4()

    with graph_database.SessionLocal() as session:
        session.add(
            GraphSpaceMembershipModel(
                id=uuid4(),
                space_id=space_id,
                user_id=user_id,
                role=role,
                is_active=True,
            ),
        )
        session.commit()

    return {
        "user_id": user_id,
        "headers": _auth_headers(
            user_id=user_id,
            email=f"graph-member-{suffix}@example.com",
            role=UserRole.RESEARCHER,
        ),
    }


def _seed_space_with_unresolved_claim() -> dict[str, object]:
    fixture = _seed_space_with_open_claims(claim_count=0)
    with graph_database.SessionLocal() as session:
        claim_id = _create_claim_without_participants(
            session,
            space_id=fixture["space_id"],
            source_id=fixture["source_id"],
            target_id=fixture["target_id"],
            claim_text="Metadata-only claim for participant backfill.",
        )
    fixture["claim_ids"] = [claim_id]
    return fixture


def _create_admin_headers() -> dict[str, str]:
    admin_id = uuid4()
    admin_email = f"graph-admin-{uuid4().hex[:12]}@example.com"
    return _auth_headers(
        user_id=admin_id,
        email=admin_email,
        role=UserRole.VIEWER,
        graph_admin=True,
    )


def _create_space_sync_headers() -> dict[str, str]:
    sync_user_id = uuid4()
    sync_user_email = f"graph-space-sync-{uuid4().hex[:12]}@example.com"
    return _auth_headers(
        user_id=sync_user_id,
        email=sync_user_email,
        role=UserRole.RESEARCHER,
        graph_service_capabilities=("space_sync",),
    )


def _create_graph_space_via_admin_api(
    client: TestClient,
    *,
    admin_headers: dict[str, str],
    space_id: UUID,
    owner_id: UUID,
    slug: str,
) -> None:
    response = client.put(
        f"/v1/admin/spaces/{space_id}",
        headers=admin_headers,
        json={
            "slug": slug,
            "name": "Graph Pack Seed Test Space",
            "description": "Service-owned graph space for pack seed tests",
            "owner_id": str(owner_id),
            "status": "active",
            "settings": {},
        },
    )
    assert response.status_code == 200, response.text


def test_graph_service_health_endpoint(graph_client: TestClient) -> None:
    response = graph_client.get("/health")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["version"] == GRAPH_SERVICE_VERSION


def test_graph_service_uses_biomedical_pack_http_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "biomedical")
    reset_database(graph_database.engine, Base.metadata)

    try:
        with TestClient(create_app()) as client:
            admin_headers = _create_admin_headers()
            suffix = uuid4().hex[:12].upper()
            entity_type_id = f"ET_CLINICAL_{suffix}"

            create_response = client.post(
                "/v1/dictionary/entity-types",
                headers=admin_headers,
                json={
                    "id": entity_type_id,
                    "display_name": f"Clinical Entity {suffix}",
                    "description": "Proof that the biomedical pack seeds clinical domain contexts.",
                    "domain_context": "clinical",
                    "expected_properties": {},
                    "source_ref": "graph-phase2-biomedical-pack-check",
                },
            )
            assert create_response.status_code == 201, create_response.text

            by_domain_response = client.get(
                "/v1/dictionary/search/by-domain/clinical",
                headers=admin_headers,
                params={"limit": 25},
            )
            assert by_domain_response.status_code == 200, by_domain_response.text
            clinical_entry_ids = {
                entry["entry_id"] for entry in by_domain_response.json()["results"]
            }
            assert entity_type_id in clinical_entry_ids

            fixture = _seed_space_with_projection()
            graph_view_response = client.get(
                f"/v1/spaces/{fixture['space_id']}/graph/views/gene/{fixture['source_id']}",
                headers=fixture["headers"],
            )
            assert graph_view_response.status_code == 200, graph_view_response.text
            graph_view_payload = graph_view_response.json()
            assert graph_view_payload["view_type"] == "gene"
            assert graph_view_payload["entity"]["id"] == str(fixture["source_id"])
    finally:
        reset_database(graph_database.engine, Base.metadata)


def test_graph_service_uses_sports_pack_domain_contexts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")
    reset_database(graph_database.engine, Base.metadata)

    try:
        with TestClient(create_app()) as client:
            admin_headers = _create_admin_headers()
            suffix = uuid4().hex[:12].upper()
            entity_type_id = f"ET_COMPETITION_{suffix}"

            create_response = client.post(
                "/v1/dictionary/entity-types",
                headers=admin_headers,
                json={
                    "id": entity_type_id,
                    "display_name": f"Competition Entity {suffix}",
                    "description": "Proof that the sports pack seeds competition domain contexts.",
                    "domain_context": "competition",
                    "expected_properties": {},
                    "source_ref": "graph-phase7-sports-pack-check",
                },
            )
            assert create_response.status_code == 201, create_response.text

            active_pack_response = client.get("/v1/domain-packs/active")
            assert active_pack_response.status_code == 200, active_pack_response.text
            active_pack_payload = active_pack_response.json()
            assert active_pack_payload["name"] == "sports"
            assert active_pack_payload["version"] == "1.0.0"
            assert "competition" in active_pack_payload["domain_contexts"]
            assert "TEAM" in active_pack_payload["entity_types"]

            sports_pack_response = client.get("/v1/domain-packs/sports")
            assert sports_pack_response.status_code == 200, sports_pack_response.text
            sports_pack_payload = sports_pack_response.json()
            assert sports_pack_payload["name"] == "sports"
            assert sports_pack_payload["version"] == "1.0.0"

            missing_pack_response = client.get("/v1/domain-packs/unknown")
            assert missing_pack_response.status_code == 404, missing_pack_response.text

            by_domain_response = client.get(
                "/v1/dictionary/search/by-domain/competition",
                headers=admin_headers,
                params={"limit": 25},
            )
            assert by_domain_response.status_code == 200, by_domain_response.text
            competition_entry_ids = {
                entry["entry_id"] for entry in by_domain_response.json()["results"]
            }
            assert entity_type_id in competition_entry_ids
    finally:
        reset_database(graph_database.engine, Base.metadata)


def test_graph_service_admin_space_registry_routes(graph_client: TestClient) -> None:
    admin_headers = _create_admin_headers()
    space_id = uuid4()
    owner_id = uuid4()

    create_response = graph_client.put(
        f"/v1/admin/spaces/{space_id}",
        headers=admin_headers,
        json={
            "slug": "graph-registry-space",
            "name": "Graph Registry Space",
            "description": "Service-owned graph space registry entry",
            "owner_id": str(owner_id),
            "status": "active",
            "settings": {"review_threshold": 0.73},
        },
    )
    assert create_response.status_code == 200, create_response.text
    created_payload = create_response.json()
    assert created_payload["id"] == str(space_id)
    assert created_payload["slug"] == "graph-registry-space"
    assert created_payload["owner_id"] == str(owner_id)
    assert created_payload["settings"]["review_threshold"] == 0.73
    with graph_database.SessionLocal() as session:
        concept_sets = session.query(ConceptSetModel).filter(
            ConceptSetModel.research_space_id == space_id,
        )
        concept_members = session.query(ConceptMemberModel).filter(
            ConceptMemberModel.research_space_id == space_id,
        )
        concept_aliases = session.query(ConceptAliasModel).filter(
            ConceptAliasModel.research_space_id == space_id,
        )
        assert concept_sets.count() == 0
        assert concept_members.count() == 0
        assert concept_aliases.count() == 0
        assert (
            session.query(ConceptMemberModel)
            .filter(
                ConceptMemberModel.research_space_id == space_id,
                ConceptMemberModel.canonical_label == "MED13",
            )
            .one_or_none()
            is None
        )

    get_response = graph_client.get(
        f"/v1/admin/spaces/{space_id}",
        headers=admin_headers,
    )
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["name"] == "Graph Registry Space"

    list_response = graph_client.get(
        "/v1/admin/spaces",
        headers=admin_headers,
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["spaces"][0]["id"] == str(space_id)

    update_response = graph_client.put(
        f"/v1/admin/spaces/{space_id}",
        headers=admin_headers,
        json={
            "slug": "graph-registry-space",
            "name": "Graph Registry Space Updated",
            "description": "Updated service-owned graph space registry entry",
            "owner_id": str(owner_id),
            "status": "suspended",
            "settings": {"review_threshold": 0.91},
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated_payload = update_response.json()
    assert updated_payload["name"] == "Graph Registry Space Updated"
    assert updated_payload["status"] == "suspended"
    assert updated_payload["settings"]["review_threshold"] == 0.91
    with graph_database.SessionLocal() as session:
        assert (
            session.query(ConceptSetModel)
            .filter(ConceptSetModel.research_space_id == space_id)
            .count()
        ) == 0


def test_graph_service_pack_seed_records_version_and_is_idempotent(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    space_id = uuid4()
    owner_id = uuid4()
    _create_graph_space_via_admin_api(
        graph_client,
        admin_headers=admin_headers,
        space_id=space_id,
        owner_id=owner_id,
        slug=f"pack-seed-biomedical-{space_id.hex[:8]}",
    )

    missing_status_response = graph_client.get(
        f"/v1/domain-packs/biomedical/spaces/{space_id}/seed-status",
        headers=admin_headers,
    )
    assert missing_status_response.status_code == 404, missing_status_response.text

    first_seed_response = graph_client.post(
        f"/v1/domain-packs/biomedical/spaces/{space_id}/seed",
        headers=admin_headers,
    )
    assert first_seed_response.status_code == 200, first_seed_response.text
    first_seed_payload = first_seed_response.json()
    first_status = first_seed_payload["status"]
    assert first_seed_payload["applied"] is True
    assert first_seed_payload["operation"] == "seed"
    assert first_status["pack_name"] == "biomedical"
    assert first_status["pack_version"] == "1.0.0"
    assert first_status["status"] == "seeded"
    assert first_status["last_operation"] == "seed"
    assert first_status["seed_count"] == 1
    assert first_status["repair_count"] == 0
    assert first_status["metadata"]["space_seed"] == "biomedical_starter_concepts"
    assert "GENE" in first_status["metadata"]["entity_types"]

    with graph_database.SessionLocal() as session:
        concept_set_count = (
            session.query(ConceptSetModel)
            .filter(ConceptSetModel.research_space_id == space_id)
            .count()
        )
        concept_member_count = (
            session.query(ConceptMemberModel)
            .filter(ConceptMemberModel.research_space_id == space_id)
            .count()
        )
        concept_alias_count = (
            session.query(ConceptAliasModel)
            .filter(ConceptAliasModel.research_space_id == space_id)
            .count()
        )
    assert concept_set_count == 4
    assert concept_member_count == 15
    assert concept_alias_count == 10

    second_seed_response = graph_client.post(
        f"/v1/domain-packs/biomedical/spaces/{space_id}/seed",
        headers=admin_headers,
    )
    assert second_seed_response.status_code == 200, second_seed_response.text
    second_seed_payload = second_seed_response.json()
    assert second_seed_payload["applied"] is False
    assert second_seed_payload["operation"] == "seed"
    assert second_seed_payload["status"]["id"] == first_status["id"]
    assert second_seed_payload["status"]["seed_count"] == 1

    repair_response = graph_client.post(
        f"/v1/domain-packs/biomedical/spaces/{space_id}/repair",
        headers=admin_headers,
    )
    assert repair_response.status_code == 200, repair_response.text
    repair_payload = repair_response.json()
    assert repair_payload["applied"] is True
    assert repair_payload["operation"] == "repair"
    assert repair_payload["status"]["id"] == first_status["id"]
    assert repair_payload["status"]["last_operation"] == "repair"
    assert repair_payload["status"]["repair_count"] == 1

    status_response = graph_client.get(
        f"/v1/domain-packs/biomedical/spaces/{space_id}/seed-status",
        headers=admin_headers,
    )
    assert status_response.status_code == 200, status_response.text
    status_payload = status_response.json()
    assert status_payload["id"] == first_status["id"]
    assert status_payload["last_operation"] == "repair"
    assert status_payload["repair_count"] == 1

    with graph_database.SessionLocal() as session:
        assert (
            session.query(ConceptSetModel)
            .filter(ConceptSetModel.research_space_id == space_id)
            .count()
        ) == concept_set_count
        assert (
            session.query(ConceptMemberModel)
            .filter(ConceptMemberModel.research_space_id == space_id)
            .count()
        ) == concept_member_count
        assert (
            session.query(ConceptAliasModel)
            .filter(ConceptAliasModel.research_space_id == space_id)
            .count()
        ) == concept_alias_count


def test_graph_service_sports_pack_seed_does_not_create_biomedical_concepts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")
    reset_database(graph_database.engine, Base.metadata)

    try:
        with TestClient(create_app()) as client:
            admin_headers = _create_admin_headers()
            space_id = uuid4()
            _create_graph_space_via_admin_api(
                client,
                admin_headers=admin_headers,
                space_id=space_id,
                owner_id=uuid4(),
                slug=f"pack-seed-sports-{space_id.hex[:8]}",
            )

            seed_response = client.post(
                f"/v1/domain-packs/sports/spaces/{space_id}/seed",
                headers=admin_headers,
            )
            assert seed_response.status_code == 200, seed_response.text
            seed_payload = seed_response.json()
            status_payload = seed_payload["status"]
            assert seed_payload["applied"] is True
            assert status_payload["pack_name"] == "sports"
            assert status_payload["pack_version"] == "1.0.0"
            assert status_payload["metadata"]["space_seed"] == "none"
            assert "TEAM" in status_payload["metadata"]["entity_types"]
            assert "GENE" not in status_payload["metadata"]["entity_types"]

            with graph_database.SessionLocal() as session:
                assert (
                    session.query(ConceptSetModel)
                    .filter(ConceptSetModel.research_space_id == space_id)
                    .count()
                ) == 0
                assert (
                    session.query(ConceptMemberModel)
                    .filter(ConceptMemberModel.research_space_id == space_id)
                    .count()
                ) == 0
                assert (
                    session.query(ConceptAliasModel)
                    .filter(ConceptAliasModel.research_space_id == space_id)
                    .count()
                ) == 0
    finally:
        reset_database(graph_database.engine, Base.metadata)


def test_graph_service_admin_routes_require_graph_admin_claim(
    graph_client: TestClient,
) -> None:
    user_id = uuid4()
    user_email = f"platform-admin-only-{uuid4().hex[:12]}@example.com"

    response = graph_client.get(
        "/v1/admin/spaces",
        headers=_auth_headers(
            user_id=user_id,
            email=user_email,
            role=UserRole.ADMIN,
            graph_admin=False,
        ),
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == (
        "Graph service admin access is required for this operation"
    )


def test_graph_service_admin_routes_require_graph_admin_claim_under_sports_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")
    reset_database(graph_database.engine, Base.metadata)

    try:
        with TestClient(create_app()) as client:
            user_id = uuid4()
            user_email = f"sports-platform-admin-only-{uuid4().hex[:12]}@example.com"

            response = client.get(
                "/v1/admin/spaces",
                headers=_auth_headers(
                    user_id=user_id,
                    email=user_email,
                    role=UserRole.ADMIN,
                    graph_admin=False,
                ),
            )

            assert response.status_code == 403, response.text
            assert response.json()["detail"] == (
                "Graph service admin access is required for this operation"
            )
    finally:
        reset_database(graph_database.engine, Base.metadata)


def test_graph_service_admin_space_membership_routes(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    admin_headers = _create_admin_headers()
    member_id = uuid4()

    create_response = graph_client.put(
        f"/v1/admin/spaces/{fixture['space_id']}/memberships/{member_id}",
        headers=admin_headers,
        json={
            "role": "curator",
            "is_active": True,
        },
    )
    assert create_response.status_code == 200, create_response.text
    created_payload = create_response.json()
    assert created_payload["space_id"] == str(fixture["space_id"])
    assert created_payload["user_id"] == str(member_id)
    assert created_payload["role"] == "curator"
    assert created_payload["is_active"] is True

    list_response = graph_client.get(
        f"/v1/admin/spaces/{fixture['space_id']}/memberships",
        headers=admin_headers,
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["memberships"][0]["user_id"] == str(member_id)

    update_response = graph_client.put(
        f"/v1/admin/spaces/{fixture['space_id']}/memberships/{member_id}",
        headers=admin_headers,
        json={
            "role": "viewer",
            "is_active": False,
        },
    )
    assert update_response.status_code == 200, update_response.text
    updated_payload = update_response.json()
    assert updated_payload["role"] == "viewer"
    assert updated_payload["is_active"] is False


def test_graph_service_space_sync_route_requires_space_sync_capability(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    fixture = _seed_space_with_projection()

    response = graph_client.post(
        f"/v1/admin/spaces/{fixture['space_id']}/sync",
        headers=admin_headers,
        json={
            "slug": "graph-sync-space",
            "name": "Graph Sync Space",
            "description": "Atomic graph sync",
            "owner_id": str(fixture["owner_id"]),
            "status": "active",
            "settings": {"review_threshold": 0.88},
            "memberships": [],
        },
    )

    assert response.status_code == 403, response.text
    assert response.json()["detail"] == (
        "Graph service space_sync capability is required for this operation"
    )


def test_graph_service_space_sync_route(
    graph_client: TestClient,
) -> None:
    sync_headers = _create_space_sync_headers()
    fixture = _seed_space_with_projection()
    synced_member_id = uuid4()

    response = graph_client.post(
        f"/v1/admin/spaces/{fixture['space_id']}/sync",
        headers=sync_headers,
        json={
            "slug": "graph-sync-space",
            "name": "Graph Sync Space",
            "description": "Atomic graph sync",
            "owner_id": str(fixture["owner_id"]),
            "status": "active",
            "settings": {"review_threshold": 0.88},
            "memberships": [
                {
                    "user_id": str(synced_member_id),
                    "role": "researcher",
                    "is_active": True,
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["space"]["id"] == str(fixture["space_id"])
    assert payload["space"]["slug"] == "graph-sync-space"
    assert payload["space"]["settings"]["review_threshold"] == 0.88
    assert payload["space"]["sync_source"] == "platform_control_plane"
    assert payload["space"]["sync_fingerprint"] is not None
    assert payload["space"]["last_synced_at"] is not None
    assert payload["total_memberships"] == 1
    assert payload["applied"] is True
    assert payload["memberships"][0]["user_id"] == str(synced_member_id)
    assert payload["memberships"][0]["role"] == "researcher"
    with graph_database.SessionLocal() as session:
        assert (
            session.query(ConceptSetModel)
            .filter(ConceptSetModel.research_space_id == fixture["space_id"])
            .count()
        ) == 0


def test_graph_service_admin_space_sync_route_is_idempotent_for_same_fingerprint(
    graph_client: TestClient,
) -> None:
    sync_headers = _create_space_sync_headers()
    fixture = _seed_space_with_projection()
    payload = {
        "slug": "graph-sync-space",
        "name": "Graph Sync Space",
        "description": "Atomic graph sync",
        "owner_id": str(fixture["owner_id"]),
        "status": "active",
        "settings": {"review_threshold": 0.88},
        "sync_fingerprint": "same-sync-fingerprint",
        "memberships": [],
    }

    first_response = graph_client.post(
        f"/v1/admin/spaces/{fixture['space_id']}/sync",
        headers=sync_headers,
        json=payload,
    )
    assert first_response.status_code == 200, first_response.text
    assert first_response.json()["applied"] is True

    second_response = graph_client.post(
        f"/v1/admin/spaces/{fixture['space_id']}/sync",
        headers=sync_headers,
        json=payload,
    )
    assert second_response.status_code == 200, second_response.text
    second_payload = second_response.json()
    assert second_payload["applied"] is False
    assert second_payload["space"]["sync_fingerprint"] == "same-sync-fingerprint"


def test_graph_service_admin_space_sync_replaces_stale_space_with_same_slug(
    graph_client: TestClient,
) -> None:
    sync_headers = _create_space_sync_headers()
    stale_space_id = uuid4()
    replacement_space_id = uuid4()
    owner_id = uuid4()
    stale_member_id = uuid4()
    replacement_member_id = uuid4()

    with graph_database.SessionLocal() as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        session.add(
            GraphSpaceModel(
                id=stale_space_id,
                slug="graph-sync-space",
                name="Stale Graph Sync Space",
                description="Outdated graph snapshot",
                owner_id=owner_id,
                status=GraphSpaceStatusEnum.ACTIVE,
                settings={},
            ),
        )
        session.flush()
        session.add(
            GraphSpaceMembershipModel(
                id=uuid4(),
                space_id=stale_space_id,
                user_id=stale_member_id,
                role=GraphSpaceMembershipRoleEnum.RESEARCHER,
                is_active=True,
            ),
        )
        seed_biomedical_starter_concepts(session, research_space_id=stale_space_id)
        session.commit()

    response = graph_client.post(
        f"/v1/admin/spaces/{replacement_space_id}/sync",
        headers=sync_headers,
        json={
            "slug": "graph-sync-space",
            "name": "Graph Sync Space",
            "description": "Replacement graph snapshot",
            "owner_id": str(owner_id),
            "status": "active",
            "settings": {"review_threshold": 0.92},
            "memberships": [
                {
                    "user_id": str(replacement_member_id),
                    "role": "researcher",
                    "is_active": True,
                },
            ],
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["applied"] is True
    assert payload["space"]["id"] == str(replacement_space_id)
    assert payload["space"]["slug"] == "graph-sync-space"

    with graph_database.SessionLocal() as session:
        assert session.get(GraphSpaceModel, stale_space_id) is None
        assert session.get(GraphSpaceModel, replacement_space_id) is not None
        assert (
            session.query(GraphSpaceMembershipModel)
            .filter(GraphSpaceMembershipModel.space_id == stale_space_id)
            .count()
        ) == 0
        assert (
            session.query(GraphSpaceMembershipModel)
            .filter(GraphSpaceMembershipModel.space_id == replacement_space_id)
            .count()
        ) == 1
        assert (
            session.query(ConceptSetModel)
            .filter(ConceptSetModel.research_space_id == stale_space_id)
            .count()
        ) == 0
        assert (
            session.query(ConceptSetModel)
            .filter(ConceptSetModel.research_space_id == replacement_space_id)
            .count()
        ) == 0


def test_graph_service_admin_space_sync_recovers_from_missed_slug_conflict(
    caplog: pytest.LogCaptureFixture,
) -> None:
    sync_headers = _create_space_sync_headers()
    stale_space_id = uuid4()
    replacement_space_id = uuid4()
    owner_id = uuid4()
    stale_member_id = uuid4()
    replacement_member_id = uuid4()

    with graph_database.SessionLocal() as session:
        seed_entity_resolution_policies(session)
        seed_relation_constraints(session)
        session.add(
            GraphSpaceModel(
                id=stale_space_id,
                slug="graph-sync-space",
                name="Stale Graph Sync Space",
                description="Outdated graph snapshot",
                owner_id=owner_id,
                status=GraphSpaceStatusEnum.ACTIVE,
                settings={},
            ),
        )
        session.flush()
        session.add(
            GraphSpaceMembershipModel(
                id=uuid4(),
                space_id=stale_space_id,
                user_id=stale_member_id,
                role=GraphSpaceMembershipRoleEnum.RESEARCHER,
                is_active=True,
            ),
        )
        seed_biomedical_starter_concepts(session, research_space_id=stale_space_id)
        session.commit()

    class _MissedSlugConflictRegistry(SqlAlchemyKernelSpaceRegistryRepository):
        def __init__(self, session) -> None:
            super().__init__(session)
            self._miss_next_slug_lookup = True

        def get_by_slug(self, slug: str):
            if self._miss_next_slug_lookup:
                self._miss_next_slug_lookup = False
                return None
            return super().get_by_slug(slug)

    app = create_app()

    def _override_space_registry(session=_TEST_SESSION_DEPENDENCY):
        return _MissedSlugConflictRegistry(session)

    app.dependency_overrides[get_space_registry_port] = _override_space_registry

    with (
        TestClient(app) as client,
        caplog.at_level(logging.WARNING, logger="artana_evidence_db.routers.spaces"),
    ):
        response = client.post(
            f"/v1/admin/spaces/{replacement_space_id}/sync",
            headers=sync_headers,
            json={
                "slug": "graph-sync-space",
                "name": "Graph Sync Space",
                "description": "Replacement graph snapshot",
                "owner_id": str(owner_id),
                "status": "active",
                "settings": {"review_threshold": 0.92},
                "memberships": [
                    {
                        "user_id": str(replacement_member_id),
                        "role": "researcher",
                        "is_active": True,
                    },
                ],
            },
        )

    app.dependency_overrides.clear()

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["applied"] is True
    assert payload["space"]["id"] == str(replacement_space_id)
    assert payload["space"]["slug"] == "graph-sync-space"
    warning_records = [
        record
        for record in caplog.records
        if record.name == "artana_evidence_db.routers.spaces"
        and record.getMessage()
        == "Recovered graph-space sync from slug uniqueness conflict"
    ]
    assert warning_records
    warning_record = warning_records[-1]
    assert warning_record.slug == "graph-sync-space"
    assert warning_record.replacement_space_id == str(replacement_space_id)
    assert warning_record.purged_space_id == str(stale_space_id)

    with graph_database.SessionLocal() as session:
        assert session.get(GraphSpaceModel, stale_space_id) is None
        assert session.get(GraphSpaceModel, replacement_space_id) is not None
        assert (
            session.query(GraphSpaceMembershipModel)
            .filter(GraphSpaceMembershipModel.space_id == stale_space_id)
            .count()
        ) == 0
        assert (
            session.query(GraphSpaceMembershipModel)
            .filter(GraphSpaceMembershipModel.space_id == replacement_space_id)
            .count()
        ) == 1


def test_graph_service_relation_reads(graph_client: TestClient) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    relation_id = fixture["relation_id"]

    relations_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=headers,
    )
    assert relations_response.status_code == 200, relations_response.text
    relations_payload = relations_response.json()
    assert relations_payload["total"] == 1
    assert relations_payload["relations"][0]["id"] == str(relation_id)

    subgraph_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph/subgraph",
        headers=headers,
        json={
            "mode": "seeded",
            "seed_entity_ids": [str(source_id)],
            "depth": 1,
            "top_k": 10,
            "max_nodes": 20,
            "max_edges": 20,
        },
    )
    assert subgraph_response.status_code == 200, subgraph_response.text
    subgraph_payload = subgraph_response.json()
    assert len(subgraph_payload["nodes"]) == 2
    assert len(subgraph_payload["edges"]) == 1

    neighborhood_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph/neighborhood/{source_id}",
        headers=headers,
        params={"depth": 1},
    )
    assert neighborhood_response.status_code == 200, neighborhood_response.text
    neighborhood_payload = neighborhood_response.json()
    assert len(neighborhood_payload["nodes"]) == 2
    assert len(neighborhood_payload["edges"]) == 1

    export_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph/export",
        headers=headers,
    )
    assert export_response.status_code == 200, export_response.text
    export_payload = export_response.json()
    assert len(export_payload["nodes"]) == 2
    assert len(export_payload["edges"]) == 1

    document_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph/document",
        headers=headers,
        json={
            "mode": "seeded",
            "seed_entity_ids": [str(source_id)],
            "depth": 1,
            "top_k": 10,
            "max_nodes": 20,
            "max_edges": 20,
            "include_claims": True,
            "include_evidence": True,
            "max_claims": 10,
            "evidence_limit_per_claim": 2,
        },
    )
    assert document_response.status_code == 200, document_response.text
    document_payload = document_response.json()
    assert document_payload["meta"]["counts"]["entity_nodes"] == 2
    assert document_payload["meta"]["counts"]["claim_nodes"] >= 1
    assert document_payload["meta"]["counts"]["evidence_nodes"] >= 1
    assert any(node["kind"] == "CLAIM" for node in document_payload["nodes"])
    assert any(node["kind"] == "EVIDENCE" for node in document_payload["nodes"])
    assert any(
        edge["kind"] == "CANONICAL_RELATION" for edge in document_payload["edges"]
    )


def test_graph_service_uses_biomedical_pack_entity_neighbors_read_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "biomedical")
    reset_database(graph_database.engine, Base.metadata)

    try:
        fixture = _seed_space_with_projection()
        rebuilt_rows = _rebuild_entity_neighbors_read_model(
            space_id=fixture["space_id"],
        )
        assert rebuilt_rows >= 2

        with graph_database.SessionLocal() as session:
            indexed_rows = list(
                session.query(EntityNeighborModel)
                .filter(EntityNeighborModel.entity_id == fixture["source_id"])
                .all(),
            )
        assert indexed_rows

        with TestClient(create_app()) as client:
            neighborhood_response = client.get(
                f"/v1/spaces/{fixture['space_id']}/graph/neighborhood/{fixture['source_id']}",
                headers=fixture["headers"],
                params={"depth": 1},
            )
            assert neighborhood_response.status_code == 200, neighborhood_response.text
            neighborhood_payload = neighborhood_response.json()
            assert len(neighborhood_payload["nodes"]) == 2
            assert len(neighborhood_payload["edges"]) == 1
    finally:
        reset_database(graph_database.engine, Base.metadata)


def test_graph_service_uses_sports_pack_entity_neighbors_read_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")
    reset_database(graph_database.engine, Base.metadata)

    try:
        fixture = _seed_space_with_projection()
        rebuilt_rows = _rebuild_entity_neighbors_read_model(
            space_id=fixture["space_id"],
        )
        assert rebuilt_rows >= 2

        with graph_database.SessionLocal() as session:
            indexed_rows = list(
                session.query(EntityNeighborModel)
                .filter(EntityNeighborModel.entity_id == fixture["source_id"])
                .all(),
            )
        assert indexed_rows

        with TestClient(create_app()) as client:
            neighborhood_response = client.get(
                f"/v1/spaces/{fixture['space_id']}/graph/neighborhood/{fixture['source_id']}",
                headers=fixture["headers"],
                params={"depth": 1},
            )
            assert neighborhood_response.status_code == 200, neighborhood_response.text
            neighborhood_payload = neighborhood_response.json()
            assert len(neighborhood_payload["nodes"]) == 2
            assert len(neighborhood_payload["edges"]) == 1
    finally:
        reset_database(graph_database.engine, Base.metadata)


def test_graph_service_relation_reads_support_external_document_refs(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]
    external_document_ref = "https://example.org/papers/med13-cardiomyopathy"

    with graph_database.SessionLocal() as session:
        _create_claim_backed_projection(
            session,
            space_id=space_id,
            source_id=source_id,
            target_id=target_id,
            source_document_ref=external_document_ref,
        )

    relations_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=headers,
    )
    assert relations_response.status_code == 200, relations_response.text
    relations_payload = relations_response.json()
    assert relations_payload["total"] >= 1
    assert any(
        any(
            link["url"] == external_document_ref and link["source"] == "external_ref"
            for link in relation["paper_links"]
        )
        for relation in relations_payload["relations"]
    )

    document_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph/document",
        headers=headers,
        json={
            "mode": "seeded",
            "seed_entity_ids": [str(source_id)],
            "depth": 1,
            "top_k": 10,
            "max_nodes": 20,
            "max_edges": 20,
            "include_claims": True,
            "include_evidence": True,
            "max_claims": 10,
            "evidence_limit_per_claim": 5,
        },
    )
    assert document_response.status_code == 200, document_response.text
    document_payload = document_response.json()
    evidence_nodes = [
        node for node in document_payload["nodes"] if node["kind"] == "EVIDENCE"
    ]
    assert any(
        node["metadata"].get("source_document_ref") == external_document_ref
        for node in evidence_nodes
    )


def test_graph_service_creates_and_curates_manual_relations(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    admin_headers = _create_admin_headers()
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/relations",
        headers=admin_headers,
        json={
            "source_id": str(source_id),
            "relation_type": "ASSOCIATED_WITH",
            "target_id": str(target_id),
            "assessment": _SUPPORTED_ASSESSMENT,
            "evidence_summary": "Manual curator relation",
            "evidence_sentence": "MED13 is associated with developmental delay.",
            "evidence_sentence_source": "verbatim_span",
            "evidence_sentence_confidence": "high",
            "evidence_tier": "COMPUTATIONAL",
            "source_document_ref": "harness_proposal:proposal-1",
            "metadata": {
                "source_kind": "document_extraction",
                "source_key": "doc:0",
                "document_id": "document-1",
                "evidence_bundle": [
                    {"source_type": "paper", "locator": "document:document-1"}
                ],
            },
        },
    )
    assert create_response.status_code == 201, create_response.text
    relation_payload = create_response.json()
    relation_id = relation_payload["id"]
    claim_id = relation_payload["source_claim_id"]
    assert relation_payload["relation_type"] == "ASSOCIATED_WITH"
    assert relation_payload["source_id"] == str(source_id)
    assert relation_payload["target_id"] == str(target_id)

    claims_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims",
        headers=fixture["headers"],
        params={"claim_status": "RESOLVED", "limit": 100},
    )
    assert claims_response.status_code == 200, claims_response.text
    claim_payload = next(
        claim for claim in claims_response.json()["claims"] if claim["id"] == claim_id
    )
    assert claim_payload["source_document_ref"] == "harness_proposal:proposal-1"
    assert claim_payload["metadata"]["source_kind"] == "document_extraction"
    assert claim_payload["metadata"]["source_key"] == "doc:0"
    assert claim_payload["metadata"]["evidence_bundle"] == [
        {"source_type": "paper", "locator": "document:document-1"}
    ]

    evidence_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id}/evidence",
        headers=fixture["headers"],
    )
    assert evidence_response.status_code == 200, evidence_response.text
    evidence_payload = evidence_response.json()
    assert evidence_payload["evidence"][0]["metadata"]["source_kind"] == (
        "document_extraction"
    )

    update_response = graph_client.put(
        f"/v1/spaces/{space_id}/relations/{relation_id}",
        headers=fixture["headers"],
        json={"curation_status": "APPROVED"},
    )
    assert update_response.status_code == 200, update_response.text
    updated_payload = update_response.json()
    assert updated_payload["id"] == relation_id
    assert updated_payload["curation_status"] == "APPROVED"

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=fixture["headers"],
    )
    assert list_response.status_code == 200, list_response.text
    statuses = {
        relation["id"]: relation["curation_status"]
        for relation in list_response.json()["relations"]
    }
    assert statuses[relation_id] == "APPROVED"


def test_graph_service_lists_and_gets_provenance(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    with graph_database.SessionLocal() as session:
        provenance_id = _create_provenance_record(
            session,
            space_id=space_id,
            source_type="PUBMED",
        )

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/provenance",
        headers=headers,
        params={"source_type": "PUBMED", "offset": 0, "limit": 50},
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["provenance"][0]["id"] == str(provenance_id)
    assert list_payload["provenance"][0]["source_type"] == "PUBMED"

    record_response = graph_client.get(
        f"/v1/spaces/{space_id}/provenance/{provenance_id}",
        headers=headers,
    )
    assert record_response.status_code == 200, record_response.text
    record_payload = record_response.json()
    assert record_payload["id"] == str(provenance_id)
    assert record_payload["source_ref"] == "pmid:123456"
    assert record_payload["raw_input"]["title"] == "Graph provenance fixture"


def test_graph_service_entity_and_observation_crud(graph_client: TestClient) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        params={"type": "GENE"},
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["entities"][0]["id"] == str(source_id)

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "GENE",
            "display_label": "MED13L",
            "metadata": {"source": "graph-service-test"},
            "identifiers": {"hgnc_id": f"HGNC:{uuid4().hex[:8]}"},
        },
    )
    assert create_response.status_code == 201, create_response.text
    created_payload = create_response.json()
    created_entity_id = created_payload["entity"]["id"]
    assert created_payload["created"] is True

    get_response = graph_client.get(
        f"/v1/spaces/{space_id}/entities/{created_entity_id}",
        headers=headers,
    )
    assert get_response.status_code == 200, get_response.text
    assert get_response.json()["display_label"] == "MED13L"

    update_response = graph_client.put(
        f"/v1/spaces/{space_id}/entities/{created_entity_id}",
        headers=headers,
        json={
            "display_label": "MED13 Like",
            "metadata": {"source": "updated"},
            "identifiers": {"ensembl": "ENSG00000123066"},
        },
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["display_label"] == "MED13 Like"
    assert update_response.json()["metadata"]["source"] == "updated"

    observation_create = graph_client.post(
        f"/v1/spaces/{space_id}/observations",
        headers=headers,
        json={
            "subject_id": str(source_id),
            "variable_id": "VAR_TEST_NOTE",
            "value": "hello graph service",
            "unit": None,
            "observed_at": None,
            "provenance_id": None,
            "confidence": 1.0,
        },
    )
    assert observation_create.status_code == 201, observation_create.text
    observation_payload = observation_create.json()
    observation_id = observation_payload["id"]
    assert observation_payload["value_text"] == "hello graph service"

    observation_list = graph_client.get(
        f"/v1/spaces/{space_id}/observations",
        headers=headers,
        params={"subject_id": str(source_id)},
    )
    assert observation_list.status_code == 200, observation_list.text
    assert observation_list.json()["total"] == 1

    observation_get = graph_client.get(
        f"/v1/spaces/{space_id}/observations/{observation_id}",
        headers=headers,
    )
    assert observation_get.status_code == 200, observation_get.text
    assert observation_get.json()["id"] == observation_id

    delete_response = graph_client.delete(
        f"/v1/spaces/{space_id}/entities/{created_entity_id}",
        headers=headers,
    )
    assert delete_response.status_code == 204, delete_response.text

    missing_get = graph_client.get(
        f"/v1/spaces/{space_id}/entities/{created_entity_id}",
        headers=headers,
    )
    assert missing_get.status_code == 404, missing_get.text


def test_graph_service_normalizes_entity_type_case_for_entity_routes(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        params={"type": "gene"},
    )
    assert list_response.status_code == 200, list_response.text
    assert list_response.json()["entities"][0]["id"] == str(source_id)

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/entities",
        headers=headers,
        json={
            "entity_type": "gene",
            "display_label": "MED13 lowercase",
            "metadata": {"source": "graph-service-test"},
            "identifiers": {"hgnc_id": f"HGNC:{uuid4().hex[:8]}"},
        },
    )
    assert create_response.status_code == 201, create_response.text
    create_payload = create_response.json()
    assert create_payload["entity"]["entity_type"] == "GENE"
    assert create_payload["created"] is True


def test_graph_service_reasoning_paths_empty_list(graph_client: TestClient) -> None:
    fixture = _seed_space_with_projection()

    response = graph_client.get(
        f"/v1/spaces/{fixture['space_id']}/reasoning-paths",
        headers=fixture["headers"],
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 0
    assert payload["paths"] == []


def test_graph_service_claim_reads_and_triage_materialization(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims()
    space_id = fixture["space_id"]
    claim_id = fixture["claim_ids"][0]
    source_id = fixture["source_id"]
    headers = fixture["headers"]

    claims_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims",
        headers=headers,
        params={"claim_status": "OPEN"},
    )
    assert claims_response.status_code == 200, claims_response.text
    claims_payload = claims_response.json()
    assert claims_payload["total"] == 1
    assert claims_payload["claims"][0]["id"] == str(claim_id)

    by_entity_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/by-entity/{source_id}",
        headers=headers,
    )
    assert by_entity_response.status_code == 200, by_entity_response.text
    assert by_entity_response.json()["total"] == 1

    participants_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id}/participants",
        headers=headers,
    )
    assert participants_response.status_code == 200, participants_response.text
    participants_payload = participants_response.json()
    assert participants_payload["total"] == 2

    evidence_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id}/evidence",
        headers=headers,
    )
    assert evidence_response.status_code == 200, evidence_response.text
    evidence_payload = evidence_response.json()
    assert evidence_payload["total"] == 1
    assert evidence_payload["evidence"][0]["sentence_source"] == "verbatim_span"

    triage_response = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id}",
        headers=headers,
        json={"claim_status": "RESOLVED"},
    )
    assert triage_response.status_code == 200, triage_response.text
    triage_payload = triage_response.json()
    assert triage_payload["claim_status"] == "RESOLVED"
    assert triage_payload["linked_relation_id"] is not None

    relations_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations",
        headers=headers,
    )
    assert relations_response.status_code == 200, relations_response.text
    assert relations_response.json()["total"] == 1

    conflicts_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations/conflicts",
        headers=headers,
    )
    assert conflicts_response.status_code == 200, conflicts_response.text
    assert conflicts_response.json()["total"] == 0


def test_graph_service_claim_resolution_records_projection_lineage_idempotently(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims()
    space_id = fixture["space_id"]
    claim_id = fixture["claim_ids"][0]
    headers = fixture["headers"]

    first_response = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id}",
        headers=headers,
        json={"claim_status": "RESOLVED"},
    )
    assert first_response.status_code == 200, first_response.text
    first_payload = first_response.json()
    relation_id = first_payload["linked_relation_id"]
    assert relation_id is not None

    with graph_database.SessionLocal() as session:
        lineage_rows = SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ).find_by_relation_id(relation_id)
        assert len(lineage_rows) == 1
        assert str(lineage_rows[0].claim_id) == str(claim_id)
        assert lineage_rows[0].projection_origin == "CLAIM_RESOLUTION"

    second_response = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id}",
        headers=headers,
        json={"claim_status": "RESOLVED"},
    )
    assert second_response.status_code == 200, second_response.text
    assert second_response.json()["linked_relation_id"] == relation_id

    with graph_database.SessionLocal() as session:
        lineage_rows = SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ).find_by_relation_id(relation_id)
        assert len(lineage_rows) == 1
        assert str(lineage_rows[0].claim_id) == str(claim_id)


def test_graph_service_claim_evidence_exposes_external_document_refs(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims()
    space_id = fixture["space_id"]
    headers = fixture["headers"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]
    external_document_ref = "https://example.org/papers/claim-evidence"

    with graph_database.SessionLocal() as session:
        claim_id = _create_claim(
            session,
            space_id=space_id,
            source_id=source_id,
            target_id=target_id,
            source_document_ref=external_document_ref,
            claim_status="OPEN",
            agent_run_id="graph-service-external-ref",
        )

    evidence_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id}/evidence",
        headers=headers,
    )
    assert evidence_response.status_code == 200, evidence_response.text
    evidence_payload = evidence_response.json()
    assert evidence_payload["total"] == 1
    evidence_row = evidence_payload["evidence"][0]
    assert evidence_row["source_document_id"] is None
    assert evidence_row["source_document_ref"] == external_document_ref
    assert evidence_row["paper_links"][0]["url"] == external_document_ref
    assert evidence_row["paper_links"][0]["source"] == "external_ref"


def test_graph_service_document_seeded_renders_unlinked_claim_graph(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims()
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]
    claim_id = fixture["claim_ids"][0]
    headers = fixture["headers"]

    response = graph_client.post(
        f"/v1/spaces/{space_id}/graph/document",
        headers=headers,
        json={
            "mode": "seeded",
            "seed_entity_ids": [str(source_id)],
            "depth": 1,
            "top_k": 10,
            "max_nodes": 20,
            "max_edges": 20,
            "include_claims": True,
            "include_evidence": True,
            "max_claims": 10,
            "evidence_limit_per_claim": 2,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    counts = payload["meta"]["counts"]
    assert counts["entity_nodes"] == 2
    assert counts["claim_nodes"] == 1
    assert counts["evidence_nodes"] == 1
    assert counts["canonical_edges"] == 0
    assert counts["claim_participant_edges"] == 2
    assert counts["claim_evidence_edges"] == 1
    assert {
        node["resource_id"] for node in payload["nodes"] if node["kind"] == "ENTITY"
    } == {
        str(source_id),
        str(target_id),
    }
    assert any(
        node["kind"] == "CLAIM" and node["resource_id"] == str(claim_id)
        for node in payload["nodes"]
    )
    assert any(edge["kind"] == "CLAIM_PARTICIPANT" for edge in payload["edges"])
    assert not any(edge["kind"] == "CANONICAL_RELATION" for edge in payload["edges"])


def test_graph_service_document_starter_renders_unlinked_claim_graph(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=2)
    space_id = fixture["space_id"]
    headers = fixture["headers"]

    response = graph_client.post(
        f"/v1/spaces/{space_id}/graph/document",
        headers=headers,
        json={
            "mode": "starter",
            "depth": 1,
            "top_k": 10,
            "max_nodes": 20,
            "max_edges": 20,
            "include_claims": True,
            "include_evidence": True,
            "max_claims": 10,
            "evidence_limit_per_claim": 2,
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    counts = payload["meta"]["counts"]
    assert counts["entity_nodes"] == 2
    assert counts["claim_nodes"] == 2
    assert counts["evidence_nodes"] == 2
    assert counts["canonical_edges"] == 0
    assert counts["claim_participant_edges"] == 4
    assert counts["claim_evidence_edges"] == 2
    assert any(node["kind"] == "CLAIM" for node in payload["nodes"])
    assert any(edge["kind"] == "CLAIM_PARTICIPANT" for edge in payload["edges"])
    assert any(edge["kind"] == "CLAIM_EVIDENCE" for edge in payload["edges"])


def test_graph_service_claim_relation_write_and_review(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=2)
    space_id = fixture["space_id"]
    claim_id_a = fixture["claim_ids"][0]
    claim_id_b = fixture["claim_ids"][1]
    headers = fixture["headers"]

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claim-relations",
        headers=headers,
        json={
            "source_claim_id": str(claim_id_a),
            "target_claim_id": str(claim_id_b),
            "relation_type": "SUPPORTS",
            "assessment": _SUPPORTED_ASSESSMENT,
            "review_status": "PROPOSED",
            "evidence_summary": "Second claim supports the first one.",
            "metadata": {},
        },
    )
    assert create_response.status_code == 200, create_response.text
    relation_payload = create_response.json()
    relation_id = relation_payload["id"]
    assert relation_payload["relation_type"] == "SUPPORTS"
    assert relation_payload["review_status"] == "PROPOSED"

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/claim-relations",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["claim_relations"][0]["id"] == relation_id

    update_response = graph_client.patch(
        f"/v1/spaces/{space_id}/claim-relations/{relation_id}",
        headers=headers,
        json={"review_status": "ACCEPTED"},
    )
    assert update_response.status_code == 200, update_response.text
    assert update_response.json()["review_status"] == "ACCEPTED"


def test_graph_service_graph_views_and_mechanism_chain(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=2)
    space_id = fixture["space_id"]
    claim_id_a = fixture["claim_ids"][0]
    claim_id_b = fixture["claim_ids"][1]
    headers = fixture["headers"]

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/claim-relations",
        headers=headers,
        json={
            "source_claim_id": str(claim_id_a),
            "target_claim_id": str(claim_id_b),
            "relation_type": "CAUSES",
            "assessment": _SUPPORTED_ASSESSMENT,
            "review_status": "ACCEPTED",
            "evidence_summary": "Mechanistic chain test edge.",
            "metadata": {},
        },
    )
    assert create_response.status_code == 200, create_response.text

    view_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph/views/claim/{claim_id_a}",
        headers=headers,
    )
    assert view_response.status_code == 200, view_response.text
    view_payload = view_response.json()
    assert view_payload["view_type"] == "claim"
    assert view_payload["claim"]["id"] == str(claim_id_a)
    assert view_payload["counts"]["claims"] >= 1

    chain_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id_a}/mechanism-chain",
        headers=headers,
        params={"max_depth": 3},
    )
    assert chain_response.status_code == 200, chain_response.text
    chain_payload = chain_response.json()
    assert chain_payload["root_claim"]["id"] == str(claim_id_a)
    assert chain_payload["counts"]["claim_relations"] == 1
    assert chain_payload["counts"]["claims"] >= 2


def test_graph_service_paper_graph_view_uses_document_reference_port(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]
    headers = fixture["headers"]

    with graph_database.SessionLocal() as session:
        source_document_id = _create_source_document_reference(
            session,
            space_id=space_id,
        )
        claim_id, relation_id = _create_claim_backed_projection(
            session,
            space_id=space_id,
            source_id=source_id,
            target_id=target_id,
            source_document_id=source_document_id,
        )

    view_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph/views/paper/{source_document_id}",
        headers=headers,
        params={"claim_limit": 25},
    )
    assert view_response.status_code == 200, view_response.text
    payload = view_response.json()
    assert payload["view_type"] == "paper"
    assert payload["paper"]["id"] == str(source_document_id)
    assert payload["paper"]["source_type"] == "pubmed"
    assert payload["counts"]["claims"] >= 1
    assert any(claim["id"] == str(claim_id) for claim in payload["claims"])
    assert any(
        relation["id"] == str(relation_id)
        for relation in payload["canonical_relations"]
    )


def test_graph_service_participant_backfill_and_coverage(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_unresolved_claim()
    space_id = fixture["space_id"]
    claim_id = fixture["claim_ids"][0]
    headers = fixture["headers"]

    coverage_before = graph_client.get(
        f"/v1/spaces/{space_id}/claim-participants/coverage",
        headers=headers,
    )
    assert coverage_before.status_code == 200, coverage_before.text
    before_payload = coverage_before.json()
    assert before_payload["total_claims"] == 1
    assert before_payload["claims_with_any_participants"] == 0

    backfill_response = graph_client.post(
        f"/v1/spaces/{space_id}/claim-participants/backfill",
        headers=headers,
        json={"dry_run": False, "limit": 50, "offset": 0},
    )
    assert backfill_response.status_code == 200, backfill_response.text
    backfill_payload = backfill_response.json()
    assert UUID(backfill_payload["operation_run_id"])
    assert backfill_payload["created_participants"] == 2

    operation_history = graph_client.get(
        "/v1/admin/operations/runs",
        headers=_create_admin_headers(),
        params={"operation_type": "claim_participant_backfill"},
    )
    assert operation_history.status_code == 200, operation_history.text
    history_payload = operation_history.json()
    assert history_payload["total"] >= 1
    assert any(
        run["id"] == backfill_payload["operation_run_id"]
        and run["status"] == "succeeded"
        for run in history_payload["runs"]
    )

    coverage_after = graph_client.get(
        f"/v1/spaces/{space_id}/claim-participants/coverage",
        headers=headers,
    )
    assert coverage_after.status_code == 200, coverage_after.text
    after_payload = coverage_after.json()
    assert after_payload["claims_with_any_participants"] == 1
    assert after_payload["claims_with_subject"] == 1
    assert after_payload["claims_with_object"] == 1

    participants_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_id}/participants",
        headers=headers,
    )
    assert participants_response.status_code == 200, participants_response.text
    assert participants_response.json()["total"] == 2


def test_graph_service_admin_readiness_and_rebuild_operations(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=2)
    admin_headers = _create_admin_headers()
    space_id = fixture["space_id"]
    claim_id_a = fixture["claim_ids"][0]
    claim_id_b = fixture["claim_ids"][1]

    resolve_a = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id_a}",
        headers=fixture["headers"],
        json={"claim_status": "RESOLVED"},
    )
    assert resolve_a.status_code == 200, resolve_a.text
    resolve_b = graph_client.patch(
        f"/v1/spaces/{space_id}/claims/{claim_id_b}",
        headers=fixture["headers"],
        json={"claim_status": "RESOLVED"},
    )
    assert resolve_b.status_code == 200, resolve_b.text

    create_relation = graph_client.post(
        f"/v1/spaces/{space_id}/claim-relations",
        headers=fixture["headers"],
        json={
            "source_claim_id": str(claim_id_a),
            "target_claim_id": str(claim_id_b),
            "relation_type": "SUPPORTS",
            "assessment": _SUPPORTED_ASSESSMENT,
            "review_status": "ACCEPTED",
            "evidence_summary": "Accepted chain for rebuild.",
            "metadata": {},
        },
    )
    assert create_relation.status_code == 200, create_relation.text

    readiness_response = graph_client.get(
        "/v1/admin/projections/readiness",
        headers=admin_headers,
    )
    assert readiness_response.status_code == 200, readiness_response.text
    readiness_payload = readiness_response.json()
    assert readiness_payload["ready"] is True

    repair_response = graph_client.post(
        "/v1/admin/projections/repair",
        headers=admin_headers,
        json={"dry_run": True, "batch_limit": 100},
    )
    assert repair_response.status_code == 200, repair_response.text
    repair_payload = repair_response.json()
    assert UUID(repair_payload["operation_run_id"])

    rebuild_response = graph_client.post(
        "/v1/admin/reasoning-paths/rebuild",
        headers=admin_headers,
        json={
            "space_id": str(space_id),
            "max_depth": 4,
            "replace_existing": True,
        },
    )
    assert rebuild_response.status_code == 200, rebuild_response.text
    rebuild_payload = rebuild_response.json()
    assert UUID(rebuild_payload["operation_run_id"])
    assert len(rebuild_payload["summaries"]) == 1
    assert rebuild_payload["summaries"][0]["rebuilt_paths"] >= 1

    operations_response = graph_client.get(
        "/v1/admin/operations/runs",
        headers=admin_headers,
        params={"limit": 10, "offset": 0},
    )
    assert operations_response.status_code == 200, operations_response.text
    operations_payload = operations_response.json()
    operation_ids = {run["id"] for run in operations_payload["runs"]}
    assert rebuild_payload["operation_run_id"] in operation_ids
    assert repair_payload["operation_run_id"] in operation_ids
    readiness_run = next(
        run
        for run in operations_payload["runs"]
        if run["operation_type"] == "projection_readiness_audit"
    )
    operation_detail = graph_client.get(
        f"/v1/admin/operations/runs/{readiness_run['id']}",
        headers=admin_headers,
    )
    assert operation_detail.status_code == 200, operation_detail.text
    assert operation_detail.json()["status"] == "succeeded"

    paths_response = graph_client.get(
        f"/v1/spaces/{space_id}/reasoning-paths",
        headers=fixture["headers"],
    )
    assert paths_response.status_code == 200, paths_response.text
    assert paths_response.json()["total"] >= 1


def test_graph_service_hypothesis_list_and_manual_create(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=0)
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    headers = fixture["headers"]

    empty_response = graph_client.get(
        f"/v1/spaces/{space_id}/hypotheses",
        headers=headers,
    )
    assert empty_response.status_code == 200, empty_response.text
    assert empty_response.json()["total"] == 0

    create_response = graph_client.post(
        f"/v1/spaces/{space_id}/hypotheses/manual",
        headers=headers,
        json={
            "statement": "MED13 may modulate developmental pathways.",
            "rationale": "Observed from converging literature signals.",
            "seed_entity_ids": [str(source_id)],
            "source_type": "manual",
        },
    )
    assert create_response.status_code == 200, create_response.text
    created_payload = create_response.json()
    assert created_payload["polarity"] == "HYPOTHESIS"
    assert created_payload["origin"] == "manual"
    assert created_payload["seed_entity_ids"] == [str(source_id)]

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/hypotheses",
        headers=headers,
    )
    assert list_response.status_code == 200, list_response.text
    list_payload = list_response.json()
    assert list_payload["total"] == 1
    assert list_payload["hypotheses"][0]["claim_id"] == created_payload["claim_id"]


def test_graph_service_enforces_space_membership(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    outsider_id = uuid4()
    outsider_email = f"outsider-{uuid4().hex[:12]}@example.com"

    response = graph_client.get(
        f"/v1/spaces/{fixture['space_id']}/relations",
        headers=_auth_headers(
            user_id=outsider_id,
            email=outsider_email,
            role=UserRole.RESEARCHER,
        ),
    )
    assert response.status_code == 403, response.text


def test_graph_service_enforces_space_membership_under_sports_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")
    reset_database(graph_database.engine, Base.metadata)

    try:
        with TestClient(create_app()) as client:
            fixture = _seed_space_with_projection()
            outsider_id = uuid4()
            outsider_email = f"sports-outsider-{uuid4().hex[:12]}@example.com"

            response = client.get(
                f"/v1/spaces/{fixture['space_id']}/relations",
                headers=_auth_headers(
                    user_id=outsider_id,
                    email=outsider_email,
                    role=UserRole.RESEARCHER,
                ),
            )
            assert response.status_code == 403, response.text
    finally:
        reset_database(graph_database.engine, Base.metadata)


def test_graph_service_enforces_member_role_hierarchy(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    viewer_member = _add_space_member(
        space_id=fixture["space_id"],
        role=GraphSpaceMembershipRoleEnum.VIEWER,
    )

    read_response = graph_client.get(
        f"/v1/spaces/{fixture['space_id']}/relations",
        headers=viewer_member["headers"],
    )
    assert read_response.status_code == 200, read_response.text

    write_response = graph_client.post(
        f"/v1/spaces/{fixture['space_id']}/entities",
        headers=viewer_member["headers"],
        json={
            "entity_type": "GENE",
            "display_label": "VIEWER SHOULD FAIL",
            "metadata": {"source": "graph-service-test"},
            "identifiers": {"hgnc_id": f"HGNC:{uuid4().hex[:8]}"},
        },
    )
    assert write_response.status_code == 403, write_response.text


def test_graph_service_enforces_member_role_hierarchy_under_sports_pack(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GRAPH_DOMAIN_PACK", "sports")
    reset_database(graph_database.engine, Base.metadata)

    try:
        with TestClient(create_app()) as client:
            fixture = _seed_space_with_projection()
            viewer_member = _add_space_member(
                space_id=fixture["space_id"],
                role=GraphSpaceMembershipRoleEnum.VIEWER,
            )

            read_response = client.get(
                f"/v1/spaces/{fixture['space_id']}/relations",
                headers=viewer_member["headers"],
            )
            assert read_response.status_code == 200, read_response.text

            write_response = client.post(
                f"/v1/spaces/{fixture['space_id']}/entities",
                headers=viewer_member["headers"],
                json={
                    "entity_type": "TEAM",
                    "display_label": "VIEWER SHOULD FAIL",
                    "metadata": {"source": "graph-service-test"},
                    "identifiers": {"team_id": f"TEAM:{uuid4().hex[:8]}"},
                },
            )
            assert write_response.status_code == 403, write_response.text
    finally:
        reset_database(graph_database.engine, Base.metadata)


def test_graph_service_dictionary_governance_routes(
    graph_client: TestClient,
) -> None:
    _seed_space_with_open_claims(claim_count=0)
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:8].upper()
    source_entity_type_id = f"GS_SRC_{suffix}"
    target_entity_type_id = f"GS_TGT_{suffix}"
    relation_type_id = f"GS_REL_{suffix}"
    variable_id = f"gs_var_{suffix.lower()}"

    source_entity_response = graph_client.post(
        "/v1/dictionary/entity-types",
        headers=admin_headers,
        json={
            "id": source_entity_type_id,
            "display_name": f"Source Entity {suffix}",
            "description": "Source entity type for graph governance service tests.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-service-test",
        },
    )
    assert source_entity_response.status_code == 201, source_entity_response.text
    assert source_entity_response.json()["id"] == source_entity_type_id

    target_entity_response = graph_client.post(
        "/v1/dictionary/entity-types",
        headers=admin_headers,
        json={
            "id": target_entity_type_id,
            "display_name": f"Target Entity {suffix}",
            "description": "Target entity type for graph governance service tests.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-service-test",
        },
    )
    assert target_entity_response.status_code == 201, target_entity_response.text

    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": relation_type_id,
            "display_name": f"Relates To {suffix}",
            "description": "Relation type for graph governance service tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Inverse {suffix}",
            "source_ref": "graph-service-test",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text

    synonym_response = graph_client.post(
        "/v1/dictionary/relation-synonyms",
        headers=admin_headers,
        json={
            "relation_type_id": relation_type_id,
            "synonym": f"links_{suffix.lower()}",
            "source": "manual",
            "source_ref": "graph-service-test",
        },
    )
    assert synonym_response.status_code == 201, synonym_response.text
    synonym_id = synonym_response.json()["id"]

    resolved_synonym_response = graph_client.get(
        "/v1/dictionary/relation-synonyms/resolve",
        headers=admin_headers,
        params={"synonym": f"links_{suffix.lower()}"},
    )
    assert resolved_synonym_response.status_code == 200, resolved_synonym_response.text
    assert resolved_synonym_response.json()["id"] == relation_type_id

    relation_constraint_response = graph_client.post(
        "/v1/dictionary/relation-constraints",
        headers=admin_headers,
        json={
            "source_type": source_entity_type_id,
            "relation_type": relation_type_id,
            "target_type": target_entity_type_id,
            "is_allowed": True,
            "requires_evidence": True,
            "source_ref": "graph-service-test",
        },
    )
    assert relation_constraint_response.status_code == 201, (
        relation_constraint_response.text
    )
    assert relation_constraint_response.json()["relation_type"] == relation_type_id
    assert relation_constraint_response.json()["profile"] == "ALLOWED"

    variable_response = graph_client.post(
        "/v1/dictionary/variables",
        headers=admin_headers,
        json={
            "id": variable_id,
            "canonical_name": f"graph_variable_{suffix.lower()}",
            "display_name": f"Graph Variable {suffix}",
            "data_type": "CODED",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "preferred_unit": None,
            "constraints": {},
            "description": "Variable for graph governance service tests.",
            "source_ref": "graph-service-test",
        },
    )
    assert variable_response.status_code == 201, variable_response.text
    assert variable_response.json()["id"] == variable_id

    review_status_response = graph_client.patch(
        f"/v1/dictionary/variables/{variable_id}/review-status",
        headers=admin_headers,
        json={"review_status": "PENDING_REVIEW"},
    )
    assert review_status_response.status_code == 200, review_status_response.text
    assert review_status_response.json()["review_status"] == "PENDING_REVIEW"

    revoke_variable_id = f"gs_var_revoke_{suffix.lower()}"
    revoke_variable_response = graph_client.post(
        "/v1/dictionary/variables",
        headers=admin_headers,
        json={
            "id": revoke_variable_id,
            "canonical_name": f"graph_variable_revoke_{suffix.lower()}",
            "display_name": f"Graph Variable Revoke {suffix}",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Variable revoke target for graph governance tests.",
            "source_ref": "graph-service-test",
        },
    )
    assert revoke_variable_response.status_code == 201, revoke_variable_response.text

    merge_variable_source_id = f"gs_var_merge_src_{suffix.lower()}"
    merge_variable_target_id = f"gs_var_merge_tgt_{suffix.lower()}"
    for variable_payload in (
        {
            "id": merge_variable_source_id,
            "canonical_name": f"graph_variable_merge_src_{suffix.lower()}",
            "display_name": f"Graph Variable Merge Source {suffix}",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Variable merge source for graph governance tests.",
            "source_ref": "graph-service-test",
        },
        {
            "id": merge_variable_target_id,
            "canonical_name": f"graph_variable_merge_tgt_{suffix.lower()}",
            "display_name": f"Graph Variable Merge Target {suffix}",
            "data_type": "STRING",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Variable merge target for graph governance tests.",
            "source_ref": "graph-service-test",
        },
    ):
        create_response = graph_client.post(
            "/v1/dictionary/variables",
            headers=admin_headers,
            json=variable_payload,
        )
        assert create_response.status_code == 201, create_response.text

    revoke_entity_type_id = f"GS_REVOKE_ENTITY_{suffix}"
    revoke_entity_response = graph_client.post(
        "/v1/dictionary/entity-types",
        headers=admin_headers,
        json={
            "id": revoke_entity_type_id,
            "display_name": f"Revoke Entity {suffix}",
            "description": "Entity type revoke target for graph governance tests.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-service-test",
        },
    )
    assert revoke_entity_response.status_code == 201, revoke_entity_response.text

    merge_entity_source_id = f"GS_MERGE_ENTITY_SRC_{suffix}"
    merge_entity_target_id = f"GS_MERGE_ENTITY_TGT_{suffix}"
    for entity_payload in (
        {
            "id": merge_entity_source_id,
            "display_name": f"Merge Entity Source {suffix}",
            "description": "Entity type merge source for graph governance tests.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-service-test",
        },
        {
            "id": merge_entity_target_id,
            "display_name": f"Merge Entity Target {suffix}",
            "description": "Entity type merge target for graph governance tests.",
            "domain_context": "general",
            "expected_properties": {},
            "source_ref": "graph-service-test",
        },
    ):
        create_response = graph_client.post(
            "/v1/dictionary/entity-types",
            headers=admin_headers,
            json=entity_payload,
        )
        assert create_response.status_code == 201, create_response.text

    revoke_relation_type_id = f"GS_REVOKE_REL_{suffix}"
    revoke_relation_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": revoke_relation_type_id,
            "display_name": f"Revoke Relation {suffix}",
            "description": "Relation type revoke target for graph governance tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Revoke Inverse {suffix}",
            "source_ref": "graph-service-test",
        },
    )
    assert revoke_relation_response.status_code == 201, revoke_relation_response.text

    merge_relation_source_id = f"GS_MERGE_REL_SRC_{suffix}"
    merge_relation_target_id = f"GS_MERGE_REL_TGT_{suffix}"
    for relation_payload in (
        {
            "id": merge_relation_source_id,
            "display_name": f"Merge Relation Source {suffix}",
            "description": "Relation type merge source for graph governance tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Merge Source Inverse {suffix}",
            "source_ref": "graph-service-test",
        },
        {
            "id": merge_relation_target_id,
            "display_name": f"Merge Relation Target {suffix}",
            "description": "Relation type merge target for graph governance tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Merge Target Inverse {suffix}",
            "source_ref": "graph-service-test",
        },
    ):
        create_response = graph_client.post(
            "/v1/dictionary/relation-types",
            headers=admin_headers,
            json=relation_payload,
        )
        assert create_response.status_code == 201, create_response.text

    value_set_response = graph_client.post(
        "/v1/dictionary/value-sets",
        headers=admin_headers,
        json={
            "id": f"vs_{suffix.lower()}",
            "variable_id": variable_id,
            "name": f"Graph Value Set {suffix}",
            "description": "Value set for graph governance service tests.",
            "external_ref": None,
            "is_extensible": True,
            "source_ref": "graph-service-test",
        },
    )
    assert value_set_response.status_code == 201, value_set_response.text
    value_set_id = value_set_response.json()["id"]

    item_response = graph_client.post(
        f"/v1/dictionary/value-sets/{value_set_id}/items",
        headers=admin_headers,
        json={
            "code": f"code_{suffix.lower()}",
            "display_label": f"Display {suffix}",
            "synonyms": [f"syn_{suffix.lower()}"],
            "external_ref": None,
            "sort_order": 1,
            "is_active": True,
            "source_ref": "graph-service-test",
        },
    )
    assert item_response.status_code == 201, item_response.text
    value_set_item_id = item_response.json()["id"]

    set_item_active_response = graph_client.patch(
        f"/v1/dictionary/value-set-items/{value_set_item_id}/active",
        headers=admin_headers,
        json={"is_active": False, "revocation_reason": "graph-service-test"},
    )
    assert set_item_active_response.status_code == 200, set_item_active_response.text
    assert set_item_active_response.json()["is_active"] is False

    constraints_list_response = graph_client.get(
        "/v1/dictionary/relation-constraints",
        headers=admin_headers,
        params={"relation_type": relation_type_id},
    )
    assert constraints_list_response.status_code == 200, constraints_list_response.text
    assert constraints_list_response.json()["total"] == 1

    by_domain_response = graph_client.get(
        "/v1/dictionary/search/by-domain/general",
        headers=admin_headers,
        params={"limit": 25},
    )
    assert by_domain_response.status_code == 200, by_domain_response.text
    assert by_domain_response.json()["total"] >= 1

    policies_response = graph_client.get(
        "/v1/dictionary/resolution-policies",
        headers=admin_headers,
    )
    assert policies_response.status_code == 200, policies_response.text
    assert policies_response.json()["total"] >= 1

    entity_type_lookup = graph_client.get(
        f"/v1/dictionary/entity-types/{source_entity_type_id}",
        headers=admin_headers,
    )
    assert entity_type_lookup.status_code == 200, entity_type_lookup.text

    relation_type_lookup = graph_client.get(
        f"/v1/dictionary/relation-types/{relation_type_id}",
        headers=admin_headers,
    )
    assert relation_type_lookup.status_code == 200, relation_type_lookup.text

    synonyms_list_response = graph_client.get(
        "/v1/dictionary/relation-synonyms",
        headers=admin_headers,
        params={"relation_type_id": relation_type_id},
    )
    assert synonyms_list_response.status_code == 200, synonyms_list_response.text
    assert synonyms_list_response.json()["total"] == 1
    assert synonyms_list_response.json()["relation_synonyms"][0]["id"] == synonym_id

    pending_synonym_response = graph_client.patch(
        f"/v1/dictionary/relation-synonyms/{synonym_id}/review-status",
        headers=admin_headers,
        json={"review_status": "PENDING_REVIEW"},
    )
    assert pending_synonym_response.status_code == 200, pending_synonym_response.text
    assert pending_synonym_response.json()["review_status"] == "PENDING_REVIEW"

    pending_synonyms_response = graph_client.get(
        "/v1/dictionary/relation-synonyms",
        headers=admin_headers,
        params={
            "relation_type_id": relation_type_id,
            "review_status": "PENDING_REVIEW",
        },
    )
    assert pending_synonyms_response.status_code == 200, pending_synonyms_response.text
    assert pending_synonyms_response.json()["total"] == 1
    assert pending_synonyms_response.json()["relation_synonyms"][0]["id"] == synonym_id

    active_synonyms_response = graph_client.get(
        "/v1/dictionary/relation-synonyms",
        headers=admin_headers,
        params={
            "relation_type_id": relation_type_id,
            "review_status": "ACTIVE",
        },
    )
    assert active_synonyms_response.status_code == 200, active_synonyms_response.text
    assert active_synonyms_response.json()["total"] == 0

    revoke_synonym_response = graph_client.post(
        f"/v1/dictionary/relation-synonyms/{synonym_id}/revoke",
        headers=admin_headers,
        json={"reason": "graph-service-test"},
    )
    assert revoke_synonym_response.status_code == 200, revoke_synonym_response.text
    assert revoke_synonym_response.json()["review_status"] == "REVOKED"
    assert revoke_synonym_response.json()["is_active"] is False

    revoke_variable_result = graph_client.post(
        f"/v1/dictionary/variables/{revoke_variable_id}/revoke",
        headers=admin_headers,
        json={"reason": "graph-service-test"},
    )
    assert revoke_variable_result.status_code == 200, revoke_variable_result.text
    assert revoke_variable_result.json()["review_status"] == "REVOKED"
    assert revoke_variable_result.json()["is_active"] is False

    merge_variable_result = graph_client.post(
        f"/v1/dictionary/variables/{merge_variable_source_id}/merge",
        headers=admin_headers,
        json={
            "target_id": merge_variable_target_id,
            "reason": "graph-service-test",
        },
    )
    assert merge_variable_result.status_code == 200, merge_variable_result.text
    assert merge_variable_result.json()["review_status"] == "REVOKED"
    assert merge_variable_result.json()["superseded_by"] == merge_variable_target_id

    revoke_entity_result = graph_client.post(
        f"/v1/dictionary/entity-types/{revoke_entity_type_id}/revoke",
        headers=admin_headers,
        json={"reason": "graph-service-test"},
    )
    assert revoke_entity_result.status_code == 200, revoke_entity_result.text
    assert revoke_entity_result.json()["review_status"] == "REVOKED"
    assert revoke_entity_result.json()["is_active"] is False

    merge_entity_result = graph_client.post(
        f"/v1/dictionary/entity-types/{merge_entity_source_id}/merge",
        headers=admin_headers,
        json={
            "target_id": merge_entity_target_id,
            "reason": "graph-service-test",
        },
    )
    assert merge_entity_result.status_code == 200, merge_entity_result.text
    assert merge_entity_result.json()["review_status"] == "REVOKED"
    assert merge_entity_result.json()["superseded_by"] == merge_entity_target_id

    revoke_relation_result = graph_client.post(
        f"/v1/dictionary/relation-types/{revoke_relation_type_id}/revoke",
        headers=admin_headers,
        json={"reason": "graph-service-test"},
    )
    assert revoke_relation_result.status_code == 200, revoke_relation_result.text
    assert revoke_relation_result.json()["review_status"] == "REVOKED"
    assert revoke_relation_result.json()["is_active"] is False

    merge_relation_result = graph_client.post(
        f"/v1/dictionary/relation-types/{merge_relation_source_id}/merge",
        headers=admin_headers,
        json={
            "target_id": merge_relation_target_id,
            "reason": "graph-service-test",
        },
    )
    assert merge_relation_result.status_code == 200, merge_relation_result.text
    assert merge_relation_result.json()["review_status"] == "REVOKED"
    assert merge_relation_result.json()["superseded_by"] == merge_relation_target_id
    changelog_response = graph_client.get(
        "/v1/dictionary/changelog",
        headers=admin_headers,
        params={"record_id": merge_variable_source_id},
    )
    assert changelog_response.status_code == 200, changelog_response.text
    changelog_actions = {
        str(entry["action"]) for entry in changelog_response.json()["changelog_entries"]
    }
    assert "MERGE" in changelog_actions

    with graph_database.SessionLocal() as session:
        session.add(
            TransformRegistryModel(
                id=f"TR_GRAPH_{suffix}",
                input_unit="mg",
                output_unit="g",
                category="UNIT_CONVERSION",
                implementation_ref="func:std_lib.convert.mg_to_g",
                status="ACTIVE",
                is_deterministic=True,
                is_production_allowed=False,
                test_input=2500,
                expected_output=2.5,
                description="Graph-service transform parity test",
                created_by="seed",
            ),
        )
        session.commit()

    transforms_list_response = graph_client.get(
        "/v1/dictionary/transforms",
        headers=admin_headers,
    )
    assert transforms_list_response.status_code == 200, transforms_list_response.text
    listed_transform_ids = {
        item["id"] for item in transforms_list_response.json()["transforms"]
    }
    assert f"TR_GRAPH_{suffix}" in listed_transform_ids

    verify_transform_response = graph_client.post(
        f"/v1/dictionary/transforms/TR_GRAPH_{suffix}/verify",
        headers=admin_headers,
    )
    assert verify_transform_response.status_code == 200, verify_transform_response.text
    assert verify_transform_response.json()["transform_id"] == f"TR_GRAPH_{suffix}"
    assert verify_transform_response.json()["passed"] is True

    promote_transform_response = graph_client.patch(
        f"/v1/dictionary/transforms/TR_GRAPH_{suffix}/promote",
        headers=admin_headers,
    )
    assert promote_transform_response.status_code == 200, (
        promote_transform_response.text
    )
    assert promote_transform_response.json()["id"] == f"TR_GRAPH_{suffix}"
    assert promote_transform_response.json()["is_production_allowed"] is True


def test_graph_service_dictionary_relation_constraint_proposal_approval(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    source_entity_type_id = f"PROP_SRC_{suffix}"
    target_entity_type_id = f"PROP_TGT_{suffix}"
    relation_type_id = f"PROP_REL_{suffix}"

    for entity_type_id, display_name in (
        (source_entity_type_id, "Proposal Source"),
        (target_entity_type_id, "Proposal Target"),
    ):
        response = graph_client.post(
            "/v1/dictionary/entity-types",
            headers=admin_headers,
            json={
                "id": entity_type_id,
                "display_name": f"{display_name} {suffix}",
                "description": "Entity type for dictionary proposal tests.",
                "domain_context": "general",
                "expected_properties": {},
                "source_ref": "graph-service-proposal-test",
            },
        )
        assert response.status_code == 201, response.text

    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": relation_type_id,
            "display_name": f"Proposal Relation {suffix}",
            "description": "Relation type for dictionary proposal tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Proposal Inverse {suffix}",
            "source_ref": "graph-service-proposal-test",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/relation-constraints",
        headers=admin_headers,
        json={
            "source_type": source_entity_type_id,
            "relation_type": relation_type_id,
            "target_type": target_entity_type_id,
            "rationale": "The graph needs this relation pattern for the project.",
            "evidence_payload": {
                "source": "integration-test",
                "example": "source uses relation against target",
            },
            "is_allowed": True,
            "requires_evidence": True,
            "profile": "REVIEW_ONLY",
            "source_ref": "graph-service-proposal-test",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_payload = proposal_response.json()
    proposal_id = proposal_payload["id"]
    assert proposal_payload["status"] == "SUBMITTED"
    assert proposal_payload["profile"] == "REVIEW_ONLY"
    assert proposal_payload["applied_constraint_id"] is None

    proposal_lookup = graph_client.get(
        f"/v1/dictionary/proposals/{proposal_id}",
        headers=admin_headers,
    )
    assert proposal_lookup.status_code == 200, proposal_lookup.text
    assert proposal_lookup.json()["id"] == proposal_id

    submitted_proposals = graph_client.get(
        "/v1/dictionary/proposals",
        headers=admin_headers,
        params={"proposal_status": "SUBMITTED", "proposal_type": "RELATION_CONSTRAINT"},
    )
    assert submitted_proposals.status_code == 200, submitted_proposals.text
    assert proposal_id in {
        proposal["id"] for proposal in submitted_proposals.json()["proposals"]
    }

    constraints_before_approval = graph_client.get(
        "/v1/dictionary/relation-constraints",
        headers=admin_headers,
        params={
            "source_type": source_entity_type_id,
            "relation_type": relation_type_id,
        },
    )
    assert constraints_before_approval.status_code == 200
    assert constraints_before_approval.json()["total"] == 0

    approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Approved for relation validation coverage."},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval_payload = approval_response.json()
    assert approval_payload["proposal"]["status"] == "APPROVED"
    assert approval_payload["proposal"]["applied_constraint_id"] is not None
    assert approval_payload["applied_constraint"]["source_type"] == (
        source_entity_type_id
    )
    assert approval_payload["applied_constraint"]["relation_type"] == relation_type_id
    assert approval_payload["applied_constraint"]["target_type"] == (
        target_entity_type_id
    )
    assert approval_payload["applied_constraint"]["profile"] == "REVIEW_ONLY"

    constraints_after_approval = graph_client.get(
        "/v1/dictionary/relation-constraints",
        headers=admin_headers,
        params={
            "source_type": source_entity_type_id,
            "relation_type": relation_type_id,
        },
    )
    assert constraints_after_approval.status_code == 200
    assert constraints_after_approval.json()["total"] == 1


def test_graph_service_dictionary_entity_type_proposal_approval(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    entity_type_id = f"PROP_ENTITY_{suffix}"

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/entity-types",
        headers=admin_headers,
        json={
            "id": entity_type_id,
            "display_name": f"Proposal Entity {suffix}",
            "description": "Entity type proposed through governed review.",
            "domain_context": "general",
            "rationale": "The active project needs this new entity category.",
            "evidence_payload": {"source": "integration-test"},
            "expected_properties": {"kind": "object"},
            "source_ref": "graph-service-entity-proposal-test",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_payload = proposal_response.json()
    proposal_id = proposal_payload["id"]
    assert proposal_payload["proposal_type"] == "ENTITY_TYPE"
    assert proposal_payload["status"] == "SUBMITTED"
    assert proposal_payload["entity_type"] == entity_type_id

    entity_before_approval = graph_client.get(
        f"/v1/dictionary/entity-types/{entity_type_id}",
        headers=admin_headers,
    )
    assert entity_before_approval.status_code == 404

    approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Approved as a valid project entity type."},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval_payload = approval_response.json()
    assert approval_payload["proposal"]["status"] == "APPROVED"
    assert approval_payload["proposal"]["applied_entity_type_id"] == entity_type_id
    assert approval_payload["applied_entity_type"]["id"] == entity_type_id
    assert approval_payload["applied_relation_type"] is None
    assert approval_payload["applied_constraint"] is None

    entity_after_approval = graph_client.get(
        f"/v1/dictionary/entity-types/{entity_type_id}",
        headers=admin_headers,
    )
    assert entity_after_approval.status_code == 200, entity_after_approval.text


def test_graph_service_dictionary_relation_type_proposal_approval(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    relation_type_id = f"PROP_REL_TYPE_{suffix}"

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=admin_headers,
        json={
            "id": relation_type_id,
            "display_name": f"Proposal Relation Type {suffix}",
            "description": "Relation type proposed through governed review.",
            "domain_context": "general",
            "rationale": "The active project needs this new connection label.",
            "evidence_payload": {"source": "integration-test"},
            "is_directional": True,
            "inverse_label": f"Inverse Proposal {suffix}",
            "source_ref": "graph-service-relation-type-proposal-test",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_payload = proposal_response.json()
    proposal_id = proposal_payload["id"]
    assert proposal_payload["proposal_type"] == "RELATION_TYPE"
    assert proposal_payload["status"] == "SUBMITTED"
    assert proposal_payload["relation_type"] == relation_type_id

    relation_before_approval = graph_client.get(
        f"/v1/dictionary/relation-types/{relation_type_id}",
        headers=admin_headers,
    )
    assert relation_before_approval.status_code == 404

    approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Approved as a valid project relation type."},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval_payload = approval_response.json()
    assert approval_payload["proposal"]["status"] == "APPROVED"
    assert approval_payload["proposal"]["applied_relation_type_id"] == relation_type_id
    assert approval_payload["applied_relation_type"]["id"] == relation_type_id
    assert approval_payload["applied_entity_type"] is None
    assert approval_payload["applied_constraint"] is None

    relation_after_approval = graph_client.get(
        f"/v1/dictionary/relation-types/{relation_type_id}",
        headers=admin_headers,
    )
    assert relation_after_approval.status_code == 200, relation_after_approval.text


def test_graph_service_dictionary_relation_constraint_proposal_rejection(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    source_entity_type_id = f"RJ_SRC_{suffix}"
    target_entity_type_id = f"RJ_TGT_{suffix}"
    relation_type_id = f"RJ_REL_{suffix}"

    for entity_type_id, display_name in (
        (source_entity_type_id, "Rejected Source"),
        (target_entity_type_id, "Rejected Target"),
    ):
        response = graph_client.post(
            "/v1/dictionary/entity-types",
            headers=admin_headers,
            json={
                "id": entity_type_id,
                "display_name": f"{display_name} {suffix}",
                "description": "Entity type for rejected proposal tests.",
                "domain_context": "general",
                "expected_properties": {},
                "source_ref": "graph-service-proposal-test",
            },
        )
        assert response.status_code == 201, response.text

    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": relation_type_id,
            "display_name": f"Rejected Relation {suffix}",
            "description": "Relation type for rejected proposal tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Rejected Inverse {suffix}",
            "source_ref": "graph-service-proposal-test",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/relation-constraints",
        headers=admin_headers,
        json={
            "source_type": source_entity_type_id,
            "relation_type": relation_type_id,
            "target_type": target_entity_type_id,
            "rationale": "This proposal should be rejected by the reviewer.",
            "evidence_payload": {"source": "integration-test"},
            "profile": "ALLOWED",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_id = proposal_response.json()["id"]

    reject_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/reject",
        headers=admin_headers,
        json={"decision_reason": "Not enough evidence for this rule."},
    )
    assert reject_response.status_code == 200, reject_response.text
    assert reject_response.json()["status"] == "REJECTED"

    constraints_response = graph_client.get(
        "/v1/dictionary/relation-constraints",
        headers=admin_headers,
        params={
            "source_type": source_entity_type_id,
            "relation_type": relation_type_id,
        },
    )
    assert constraints_response.status_code == 200
    assert constraints_response.json()["total"] == 0

    changelog_response = graph_client.get(
        "/v1/dictionary/changelog",
        headers=admin_headers,
        params={"table_name": "dictionary_proposals", "record_id": proposal_id},
    )
    assert changelog_response.status_code == 200
    changelog_entries = changelog_response.json()["changelog_entries"]
    assert [entry["action"] for entry in changelog_entries] == ["REJECT", "CREATE"]
    reject_entry = changelog_entries[0]
    assert reject_entry["before_snapshot"]["status"] == "SUBMITTED"
    assert reject_entry["after_snapshot"]["status"] == "REJECTED"
    assert (
        reject_entry["after_snapshot"]["decision_reason"]
        == "Not enough evidence for this rule."
    )


def test_graph_service_dictionary_proposal_request_changes_then_approve(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    relation_type_id = f"CHANGES_REL_{suffix}"

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=admin_headers,
        json={
            "id": relation_type_id,
            "display_name": f"Changes Requested Relation {suffix}",
            "description": "Relation type that needs review feedback before approval.",
            "domain_context": "general",
            "rationale": "Initial proposal for lifecycle coverage.",
            "evidence_payload": {"source": "integration-test"},
            "is_directional": True,
            "source_ref": f"graph-service-request-changes:{suffix.lower()}",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_id = proposal_response.json()["id"]

    request_changes_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/request-changes",
        headers=admin_headers,
        json={"decision_reason": "Please tighten the wording before approval."},
    )
    assert request_changes_response.status_code == 200, request_changes_response.text
    request_changes_payload = request_changes_response.json()
    assert request_changes_payload["status"] == "CHANGES_REQUESTED"
    assert (
        request_changes_payload["decision_reason"]
        == "Please tighten the wording before approval."
    )
    changelog_after_request_changes = graph_client.get(
        "/v1/dictionary/changelog",
        headers=admin_headers,
        params={"table_name": "dictionary_proposals", "record_id": proposal_id},
    )
    assert changelog_after_request_changes.status_code == 200
    request_changes_entries = changelog_after_request_changes.json()[
        "changelog_entries"
    ]
    assert [entry["action"] for entry in request_changes_entries] == [
        "REQUEST_CHANGES",
        "CREATE",
    ]
    request_changes_entry = request_changes_entries[0]
    assert request_changes_entry["before_snapshot"]["status"] == "SUBMITTED"
    assert request_changes_entry["after_snapshot"]["status"] == "CHANGES_REQUESTED"
    assert (
        request_changes_entry["after_snapshot"]["decision_reason"]
        == "Please tighten the wording before approval."
    )

    approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Re-reviewed and approved."},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval_payload = approval_response.json()
    assert approval_payload["proposal"]["status"] == "APPROVED"
    assert approval_payload["proposal"]["applied_relation_type_id"] == relation_type_id

    changelog_after_approval = graph_client.get(
        "/v1/dictionary/changelog",
        headers=admin_headers,
        params={"table_name": "dictionary_proposals", "record_id": proposal_id},
    )
    assert changelog_after_approval.status_code == 200
    approval_entries = changelog_after_approval.json()["changelog_entries"]
    assert [entry["action"] for entry in approval_entries] == [
        "APPROVE",
        "REQUEST_CHANGES",
        "CREATE",
    ]
    approval_entry = approval_entries[0]
    assert approval_entry["before_snapshot"]["status"] == "CHANGES_REQUESTED"
    assert approval_entry["after_snapshot"]["status"] == "APPROVED"
    assert (
        approval_entry["after_snapshot"]["applied_relation_type_id"] == relation_type_id
    )


def test_graph_service_dictionary_proposal_merge_tracks_canonical_target(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    target_relation_type_id = f"MERGE_TARGET_REL_{suffix}"
    proposed_relation_type_id = f"MERGE_PROPOSAL_REL_{suffix}"

    target_relation_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": target_relation_type_id,
            "display_name": f"Merge Target Relation {suffix}",
            "description": "Existing canonical relation type.",
            "domain_context": "general",
            "is_directional": True,
            "source_ref": f"graph-service-merge-target:{suffix.lower()}",
        },
    )
    assert target_relation_response.status_code == 201, target_relation_response.text

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=admin_headers,
        json={
            "id": proposed_relation_type_id,
            "display_name": f"Merge Candidate Relation {suffix}",
            "description": "Candidate relation type that should merge into an existing one.",
            "domain_context": "general",
            "rationale": "This proposal overlaps an existing canonical relation type.",
            "evidence_payload": {"source": "integration-test"},
            "is_directional": True,
            "source_ref": f"graph-service-merge-proposal:{suffix.lower()}",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_id = proposal_response.json()["id"]

    merge_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/merge",
        headers=admin_headers,
        json={
            "target_id": target_relation_type_id,
            "decision_reason": "Duplicate meaning; keep the existing canonical label.",
        },
    )
    assert merge_response.status_code == 200, merge_response.text
    merge_payload = merge_response.json()
    assert merge_payload["status"] == "MERGED"
    assert merge_payload["merge_target_type"] == "RELATION_TYPE"
    assert merge_payload["merge_target_id"] == target_relation_type_id
    assert merge_payload["applied_relation_type_id"] is None

    proposed_relation_lookup = graph_client.get(
        f"/v1/dictionary/relation-types/{proposed_relation_type_id}",
        headers=admin_headers,
    )
    assert proposed_relation_lookup.status_code == 404

    changelog_response = graph_client.get(
        "/v1/dictionary/changelog",
        headers=admin_headers,
        params={"table_name": "dictionary_proposals", "record_id": proposal_id},
    )
    assert changelog_response.status_code == 200
    changelog_entries = changelog_response.json()["changelog_entries"]
    assert [entry["action"] for entry in changelog_entries] == ["MERGE", "CREATE"]
    merge_entry = changelog_entries[0]
    assert merge_entry["before_snapshot"]["status"] == "SUBMITTED"
    assert merge_entry["after_snapshot"]["status"] == "MERGED"
    assert merge_entry["after_snapshot"]["merge_target_type"] == "RELATION_TYPE"
    assert merge_entry["after_snapshot"]["merge_target_id"] == target_relation_type_id


def test_graph_service_dictionary_proposal_rejects_repeated_decision(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    relation_type_id = f"REDECIDE_REL_{suffix}"

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=admin_headers,
        json={
            "id": relation_type_id,
            "display_name": f"Re-decision Relation {suffix}",
            "description": "Relation type used to verify terminal proposal decisions.",
            "domain_context": "general",
            "rationale": "This proposal should only be decided once.",
            "evidence_payload": {"source": "integration-test"},
            "is_directional": True,
            "source_ref": f"graph-service-redecision:{suffix.lower()}",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_id = proposal_response.json()["id"]

    approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Approved once."},
    )
    assert approval_response.status_code == 200, approval_response.text

    repeat_approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Approved twice."},
    )
    assert repeat_approval_response.status_code == 409
    assert (
        repeat_approval_response.json()["detail"]
        == f"Dictionary proposal '{proposal_id}' is already APPROVED"
    )


def test_graph_service_dictionary_domain_context_proposal_approval(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12]
    domain_context_id = f"proposal-domain-{suffix}"

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/domain-contexts",
        headers=admin_headers,
        json={
            "id": domain_context_id,
            "display_name": f"Proposal Domain {suffix}",
            "description": "Domain context proposed through governed review.",
            "rationale": "This project needs a dedicated dictionary pack scope.",
            "evidence_payload": {"source": "integration-test"},
            "source_ref": "graph-service-domain-context-proposal-test",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_payload = proposal_response.json()
    proposal_id = proposal_payload["id"]
    assert proposal_payload["proposal_type"] == "DOMAIN_CONTEXT"
    assert proposal_payload["status"] == "SUBMITTED"
    assert proposal_payload["domain_context"] == domain_context_id
    assert proposal_payload["applied_domain_context_id"] is None

    contexts_before_approval = graph_client.get(
        "/v1/dictionary/domain-contexts",
        headers=admin_headers,
    )
    assert contexts_before_approval.status_code == 200
    assert domain_context_id not in {
        context["id"] for context in contexts_before_approval.json()["domain_contexts"]
    }

    approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Approved as a valid dictionary domain."},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval_payload = approval_response.json()
    assert approval_payload["proposal"]["status"] == "APPROVED"
    assert approval_payload["proposal"]["applied_domain_context_id"] == (
        domain_context_id
    )
    assert approval_payload["applied_domain_context"]["id"] == domain_context_id

    contexts_after_approval = graph_client.get(
        "/v1/dictionary/domain-contexts",
        headers=admin_headers,
    )
    assert contexts_after_approval.status_code == 200
    assert domain_context_id in {
        context["id"] for context in contexts_after_approval.json()["domain_contexts"]
    }


def test_graph_service_dictionary_relation_synonym_proposal_approval(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    relation_type_id = f"PROP_SYN_REL_{suffix}"
    synonym = f"proposal synonym {suffix}"

    relation_type_response = graph_client.post(
        "/v1/dictionary/relation-types",
        headers=admin_headers,
        json={
            "id": relation_type_id,
            "display_name": f"Proposal Synonym Relation {suffix}",
            "description": "Relation type for relation-synonym proposal tests.",
            "domain_context": "general",
            "is_directional": True,
            "inverse_label": f"Proposal Synonym Inverse {suffix}",
            "source_ref": "graph-service-relation-synonym-proposal-test",
        },
    )
    assert relation_type_response.status_code == 201, relation_type_response.text

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/relation-synonyms",
        headers=admin_headers,
        json={
            "relation_type_id": relation_type_id,
            "synonym": synonym,
            "rationale": "The source data uses this alternate relation wording.",
            "evidence_payload": {"source": "integration-test"},
            "source": "integration-test",
            "source_ref": "graph-service-relation-synonym-proposal-test",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_payload = proposal_response.json()
    proposal_id = proposal_payload["id"]
    assert proposal_payload["proposal_type"] == "RELATION_SYNONYM"
    assert proposal_payload["status"] == "SUBMITTED"
    assert proposal_payload["relation_type"] == relation_type_id
    assert proposal_payload["synonym"] == synonym

    resolve_before_approval = graph_client.get(
        "/v1/dictionary/relation-synonyms/resolve",
        headers=admin_headers,
        params={"synonym": synonym},
    )
    assert resolve_before_approval.status_code == 404

    approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Approved as a valid relation synonym."},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval_payload = approval_response.json()
    assert approval_payload["proposal"]["status"] == "APPROVED"
    assert approval_payload["proposal"]["applied_relation_synonym_id"] is not None
    assert approval_payload["applied_relation_synonym"]["relation_type"] == (
        relation_type_id
    )
    assert approval_payload["applied_relation_synonym"]["synonym"] == synonym.upper()

    resolve_after_approval = graph_client.get(
        "/v1/dictionary/relation-synonyms/resolve",
        headers=admin_headers,
        params={"synonym": synonym},
    )
    assert resolve_after_approval.status_code == 200, resolve_after_approval.text
    assert resolve_after_approval.json()["id"] == relation_type_id


def test_graph_service_dictionary_variable_proposal_approval(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    variable_id = f"PROP_VAR_{suffix}"

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/variables",
        headers=admin_headers,
        json={
            "id": variable_id,
            "canonical_name": f"proposal_variable_{suffix.lower()}",
            "display_name": f"Proposal Variable {suffix}",
            "data_type": "FLOAT",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "preferred_unit": "mg/dL",
            "constraints": {"min": 0},
            "description": "Continuous variable proposed through governed review.",
            "rationale": "The graph service needs this variable for observations.",
            "evidence_payload": {"source": "integration-test"},
            "source_ref": "graph-service-variable-proposal-test",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_payload = proposal_response.json()
    proposal_id = proposal_payload["id"]
    assert proposal_payload["proposal_type"] == "VARIABLE"
    assert proposal_payload["status"] == "SUBMITTED"
    assert proposal_payload["variable_id"] == variable_id
    assert proposal_payload["canonical_name"] == f"proposal_variable_{suffix.lower()}"
    assert proposal_payload["data_type"] == "FLOAT"
    assert proposal_payload["preferred_unit"] == "mg/dL"
    assert proposal_payload["constraints"] == {"min": 0}

    approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Approved as a valid graph observation variable."},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval_payload = approval_response.json()
    assert approval_payload["proposal"]["status"] == "APPROVED"
    assert approval_payload["proposal"]["applied_variable_id"] == variable_id
    assert approval_payload["applied_variable"]["id"] == variable_id
    assert approval_payload["applied_variable"]["data_type"] == "FLOAT"
    assert approval_payload["applied_variable"]["preferred_unit"] == "mg/dL"
    assert approval_payload["applied_variable"]["constraints"] == {"min": 0}

    duplicate_proposal_response = graph_client.post(
        "/v1/dictionary/proposals/variables",
        headers=admin_headers,
        json={
            "id": variable_id,
            "canonical_name": f"proposal_variable_{suffix.lower()}",
            "display_name": f"Proposal Variable {suffix}",
            "data_type": "FLOAT",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "preferred_unit": "mg/dL",
            "constraints": {"min": 0},
            "description": "Continuous variable proposed through governed review.",
            "rationale": "The graph service needs this variable for observations.",
            "evidence_payload": {"source": "integration-test"},
            "source_ref": "graph-service-variable-proposal-test-duplicate",
        },
    )
    assert duplicate_proposal_response.status_code == 400
    assert (
        duplicate_proposal_response.json()["detail"]
        == f"Variable '{variable_id}' already exists"
    )


def test_graph_service_dictionary_proposal_reuses_source_ref_idempotently(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    relation_type = f"IDEMP_REL_{suffix}"
    source_ref = f"graph-service-proposal-replay:{suffix.lower()}"
    request_payload = {
        "id": relation_type,
        "display_name": f"Idempotent Relation {suffix}",
        "description": "Relation type proposed through governed replay-safe flow.",
        "domain_context": "general",
        "rationale": "The same proposal may be retried by a client.",
        "evidence_payload": {"source": "integration-test"},
        "is_directional": True,
        "source_ref": source_ref,
    }

    first_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=admin_headers,
        json=request_payload,
    )
    assert first_response.status_code == 201, first_response.text
    first_payload = first_response.json()

    second_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=admin_headers,
        json=request_payload,
    )
    assert second_response.status_code == 201, second_response.text
    second_payload = second_response.json()
    assert second_payload["id"] == first_payload["id"]
    assert second_payload["source_ref"] == source_ref

    proposals_response = graph_client.get(
        "/v1/dictionary/proposals",
        headers=admin_headers,
        params={"proposal_type": "RELATION_TYPE"},
    )
    assert proposals_response.status_code == 200, proposals_response.text
    matching_proposals = [
        proposal
        for proposal in proposals_response.json()["proposals"]
        if proposal["relation_type"] == relation_type
    ]
    assert len(matching_proposals) == 1


def test_graph_service_dictionary_proposal_reuses_idempotency_header(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    relation_type = f"IDEMP_HEADER_REL_{suffix}"
    request_payload = {
        "id": relation_type,
        "display_name": f"Idempotent Header Relation {suffix}",
        "description": "Relation type proposed through governed header replay flow.",
        "domain_context": "general",
        "rationale": "The same proposal may be retried by a client header.",
        "evidence_payload": {"source": "integration-test"},
        "is_directional": True,
    }
    replay_headers = {
        **admin_headers,
        "Idempotency-Key": f"proposal-replay-{suffix.lower()}",
    }

    first_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=replay_headers,
        json=request_payload,
    )
    assert first_response.status_code == 201, first_response.text
    first_payload = first_response.json()

    second_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=replay_headers,
        json=request_payload,
    )
    assert second_response.status_code == 201, second_response.text
    second_payload = second_response.json()
    assert second_payload["id"] == first_payload["id"]
    assert second_payload["source_ref"].startswith("idempotency-key:")

    conflict_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=replay_headers,
        json={**request_payload, "id": f"{relation_type}_DIFFERENT"},
    )
    assert conflict_response.status_code == 400
    detail = conflict_response.json()["detail"]
    assert "already linked to a different dictionary proposal" in detail


def test_graph_service_dictionary_proposal_idempotency_header_is_actor_scoped(
    graph_client: TestClient,
) -> None:
    first_admin_headers = _create_admin_headers()
    second_admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    relation_type = f"IDEMP_ACTOR_REL_{suffix}"
    request_payload = {
        "id": relation_type,
        "display_name": f"Actor Scoped Relation {suffix}",
        "description": "Relation type proposed through actor-scoped replay flow.",
        "domain_context": "general",
        "rationale": "Different actors may reuse common idempotency key values.",
        "evidence_payload": {"source": "integration-test"},
        "is_directional": True,
    }
    idempotency_key = f"shared-proposal-replay-{suffix.lower()}"

    first_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers={**first_admin_headers, "Idempotency-Key": idempotency_key},
        json=request_payload,
    )
    assert first_response.status_code == 201, first_response.text
    first_payload = first_response.json()

    second_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers={**second_admin_headers, "Idempotency-Key": idempotency_key},
        json=request_payload,
    )
    assert second_response.status_code == 201, second_response.text
    second_payload = second_response.json()

    assert second_payload["id"] != first_payload["id"]
    assert second_payload["proposed_by"] != first_payload["proposed_by"]
    assert first_payload["source_ref"].startswith("idempotency-key:manual:")
    assert second_payload["source_ref"].startswith("idempotency-key:manual:")
    assert second_payload["source_ref"] != first_payload["source_ref"]


def test_graph_service_dictionary_value_set_proposal_approval(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    variable_id = f"PROP_VAR_{suffix}"
    value_set_id = f"PROP_VS_{suffix}"

    variable_response = graph_client.post(
        "/v1/dictionary/variables",
        headers=admin_headers,
        json={
            "id": variable_id,
            "canonical_name": f"proposal_variable_{suffix.lower()}",
            "display_name": f"Proposal Variable {suffix}",
            "data_type": "CODED",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Coded variable for value-set proposal tests.",
            "source_ref": "graph-service-value-set-proposal-test",
        },
    )
    assert variable_response.status_code == 201, variable_response.text

    proposal_response = graph_client.post(
        "/v1/dictionary/proposals/value-sets",
        headers=admin_headers,
        json={
            "id": value_set_id,
            "variable_id": variable_id,
            "name": f"Proposal Value Set {suffix}",
            "description": "Value set proposed through governed review.",
            "external_ref": f"test:{suffix}",
            "is_extensible": True,
            "rationale": "The coded variable needs an official value set.",
            "evidence_payload": {"source": "integration-test"},
            "source_ref": "graph-service-value-set-proposal-test",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_payload = proposal_response.json()
    proposal_id = proposal_payload["id"]
    assert proposal_payload["proposal_type"] == "VALUE_SET"
    assert proposal_payload["status"] == "SUBMITTED"
    assert proposal_payload["value_set_id"] == value_set_id
    assert proposal_payload["variable_id"] == variable_id

    value_sets_before_approval = graph_client.get(
        "/v1/dictionary/value-sets",
        headers=admin_headers,
        params={"variable_id": variable_id},
    )
    assert value_sets_before_approval.status_code == 200
    assert value_sets_before_approval.json()["total"] == 0

    approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Approved as a valid value set."},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval_payload = approval_response.json()
    assert approval_payload["proposal"]["status"] == "APPROVED"
    assert approval_payload["proposal"]["applied_value_set_id"] == value_set_id
    assert approval_payload["applied_value_set"]["id"] == value_set_id
    assert approval_payload["applied_value_set"]["is_extensible"] is True

    value_sets_after_approval = graph_client.get(
        "/v1/dictionary/value-sets",
        headers=admin_headers,
        params={"variable_id": variable_id},
    )
    assert value_sets_after_approval.status_code == 200
    assert value_set_id in {
        value_set["id"] for value_set in value_sets_after_approval.json()["value_sets"]
    }


def test_graph_service_dictionary_value_set_item_proposal_approval(
    graph_client: TestClient,
) -> None:
    admin_headers = _create_admin_headers()
    suffix = uuid4().hex[:12].upper()
    variable_id = f"PROP_ITEM_VAR_{suffix}"
    value_set_id = f"PROP_ITEM_VS_{suffix}"
    code = f"ITEM_{suffix}"

    variable_response = graph_client.post(
        "/v1/dictionary/variables",
        headers=admin_headers,
        json={
            "id": variable_id,
            "canonical_name": f"proposal_item_variable_{suffix.lower()}",
            "display_name": f"Proposal Item Variable {suffix}",
            "data_type": "CODED",
            "domain_context": "general",
            "sensitivity": "INTERNAL",
            "constraints": {},
            "description": "Coded variable for value-set item proposal tests.",
            "source_ref": "graph-service-value-set-item-proposal-test",
        },
    )
    assert variable_response.status_code == 201, variable_response.text

    value_set_response = graph_client.post(
        "/v1/dictionary/value-sets",
        headers=admin_headers,
        json={
            "id": value_set_id,
            "variable_id": variable_id,
            "name": f"Proposal Item Value Set {suffix}",
            "description": "Parent value set for item proposal tests.",
            "is_extensible": False,
            "source_ref": "graph-service-value-set-item-proposal-test",
        },
    )
    assert value_set_response.status_code == 201, value_set_response.text

    proposal_response = graph_client.post(
        f"/v1/dictionary/proposals/value-sets/{value_set_id}/items",
        headers=admin_headers,
        json={
            "code": code,
            "display_label": f"Proposal Item {suffix}",
            "synonyms": [f"Item Synonym {suffix}"],
            "external_ref": f"test:{suffix}",
            "sort_order": 7,
            "is_active": True,
            "rationale": "The value set needs this official code.",
            "evidence_payload": {"source": "integration-test"},
            "source_ref": "graph-service-value-set-item-proposal-test",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_payload = proposal_response.json()
    proposal_id = proposal_payload["id"]
    assert proposal_payload["proposal_type"] == "VALUE_SET_ITEM"
    assert proposal_payload["status"] == "SUBMITTED"
    assert proposal_payload["value_set_id"] == value_set_id
    assert proposal_payload["code"] == code

    items_before_approval = graph_client.get(
        f"/v1/dictionary/value-sets/{value_set_id}/items",
        headers=admin_headers,
    )
    assert items_before_approval.status_code == 200
    assert items_before_approval.json()["total"] == 0

    approval_response = graph_client.post(
        f"/v1/dictionary/proposals/{proposal_id}/approve",
        headers=admin_headers,
        json={"decision_reason": "Approved as a valid value-set item."},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval_payload = approval_response.json()
    assert approval_payload["proposal"]["status"] == "APPROVED"
    assert approval_payload["proposal"]["applied_value_set_item_id"] is not None
    assert approval_payload["applied_value_set_item"]["code"] == code
    assert approval_payload["applied_value_set_item"]["sort_order"] == 7

    items_after_approval = graph_client.get(
        f"/v1/dictionary/value-sets/{value_set_id}/items",
        headers=admin_headers,
    )
    assert items_after_approval.status_code == 200
    assert code in {item["code"] for item in items_after_approval.json()["items"]}


def test_graph_service_lists_dictionary_domain_contexts(
    graph_client: TestClient,
) -> None:
    _seed_space_with_open_claims(claim_count=0)

    response = graph_client.get(
        "/v1/dictionary/domain-contexts",
        headers=_create_admin_headers(),
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] >= 3
    domain_context_ids = {item["id"] for item in payload["domain_contexts"]}
    assert {"general", "clinical", "genomics"}.issubset(domain_context_ids)


def test_graph_service_dictionary_routes_require_admin(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=0)

    response = graph_client.get(
        "/v1/dictionary/entity-types",
        headers=fixture["headers"],
    )
    assert response.status_code == 403, response.text


def test_graph_service_concept_governance_routes(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_open_claims(claim_count=0)
    space_id = fixture["space_id"]
    headers = fixture["headers"]

    concept_set_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/sets",
        headers=headers,
        json={
            "name": "Mechanism Concepts",
            "slug": "mechanism-concepts",
            "domain_context": "general",
            "description": "Concept set for graph service tests.",
            "source_ref": "graph-service-test",
        },
    )
    assert concept_set_response.status_code == 201, concept_set_response.text
    concept_set_id = concept_set_response.json()["id"]

    concept_sets_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/sets",
        headers=headers,
    )
    assert concept_sets_response.status_code == 200, concept_sets_response.text
    assert concept_sets_response.json()["total"] == 1

    concept_member_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/members",
        headers=headers,
        json={
            "concept_set_id": concept_set_id,
            "domain_context": "general",
            "canonical_label": "Transcriptional dysregulation",
            "normalized_label": "transcriptional dysregulation",
            "sense_key": "mechanism",
            "dictionary_dimension": None,
            "dictionary_entry_id": None,
            "is_provisional": True,
            "metadata_payload": {"kind": "mechanism"},
            "source_ref": "graph-service-test",
        },
    )
    assert concept_member_response.status_code == 201, concept_member_response.text
    concept_member_id = concept_member_response.json()["id"]

    concept_members_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/members",
        headers=headers,
        params={"concept_set_id": concept_set_id},
    )
    assert concept_members_response.status_code == 200, concept_members_response.text
    assert concept_members_response.json()["total"] == 1

    concept_alias_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/aliases",
        headers=headers,
        json={
            "concept_member_id": concept_member_id,
            "domain_context": "general",
            "alias_label": "tx dysregulation",
            "alias_normalized": "tx dysregulation",
            "source": "manual",
            "source_ref": "graph-service-test",
        },
    )
    assert concept_alias_response.status_code == 201, concept_alias_response.text

    aliases_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/aliases",
        headers=headers,
        params={"concept_member_id": concept_member_id},
    )
    assert aliases_response.status_code == 200, aliases_response.text
    assert aliases_response.json()["total"] == 1

    upsert_policy_response = graph_client.put(
        f"/v1/spaces/{space_id}/concepts/policy",
        headers=headers,
        json={
            "mode": "BALANCED",
            "minimum_edge_confidence": 0.7,
            "minimum_distinct_documents": 2,
            "allow_generic_relations": False,
            "max_edges_per_document": 4,
            "policy_payload": {"strategy": "service-test"},
            "source_ref": "graph-service-test",
        },
    )
    assert upsert_policy_response.status_code == 200, upsert_policy_response.text
    assert upsert_policy_response.json()["mode"] == "BALANCED"

    policy_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/policy",
        headers=headers,
    )
    assert policy_response.status_code == 200, policy_response.text
    assert policy_response.json()["mode"] == "BALANCED"

    decision_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/decisions/propose",
        headers=headers,
        json={
            "decision_type": "MAP",
            "decision_payload": {"action": "map"},
            "evidence_payload": {"source": "manual"},
            "confidence": 0.91,
            "rationale": "This concept should be reviewed and mapped later.",
            "concept_set_id": concept_set_id,
            "concept_member_id": concept_member_id,
            "concept_link_id": None,
        },
    )
    assert decision_response.status_code == 201, decision_response.text
    decision_id = decision_response.json()["id"]

    decision_status_response = graph_client.patch(
        f"/v1/spaces/{space_id}/concepts/decisions/{decision_id}/status",
        headers=headers,
        json={"decision_status": "APPROVED"},
    )
    assert decision_status_response.status_code == 200, decision_status_response.text
    assert decision_status_response.json()["decision_status"] == "APPROVED"

    decisions_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/decisions",
        headers=headers,
        params={"decision_status": "APPROVED"},
    )
    assert decisions_response.status_code == 200, decisions_response.text
    assert decisions_response.json()["total"] == 1


def test_graph_service_phase9_concept_proposal_approve_and_merge(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    proposal_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals",
        headers=headers,
        json={
            "domain_context": "general",
            "entity_type": "PHENOTYPE",
            "canonical_label": "Astrocyte activation",
            "synonyms": ["Reactive astrocytes"],
            "external_refs": [{"namespace": "mesh", "identifier": "D000001"}],
            "evidence_payload": {"source": "phase9-test"},
            "rationale": "A reusable graph concept should own this vocabulary.",
            "source_ref": "phase9-concept-astrocyte",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal_payload = proposal_response.json()
    assert proposal_payload["candidate_decision"] == "CREATE_NEW"

    approve_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals/{proposal_payload['id']}/approve",
        headers=headers,
        json={"decision_reason": "Looks valid for the test domain."},
    )
    assert approve_response.status_code == 200, approve_response.text
    approved_payload = approve_response.json()
    assert approved_payload["status"] == "APPLIED"
    concept_member_id = approved_payload["applied_concept_member_id"]
    assert concept_member_id is not None

    duplicate_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals",
        headers=headers,
        json={
            "domain_context": "general",
            "entity_type": "PHENOTYPE",
            "canonical_label": "Reactive astrocytosis",
            "synonyms": ["Astrocyte activation"],
            "external_refs": [{"namespace": "mesh", "identifier": "D000001"}],
            "evidence_payload": {"source": "phase9-test"},
            "source_ref": "phase9-concept-astrocyte-duplicate",
        },
    )
    assert duplicate_response.status_code == 201, duplicate_response.text
    duplicate_payload = duplicate_response.json()
    assert duplicate_payload["status"] == "DUPLICATE_CANDIDATE"
    assert duplicate_payload["candidate_decision"] == "EXTERNAL_REF_MATCH"
    assert duplicate_payload["existing_concept_member_id"] == concept_member_id

    merge_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals/{duplicate_payload['id']}/merge",
        headers=headers,
        json={
            "target_concept_member_id": concept_member_id,
            "decision_reason": "Same external reference.",
        },
    )
    assert merge_response.status_code == 200, merge_response.text
    assert merge_response.json()["status"] == "MERGED"

    repeated_merge_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals/{duplicate_payload['id']}/merge",
        headers=headers,
        json={
            "target_concept_member_id": concept_member_id,
            "decision_reason": "Same external reference.",
        },
    )
    assert repeated_merge_response.status_code == 200, repeated_merge_response.text
    assert repeated_merge_response.json()["status"] == "MERGED"

    aliases_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/aliases",
        headers=headers,
        params={"concept_member_id": concept_member_id},
    )
    assert aliases_response.status_code == 200, aliases_response.text
    alias_labels = {
        item["alias_label"] for item in aliases_response.json()["concept_aliases"]
    }
    assert "Reactive astrocytosis" in alias_labels
    assert "mesh:D000001" in alias_labels


def test_graph_service_phase9_synonym_collision_requires_review(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    created_member_ids: list[str] = []
    for label, synonym, source_ref in (
        ("Concept Alpha", "alpha alias", "phase9-alpha"),
        ("Concept Beta", "beta alias", "phase9-beta"),
    ):
        response = graph_client.post(
            f"/v1/spaces/{space_id}/concepts/proposals",
            headers=headers,
            json={
                "domain_context": "general",
                "entity_type": "PHENOTYPE",
                "canonical_label": label,
                "synonyms": [synonym],
                "evidence_payload": {"source": "phase9-test"},
                "source_ref": source_ref,
            },
        )
        assert response.status_code == 201, response.text
        approve_response = graph_client.post(
            f"/v1/spaces/{space_id}/concepts/proposals/{response.json()['id']}/approve",
            headers=headers,
            json={"decision_reason": "Seed test concept."},
        )
        assert approve_response.status_code == 200, approve_response.text
        created_member_ids.append(approve_response.json()["applied_concept_member_id"])

    collision_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals",
        headers=headers,
        json={
            "domain_context": "general",
            "entity_type": "PHENOTYPE",
            "canonical_label": "Concept Gamma",
            "synonyms": ["alpha alias", "beta alias"],
            "evidence_payload": {"source": "phase9-test"},
            "source_ref": "phase9-collision",
        },
    )
    assert collision_response.status_code == 201, collision_response.text
    payload = collision_response.json()
    assert payload["candidate_decision"] == "SYNONYM_COLLISION"
    matched_ids = set(
        payload["duplicate_checks_payload"]["synonyms"]["concept_member_ids"],
    )
    assert matched_ids == set(created_member_ids)

    approve_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals/{payload['id']}/approve",
        headers=headers,
        json={"decision_reason": "This should stay human-gated."},
    )
    assert approve_response.status_code == 400, approve_response.text


def test_graph_service_phase9_graph_change_plan_and_idempotency(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    payload = {
        "concepts": [
            {
                "local_id": "gene-med13",
                "domain_context": "general",
                "entity_type": "GENE",
                "canonical_label": "MED13",
                "external_refs": [{"namespace": "hgnc", "identifier": "MED13"}],
            },
            {
                "local_id": "phenotype-delay",
                "domain_context": "general",
                "entity_type": "PHENOTYPE",
                "canonical_label": "Developmental delay",
                "external_refs": [{"namespace": "mondo", "identifier": "0000001"}],
            },
        ],
        "claims": [
            {
                "source_local_id": "gene-med13",
                "target_local_id": "phenotype-delay",
                "relation_type": "ASSOCIATED_WITH",
                "assessment": _SUPPORTED_ASSESSMENT,
                "claim_text": "MED13 is associated with developmental delay.",
                "evidence_payload": {"sentence": "Synthetic evidence."},
            },
        ],
        "source_ref": "phase9-graph-change",
    }

    response = graph_client.post(
        f"/v1/spaces/{space_id}/graph-change-proposals",
        headers=headers,
        json=payload,
    )
    assert response.status_code == 201, response.text
    first_payload = response.json()
    assert first_payload["status"] == "READY_FOR_REVIEW"
    assert first_payload["resolution_plan_payload"]["errors"] == []
    assert len(first_payload["resolution_plan_payload"]["concept_steps"]) == 2
    assert len(first_payload["resolution_plan_payload"]["claim_steps"]) == 1

    replay_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph-change-proposals",
        headers=headers,
        json=payload,
    )
    assert replay_response.status_code == 201, replay_response.text
    assert replay_response.json()["id"] == first_payload["id"]

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph-change-proposals",
        headers=headers,
        params={"status": "READY_FOR_REVIEW"},
    )
    assert list_response.status_code == 200, list_response.text
    listed_ids = {
        item["id"] for item in list_response.json()["graph_change_proposals"]
    }
    assert first_payload["id"] in listed_ids

    review_payload = {**payload, "source_ref": "phase9-graph-change-review"}
    review_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph-change-proposals",
        headers=headers,
        json=review_payload,
    )
    assert review_response.status_code == 201, review_response.text
    review_id = review_response.json()["id"]

    request_changes_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph-change-proposals/{review_id}/request-changes",
        headers=headers,
        json={"decision_reason": "Needs clearer source evidence."},
    )
    assert request_changes_response.status_code == 200, request_changes_response.text
    assert request_changes_response.json()["status"] == "CHANGES_REQUESTED"

    reject_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph-change-proposals/{review_id}/reject",
        headers=headers,
        json={"decision_reason": "The revised bundle is still not acceptable."},
    )
    assert reject_response.status_code == 200, reject_response.text
    assert reject_response.json()["status"] == "REJECTED"

    rejected_list_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph-change-proposals",
        headers=headers,
        params={"status": "REJECTED"},
    )
    assert rejected_list_response.status_code == 200, rejected_list_response.text
    rejected_ids = {
        item["id"]
        for item in rejected_list_response.json()["graph_change_proposals"]
    }
    assert review_id in rejected_ids

    missing_evidence_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph-change-proposals",
        headers=headers,
        json={
            "concepts": payload["concepts"],
            "claims": [
                {
                    "source_local_id": "gene-med13",
                    "target_local_id": "phenotype-delay",
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                },
            ],
            "source_ref": "phase9-graph-change-missing-evidence",
        },
    )
    assert missing_evidence_response.status_code == 400, missing_evidence_response.text
    assert "requires evidence" in missing_evidence_response.text


def test_graph_service_phase10_operating_mode_and_workflow_plan(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    default_mode_response = graph_client.get(
        f"/v1/spaces/{space_id}/operating-mode",
        headers=headers,
    )
    assert default_mode_response.status_code == 200, default_mode_response.text
    assert default_mode_response.json()["mode"] == "manual"

    patch_response = graph_client.patch(
        f"/v1/spaces/{space_id}/operating-mode",
        headers=headers,
        json={
            "mode": "ai_full_graph",
            "workflow_policy": {
                "allow_ai_graph_repair": True,
                "allow_ai_evidence_decisions": False,
                "batch_auto_apply_low_risk": False,
                "trusted_ai_principals": ["agent:phase10"],
                "min_ai_confidence": 0.85,
            },
        },
    )
    assert patch_response.status_code == 200, patch_response.text
    patched_payload = patch_response.json()
    assert patched_payload["mode"] == "ai_full_graph"
    assert patched_payload["capabilities"]["ai_graph_repair_allowed"] is True

    capabilities_response = graph_client.get(
        f"/v1/spaces/{space_id}/operating-mode/capabilities",
        headers=headers,
    )
    assert capabilities_response.status_code == 200, capabilities_response.text
    assert "evidence_approval" in (
        capabilities_response.json()["capabilities"]["supported_workflow_kinds"]
    )

    payload = {
        "graph_change_proposal": {
            "concepts": [
                {
                    "local_id": "gene-med13",
                    "domain_context": "general",
                    "entity_type": "GENE",
                    "canonical_label": "MED13",
                    "external_refs": [{"namespace": "hgnc", "identifier": "MED13"}],
                },
                {
                    "local_id": "phenotype-phase10",
                    "domain_context": "general",
                    "entity_type": "PHENOTYPE",
                    "canonical_label": "Phase 10 workflow phenotype",
                },
            ],
            "claims": [
                {
                    "source_local_id": "gene-med13",
                    "target_local_id": "phenotype-phase10",
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "claim_text": "MED13 is associated with the phase 10 phenotype.",
                    "evidence_payload": {"sentence": "Synthetic phase 10 evidence."},
                },
            ],
            "source_ref": "phase10-workflow-graph-change",
        },
    }
    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=headers,
        json={
            "kind": "evidence_approval",
            "input_payload": payload,
            "source_ref": "phase10-workflow-plan",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow_payload = workflow_response.json()
    assert workflow_payload["status"] == "PLAN_READY"
    assert len(
        workflow_payload["generated_resources_payload"]["graph_change_proposal_ids"],
    ) == 1

    stale_action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow_payload['id']}/actions",
        headers=headers,
        json={
            "action": "approve",
            "input_hash": "0" * 64,
            "reason": "This hash should be stale.",
        },
    )
    assert stale_action_response.status_code == 400, stale_action_response.text
    assert "input_hash" in stale_action_response.text

    untrusted_ai_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow_payload['id']}/actions",
        headers=headers,
        json={
            "action": "approve",
            "input_hash": workflow_payload["workflow_hash"],
            "risk_tier": "low",
            "confidence_assessment": _DECISION_CONFIDENCE_ASSESSMENT,
            "ai_decision": {
                "ai_principal": "agent:untrusted",
                "rationale": "Testing the trusted principal gate.",
            },
        },
    )
    assert untrusted_ai_response.status_code == 400, untrusted_ai_response.text
    assert "Authenticated AI principal" in untrusted_ai_response.text

    with graph_database.SessionLocal() as session:
        blocked_events = session.scalars(
            sa.select(GraphWorkflowEventModel).where(
                GraphWorkflowEventModel.workflow_id == UUID(workflow_payload["id"]),
                GraphWorkflowEventModel.reason.contains(
                    "Authenticated AI principal",
                ),
            ),
        ).all()
    assert blocked_events

    trusted_ai_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow_payload['id']}/actions",
        headers={**headers, "X-TEST-GRAPH-AI-PRINCIPAL": "agent:phase10"},
        json={
            "action": "approve",
            "input_hash": workflow_payload["workflow_hash"],
            "risk_tier": "low",
            "confidence_assessment": _DECISION_CONFIDENCE_ASSESSMENT,
            "ai_decision": {
                "ai_principal": "agent:phase10",
                "rationale": "Testing the authenticated AI principal gate.",
            },
        },
    )
    assert trusted_ai_response.status_code == 200, trusted_ai_response.text
    assert trusted_ai_response.json()["status"] == "APPLIED"

    explain_response = graph_client.get(
        f"/v1/spaces/{space_id}/explain/workflow/{workflow_payload['id']}",
        headers=headers,
    )
    assert explain_response.status_code == 200, explain_response.text
    assert explain_response.json()["generated_resources"][
        "graph_change_proposal_ids"
    ] == workflow_payload["generated_resources_payload"]["graph_change_proposal_ids"]

    list_response = graph_client.get(
        f"/v1/spaces/{space_id}/workflows",
        headers=headers,
        params={"kind": "evidence_approval"},
    )
    assert list_response.status_code == 200, list_response.text
    assert workflow_payload["id"] in {
        item["id"] for item in list_response.json()["workflows"]
    }


def test_graph_service_workflow_count_is_not_capped_by_list_limit(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    with graph_database.SessionLocal() as session:
        session.add_all(
            [
                GraphWorkflowModel(
                    id=uuid4(),
                    research_space_id=space_id,
                    kind="batch_review",
                    status="WAITING_REVIEW",
                    operating_mode="manual",
                    input_payload={},
                    plan_payload={},
                    generated_resources_payload={},
                    decision_payload={},
                    policy_payload={},
                    explanation_payload={},
                    source_ref=f"count-regression:{index}",
                    workflow_hash=f"{index:064x}"[-64:],
                    created_by="manual:count-test",
                    updated_by="manual:count-test",
                )
                for index in range(10_005)
            ],
        )
        session.commit()

    response = graph_client.get(
        f"/v1/spaces/{space_id}/workflows",
        headers=headers,
        params={"kind": "batch_review", "limit": 1},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total"] == 10_005
    assert len(payload["workflows"]) == 1


def test_graph_service_batch_review_applies_mixed_resources_idempotently(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    admin_headers = _create_admin_headers()
    space_id = fixture["space_id"]
    suffix = uuid4().hex[:8]

    concept_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals",
        headers=headers,
        json={
            "domain_context": "general",
            "entity_type": "PHENOTYPE",
            "canonical_label": f"Batch review phenotype {suffix}",
            "evidence_payload": {"source": "phase12-batch"},
            "source_ref": f"phase12-batch-concept-{suffix}",
        },
    )
    assert concept_response.status_code == 201, concept_response.text
    concept_payload = concept_response.json()

    dictionary_response = graph_client.post(
        "/v1/dictionary/proposals/relation-types",
        headers=admin_headers,
        json={
            "id": f"BATCH_RELATED_{suffix.upper()}",
            "display_name": f"Batch related {suffix}",
            "description": "Synthetic relation type for batch review coverage.",
            "domain_context": "general",
            "rationale": "Batch review should use the dictionary proposal service.",
            "evidence_payload": {"source": "phase12-batch"},
        },
    )
    assert dictionary_response.status_code == 201, dictionary_response.text
    dictionary_payload = dictionary_response.json()

    connector_response = graph_client.post(
        f"/v1/spaces/{space_id}/connector-proposals",
        headers=headers,
        json={
            "connector_slug": f"phase12-batch-{suffix}",
            "display_name": f"Phase 12 Batch {suffix}",
            "connector_kind": "document_source",
            "domain_context": "genomics",
            "metadata_payload": {"runtime": "external"},
            "mapping_payload": {
                "field_mappings": [
                    {
                        "source_field": "gene",
                        "target_dimension": "entity_type",
                        "target_id": "GENE",
                    },
                ],
            },
            "evidence_payload": {"source": "phase12-batch"},
            "source_ref": f"phase12-batch-connector-{suffix}",
        },
    )
    assert connector_response.status_code == 201, connector_response.text
    connector_payload = connector_response.json()

    graph_change_response = graph_client.post(
        f"/v1/spaces/{space_id}/graph-change-proposals",
        headers=headers,
        json={
            "concepts": [
                {
                    "local_id": "gene-med13",
                    "domain_context": "general",
                    "entity_type": "GENE",
                    "canonical_label": "MED13",
                    "external_refs": [{"namespace": "hgnc", "identifier": "MED13"}],
                },
                {
                    "local_id": f"phenotype-batch-{suffix}",
                    "domain_context": "general",
                    "entity_type": "PHENOTYPE",
                    "canonical_label": f"Batch graph phenotype {suffix}",
                },
            ],
            "claims": [
                {
                    "source_local_id": "gene-med13",
                    "target_local_id": f"phenotype-batch-{suffix}",
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "claim_text": "Synthetic batch graph evidence.",
                    "evidence_payload": {"sentence": "Synthetic batch graph evidence."},
                },
            ],
            "source_ref": f"phase12-batch-graph-change-{suffix}",
        },
    )
    assert graph_change_response.status_code == 201, graph_change_response.text
    graph_change_payload = graph_change_response.json()

    claim_response = graph_client.post(
        f"/v1/spaces/{space_id}/claims",
        headers=headers,
        json={
            "source_entity_id": str(fixture["source_id"]),
            "target_entity_id": str(fixture["target_id"]),
            "relation_type": "ASSOCIATED_WITH",
            "assessment": _SUPPORTED_ASSESSMENT,
            "claim_text": "Batch review should resolve this valid claim.",
            "evidence_summary": "Synthetic claim evidence for batch review.",
            "source_document_ref": f"phase12-batch-doc-{suffix}",
            "source_ref": f"phase12-batch-claim-{suffix}",
        },
    )
    assert claim_response.status_code == 201, claim_response.text
    claim_payload = claim_response.json()

    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=headers,
        json={
            "kind": "batch_review",
            "input_payload": {
                "generated_resources": [
                    {
                        "resource_type": "concept_proposal",
                        "resource_id": concept_payload["id"],
                        "action": "approve",
                        "input_hash": concept_payload["proposal_hash"],
                        "reason": "Approve concept through batch review.",
                    },
                    {
                        "resource_type": "dictionary_proposal",
                        "resource_id": dictionary_payload["id"],
                        "action": "approve",
                        "reason": "Approve dictionary proposal through batch review.",
                    },
                    {
                        "resource_type": "connector_proposal",
                        "resource_id": connector_payload["id"],
                        "action": "approve",
                        "reason": "Approve connector metadata through batch review.",
                    },
                    {
                        "resource_type": "graph_change_proposal",
                        "resource_id": graph_change_payload["id"],
                        "action": "apply",
                        "input_hash": graph_change_payload["proposal_hash"],
                        "reason": "Apply graph-change through batch review.",
                    },
                    {
                        "resource_type": "claim",
                        "resource_id": claim_payload["id"],
                        "action": "resolve",
                        "reason": "Resolve claim through batch review.",
                    },
                    {
                        "resource_type": "claim",
                        "resource_id": str(uuid4()),
                        "action": "reject",
                        "reason": "Intentional partial failure.",
                    },
                ],
            },
            "source_ref": f"phase12-batch-workflow-{suffix}",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    workflow_payload = workflow_response.json()

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow_payload['id']}/actions",
        headers=headers,
        json={
            "action": "approve",
            "input_hash": workflow_payload["workflow_hash"],
            "reason": "Apply the batch.",
        },
    )
    assert action_response.status_code == 200, action_response.text
    batch_payload = action_response.json()
    assert batch_payload["status"] == "CHANGES_REQUESTED"
    assert len(batch_payload["generated_resources_payload"]["applied_resource_refs"]) == 5
    assert len(batch_payload["generated_resources_payload"]["failed_resource_refs"]) == 1

    replay_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{workflow_payload['id']}/actions",
        headers=headers,
        json={
            "action": "approve",
            "input_hash": batch_payload["workflow_hash"],
            "reason": "Replay the batch safely.",
        },
    )
    assert replay_response.status_code == 200, replay_response.text
    replay_payload = replay_response.json()
    assert replay_payload["status"] == "CHANGES_REQUESTED"
    assert len(replay_payload["generated_resources_payload"]["applied_resource_refs"]) == 5
    assert len(replay_payload["generated_resources_payload"]["failed_resource_refs"]) == 1


def test_graph_service_phase10_evidence_workflow_applies_valid_claim(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]

    patch_response = graph_client.patch(
        f"/v1/spaces/{space_id}/operating-mode",
        headers=headers,
        json={
            "mode": "human_evidence_ai_graph",
            "workflow_policy": {
                "allow_ai_graph_repair": True,
                "allow_ai_evidence_decisions": False,
            },
        },
    )
    assert patch_response.status_code == 200, patch_response.text

    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": str(source_id),
                    "target_entity_id": str(target_id),
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "claim_text": "Phase 10 evidence independently links MED13 to developmental delay.",
                    "evidence_summary": "Synthetic phase 10 evidence summary.",
                    "evidence_sentence": "Phase 10 evidence links MED13 to developmental delay.",
                    "evidence_sentence_source": "verbatim_span",
                    "evidence_sentence_confidence": "high",
                    "source_document_ref": "phase10:doc:claim",
                    "source_ref": "phase10:claim:valid",
                },
            },
            "source_ref": "phase10-valid-claim-workflow",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    payload = workflow_response.json()
    assert payload["status"] == "APPLIED"
    claim_ids = payload["generated_resources_payload"]["claim_ids"]
    assert len(claim_ids) == 1

    participants_response = graph_client.get(
        f"/v1/spaces/{space_id}/claims/{claim_ids[0]}/participants",
        headers=headers,
    )
    assert participants_response.status_code == 200, participants_response.text
    assert participants_response.json()["total"] == 2

    explanation_response = graph_client.get(
        f"/v1/spaces/{space_id}/explain/claim/{claim_ids[0]}",
        headers=headers,
    )
    assert explanation_response.status_code == 200, explanation_response.text
    assert explanation_response.json()["validation"]["persistability"] == "PERSISTABLE"


def test_graph_service_phase10_evidence_workflow_creates_dictionary_proposal(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    source_id = fixture["source_id"]
    target_id = fixture["target_id"]

    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": str(source_id),
                    "target_entity_id": str(target_id),
                    "relation_type": "PROTECTS_AGAINST",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "claim_text": "MED13 protects against the phenotype in a synthetic example.",
                    "evidence_summary": "Synthetic evidence for an unknown relation type.",
                    "source_document_ref": "phase10:doc:unknown-relation",
                    "source_ref": "phase10:claim:unknown-relation",
                },
            },
            "source_ref": "phase10-dictionary-proposal-workflow",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    payload = workflow_response.json()
    assert payload["status"] == "PLAN_READY"
    dictionary_proposal_ids = payload["generated_resources_payload"][
        "dictionary_proposal_ids"
    ]
    assert len(dictionary_proposal_ids) == 1

    proposals_response = graph_client.get(
        "/v1/dictionary/proposals",
        headers=_create_admin_headers(),
        params={"proposal_type": "RELATION_TYPE"},
    )
    assert proposals_response.status_code == 200, proposals_response.text
    assert dictionary_proposal_ids[0] in {
        proposal["id"] for proposal in proposals_response.json()["proposals"]
    }


def test_graph_service_evidence_workflow_composes_dictionary_and_graph_repair(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]
    suffix = uuid4().hex[:8]

    patch_response = graph_client.patch(
        f"/v1/spaces/{space_id}/operating-mode",
        headers=headers,
        json={
            "mode": "ai_full_graph",
            "workflow_policy": {
                "allow_ai_graph_repair": True,
                "trusted_ai_principals": ["agent:phase12"],
                "min_ai_confidence": 0.85,
            },
        },
    )
    assert patch_response.status_code == 200, patch_response.text

    workflow_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows",
        headers=headers,
        json={
            "kind": "evidence_approval",
            "input_payload": {
                "claim_request": {
                    "source_entity_id": str(fixture["source_id"]),
                    "target_entity_id": str(fixture["target_id"]),
                    "relation_type": f"PHASE12_CONNECTS_{suffix.upper()}",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "claim_text": "Composed evidence needs a dictionary rule and graph repair.",
                    "evidence_summary": "Synthetic composed evidence summary.",
                    "source_document_ref": f"phase12-composed-doc-{suffix}",
                    "source_ref": f"phase12-composed-claim-{suffix}",
                },
                "graph_change_proposal": {
                    "concepts": [
                        {
                            "local_id": "gene-med13",
                            "domain_context": "general",
                            "entity_type": "GENE",
                            "canonical_label": "MED13",
                            "external_refs": [
                                {"namespace": "hgnc", "identifier": "MED13"},
                            ],
                        },
                        {
                            "local_id": f"phenotype-composed-{suffix}",
                            "domain_context": "general",
                            "entity_type": "PHENOTYPE",
                            "canonical_label": f"Composed phenotype {suffix}",
                        },
                    ],
                    "claims": [
                        {
                            "source_local_id": "gene-med13",
                            "target_local_id": f"phenotype-composed-{suffix}",
                            "relation_type": "ASSOCIATED_WITH",
                            "assessment": _SUPPORTED_ASSESSMENT,
                            "claim_text": "Synthetic composed graph repair claim.",
                            "evidence_payload": {
                                "sentence": "Synthetic composed graph repair claim.",
                            },
                        },
                    ],
                    "source_ref": f"phase12-composed-graph-change-{suffix}",
                },
            },
            "source_ref": f"phase12-composed-workflow-{suffix}",
        },
    )
    assert workflow_response.status_code == 201, workflow_response.text
    payload = workflow_response.json()

    assert payload["status"] == "PLAN_READY"
    generated = payload["generated_resources_payload"]
    assert len(generated["graph_change_proposal_ids"]) == 1
    assert len(generated["dictionary_proposal_ids"]) == 1
    assert generated["pending_claim_request"]["source_ref"] == (
        f"phase12-composed-claim-{suffix}"
    )
    assert "claim_ids" not in generated

    action_response = graph_client.post(
        f"/v1/spaces/{space_id}/workflows/{payload['id']}/actions",
        headers={**headers, "X-TEST-GRAPH-AI-PRINCIPAL": "agent:phase12"},
        json={
            "action": "approve",
            "input_hash": payload["workflow_hash"],
            "risk_tier": "low",
            "confidence_assessment": _DECISION_CONFIDENCE_ASSESSMENT,
            "ai_decision": {
                "ai_principal": "agent:phase12",
                "rationale": "Apply graph repair but keep pending claim blocked by dictionary review.",
            },
        },
    )
    assert action_response.status_code == 200, action_response.text
    action_payload = action_response.json()
    assert action_payload["status"] == "PLAN_READY"
    assert "claim_ids" not in action_payload["generated_resources_payload"]

    graph_change_response = graph_client.get(
        f"/v1/spaces/{space_id}/graph-change-proposals/{generated['graph_change_proposal_ids'][0]}",
        headers=headers,
    )
    assert graph_change_response.status_code == 200, graph_change_response.text
    assert graph_change_response.json()["status"] == "APPLIED"


def test_graph_service_phase9_ai_full_mode_auto_merge_and_rejections(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    ai_headers = {**headers, "X-TEST-GRAPH-AI-PRINCIPAL": "agent:phase9"}
    space_id = fixture["space_id"]
    owner_id = fixture["owner_id"]
    with graph_database.SessionLocal() as session:
        space = session.get(GraphSpaceModel, space_id)
        assert space is not None
        space.settings = {
            "ai_full_mode": {
                "governance_mode": "ai_full",
                "trusted_principals": ["agent:phase9"],
                "min_confidence": 0.85,
                "allow_high_risk_actions": False,
            },
        }
        session.commit()

    base_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals",
        headers=headers,
        json={
            "domain_context": "general",
            "entity_type": "PHENOTYPE",
            "canonical_label": "Cardiac fibrosis",
            "external_refs": [{"namespace": "mesh", "identifier": "D999999"}],
            "evidence_payload": {"source": "phase9-test"},
            "source_ref": "phase9-ai-base",
        },
    )
    assert base_response.status_code == 201, base_response.text
    approve_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals/{base_response.json()['id']}/approve",
        headers=headers,
        json={"decision_reason": "Seed AI merge target."},
    )
    assert approve_response.status_code == 200, approve_response.text
    target_member_id = approve_response.json()["applied_concept_member_id"]

    duplicate_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals",
        headers=headers,
        json={
            "domain_context": "general",
            "entity_type": "PHENOTYPE",
            "canonical_label": "Fibrotic heart remodeling",
            "external_refs": [{"namespace": "mesh", "identifier": "D999999"}],
            "evidence_payload": {"source": "phase9-test"},
            "source_ref": "phase9-ai-duplicate",
        },
    )
    assert duplicate_response.status_code == 201, duplicate_response.text
    duplicate_payload = duplicate_response.json()

    mismatched_decision_response = graph_client.post(
        f"/v1/spaces/{space_id}/ai-decisions",
        headers={**headers, "X-TEST-GRAPH-AI-PRINCIPAL": "agent:other"},
        json={
            "target_type": "concept_proposal",
            "target_id": duplicate_payload["id"],
            "action": "MERGE",
            "ai_principal": "agent:phase9",
            "confidence_assessment": _DECISION_CONFIDENCE_ASSESSMENT,
            "risk_tier": "low",
            "input_hash": duplicate_payload["proposal_hash"],
            "evidence_payload": {"rationale": "Testing authenticated principal bind."},
            "decision_payload": {"target_concept_member_id": target_member_id},
        },
    )
    assert mismatched_decision_response.status_code == 400
    assert "does not match" in mismatched_decision_response.text

    stale_decision_response = graph_client.post(
        f"/v1/spaces/{space_id}/ai-decisions",
        headers=ai_headers,
        json={
            "target_type": "concept_proposal",
            "target_id": duplicate_payload["id"],
            "action": "MERGE",
            "ai_principal": "agent:phase9",
            "confidence_assessment": _DECISION_CONFIDENCE_ASSESSMENT,
            "risk_tier": "low",
            "input_hash": "0" * 64,
            "evidence_payload": {"rationale": "Exact external ref match."},
            "decision_payload": {"target_concept_member_id": target_member_id},
        },
    )
    assert stale_decision_response.status_code == 400, stale_decision_response.text
    assert "input_hash" in stale_decision_response.text

    ai_decision_response = graph_client.post(
        f"/v1/spaces/{space_id}/ai-decisions",
        headers=ai_headers,
        json={
            "target_type": "concept_proposal",
            "target_id": duplicate_payload["id"],
            "action": "MERGE",
            "ai_principal": "agent:phase9",
            "confidence_assessment": _DECISION_CONFIDENCE_ASSESSMENT,
            "risk_tier": "low",
            "input_hash": duplicate_payload["proposal_hash"],
            "evidence_payload": {"rationale": "Exact external ref match."},
            "decision_payload": {"target_concept_member_id": target_member_id},
        },
    )
    assert ai_decision_response.status_code == 201, ai_decision_response.text
    ai_payload = ai_decision_response.json()
    assert ai_payload["status"] == "APPLIED"
    assert ai_payload["policy_outcome"] == "ai_allowed_when_low_risk"

    merged_response = graph_client.get(
        f"/v1/spaces/{space_id}/concepts/proposals/{duplicate_payload['id']}",
        headers=headers,
    )
    assert merged_response.status_code == 200, merged_response.text
    assert merged_response.json()["status"] == "MERGED"

    with graph_database.SessionLocal() as session:
        space = session.get(GraphSpaceModel, space_id)
        assert space is not None
        space.settings = {
            "ai_full_mode": {
                "governance_mode": "human_review",
                "trusted_principals": ["agent:phase9"],
                "min_confidence": 0.85,
            },
        }
        session.commit()

    human_mode_response = graph_client.post(
        f"/v1/spaces/{space_id}/concepts/proposals",
        headers=headers,
        json={
            "domain_context": "general",
            "entity_type": "PHENOTYPE",
            "canonical_label": f"Human review concept {owner_id}",
            "evidence_payload": {"source": "phase9-test"},
            "source_ref": "phase9-human-required",
        },
    )
    assert human_mode_response.status_code == 201, human_mode_response.text
    human_payload = human_mode_response.json()
    human_required_response = graph_client.post(
        f"/v1/spaces/{space_id}/ai-decisions",
        headers=ai_headers,
        json={
            "target_type": "concept_proposal",
            "target_id": human_payload["id"],
            "action": "APPROVE",
            "ai_principal": "agent:phase9",
            "confidence_assessment": _DECISION_CONFIDENCE_ASSESSMENT,
            "risk_tier": "low",
            "input_hash": human_payload["proposal_hash"],
            "evidence_payload": {"rationale": "Testing human gate."},
            "decision_payload": {},
        },
    )
    assert human_required_response.status_code == 400, human_required_response.text

    decisions_response = graph_client.get(
        f"/v1/spaces/{space_id}/ai-decisions",
        headers=headers,
        params={"target_type": "concept_proposal"},
    )
    assert decisions_response.status_code == 200, decisions_response.text
    decisions = decisions_response.json()["ai_decisions"]
    assert any(decision["status"] == "REJECTED" for decision in decisions)
    assert any(
        decision["rejection_reason"]
        == "AI decision principal does not match authenticated AI principal"
        for decision in decisions
    )


def test_graph_service_phase9_connector_metadata_workflow(
    graph_client: TestClient,
) -> None:
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    proposal_response = graph_client.post(
        f"/v1/spaces/{space_id}/connector-proposals",
        headers=headers,
        json={
            "connector_slug": "pubmed-phase9",
            "display_name": "PubMed Phase 9",
            "connector_kind": "document_source",
            "domain_context": "genomics",
            "metadata_payload": {"runtime": "external"},
            "mapping_payload": {
                "field_mappings": [
                    {
                        "source_field": "gene",
                        "target_dimension": "entity_type",
                        "target_id": "GENE",
                    },
                    {
                        "source_field": "association",
                        "target_dimension": "relation_type",
                        "target_id": "ASSOCIATED_WITH",
                    },
                ],
            },
            "evidence_payload": {"source": "phase9-test"},
            "source_ref": "phase9-connector",
        },
    )
    assert proposal_response.status_code == 201, proposal_response.text
    payload = proposal_response.json()
    assert payload["validation_payload"]["valid"] is True
    assert payload["approval_payload"] == {}

    detail_response = graph_client.get(
        f"/v1/spaces/{space_id}/connector-proposals/{payload['id']}",
        headers=headers,
    )
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["id"] == payload["id"]

    approval_response = graph_client.post(
        f"/v1/spaces/{space_id}/connector-proposals/{payload['id']}/approve",
        headers=headers,
        json={"decision_reason": "Metadata and mappings are valid."},
    )
    assert approval_response.status_code == 200, approval_response.text
    approval_payload = approval_response.json()
    assert approval_payload["status"] == "APPROVED"
    assert approval_payload["approval_payload"]["approved_metadata_only"] is True
    assert approval_payload["approval_payload"]["connector_runtime_executed"] is False

    approved_list_response = graph_client.get(
        f"/v1/spaces/{space_id}/connector-proposals",
        headers=headers,
        params={"status": "APPROVED"},
    )
    assert approved_list_response.status_code == 200, approved_list_response.text
    approved_ids = {
        item["id"] for item in approved_list_response.json()["connector_proposals"]
    }
    assert payload["id"] in approved_ids

    invalid_response = graph_client.post(
        f"/v1/spaces/{space_id}/connector-proposals",
        headers=headers,
        json={
            "connector_slug": "invalid-phase9",
            "display_name": "Invalid Phase 9 Connector",
            "connector_kind": "document_source",
            "domain_context": "genomics",
            "mapping_payload": {
                "field_mappings": [
                    {
                        "source_field": "missing",
                        "target_dimension": "entity_type",
                        "target_id": "NOT_A_REAL_TYPE",
                    },
                ],
            },
            "evidence_payload": {"source": "phase9-test"},
            "source_ref": "phase9-connector-invalid",
        },
    )
    assert invalid_response.status_code == 201, invalid_response.text
    invalid_payload = invalid_response.json()
    assert invalid_payload["validation_payload"]["valid"] is False

    invalid_approval_response = graph_client.post(
        f"/v1/spaces/{space_id}/connector-proposals/{invalid_payload['id']}/approve",
        headers=headers,
        json={"decision_reason": "Invalid mappings cannot be approved."},
    )
    assert invalid_approval_response.status_code == 400, invalid_approval_response.text

    changes_response = graph_client.post(
        f"/v1/spaces/{space_id}/connector-proposals/{invalid_payload['id']}/request-changes",
        headers=headers,
        json={"decision_reason": "Fix the missing entity type mapping."},
    )
    assert changes_response.status_code == 200, changes_response.text
    assert changes_response.json()["status"] == "CHANGES_REQUESTED"

    reject_response = graph_client.post(
        f"/v1/spaces/{space_id}/connector-proposals/{invalid_payload['id']}/reject",
        headers=headers,
        json={"decision_reason": "Rejected after requested changes."},
    )
    assert reject_response.status_code == 200, reject_response.text
    assert reject_response.json()["status"] == "REJECTED"

    rejected_list_response = graph_client.get(
        f"/v1/spaces/{space_id}/connector-proposals",
        headers=headers,
        params={"status": "REJECTED"},
    )
    assert rejected_list_response.status_code == 200, rejected_list_response.text
    rejected_ids = {
        item["id"]
        for item in rejected_list_response.json()["connector_proposals"]
    }
    assert invalid_payload["id"] in rejected_ids


def test_graph_service_phase9_rejects_cross_space_governance_mutations(
    graph_client: TestClient,
) -> None:
    first_fixture = _seed_space_with_projection()
    second_fixture = _seed_space_with_projection()
    first_headers = first_fixture["headers"]
    second_headers = second_fixture["headers"]
    first_space_id = first_fixture["space_id"]
    second_space_id = second_fixture["space_id"]
    suffix = str(uuid4())

    concept_response = graph_client.post(
        f"/v1/spaces/{first_space_id}/concepts/proposals",
        headers=first_headers,
        json={
            "domain_context": "general",
            "entity_type": "PHENOTYPE",
            "canonical_label": f"Cross-space concept {suffix}",
            "evidence_payload": {"source": "phase9-cross-space-test"},
            "source_ref": f"phase9-cross-space-concept:{suffix}",
        },
    )
    assert concept_response.status_code == 201, concept_response.text
    concept_payload = concept_response.json()

    foreign_approve_response = graph_client.post(
        f"/v1/spaces/{second_space_id}/concepts/proposals/{concept_payload['id']}/approve",
        headers=second_headers,
        json={"decision_reason": "This should not cross spaces."},
    )
    assert foreign_approve_response.status_code == 404, foreign_approve_response.text

    unchanged_concept_response = graph_client.get(
        f"/v1/spaces/{first_space_id}/concepts/proposals/{concept_payload['id']}",
        headers=first_headers,
    )
    assert unchanged_concept_response.status_code == 200, unchanged_concept_response.text
    assert unchanged_concept_response.json()["status"] == "SUBMITTED"

    graph_change_response = graph_client.post(
        f"/v1/spaces/{first_space_id}/graph-change-proposals",
        headers=first_headers,
        json={
            "concepts": [
                {
                    "local_id": "gene-med13",
                    "domain_context": "general",
                    "entity_type": "GENE",
                    "canonical_label": "MED13",
                    "external_refs": [{"namespace": "hgnc", "identifier": "MED13"}],
                },
                {
                    "local_id": "phenotype-cross-space",
                    "domain_context": "general",
                    "entity_type": "PHENOTYPE",
                    "canonical_label": f"Cross-space phenotype {suffix}",
                },
            ],
            "claims": [
                {
                    "source_local_id": "gene-med13",
                    "target_local_id": "phenotype-cross-space",
                    "relation_type": "ASSOCIATED_WITH",
                    "assessment": _SUPPORTED_ASSESSMENT,
                    "claim_text": "MED13 is associated with the phenotype.",
                    "evidence_payload": {"sentence": "Synthetic evidence."},
                },
            ],
            "source_ref": f"phase9-cross-space-graph-change:{suffix}",
        },
    )
    assert graph_change_response.status_code == 201, graph_change_response.text
    graph_change_payload = graph_change_response.json()

    foreign_graph_reject_response = graph_client.post(
        f"/v1/spaces/{second_space_id}/graph-change-proposals/{graph_change_payload['id']}/reject",
        headers=second_headers,
        json={"decision_reason": "This should not cross spaces."},
    )
    assert foreign_graph_reject_response.status_code == 404, (
        foreign_graph_reject_response.text
    )

    connector_response = graph_client.post(
        f"/v1/spaces/{first_space_id}/connector-proposals",
        headers=first_headers,
        json={
            "connector_slug": f"cross-space-{suffix}",
            "display_name": "Cross Space Connector",
            "connector_kind": "document_source",
            "domain_context": "genomics",
            "mapping_payload": {
                "field_mappings": [
                    {
                        "source_field": "gene",
                        "target_dimension": "entity_type",
                        "target_id": "GENE",
                    },
                ],
            },
            "evidence_payload": {"source": "phase9-cross-space-test"},
            "source_ref": f"phase9-cross-space-connector:{suffix}",
        },
    )
    assert connector_response.status_code == 201, connector_response.text
    connector_payload = connector_response.json()

    foreign_connector_approve_response = graph_client.post(
        f"/v1/spaces/{second_space_id}/connector-proposals/{connector_payload['id']}/approve",
        headers=second_headers,
        json={"decision_reason": "This should not cross spaces."},
    )
    assert foreign_connector_approve_response.status_code == 404, (
        foreign_connector_approve_response.text
    )

    with graph_database.SessionLocal() as session:
        second_space = session.get(GraphSpaceModel, second_space_id)
        assert second_space is not None
        second_space.settings = {
            "ai_full_mode": {
                "governance_mode": "ai_full",
                "trusted_principals": ["agent:phase9-cross-space"],
                "min_confidence": 0.85,
            },
        }
        session.commit()

    foreign_ai_decision_response = graph_client.post(
        f"/v1/spaces/{second_space_id}/ai-decisions",
        headers=second_headers,
        json={
            "target_type": "concept_proposal",
            "target_id": concept_payload["id"],
            "action": "APPROVE",
            "ai_principal": "agent:phase9-cross-space",
            "confidence_assessment": {
                **_DECISION_CONFIDENCE_ASSESSMENT,
                "rationale": "This should not cross spaces.",
            },
            "risk_tier": "low",
            "input_hash": concept_payload["proposal_hash"],
            "evidence_payload": {"rationale": "This should not cross spaces."},
            "decision_payload": {},
        },
    )
    assert foreign_ai_decision_response.status_code == 404, (
        foreign_ai_decision_response.text
    )

    decisions_response = graph_client.get(
        f"/v1/spaces/{second_space_id}/ai-decisions",
        headers=second_headers,
        params={"target_type": "concept_proposal"},
    )
    assert decisions_response.status_code == 200, decisions_response.text
    assert decisions_response.json()["total"] == 0


def test_graph_service_mechanistic_gaps_max_hops_cap_rejected(
    graph_client: TestClient,
) -> None:
    """The ``max_hops`` query parameter must be in ``[2, 4]``.

    Out-of-range values are rejected with a FastAPI 422 before the handler
    runs, and valid values (2, 3, 4) return 200 with an (empty) payload
    for an empty space.
    """
    fixture = _seed_space_with_projection()
    headers = fixture["headers"]
    space_id = fixture["space_id"]

    # Out of range (too high) — 422.
    too_high = graph_client.get(
        f"/v1/spaces/{space_id}/relations/mechanistic-gaps",
        headers=headers,
        params={"max_hops": 5},
    )
    assert too_high.status_code == 422, too_high.text

    # Out of range (too low) — 422.
    too_low = graph_client.get(
        f"/v1/spaces/{space_id}/relations/mechanistic-gaps",
        headers=headers,
        params={"max_hops": 1},
    )
    assert too_low.status_code == 422, too_low.text

    # Default (omitted) — 200, behaves as legacy 2-hop.
    default_response = graph_client.get(
        f"/v1/spaces/{space_id}/relations/mechanistic-gaps",
        headers=headers,
    )
    assert default_response.status_code == 200, default_response.text
    default_payload = default_response.json()
    assert default_payload["max_hops"] == 2

    # Valid explicit values.
    for valid_value in (2, 3, 4):
        response = graph_client.get(
            f"/v1/spaces/{space_id}/relations/mechanistic-gaps",
            headers=headers,
            params={"max_hops": valid_value},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["max_hops"] == valid_value
