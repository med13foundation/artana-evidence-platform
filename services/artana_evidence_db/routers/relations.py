"""Deterministic relation and graph routes for the standalone graph service."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal
from uuid import UUID

from artana_evidence_db._relation_evidence_presenter import (
    load_relation_evidence_presentation,
)
from artana_evidence_db._relation_subgraph_helpers import (
    collect_candidate_relations,
    limit_relations_to_anchor_component,
    materialize_nodes,
    ordered_node_ids_for_relations,
)
from artana_evidence_db.auth import (
    get_current_active_user,
    is_graph_service_admin,
)
from artana_evidence_db.claim_metrics import (
    emit_graph_filter_preset_usage,
)
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_dictionary_service,
    get_kernel_claim_evidence_service,
    get_kernel_claim_participant_service,
    get_kernel_entity_service,
    get_kernel_relation_claim_service,
    get_kernel_relation_projection_materialization_service,
    get_kernel_relation_service,
    get_kernel_relation_suggestion_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from artana_evidence_db.fact_assessment_support import fact_assessment_metadata
from artana_evidence_db.graph_validation_service import GraphValidationService
from artana_evidence_db.hybrid_graph_errors import (
    EmbeddingNotReadyError,
)
from artana_evidence_db.kernel_services import (
    KernelClaimEvidenceService,
    KernelClaimParticipantService,
    KernelEntityService,
    KernelRelationClaimService,
    KernelRelationProjectionMaterializationService,
    KernelRelationService,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.relation_projection_materialization_support import (
    RelationProjectionMaterializationError,
)
from artana_evidence_db.semantic_ports import DictionaryPort
from artana_evidence_db.service_contracts import (
    KernelGraphExportResponse,
    KernelGraphSubgraphMeta,
    KernelGraphSubgraphRequest,
    KernelGraphSubgraphResponse,
    KernelMechanisticGapListResponse,
    KernelMechanisticGapResponse,
    KernelReachabilityGapListResponse,
    KernelReachabilityGapResponse,
    KernelRelationCreateRequest,
    KernelRelationCurationUpdateRequest,
    KernelRelationListResponse,
    KernelRelationResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionRequest,
    KernelRelationSuggestionResponse,
    KernelRelationSuggestionSkippedSourceResponse,
    KernelRelationTripleValidationRequest,
)
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from artana_evidence_db.kernel_services import KernelRelationSuggestionService

router = APIRouter(prefix="/v1/spaces", tags=["relations"])

_CANONICAL_CURATION_STATUSES = frozenset(
    {"APPROVED", "UNDER_REVIEW", "DRAFT", "REJECTED", "RETRACTED"},
)
_CURATION_STATUS_ALIAS: dict[str, str] = {"PENDING_REVIEW": "DRAFT"}
_CLAIM_VALIDATION_STATES = frozenset(
    {
        "ALLOWED",
        "FORBIDDEN",
        "UNDEFINED",
        "INVALID_COMPONENTS",
        "ENDPOINT_UNRESOLVED",
        "SELF_LOOP",
    },
)
_CERTAINTY_BANDS = frozenset({"HIGH", "MEDIUM", "LOW"})
_ClaimValidationState = Literal[
    "ALLOWED",
    "FORBIDDEN",
    "UNDEFINED",
    "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED",
    "SELF_LOOP",
]
_CertaintyBand = Literal["HIGH", "MEDIUM", "LOW"]
_CLAIM_VALIDATION_STATE_MAP: dict[str, _ClaimValidationState] = {
    "ALLOWED": "ALLOWED",
    "FORBIDDEN": "FORBIDDEN",
    "UNDEFINED": "UNDEFINED",
    "INVALID_COMPONENTS": "INVALID_COMPONENTS",
    "ENDPOINT_UNRESOLVED": "ENDPOINT_UNRESOLVED",
    "SELF_LOOP": "SELF_LOOP",
}


def _normalize_filter_values(values: list[str] | None) -> set[str] | None:
    if values is None:
        return None
    normalized = {value.strip().upper() for value in values if value.strip()}
    return normalized or None


def _parse_node_ids_param(node_ids: list[str] | None) -> list[str]:
    if node_ids is None:
        return []
    normalized: list[str] = []
    for raw in node_ids:
        normalized.extend(part.strip() for part in raw.split(",") if part.strip())
    return normalized


def _normalize_curation_status_filter(status_value: str | None) -> str | None:
    if status_value is None:
        return None
    normalized = status_value.strip().upper()
    if not normalized:
        return None
    return _CURATION_STATUS_ALIAS.get(normalized, normalized)


def _normalize_curation_status_filters(
    statuses: list[str] | None,
) -> set[str] | None:
    normalized_values = _normalize_filter_values(statuses)
    if normalized_values is None:
        return None
    normalized = {
        _CURATION_STATUS_ALIAS.get(value, value) for value in normalized_values
    }
    return normalized or None


def _normalize_curation_status_update(status_value: str) -> str:
    normalized = status_value.strip().upper()
    if normalized not in _CANONICAL_CURATION_STATUSES:
        msg = "curation_status must be one of: " + ", ".join(
            sorted(_CANONICAL_CURATION_STATUSES),
        )
        raise ValueError(msg)
    return normalized


def _normalize_claim_validation_state(
    value: str | None,
) -> _ClaimValidationState | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    normalized_state = _CLAIM_VALIDATION_STATE_MAP.get(normalized)
    if normalized_state is None:
        msg = "validation_state must be one of: " + ", ".join(
            sorted(_CLAIM_VALIDATION_STATES),
        )
        raise ValueError(msg)
    return normalized_state


def _normalize_certainty_band(value: str | None) -> _CertaintyBand | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if normalized not in _CERTAINTY_BANDS:
        msg = "certainty_band must be one of: HIGH, MEDIUM, LOW"
        raise ValueError(msg)
    if normalized == "HIGH":
        return "HIGH"
    if normalized == "MEDIUM":
        return "MEDIUM"
    return "LOW"


def _normalize_claim_evidence_sentence_source(
    value: str | None,
) -> Literal["verbatim_span", "artana_generated"] | None:
    if value == "verbatim_span":
        return "verbatim_span"
    if value == "artana_generated":
        return "artana_generated"
    return None


def _normalize_claim_evidence_sentence_confidence(
    value: str | None,
) -> Literal["low", "medium", "high"] | None:
    if value == "low":
        return "low"
    if value == "medium":
        return "medium"
    if value == "high":
        return "high"
    return None


def _manual_relation_claim_text(
    *,
    evidence_summary: str | None,
    evidence_sentence: str | None,
    relation_type: str,
    source_label: str | None,
    target_label: str | None,
) -> str:
    if evidence_sentence is not None and evidence_sentence.strip():
        return evidence_sentence.strip()[:2000]
    if evidence_summary is not None and evidence_summary.strip():
        return evidence_summary.strip()[:2000]
    source_text = source_label.strip() if source_label is not None else ""
    target_text = target_label.strip() if target_label is not None else ""
    if source_text and target_text:
        return f"{source_text} {relation_type} {target_text}"
    if source_text:
        return f"{source_text} {relation_type}"
    if target_text:
        return f"{relation_type} {target_text}"
    return relation_type


def _build_validation_error_detail(validation: object) -> dict[str, object]:
    next_actions = getattr(validation, "next_actions", [])
    serialized_next_actions = [
        action.model_dump(mode="json") for action in next_actions
    ]
    return {
        "code": getattr(validation, "code", "validation_failed"),
        "message": getattr(validation, "message", "Relation validation failed."),
        "severity": getattr(validation, "severity", "blocking"),
        "validation_state": getattr(validation, "validation_state", None),
        "persistability": getattr(validation, "persistability", None),
        "next_actions": serialized_next_actions,
    }


@router.get(
    "/{space_id}/relations",
    response_model=KernelRelationListResponse,
    summary="List canonical relations in one graph space",
)
def list_relations(  # noqa: PLR0913
    space_id: UUID,
    *,
    relation_type: str | None = Query(default=None),
    curation_status: str | None = Query(default=None),
    validation_state: str | None = Query(default=None),
    source_document_id: str | None = Query(default=None),
    certainty_band: str | None = Query(default=None),
    node_query: str | None = Query(default=None),
    node_ids: list[str] | None = Query(
        default=None,
        description="Comma-separated entity IDs to match relation source or target.",
    ),
    max_source_family_count: int | None = Query(
        default=None,
        ge=1,
        description=(
            "Match relations whose distinct_source_family_count is at most "
            "this value. Use 1 to find single-source ('fragile') relations."
        ),
    ),
    fragile_only: bool = Query(
        default=False,
        description=(
            "Convenience flag equivalent to max_source_family_count=1. "
            "Returns only relations supported by exactly one source family."
        ),
    ),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelRelationListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    try:
        normalized_curation_status = _normalize_curation_status_filter(
            curation_status,
        )
        normalized_validation_state = _normalize_claim_validation_state(
            validation_state,
        )
        normalized_certainty_band = _normalize_certainty_band(certainty_band)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    parsed_node_ids = _parse_node_ids_param(node_ids)
    # fragile_only is sugar for max_source_family_count=1; explicit value wins.
    effective_max_source_family_count = max_source_family_count
    if effective_max_source_family_count is None and fragile_only:
        effective_max_source_family_count = 1
    relations = relation_service.list_by_research_space(
        str(space_id),
        relation_type=relation_type,
        curation_status=normalized_curation_status,
        validation_state=normalized_validation_state,
        source_document_id=source_document_id,
        certainty_band=normalized_certainty_band,
        node_query=node_query,
        node_ids=parsed_node_ids,
        max_source_family_count=effective_max_source_family_count,
        limit=limit,
        offset=offset,
    )
    total = relation_service.count_by_research_space(
        str(space_id),
        relation_type=relation_type,
        curation_status=normalized_curation_status,
        validation_state=normalized_validation_state,
        source_document_id=source_document_id,
        certainty_band=normalized_certainty_band,
        node_query=node_query,
        node_ids=parsed_node_ids,
        max_source_family_count=effective_max_source_family_count,
    )
    evidence_by_relation_id = load_relation_evidence_presentation(
        session=session,
        relation_ids=[UUID(str(relation.id)) for relation in relations],
    )
    relation_rows: list[KernelRelationResponse] = []
    for relation in relations:
        evidence = evidence_by_relation_id.get(str(relation.id))
        relation_rows.append(
            KernelRelationResponse.from_model(
                relation,
                evidence_summary=evidence.evidence_summary if evidence else None,
                evidence_sentence=evidence.evidence_sentence if evidence else None,
                evidence_sentence_source=(
                    evidence.evidence_sentence_source if evidence else None
                ),
                evidence_sentence_confidence=(
                    evidence.evidence_sentence_confidence if evidence else None
                ),
                evidence_sentence_rationale=(
                    evidence.evidence_sentence_rationale if evidence else None
                ),
                paper_links=evidence.paper_links if evidence else [],
            ),
        )

    return KernelRelationListResponse(
        relations=relation_rows,
        total=total,
        offset=offset,
        limit=limit,
    )


@router.get(
    "/{space_id}/relations/reachability-gaps",
    response_model=KernelReachabilityGapListResponse,
    summary=(
        "Find entities reachable from a seed via multi-hop paths but with no direct edge"
    ),
)
def list_reachability_gaps(  # noqa: PLR0913
    space_id: UUID,
    *,
    seed_entity_id: UUID = Query(
        ...,
        description="Required starting point for the multi-hop traversal.",
    ),
    max_path_length: int = Query(
        default=2,
        ge=2,
        le=5,
        description=(
            "Maximum BFS depth.  Length 1 has no gaps by definition; values "
            "greater than 5 are rejected to bound traversal cost."
        ),
    ),
    relation_type: list[str] | None = Query(
        default=None,
        description="Optional list of relation types to restrict the traversal.",
    ),
    claim_backed_only: bool = Query(default=True),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelReachabilityGapListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    try:
        gaps = relation_service.find_reachability_gaps(
            str(seed_entity_id),
            max_path_length=max_path_length,
            relation_types=relation_type,
            claim_backed_only=claim_backed_only,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    # Re-run unpaginated to compute the total — the underlying BFS is the same
    # cost as the paginated call so we accept the duplicate query for now.
    all_gaps = relation_service.find_reachability_gaps(
        str(seed_entity_id),
        max_path_length=max_path_length,
        relation_types=relation_type,
        claim_backed_only=claim_backed_only,
    )

    return KernelReachabilityGapListResponse(
        seed_entity_id=seed_entity_id,
        max_path_length=max_path_length,
        gaps=[
            KernelReachabilityGapResponse(
                seed_entity_id=gap.seed_entity_id,
                target_entity_id=gap.target_entity_id,
                min_path_length=gap.min_path_length,
                bridge_entity_id=gap.bridge_entity_id,
            )
            for gap in gaps
        ],
        total=len(all_gaps),
        offset=offset,
        limit=limit,
    )


_DEFAULT_MECHANISTIC_INTERMEDIATE_TYPES = [
    "BIOLOGICAL_PROCESS",
    "SIGNALING_PATHWAY",
    "MOLECULAR_FUNCTION",
    "PROTEIN_DOMAIN",
]


@router.get(
    "/{space_id}/relations/mechanistic-gaps",
    response_model=KernelMechanisticGapListResponse,
    summary=(
        "Find direct relations that lack an N-hop bridge (default 2) through "
        "mechanism entities"
    ),
)
def list_mechanistic_gaps(  # noqa: PLR0913
    space_id: UUID,
    *,
    relation_type: list[str] | None = Query(
        default=None,
        description=(
            "Direct relation types to scan.  Defaults to ASSOCIATED_WITH if "
            "not specified."
        ),
    ),
    source_entity_type: str | None = Query(
        default=None,
        description="Optional narrowing of candidate relations by source entity type.",
    ),
    target_entity_type: str | None = Query(
        default=None,
        description="Optional narrowing of candidate relations by target entity type.",
    ),
    intermediate_entity_type: list[str] | None = Query(
        default=None,
        description=(
            "Entity types that count as 'mechanism' bridges.  Defaults to "
            "BIOLOGICAL_PROCESS, SIGNALING_PATHWAY, MOLECULAR_FUNCTION, "
            "PROTEIN_DOMAIN."
        ),
    ),
    max_hops: int = Query(
        default=2,
        ge=2,
        le=4,
        description=(
            "Maximum bridge path length (in edges).  Default 2 preserves the "
            "legacy 2-hop bridge test.  Must be in [2, 4]: length 1 is a "
            "direct relation (different question), and depths beyond 4 in a "
            "biomedical graph rarely reflect meaningful mechanism chains."
        ),
    ),
    claim_backed_only: bool = Query(default=True),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelMechanisticGapListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    effective_relation_types = [
        rt.strip().upper() for rt in (relation_type or ["ASSOCIATED_WITH"]) if rt
    ]
    if not effective_relation_types:
        effective_relation_types = ["ASSOCIATED_WITH"]
    effective_intermediate_types = [
        t.strip().upper()
        for t in (intermediate_entity_type or _DEFAULT_MECHANISTIC_INTERMEDIATE_TYPES)
        if t
    ]
    if not effective_intermediate_types:
        effective_intermediate_types = list(_DEFAULT_MECHANISTIC_INTERMEDIATE_TYPES)

    gaps = relation_service.find_mechanistic_gaps(
        str(space_id),
        relation_types=effective_relation_types,
        source_entity_type=source_entity_type,
        target_entity_type=target_entity_type,
        intermediate_entity_types=effective_intermediate_types,
        claim_backed_only=claim_backed_only,
        limit=limit,
        offset=offset,
        max_hops=max_hops,
    )
    all_gaps = relation_service.find_mechanistic_gaps(
        str(space_id),
        relation_types=effective_relation_types,
        source_entity_type=source_entity_type,
        target_entity_type=target_entity_type,
        intermediate_entity_types=effective_intermediate_types,
        claim_backed_only=claim_backed_only,
        max_hops=max_hops,
    )

    return KernelMechanisticGapListResponse(
        relation_types=effective_relation_types,
        intermediate_entity_types=effective_intermediate_types,
        source_entity_type=source_entity_type,
        target_entity_type=target_entity_type,
        max_hops=max_hops,
        gaps=[
            KernelMechanisticGapResponse(
                relation_id=gap.relation_id,
                source_entity_id=gap.source_entity_id,
                target_entity_id=gap.target_entity_id,
                relation_type=gap.relation_type,
                source_intermediate_count=gap.source_intermediate_count,
                target_intermediate_count=gap.target_intermediate_count,
                bridge_entity_id=gap.bridge_entity_id,
                bridge_path=(
                    list(gap.bridge_path) if gap.bridge_path is not None else None
                ),
            )
            for gap in gaps
        ],
        total=len(all_gaps),
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/relations/suggestions",
    response_model=KernelRelationSuggestionListResponse,
    summary="Suggest missing dictionary-constrained relations in one graph space",
)
def suggest_relations(
    space_id: UUID,
    request: KernelRelationSuggestionRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_suggestion_service: KernelRelationSuggestionService = Depends(
        get_kernel_relation_suggestion_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationSuggestionListResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    try:
        result = relation_suggestion_service.suggest_relations(
            research_space_id=str(space_id),
            source_entity_ids=[
                str(entity_id) for entity_id in request.source_entity_ids
            ],
            limit_per_source=request.limit_per_source,
            min_score=request.min_score,
            allowed_relation_types=request.allowed_relation_types,
            target_entity_types=request.target_entity_types,
            exclude_existing_relations=request.exclude_existing_relations,
            require_all_ready=request.require_all_ready,
        )
    except EmbeddingNotReadyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=exc.detail_payload or str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return KernelRelationSuggestionListResponse(
        suggestions=[
            KernelRelationSuggestionResponse.model_validate(
                suggestion.model_dump(mode="python"),
            )
            for suggestion in result.suggestions
        ],
        total=len(result.suggestions),
        limit_per_source=request.limit_per_source,
        min_score=request.min_score,
        incomplete=result.incomplete,
        skipped_sources=[
            KernelRelationSuggestionSkippedSourceResponse.model_validate(
                skipped_source.model_dump(mode="python"),
            )
            for skipped_source in result.skipped_sources
        ],
    )


@router.post(
    "/{space_id}/relations",
    response_model=KernelRelationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one canonical relation from a manual support claim",
)
def create_relation(
    space_id: UUID,
    request: KernelRelationCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_claim_service: KernelRelationClaimService = Depends(
        get_kernel_relation_claim_service,
    ),
    claim_participant_service: KernelClaimParticipantService = Depends(
        get_kernel_claim_participant_service,
    ),
    claim_evidence_service: KernelClaimEvidenceService = Depends(
        get_kernel_claim_evidence_service,
    ),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    relation_projection_materialization_service: KernelRelationProjectionMaterializationService = Depends(
        get_kernel_relation_projection_materialization_service,
    ),
    session: Session = Depends(get_session),
) -> KernelRelationResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    if not is_graph_service_admin(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "POST /relations requires graph-service admin access. Create or "
                "resolve claims to materialize canonical relations."
            ),
        )

    try:
        source_entity = entity_service.get_entity(str(request.source_id))
        target_entity = entity_service.get_entity(str(request.target_id))
        if (
            source_entity is None
            or target_entity is None
            or str(source_entity.research_space_id) != str(space_id)
            or str(target_entity.research_space_id) != str(space_id)
        ):
            msg = "Source or target entity not found"
            raise ValueError(msg)

        validation_service = GraphValidationService(
            entity_service=entity_service,
            dictionary_service=dictionary_service,
        )
        validation = validation_service.validate_triple(
            space_id=str(space_id),
            request=KernelRelationTripleValidationRequest(
                source_entity_id=request.source_id,
                target_entity_id=request.target_id,
                relation_type=request.relation_type,
                evidence_summary=request.evidence_summary,
                evidence_sentence=request.evidence_sentence,
                source_document_ref=request.source_document_ref,
            ),
        )
        canonical_relation_type = validation.normalized_relation_type
        if not canonical_relation_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="relation_type is required",
            )
        if (
            not validation.valid
            or validation.persistability != "PERSISTABLE"
            or validation.code != "allowed"
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_build_validation_error_detail(validation),
            )
        confidence_metadata = fact_assessment_metadata(request.assessment)
        request_metadata = dict(request.metadata)
        derived_confidence = request.derived_confidence
        manual_claim = relation_claim_service.create_claim(
            research_space_id=str(space_id),
            source_document_id=None,
            source_document_ref=request.source_document_ref,
            agent_run_id=None,
            source_type=source_entity.entity_type,
            relation_type=canonical_relation_type,
            target_type=target_entity.entity_type,
            source_label=source_entity.display_label,
            target_label=target_entity.display_label,
            confidence=derived_confidence,
            validation_state="ALLOWED",
            validation_reason="Created via canonical relation API",
            persistability="PERSISTABLE",
            claim_status="RESOLVED",
            polarity="SUPPORT",
            claim_text=_manual_relation_claim_text(
                evidence_summary=request.evidence_summary,
                evidence_sentence=request.evidence_sentence,
                relation_type=canonical_relation_type,
                source_label=source_entity.display_label,
                target_label=target_entity.display_label,
            ),
            claim_section=None,
            linked_relation_id=None,
            metadata={
                **request_metadata,
                "origin": "manual_relation_api",
                "source_entity_id": str(request.source_id),
                "target_entity_id": str(request.target_id),
                **confidence_metadata,
                "provenance_id": (
                    str(request.provenance_id)
                    if request.provenance_id is not None
                    else None
                ),
            },
        )
        claim_id = str(manual_claim.id)
        claim_participant_service.create_participant(
            claim_id=claim_id,
            research_space_id=str(space_id),
            role="SUBJECT",
            label=source_entity.display_label,
            entity_id=str(source_entity.id),
            position=0,
            qualifiers={"origin": "manual_relation_api"},
        )
        claim_participant_service.create_participant(
            claim_id=claim_id,
            research_space_id=str(space_id),
            role="OBJECT",
            label=target_entity.display_label,
            entity_id=str(target_entity.id),
            position=1,
            qualifiers={"origin": "manual_relation_api"},
        )
        if (
            request.evidence_summary is not None
            or request.evidence_sentence is not None
            or request.provenance_id is not None
            or request.source_document_ref is not None
        ):
            claim_evidence_service.create_evidence(
                claim_id=claim_id,
                source_document_id=None,
                source_document_ref=request.source_document_ref,
                agent_run_id=None,
                sentence=request.evidence_sentence,
                sentence_source=_normalize_claim_evidence_sentence_source(
                    request.evidence_sentence_source,
                ),
                sentence_confidence=_normalize_claim_evidence_sentence_confidence(
                    request.evidence_sentence_confidence,
                ),
                sentence_rationale=request.evidence_sentence_rationale,
                figure_reference=None,
                table_reference=None,
                confidence=derived_confidence,
                metadata={
                    **request_metadata,
                    "origin": "manual_relation_api",
                    "evidence_summary": request.evidence_summary,
                    "evidence_tier": request.evidence_tier or "COMPUTATIONAL",
                    **confidence_metadata,
                    "provenance_id": (
                        str(request.provenance_id)
                        if request.provenance_id is not None
                        else None
                    ),
                },
            )
        materialized = (
            relation_projection_materialization_service.materialize_support_claim(
                claim_id=claim_id,
                research_space_id=str(space_id),
                projection_origin="MANUAL_RELATION",
                reviewed_by=str(current_user.id),
            )
        )
        relation = materialized.relation
        if relation is None:
            msg = "Manual relation claim did not materialize a canonical relation"
            raise ValueError(msg)
        session.commit()
        return KernelRelationResponse.from_model(
            relation,
            source_claim_id=claim_id,
        )
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Relation write conflicts with dictionary constraints, "
                "research-space isolation, or required evidence checks"
            ),
        ) from exc
    except RelationProjectionMaterializationError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create relation: {exc!s}",
        ) from exc


@router.put(
    "/{space_id}/relations/{relation_id}",
    response_model=KernelRelationResponse,
    summary="Update one relation curation status",
)
def update_relation_curation_status(
    space_id: UUID,
    relation_id: UUID,
    request: KernelRelationCurationUpdateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelRelationResponse:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.CURATOR,
    )

    existing = relation_service.get_relation(str(relation_id))
    if existing is None or str(existing.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Relation not found",
        )

    try:
        normalized_status = _normalize_curation_status_update(request.curation_status)
        updated = relation_service.update_curation_status(
            str(relation_id),
            curation_status=normalized_status,
            reviewed_by=str(current_user.id),
        )
        session.commit()
        return KernelRelationResponse.from_model(updated)
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update relation: {exc!s}",
        ) from exc


@router.post(
    "/{space_id}/graph/subgraph",
    response_model=KernelGraphSubgraphResponse,
    summary="Retrieve a bounded graph subgraph",
)
def get_subgraph(
    space_id: UUID,
    request: KernelGraphSubgraphRequest,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelGraphSubgraphResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    relation_types = _normalize_filter_values(request.relation_types)
    curation_statuses = _normalize_curation_status_filters(request.curation_statuses)
    emit_graph_filter_preset_usage(
        endpoint="subgraph",
        curation_statuses=(
            sorted(curation_statuses) if curation_statuses is not None else None
        ),
    )
    seed_entity_ids = [str(seed_id) for seed_id in request.seed_entity_ids]
    mode = request.mode
    space_id_str = str(space_id)

    if mode == "starter" and seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids must be empty when mode='starter'.",
        )
    if mode == "seeded" and not seed_entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="seed_entity_ids is required when mode='seeded'.",
        )

    try:
        candidate_relations = collect_candidate_relations(
            mode=mode,
            space_id=space_id_str,
            request=request,
            relation_service=relation_service,
            relation_types=relation_types,
            curation_statuses=curation_statuses,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if mode == "starter":
        candidate_relations = limit_relations_to_anchor_component(
            relations=candidate_relations,
            preferred_seed_entity_ids=seed_entity_ids,
        )

    pre_cap_node_ids = set(seed_entity_ids)
    for relation in candidate_relations:
        pre_cap_node_ids.add(str(relation.source_id))
        pre_cap_node_ids.add(str(relation.target_id))
    pre_cap_edge_count = len(candidate_relations)
    pre_cap_node_count = len(pre_cap_node_ids)

    bounded_relations = candidate_relations[: request.max_edges]
    ordered_node_ids = ordered_node_ids_for_relations(
        bounded_relations,
        seed_entity_ids=seed_entity_ids,
    )
    bounded_node_ids = ordered_node_ids[: request.max_nodes]
    bounded_node_id_set = set(bounded_node_ids)

    final_relations = [
        relation
        for relation in bounded_relations
        if str(relation.source_id) in bounded_node_id_set
        and str(relation.target_id) in bounded_node_id_set
    ]
    final_node_ids = ordered_node_ids_for_relations(
        final_relations,
        seed_entity_ids=seed_entity_ids,
    )[: request.max_nodes]

    nodes = materialize_nodes(
        entity_ids=final_node_ids,
        space_id=space_id_str,
        entity_service=entity_service,
    )
    edges = [
        KernelRelationResponse.from_model(relation) for relation in final_relations
    ]
    return KernelGraphSubgraphResponse(
        nodes=nodes,
        edges=edges,
        meta=KernelGraphSubgraphMeta(
            mode=mode,
            seed_entity_ids=request.seed_entity_ids,
            requested_depth=request.depth,
            requested_top_k=request.top_k,
            pre_cap_node_count=pre_cap_node_count,
            pre_cap_edge_count=pre_cap_edge_count,
            truncated_nodes=len(nodes) < pre_cap_node_count,
            truncated_edges=len(edges) < pre_cap_edge_count,
        ),
    )


@router.get(
    "/{space_id}/graph/neighborhood/{entity_id}",
    response_model=KernelGraphExportResponse,
    summary="Get one entity neighborhood",
)
def get_neighborhood(
    space_id: UUID,
    entity_id: UUID,
    *,
    depth: int = Query(default=1, ge=1, le=3),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    relation_service: KernelRelationService = Depends(get_kernel_relation_service),
    session: Session = Depends(get_session),
) -> KernelGraphExportResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    try:
        relations = relation_service.get_neighborhood_in_space(
            str(space_id),
            str(entity_id),
            depth=depth,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    entity_ids: set[str] = {str(entity_id)}
    for relation in relations:
        entity_ids.add(str(relation.source_id))
        entity_ids.add(str(relation.target_id))

    nodes = materialize_nodes(
        entity_ids=sorted(entity_ids),
        space_id=str(space_id),
        entity_service=entity_service,
    )
    return KernelGraphExportResponse(
        nodes=nodes,
        edges=[KernelRelationResponse.from_model(relation) for relation in relations],
    )


__all__ = [
    "create_relation",
    "get_neighborhood",
    "get_subgraph",
    "list_relations",
    "router",
    "update_relation_curation_status",
]
