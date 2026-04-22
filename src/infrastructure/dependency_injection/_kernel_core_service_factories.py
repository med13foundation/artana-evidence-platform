# mypy: disable-error-code=no-untyped-def
"""Core kernel service factory mixin."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_db.claim_evidence_repository import (
    SqlAlchemyKernelClaimEvidenceRepository,
)
from artana_evidence_db.claim_participant_repository import (
    SqlAlchemyKernelClaimParticipantRepository,
)
from artana_evidence_db.claim_relation_repository import (
    SqlAlchemyKernelClaimRelationRepository,
)
from artana_evidence_db.composition import build_entity_repository
from artana_evidence_db.dictionary_management_service import DictionaryManagementService
from artana_evidence_db.embedding_models import (
    KernelEntitySimilarityResult,
    KernelEntitySimilarityScoreBreakdown,
)
from artana_evidence_db.entity_embedding_repository import (
    SqlAlchemyEntityEmbeddingRepository,
)
from artana_evidence_db.entity_service import KernelEntityService
from artana_evidence_db.governance import (
    build_concept_repository,
    build_concept_service,
    build_dictionary_repository,
    build_dictionary_service,
)
from artana_evidence_db.graph_domain_config import (
    GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
)
from artana_evidence_db.graph_query_repository import SqlAlchemyGraphQueryRepository
from artana_evidence_db.hybrid_graph_errors import EmbeddingNotReadyError
from artana_evidence_db.hybrid_graph_scoring import (
    compute_jaccard_overlap,
    compute_similarity_score,
)
from artana_evidence_db.kernel_repositories import (
    SqlAlchemyKernelObservationRepository,
    SqlAlchemyKernelReasoningPathRepository,
    SqlAlchemyKernelSourceDocumentReferenceRepository,
    SqlAlchemyKernelSpaceRegistryRepository,
)
from artana_evidence_db.kernel_runtime_factories import (
    build_relation_repository,
    create_kernel_relation_suggestion_service,
)
from artana_evidence_db.observation_service import KernelObservationService
from artana_evidence_db.provenance_repository import SqlAlchemyProvenanceRepository
from artana_evidence_db.provenance_service import ProvenanceService
from artana_evidence_db.relation_claim_repository import (
    SqlAlchemyKernelRelationClaimRepository,
)
from artana_evidence_db.relation_projection_source_repository import (
    SqlAlchemyKernelRelationProjectionSourceRepository,
)
from artana_evidence_db.relation_service import KernelRelationService

from src.infrastructure.embeddings import HybridTextEmbeddingProvider

if TYPE_CHECKING:
    from artana_evidence_db.governance_ports import (
        DictionarySearchHarnessPort,
    )
    from artana_evidence_db.kernel_repositories import (
        EntityEmbeddingRepository,
        KernelEntityRepository,
        KernelObservationRepository,
        KernelRelationRepository,
    )
    from sqlalchemy.orm import Session

    from src.domain.ports import ConceptPort, DictionaryPort


class _CompatibilityEntitySimilarityService:
    """Minimal compatibility implementation for the dormant similarity factory."""

    def __init__(
        self,
        *,
        entity_repo: object,
        embedding_repo: SqlAlchemyEntityEmbeddingRepository,
        embedding_provider: HybridTextEmbeddingProvider,
    ) -> None:
        self._entities = entity_repo
        self._embeddings = embedding_repo
        self._embedding_provider = embedding_provider

    def get_similar_entities(
        self,
        *,
        research_space_id: str,
        entity_id: str,
        limit: int,
        min_similarity: float,
        target_entity_types: list[str] | None = None,
    ) -> list[KernelEntitySimilarityResult]:
        source_entity = self._entities.get_by_id(entity_id)
        if source_entity is None or str(source_entity.research_space_id) != str(
            research_space_id,
        ):
            msg = f"Entity {entity_id} not found in research space {research_space_id}"
            raise ValueError(msg)

        source_embedding = self._embeddings.get_embedding(entity_id=entity_id)
        if source_embedding is None:
            msg = (
                f"Embedding not ready for entity {entity_id}. "
                "Run embedding refresh before similarity search."
            )
            raise EmbeddingNotReadyError(msg)

        source_neighbor_ids = set(
            self._embeddings.list_neighbor_ids_for_overlap(
                research_space_id=research_space_id,
                entity_id=entity_id,
            ),
        )
        candidates = self._embeddings.find_similar_entities(
            research_space_id=research_space_id,
            entity_id=entity_id,
            limit=limit,
            min_similarity=min_similarity,
            target_entity_types=target_entity_types,
        )
        results: list[KernelEntitySimilarityResult] = []
        for candidate in candidates:
            target_neighbors = set(
                self._embeddings.list_neighbor_ids_for_overlap(
                    research_space_id=research_space_id,
                    entity_id=str(candidate.entity_id),
                ),
            )
            graph_overlap_score = compute_jaccard_overlap(
                source_neighbor_ids,
                target_neighbors,
            )
            similarity_score = compute_similarity_score(
                vector_score=candidate.vector_score,
                graph_overlap_score=graph_overlap_score,
            )
            if similarity_score < min_similarity:
                continue
            results.append(
                KernelEntitySimilarityResult(
                    entity_id=candidate.entity_id,
                    entity_type=candidate.entity_type,
                    display_label=candidate.display_label,
                    similarity_score=similarity_score,
                    score_breakdown=KernelEntitySimilarityScoreBreakdown(
                        vector_score=candidate.vector_score,
                        graph_overlap_score=graph_overlap_score,
                    ),
                ),
            )
        results.sort(key=lambda item: item.similarity_score, reverse=True)
        return results[: max(1, limit)]

    def refresh_embeddings(
        self,
        *,
        research_space_id: str,
        entity_ids: list[str] | None = None,
        limit: int = 500,
        model_name: str | None = None,
        embedding_version: int | None = None,
    ) -> dict[str, object]:
        del model_name, embedding_version
        entities: list[object] = []
        missing_entities: list[str] = []
        if entity_ids is None:
            entities = self._entities.find_by_research_space(
                research_space_id,
                limit=max(1, limit),
                offset=0,
            )
        else:
            for entity_id in entity_ids:
                entity = self._entities.get_by_id(entity_id)
                if entity is None or str(entity.research_space_id) != str(
                    research_space_id,
                ):
                    missing_entities.append(str(entity_id))
                    continue
                entities.append(entity)
        refreshed = 0
        unchanged = 0
        for entity in entities:
            canonical_text = " ".join(
                part
                for part in [
                    getattr(entity, "entity_type", ""),
                    getattr(entity, "display_label", "") or "",
                ]
                if isinstance(part, str) and part.strip()
            )
            if not canonical_text:
                unchanged += 1
                continue
            embedding = self._embedding_provider.embed_text(canonical_text)
            fingerprint = canonical_text
            existing = self._embeddings.get_embedding(entity_id=str(entity.id))
            if (
                existing is not None
                and existing.source_fingerprint == fingerprint
                and existing.embedding == embedding
            ):
                unchanged += 1
                continue
            self._embeddings.upsert_embedding(
                research_space_id=research_space_id,
                entity_id=str(entity.id),
                embedding=embedding,
                embedding_model="text-embedding-3-small",
                embedding_version=1,
                source_fingerprint=fingerprint,
            )
            refreshed += 1
        return {
            "requested": len(entity_ids) if entity_ids is not None else len(entities),
            "processed": len(entities),
            "refreshed": refreshed,
            "unchanged": unchanged,
            "missing_entities": missing_entities,
        }


def _build_dictionary_service_with_optional_harness(
    session: Session,
    *,
    dictionary_search_harness: DictionarySearchHarnessPort | None = None,
    embedding_provider: HybridTextEmbeddingProvider | None = None,
) -> DictionaryPort:
    if dictionary_search_harness is None:
        return build_dictionary_service(
            session,
            dictionary_loading_extension=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
            embedding_provider=embedding_provider,
        )

    return DictionaryManagementService(
        dictionary_repo=build_dictionary_repository(
            session,
            dictionary_loading_extension=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
        ),
        dictionary_search_harness=dictionary_search_harness,
        embedding_provider=embedding_provider or HybridTextEmbeddingProvider(),
    )


class KernelCoreServiceFactoryMixin:
    """Factory methods for core dictionary, entity, relation, and provenance services."""

    @staticmethod
    def build_dictionary_repository(session: Session):
        return build_dictionary_repository(
            session,
            dictionary_loading_extension=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
        )

    @staticmethod
    def _build_dictionary_repository(session: Session):
        return build_dictionary_repository(
            session,
            dictionary_loading_extension=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
        )

    @staticmethod
    def _build_concept_repository(session: Session):
        return build_concept_repository(session)

    @staticmethod
    def build_provenance_repository(session: Session):
        return SqlAlchemyProvenanceRepository(session)

    @staticmethod
    def _build_provenance_repository(session: Session):
        return SqlAlchemyProvenanceRepository(session)

    @staticmethod
    def _build_graph_query_repository(session: Session):
        return SqlAlchemyGraphQueryRepository(
            session,
            relation_repository=build_relation_repository(session),
        )

    @staticmethod
    def _build_entity_repository(session: Session) -> KernelEntityRepository:
        return build_entity_repository(session)

    def create_kernel_entity_service(
        self,
        session: Session,
    ):
        return KernelEntityService(
            entity_repo=build_entity_repository(session),
            dictionary_repo=build_dictionary_repository(
                session,
                dictionary_loading_extension=GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG,
            ),
        )

    @staticmethod
    def _build_entity_embedding_repository(
        session: Session,
    ) -> EntityEmbeddingRepository:
        return SqlAlchemyEntityEmbeddingRepository(session)

    @staticmethod
    def _build_observation_repository(
        session: Session,
    ) -> KernelObservationRepository:
        return SqlAlchemyKernelObservationRepository(session)

    @staticmethod
    def _build_relation_repository(
        session: Session,
    ) -> KernelRelationRepository:
        return build_relation_repository(session)

    @staticmethod
    def _build_relation_claim_repository(
        session: Session,
    ):
        return SqlAlchemyKernelRelationClaimRepository(session)

    @staticmethod
    def _build_relation_projection_source_repository(
        session: Session,
    ):
        return SqlAlchemyKernelRelationProjectionSourceRepository(session)

    @staticmethod
    def _build_claim_participant_repository(
        session: Session,
    ):
        return SqlAlchemyKernelClaimParticipantRepository(session)

    @staticmethod
    def _build_claim_evidence_repository(
        session: Session,
    ):
        return SqlAlchemyKernelClaimEvidenceRepository(session)

    @staticmethod
    def _build_claim_relation_repository(
        session: Session,
    ):
        return SqlAlchemyKernelClaimRelationRepository(session)

    @staticmethod
    def _build_reasoning_path_repository(
        session: Session,
    ):
        return SqlAlchemyKernelReasoningPathRepository(session)

    @staticmethod
    def _build_space_registry_repository(
        session: Session,
    ):
        return SqlAlchemyKernelSpaceRegistryRepository(session)

    @staticmethod
    def _build_source_document_reference_repository(
        session: Session,
    ):
        return SqlAlchemyKernelSourceDocumentReferenceRepository(session)

    def _build_dictionary_service(
        self,
        session: Session,
        *,
        dictionary_search_harness: DictionarySearchHarnessPort | None = None,
        embedding_provider: HybridTextEmbeddingProvider | None = None,
    ) -> DictionaryPort:
        return _build_dictionary_service_with_optional_harness(
            session,
            dictionary_search_harness=dictionary_search_harness,
            embedding_provider=embedding_provider,
        )

    def build_dictionary_service(
        self,
        session: Session,
        *,
        dictionary_search_harness: DictionarySearchHarnessPort | None = None,
        embedding_provider: HybridTextEmbeddingProvider | None = None,
    ) -> DictionaryPort:
        return _build_dictionary_service_with_optional_harness(
            session,
            dictionary_search_harness=dictionary_search_harness,
            embedding_provider=embedding_provider,
        )

    @staticmethod
    def build_entity_repository(session: Session) -> KernelEntityRepository:
        return build_entity_repository(session)

    def create_kernel_entity_similarity_service(
        self,
        session: Session,
    ):
        return _CompatibilityEntitySimilarityService(
            entity_repo=build_entity_repository(session),
            embedding_repo=SqlAlchemyEntityEmbeddingRepository(session),
            embedding_provider=HybridTextEmbeddingProvider(),
        )

    def create_kernel_observation_service(
        self,
        session: Session,
        *,
        dictionary_service: DictionaryPort | None = None,
        entity_repository: KernelEntityRepository | None = None,
        observation_repository: KernelObservationRepository | None = None,
    ):
        return KernelObservationService(
            observation_repo=(
                observation_repository or SqlAlchemyKernelObservationRepository(session)
            ),
            entity_repo=entity_repository or build_entity_repository(session),
            dictionary_repo=(
                dictionary_service or self.create_dictionary_management_service(session)
            ),
        )

    def create_kernel_relation_service(
        self,
        session: Session,
    ):
        return KernelRelationService(
            relation_repo=build_relation_repository(session),
            entity_repo=build_entity_repository(session),
        )

    def create_kernel_relation_suggestion_service(
        self,
        session: Session,
    ):
        return create_kernel_relation_suggestion_service(session)

    def create_dictionary_management_service(
        self,
        session: Session,
    ) -> DictionaryPort:
        return _build_dictionary_service_with_optional_harness(
            session,
            embedding_provider=HybridTextEmbeddingProvider(),
        )

    def create_concept_management_service(
        self,
        session: Session,
    ) -> ConceptPort:
        return build_concept_service(session)

    def create_provenance_service(
        self,
        session: Session,
    ):
        return ProvenanceService(
            provenance_repo=SqlAlchemyProvenanceRepository(session),
        )


__all__ = ["KernelCoreServiceFactoryMixin"]
