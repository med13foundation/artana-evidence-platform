"""Service-local authz and graph dependency providers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_db.ai_full_mode_service import AIFullModeService
from artana_evidence_db.dictionary_proposal_service import DictionaryProposalService
from artana_evidence_db.graph_workflow_service import GraphWorkflowService
from artana_evidence_db.kernel_repositories import (
    SqlAlchemyKernelClaimEvidenceRepository,
    SqlAlchemyKernelClaimParticipantRepository,
    SqlAlchemyKernelClaimRelationRepository,
    SqlAlchemyKernelReasoningPathRepository,
    SqlAlchemyKernelRelationClaimRepository,
    SqlAlchemyKernelRelationProjectionSourceRepository,
    SqlAlchemyKernelSourceDocumentReferenceRepository,
    SqlAlchemyKernelSpaceAccessRepository,
    SqlAlchemyKernelSpaceMembershipRepository,
    SqlAlchemyKernelSpaceRegistryRepository,
    SqlAlchemyProvenanceRepository,
)
from artana_evidence_db.kernel_runtime_factories import (
    build_graph_read_model_update_dispatcher,
    create_kernel_entity_embedding_status_service,
    create_kernel_relation_suggestion_service,
)
from artana_evidence_db.kernel_services import (
    KernelClaimEvidenceService,
    KernelClaimParticipantBackfillService,
    KernelClaimParticipantService,
    KernelClaimProjectionReadinessService,
    KernelClaimRelationService,
    KernelEntityEmbeddingStatusService,
    KernelEntityService,
    KernelGraphViewService,
    KernelObservationService,
    KernelReasoningPathService,
    KernelRelationClaimService,
    KernelRelationProjectionMaterializationService,
    KernelRelationProjectionSourceService,
    KernelRelationService,
    ProvenanceService,
)
from artana_evidence_db.reasoning_path_service import (
    KernelReasoningPathInvalidationService,
)
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session

from .auth import (
    to_graph_access_role,
    to_graph_principal,
    to_graph_rls_session_context,
    to_graph_tenant_membership,
)
from .composition import (
    build_concept_service,
    build_dictionary_repository,
    build_dictionary_service,
    build_entity_repository,
    build_observation_service,
    build_relation_repository,
)
from .database import get_session, set_graph_rls_session_context
from .graph_access import evaluate_graph_tenant_access
from .graph_domain_config import GraphDictionaryLoadingExtension, GraphViewExtension
from .ports import SpaceAccessPort, SpaceRegistryPort
from .runtime.pack_registry import create_graph_domain_pack
from .semantic_ports import ConceptPort, DictionaryPort
from .space_membership import MembershipRole
from .user_models import User

if TYPE_CHECKING:
    from artana_evidence_db.kernel_services import KernelRelationSuggestionService


def get_space_registry_port(
    session: Session = Depends(get_session),
) -> SpaceRegistryPort:
    """Return the graph-local space registry adapter."""
    return SqlAlchemyKernelSpaceRegistryRepository(session)


def get_graph_dictionary_loading_extension() -> GraphDictionaryLoadingExtension:
    """Return the service-local dictionary-loading configuration."""
    return create_graph_domain_pack().dictionary_loading_extension


def get_graph_view_extension() -> GraphViewExtension:
    """Return the service-local graph view configuration."""
    return create_graph_domain_pack().view_extension


def get_space_membership_repository(
    session: Session = Depends(get_session),
) -> SqlAlchemyKernelSpaceMembershipRepository:
    """Return the graph-local space membership adapter."""
    return SqlAlchemyKernelSpaceMembershipRepository(session)


def get_space_access_port(
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    session: Session = Depends(get_session),
) -> SpaceAccessPort:
    """Return the graph-local space access adapter."""
    return SqlAlchemyKernelSpaceAccessRepository(
        session,
        space_registry=space_registry,
    )


def verify_space_membership(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
) -> None:
    """Verify that the caller can access one graph space."""
    principal = to_graph_principal(current_user)
    set_graph_rls_session_context(
        session,
        context=to_graph_rls_session_context(current_user),
    )

    if principal.is_platform_admin:
        return

    membership_role = space_access.get_effective_role(space_id, current_user.id)
    decision = evaluate_graph_tenant_access(
        principal=principal,
        tenant_membership=to_graph_tenant_membership(
            space_id=space_id,
            membership_role=membership_role,
        ),
    )
    if decision.allowed:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User is not a member of this graph space",
    )


def require_space_role(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
    required_role: MembershipRole,
) -> None:
    """Require one membership role or higher for a graph space."""
    principal = to_graph_principal(current_user)
    set_graph_rls_session_context(
        session,
        context=to_graph_rls_session_context(current_user),
    )

    if principal.is_platform_admin:
        return

    membership_role = space_access.get_effective_role(space_id, current_user.id)
    if membership_role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this graph space",
        )

    decision = evaluate_graph_tenant_access(
        principal=principal,
        tenant_membership=to_graph_tenant_membership(
            space_id=space_id,
            membership_role=membership_role,
        ),
        required_role=to_graph_access_role(required_role),
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User lacks permission for this operation",
        )


def get_kernel_entity_service(
    session: Session = Depends(get_session),
    dictionary_loading_extension: GraphDictionaryLoadingExtension = Depends(
        get_graph_dictionary_loading_extension,
    ),
) -> KernelEntityService:
    """Return kernel entity service bound to the graph service session."""
    return KernelEntityService(
        entity_repo=build_entity_repository(session),
        dictionary_repo=build_dictionary_repository(
            session,
            dictionary_loading_extension=dictionary_loading_extension,
        ),
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
    )


def get_kernel_entity_embedding_status_service(
    session: Session = Depends(get_session),
) -> KernelEntityEmbeddingStatusService:
    """Return graph-owned entity embedding readiness service."""
    return create_kernel_entity_embedding_status_service(session)


def get_kernel_relation_service(
    session: Session = Depends(get_session),
) -> KernelRelationService:
    """Return kernel relation service bound to the graph service session."""
    return KernelRelationService(
        build_relation_repository(session),
        build_entity_repository(session),
    )


def get_kernel_relation_suggestion_service(
    session: Session = Depends(get_session),
) -> KernelRelationSuggestionService:
    """Return kernel relation suggestion service bound to the graph session."""
    return create_kernel_relation_suggestion_service(session)


def get_kernel_reasoning_path_invalidation_service(
    session: Session = Depends(get_session),
) -> KernelReasoningPathInvalidationService:
    """Return reasoning-path invalidation service bound to the graph session."""
    return KernelReasoningPathInvalidationService(
        reasoning_path_repo=SqlAlchemyKernelReasoningPathRepository(session),
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
    )


def get_kernel_relation_claim_service(
    session: Session = Depends(get_session),
) -> KernelRelationClaimService:
    """Return kernel relation-claim service."""
    return KernelRelationClaimService(
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
        reasoning_path_invalidation_service=(
            get_kernel_reasoning_path_invalidation_service(session)
        ),
    )


def get_kernel_claim_participant_service(
    session: Session = Depends(get_session),
) -> KernelClaimParticipantService:
    """Return kernel claim-participant service."""
    return KernelClaimParticipantService(
        claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
    )


def get_kernel_relation_projection_source_service(
    session: Session = Depends(get_session),
) -> KernelRelationProjectionSourceService:
    """Return projection-source lineage service."""
    return KernelRelationProjectionSourceService(
        relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
    )


def get_kernel_claim_relation_service(
    session: Session = Depends(get_session),
) -> KernelClaimRelationService:
    """Return kernel claim-relation service."""
    return KernelClaimRelationService(
        claim_relation_repo=SqlAlchemyKernelClaimRelationRepository(session),
        reasoning_path_invalidation_service=(
            get_kernel_reasoning_path_invalidation_service(session)
        ),
    )


def get_kernel_claim_evidence_service(
    session: Session = Depends(get_session),
) -> KernelClaimEvidenceService:
    """Return kernel claim-evidence service."""
    return KernelClaimEvidenceService(
        claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
    )


def get_kernel_reasoning_path_service(
    session: Session = Depends(get_session),
) -> KernelReasoningPathService:
    """Return reasoning-path service bound to the graph service session."""
    reasoning_path_invalidation_service = (
        get_kernel_reasoning_path_invalidation_service(session)
    )
    return KernelReasoningPathService(
        reasoning_path_repo=SqlAlchemyKernelReasoningPathRepository(session),
        relation_claim_service=get_kernel_relation_claim_service(session),
        claim_participant_service=get_kernel_claim_participant_service(session),
        claim_evidence_service=get_kernel_claim_evidence_service(session),
        claim_relation_service=get_kernel_claim_relation_service(session),
        relation_service=get_kernel_relation_service(session),
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
        reasoning_path_invalidation_service=reasoning_path_invalidation_service,
        session=session,
        space_registry_port=SqlAlchemyKernelSpaceRegistryRepository(session),
    )


def get_dictionary_service(
    session: Session = Depends(get_session),
    dictionary_loading_extension: GraphDictionaryLoadingExtension = Depends(
        get_graph_dictionary_loading_extension,
    ),
) -> DictionaryPort:
    """Return dictionary service bound to the graph service session."""
    return build_dictionary_service(
        session,
        dictionary_loading_extension=dictionary_loading_extension,
    )


def get_ai_full_mode_service(
    session: Session = Depends(get_session),
    dictionary_loading_extension: GraphDictionaryLoadingExtension = Depends(
        get_graph_dictionary_loading_extension,
    ),
) -> AIFullModeService:
    """Return AI Full Mode governance service bound to the graph session."""
    return AIFullModeService(
        session=session,
        dictionary_service=get_dictionary_service(
            session,
            dictionary_loading_extension=dictionary_loading_extension,
        ),
        relation_claim_service=get_kernel_relation_claim_service(session),
    )


def get_dictionary_proposal_service(
    session: Session = Depends(get_session),
    dictionary_loading_extension: GraphDictionaryLoadingExtension = Depends(
        get_graph_dictionary_loading_extension,
    ),
) -> DictionaryProposalService:
    """Return dictionary proposal governance service."""
    return DictionaryProposalService(
        session=session,
        dictionary_service=get_dictionary_service(
            session,
            dictionary_loading_extension=dictionary_loading_extension,
        ),
    )


def get_graph_workflow_service(
    session: Session = Depends(get_session),
    dictionary_loading_extension: GraphDictionaryLoadingExtension = Depends(
        get_graph_dictionary_loading_extension,
    ),
) -> GraphWorkflowService:
    """Return unified graph workflow service."""
    dictionary_service = get_dictionary_service(
        session,
        dictionary_loading_extension=dictionary_loading_extension,
    )
    return GraphWorkflowService(
        session=session,
        entity_service=get_kernel_entity_service(
            session,
            dictionary_loading_extension=dictionary_loading_extension,
        ),
        relation_claim_service=get_kernel_relation_claim_service(session),
        claim_participant_service=get_kernel_claim_participant_service(session),
        claim_evidence_service=get_kernel_claim_evidence_service(session),
        dictionary_service=dictionary_service,
        dictionary_proposal_service=DictionaryProposalService(
            session=session,
            dictionary_service=dictionary_service,
        ),
        ai_full_mode_service=AIFullModeService(
            session=session,
            dictionary_service=dictionary_service,
            relation_claim_service=get_kernel_relation_claim_service(session),
        ),
    )


def get_kernel_observation_service(
    session: Session = Depends(get_session),
) -> KernelObservationService:
    """Return observation service bound to the graph service session."""
    return build_observation_service(session)


def get_provenance_service(
    session: Session = Depends(get_session),
) -> ProvenanceService:
    """Return provenance service bound to the graph service session."""
    return ProvenanceService(
        provenance_repo=SqlAlchemyProvenanceRepository(session),
    )


def get_concept_service(
    session: Session = Depends(get_session),
) -> ConceptPort:
    """Return concept service bound to the graph service session."""
    return build_concept_service(session)


def get_kernel_relation_projection_materialization_service(
    session: Session = Depends(get_session),
    dictionary_loading_extension: GraphDictionaryLoadingExtension = Depends(
        get_graph_dictionary_loading_extension,
    ),
) -> KernelRelationProjectionMaterializationService:
    """Return projection materialization service bound to the graph session."""
    return KernelRelationProjectionMaterializationService(
        relation_repo=build_relation_repository(session),
        relation_claim_repo=SqlAlchemyKernelRelationClaimRepository(session),
        claim_participant_repo=SqlAlchemyKernelClaimParticipantRepository(session),
        claim_evidence_repo=SqlAlchemyKernelClaimEvidenceRepository(session),
        entity_repo=build_entity_repository(session),
        dictionary_repo=build_dictionary_repository(
            session,
            dictionary_loading_extension=dictionary_loading_extension,
        ),
        relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
            session,
        ),
        read_model_update_dispatcher=build_graph_read_model_update_dispatcher(session),
        reasoning_path_invalidation_service=(
            get_kernel_reasoning_path_invalidation_service(session)
        ),
    )


def get_kernel_graph_view_service(
    session: Session = Depends(get_session),
    dictionary_loading_extension: GraphDictionaryLoadingExtension = Depends(
        get_graph_dictionary_loading_extension,
    ),
    graph_view_extension: GraphViewExtension = Depends(get_graph_view_extension),
) -> KernelGraphViewService:
    """Return graph-view service bound to the graph service session."""
    from artana_evidence_db.graph_view_support import (
        KernelGraphViewServiceDependencies,
    )

    return KernelGraphViewService(
        KernelGraphViewServiceDependencies(
            entity_service=get_kernel_entity_service(
                session,
                dictionary_loading_extension=dictionary_loading_extension,
            ),
            relation_service=get_kernel_relation_service(session),
            relation_claim_service=get_kernel_relation_claim_service(session),
            claim_participant_service=get_kernel_claim_participant_service(session),
            claim_relation_service=get_kernel_claim_relation_service(session),
            claim_evidence_service=get_kernel_claim_evidence_service(session),
            source_document_lookup=(
                SqlAlchemyKernelSourceDocumentReferenceRepository(session)
            ),
            view_extension=graph_view_extension,
        ),
    )


def get_kernel_claim_participant_backfill_service(
    session: Session = Depends(get_session),
) -> KernelClaimParticipantBackfillService:
    """Return participant backfill service bound to the graph session."""
    return KernelClaimParticipantBackfillService(
        session=session,
        relation_claim_service=get_kernel_relation_claim_service(session),
        claim_participant_service=get_kernel_claim_participant_service(session),
        entity_repository=build_entity_repository(session),
        concept_service=get_concept_service(session),
        reasoning_path_service=get_kernel_reasoning_path_service(session),
    )


def get_kernel_claim_projection_readiness_service(
    session: Session = Depends(get_session),
    dictionary_loading_extension: GraphDictionaryLoadingExtension = Depends(
        get_graph_dictionary_loading_extension,
    ),
) -> KernelClaimProjectionReadinessService:
    """Return projection readiness service bound to the graph session."""
    from artana_evidence_db.relation_projection_invariant_service import (
        KernelRelationProjectionInvariantService,
    )

    return KernelClaimProjectionReadinessService(
        session=session,
        relation_projection_invariant_service=KernelRelationProjectionInvariantService(
            relation_projection_repo=SqlAlchemyKernelRelationProjectionSourceRepository(
                session,
            ),
        ),
        relation_projection_materialization_service=(
            get_kernel_relation_projection_materialization_service(
                session,
                dictionary_loading_extension=dictionary_loading_extension,
            )
        ),
        claim_participant_backfill_service=(
            get_kernel_claim_participant_backfill_service(session)
        ),
    )


__all__ = [
    "get_ai_full_mode_service",
    "get_concept_service",
    "get_dictionary_service",
    "get_graph_dictionary_loading_extension",
    "get_graph_view_extension",
    "get_kernel_claim_evidence_service",
    "get_kernel_claim_participant_backfill_service",
    "get_kernel_claim_participant_service",
    "get_kernel_claim_projection_readiness_service",
    "get_kernel_claim_relation_service",
    "get_kernel_entity_service",
    "get_kernel_graph_view_service",
    "get_kernel_observation_service",
    "get_kernel_reasoning_path_invalidation_service",
    "get_kernel_reasoning_path_service",
    "get_kernel_relation_claim_service",
    "get_kernel_relation_projection_materialization_service",
    "get_kernel_relation_projection_source_service",
    "get_kernel_relation_service",
    "get_space_access_port",
    "get_provenance_service",
    "require_space_role",
    "verify_space_membership",
]
