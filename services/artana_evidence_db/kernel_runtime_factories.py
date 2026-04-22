"""Service-local graph runtime factory helpers."""

from __future__ import annotations

from artana_evidence_db.entity_claim_summary_projector import (
    KernelEntityClaimSummaryProjector,
)
from artana_evidence_db.entity_embedding_repository import (
    SqlAlchemyEntityEmbeddingRepository,
)
from artana_evidence_db.entity_embedding_status_projector import (
    KernelEntityEmbeddingStatusProjector,
)
from artana_evidence_db.entity_embedding_status_repository import (
    SqlAlchemyEntityEmbeddingStatusRepository,
)
from artana_evidence_db.entity_embedding_status_service import (
    KernelEntityEmbeddingStatusService,
)
from artana_evidence_db.entity_mechanism_paths_projector import (
    KernelEntityMechanismPathsProjector,
)
from artana_evidence_db.entity_neighbors_projector import KernelEntityNeighborsProjector
from artana_evidence_db.entity_relation_summary_projector import (
    KernelEntityRelationSummaryProjector,
)
from artana_evidence_db.governance import build_dictionary_repository
from artana_evidence_db.kernel_relation_suggestion_service import (
    KernelRelationSuggestionService,
)
from artana_evidence_db.kernel_repositories import (
    SqlAlchemyKernelEntityRepository,
    SqlAlchemyKernelRelationRepository,
)
from artana_evidence_db.phi_encryption_support import (
    build_phi_encryption_service_from_env,
    is_phi_encryption_enabled,
)
from artana_evidence_db.read_model_support import (
    ProjectorBackedGraphReadModelUpdateDispatcher,
)
from artana_evidence_db.relation_autopromotion_policy import AutoPromotionPolicy
from artana_evidence_db.runtime.pack_registry import create_graph_domain_pack
from artana_evidence_db.text_embedding_provider import (
    HybridTextEmbeddingProvider as DefaultHybridTextEmbeddingProvider,
)
from sqlalchemy.orm import Session

HybridTextEmbeddingProvider = DefaultHybridTextEmbeddingProvider


def _build_relation_autopromotion_policy() -> AutoPromotionPolicy:
    """Resolve relation auto-promotion policy at composition time."""
    return AutoPromotionPolicy.from_environment(
        defaults=create_graph_domain_pack().relation_autopromotion_defaults,
    )


def _build_entity_repository(session: Session) -> SqlAlchemyKernelEntityRepository:
    enable_phi_encryption = is_phi_encryption_enabled()
    phi_encryption_service = (
        build_phi_encryption_service_from_env() if enable_phi_encryption else None
    )
    return SqlAlchemyKernelEntityRepository(
        session,
        phi_encryption_service=phi_encryption_service,
        enable_phi_encryption=enable_phi_encryption,
    )


def _build_entity_embedding_repository(
    session: Session,
) -> SqlAlchemyEntityEmbeddingRepository:
    return SqlAlchemyEntityEmbeddingRepository(session)


def _build_entity_embedding_status_repository(
    session: Session,
) -> SqlAlchemyEntityEmbeddingStatusRepository:
    return SqlAlchemyEntityEmbeddingStatusRepository(session)


def _build_embedding_provider() -> object:
    """Resolve the graph-owned embedding provider."""
    if callable(HybridTextEmbeddingProvider):
        return HybridTextEmbeddingProvider()
    message = "HybridTextEmbeddingProvider is not configured as a callable provider"
    raise RuntimeError(message)


def create_kernel_entity_embedding_status_service(
    session: Session,
) -> KernelEntityEmbeddingStatusService:
    """Build graph-owned embedding readiness and refresh service."""
    return KernelEntityEmbeddingStatusService(
        entity_repo=_build_entity_repository(session),
        embedding_repo=_build_entity_embedding_repository(session),
        status_repo=_build_entity_embedding_status_repository(session),
        embedding_provider=_build_embedding_provider(),
    )


def build_relation_repository(
    session: Session,
) -> SqlAlchemyKernelRelationRepository:
    """Build the graph relation repository with local autopromotion policy."""
    return SqlAlchemyKernelRelationRepository(
        session,
        auto_promotion_policy=_build_relation_autopromotion_policy(),
    )


def create_kernel_relation_suggestion_service(
    session: Session,
) -> KernelRelationSuggestionService:
    """Build relation suggestions from graph-local runtime dependencies."""
    graph_domain_pack = create_graph_domain_pack()
    return KernelRelationSuggestionService(
        entity_repo=_build_entity_repository(session),
        relation_repo=build_relation_repository(session),
        dictionary_repo=build_dictionary_repository(
            session,
            dictionary_loading_extension=graph_domain_pack.dictionary_loading_extension,
        ),
        embedding_repo=_build_entity_embedding_repository(session),
        embedding_status_repo=_build_entity_embedding_status_repository(session),
        relation_suggestion_extension=graph_domain_pack.relation_suggestion_extension,
    )


def build_graph_read_model_update_dispatcher(
    session: Session,
) -> ProjectorBackedGraphReadModelUpdateDispatcher:
    """Build the current graph read-model dispatcher runtime adapter."""
    entity_claim_summary_projector = KernelEntityClaimSummaryProjector(session)
    entity_embedding_status_projector = KernelEntityEmbeddingStatusProjector(
        create_kernel_entity_embedding_status_service(session),
    )
    entity_mechanism_paths_projector = KernelEntityMechanismPathsProjector(session)
    entity_neighbors_projector = KernelEntityNeighborsProjector(session)
    entity_relation_summary_projector = KernelEntityRelationSummaryProjector(session)
    return ProjectorBackedGraphReadModelUpdateDispatcher(
        projectors={
            entity_claim_summary_projector.definition.name: (
                entity_claim_summary_projector
            ),
            entity_embedding_status_projector.definition.name: (
                entity_embedding_status_projector
            ),
            entity_mechanism_paths_projector.definition.name: (
                entity_mechanism_paths_projector
            ),
            entity_neighbors_projector.definition.name: entity_neighbors_projector,
            entity_relation_summary_projector.definition.name: (
                entity_relation_summary_projector
            ),
        },
    )


__all__ = [
    "build_graph_read_model_update_dispatcher",
    "build_relation_repository",
    "create_kernel_entity_embedding_status_service",
    "create_kernel_relation_suggestion_service",
]
