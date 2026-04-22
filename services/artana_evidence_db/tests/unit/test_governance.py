from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_db.biomedical_concept_bootstrap import (
    seed_biomedical_starter_concepts,
    seed_biomedical_starter_concepts_for_existing_spaces,
)
from artana_evidence_db.concept_management_service import ConceptManagementService
from artana_evidence_db.concept_repository import GraphConceptRepository
from artana_evidence_db.dictionary_management_service import DictionaryManagementService
from artana_evidence_db.dictionary_repository import GraphDictionaryRepository
from artana_evidence_db.governance import (
    build_concept_repository as build_service_concept_repository,
)
from artana_evidence_db.governance import (
    build_concept_service as build_service_concept_service,
)
from artana_evidence_db.governance import (
    build_dictionary_repository as build_service_dictionary_repository,
)
from artana_evidence_db.governance import (
    build_dictionary_service as build_service_dictionary_service,
)
from artana_evidence_db.graph_domain_config import (
    GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
    GraphDictionaryLoadingConfig,
)
from artana_evidence_db.kernel_concept_models import (
    ConceptAliasModel,
    ConceptMemberModel,
    ConceptSetModel,
)
from artana_evidence_db.kernel_dictionary_models import (
    DictionaryDomainContextModel,
    DictionaryEntityTypeModel,
    DictionaryRelationTypeModel,
)
from artana_evidence_db.space_models import (
    GraphSpaceModel,
    GraphSpaceStatusEnum,
)
from sqlalchemy.orm import Session


def test_build_governance_repositories_use_service_local_persistence(
    db_session: Session,
) -> None:
    dictionary_loading_extension = GraphDictionaryLoadingConfig(
        builtin_domain_contexts=(
            GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG.builtin_domain_contexts
        ),
    )
    dictionary_repo = build_service_dictionary_repository(
        db_session,
        dictionary_loading_extension=dictionary_loading_extension,
    )
    concept_repo = build_service_concept_repository(db_session)

    assert isinstance(dictionary_repo, GraphDictionaryRepository)
    assert isinstance(concept_repo, GraphConceptRepository)
    assert (
        dictionary_repo.__class__.__module__
        == "artana_evidence_db.dictionary_repository"
    )
    assert concept_repo.__class__.__module__ == "artana_evidence_db.concept_repository"
    assert (
        build_service_dictionary_repository(
            db_session,
            dictionary_loading_extension=dictionary_loading_extension,
        ).__class__
        is dictionary_repo.__class__
    )
    assert (
        build_service_concept_repository(db_session).__class__ is concept_repo.__class__
    )


def test_build_governance_services_use_service_local_repositories(
    db_session: Session,
) -> None:
    dictionary_loading_extension = GraphDictionaryLoadingConfig(
        builtin_domain_contexts=(
            GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG.builtin_domain_contexts
        ),
    )
    service_dictionary_service = build_service_dictionary_service(
        db_session,
        dictionary_loading_extension=dictionary_loading_extension,
    )
    service_concept_service = build_service_concept_service(db_session)

    assert isinstance(service_dictionary_service, DictionaryManagementService)
    assert isinstance(service_concept_service, ConceptManagementService)

    assert service_dictionary_service._dictionary.__class__.__module__ == (
        "artana_evidence_db.dictionary_repository"
    )  # noqa: SLF001
    assert service_concept_service._concepts.__class__.__module__ == (  # noqa: SLF001
        "artana_evidence_db.concept_repository"
    )
    assert isinstance(
        service_dictionary_service._dictionary,
        GraphDictionaryRepository,
    )  # noqa: SLF001
    assert isinstance(
        service_concept_service._concepts,
        GraphConceptRepository,
    )  # noqa: SLF001


def test_graph_governance_repository_seeds_pack_domain_contexts(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del monkeypatch
    repository = build_service_dictionary_repository(
        db_session,
        dictionary_loading_extension=GraphDictionaryLoadingConfig(
            builtin_domain_contexts=(
                GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG.builtin_domain_contexts
            ),
        ),
    )

    repository._ensure_domain_context_reference("clinical")  # noqa: SLF001

    clinical = repository._session.get(
        DictionaryDomainContextModel,
        "clinical",
    )  # noqa: SLF001
    assert clinical is not None
    assert clinical.description == "Clinical and biomedical literature domain context."


def test_graph_governance_repository_seeds_builtin_entity_and_relation_types(
    db_session: Session,
) -> None:
    repository = build_service_dictionary_repository(
        db_session,
        dictionary_loading_extension=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
    )

    entity_types = repository.find_entity_types()
    relation_types = repository.find_relation_types()

    assert {
        "GENE",
        "PHENOTYPE",
        "SYNDROME",
        "PROTEIN_COMPLEX",
        "SIGNALING_PATHWAY",
        "MOLECULAR_FUNCTION",
    }.issubset({entity_type.id for entity_type in entity_types})
    assert {
        "ASSOCIATED_WITH",
        "CAUSES",
        "REGULATES",
        "COMPONENT_OF",
        "PARTICIPATES_IN",
    }.issubset({relation_type.id for relation_type in relation_types})
    assert db_session.get(DictionaryEntityTypeModel, "GENE") is not None
    assert db_session.get(DictionaryRelationTypeModel, "REGULATES") is not None


def test_seed_biomedical_starter_concepts_is_idempotent(
    db_session: Session,
) -> None:
    space_id = uuid4()

    seed_biomedical_starter_concepts(
        db_session,
        research_space_id=space_id,
    )
    seed_biomedical_starter_concepts(
        db_session,
        research_space_id=space_id,
    )

    concept_sets = db_session.query(ConceptSetModel).all()
    concept_members = db_session.query(ConceptMemberModel).all()
    concept_aliases = db_session.query(ConceptAliasModel).all()

    assert len(concept_sets) == 4
    assert len(concept_members) == 15
    assert len(concept_aliases) == 10
    assert {model.canonical_label for model in concept_members} >= {
        "MED13",
        "Developmental Delay",
        "Wnt Signaling",
        "Loss of Function",
    }


def test_seed_biomedical_starter_concepts_for_existing_spaces(
    db_session: Session,
) -> None:
    first_space_id = uuid4()
    second_space_id = uuid4()
    owner_id = uuid4()
    db_session.add_all(
        [
            GraphSpaceModel(
                id=first_space_id,
                slug="first-space",
                name="First Space",
                description=None,
                owner_id=owner_id,
                status=GraphSpaceStatusEnum.ACTIVE,
                settings={},
            ),
            GraphSpaceModel(
                id=second_space_id,
                slug="second-space",
                name="Second Space",
                description=None,
                owner_id=owner_id,
                status=GraphSpaceStatusEnum.ACTIVE,
                settings={},
            ),
        ],
    )
    db_session.flush()

    seed_biomedical_starter_concepts_for_existing_spaces(db_session)

    seeded_space_ids = {
        model.research_space_id for model in db_session.query(ConceptSetModel).all()
    }
    assert seeded_space_ids == {first_space_id, second_space_id}
