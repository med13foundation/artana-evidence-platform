"""Service-local governance adapters for the standalone graph API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_db.concept_decision_harness import (
    DeterministicConceptDecisionHarnessAdapter,
)
from artana_evidence_db.concept_repository import GraphConceptRepository
from artana_evidence_db.deterministic_dictionary_search_harness import (
    GraphDeterministicDictionarySearchHarness,
)
from artana_evidence_db.dictionary_repository import GraphDictionaryRepository
from artana_evidence_db.kernel_services import (
    ConceptManagementService,
    DictionaryManagementService,
)

if TYPE_CHECKING:
    from typing import Protocol

    from artana_evidence_db.graph_domain_config import (
        GraphDictionaryLoadingExtension,
    )
    from artana_evidence_db.semantic_ports import ConceptPort, DictionaryPort
    from sqlalchemy.orm import Session

    class HybridTextEmbeddingProvider(Protocol):
        pass


def build_dictionary_repository(
    session: Session,
    *,
    dictionary_loading_extension: GraphDictionaryLoadingExtension,
) -> GraphDictionaryRepository:
    """Build the graph-service dictionary repository adapter."""
    return GraphDictionaryRepository(
        session,
        builtin_domain_contexts=dictionary_loading_extension.builtin_domain_contexts,
        builtin_entity_types=dictionary_loading_extension.builtin_entity_types,
        builtin_relation_types=dictionary_loading_extension.builtin_relation_types,
        builtin_relation_synonyms=dictionary_loading_extension.builtin_relation_synonyms,
        builtin_relation_constraints=(
            dictionary_loading_extension.builtin_relation_constraints
        ),
        builtin_qualifier_definitions=(
            dictionary_loading_extension.builtin_qualifier_definitions
        ),
    )


def seed_builtin_dictionary_entries(
    session: Session,
    *,
    dictionary_loading_extension: GraphDictionaryLoadingExtension,
) -> None:
    """Persist pack-owned dictionary defaults for the active graph runtime."""
    repository = GraphDictionaryRepository(
        session,
        builtin_domain_contexts=dictionary_loading_extension.builtin_domain_contexts,
        builtin_entity_types=dictionary_loading_extension.builtin_entity_types,
        builtin_relation_types=dictionary_loading_extension.builtin_relation_types,
        builtin_relation_synonyms=dictionary_loading_extension.builtin_relation_synonyms,
        builtin_relation_constraints=(
            dictionary_loading_extension.builtin_relation_constraints
        ),
        builtin_qualifier_definitions=(
            dictionary_loading_extension.builtin_qualifier_definitions
        ),
    )
    repository.seed_builtin_dictionary_entries()


def build_concept_repository(session: Session) -> GraphConceptRepository:
    """Build the graph-service concept repository adapter."""
    return GraphConceptRepository(session)


def build_dictionary_service(
    session: Session,
    *,
    dictionary_loading_extension: GraphDictionaryLoadingExtension,
    embedding_provider: HybridTextEmbeddingProvider | None = None,
) -> DictionaryPort:
    """Build the graph-service dictionary service from local governance adapters."""
    dictionary_repo = build_dictionary_repository(
        session,
        dictionary_loading_extension=dictionary_loading_extension,
    )
    return DictionaryManagementService(
        dictionary_repo=dictionary_repo,
        dictionary_search_harness=GraphDeterministicDictionarySearchHarness(
            dictionary_repo=dictionary_repo,
        ),
        embedding_provider=embedding_provider,
    )


def build_concept_service(session: Session) -> ConceptPort:
    """Build the graph-service concept service from local governance adapters."""
    return ConceptManagementService(
        concept_repo=build_concept_repository(session),
        concept_harness=DeterministicConceptDecisionHarnessAdapter(),
    )


__all__ = [
    "GraphConceptRepository",
    "GraphDictionaryRepository",
    "build_concept_repository",
    "build_concept_service",
    "build_dictionary_repository",
    "build_dictionary_service",
    "seed_builtin_dictionary_entries",
]
