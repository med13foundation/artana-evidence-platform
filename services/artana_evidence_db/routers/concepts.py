"""Concept governance routes for the standalone graph service."""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from artana_evidence_db.auth import get_current_active_user
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_concept_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.semantic_ports import ConceptPort
from artana_evidence_db.service_contracts import (
    ConceptAliasListResponse,
    ConceptAliasResponse,
    ConceptDecisionListResponse,
    ConceptDecisionResponse,
    ConceptDecisionStatusRequest,
    ConceptMemberListResponse,
    ConceptMemberResponse,
    ConceptPolicyResponse,
    ConceptSetListResponse,
    ConceptSetResponse,
)
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/spaces", tags=["concepts"])


class ConceptSetCreateRequest(BaseModel):
    """Create one concept set in a graph space."""

    model_config = ConfigDict(strict=False)

    name: str = Field(..., min_length=1, max_length=128)
    slug: str = Field(..., min_length=1, max_length=128)
    domain_context: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConceptMemberCreateRequest(BaseModel):
    """Create one concept member in a graph space."""

    model_config = ConfigDict(strict=False)

    concept_set_id: UUID
    domain_context: str = Field(..., min_length=1, max_length=64)
    canonical_label: str = Field(..., min_length=1, max_length=255)
    normalized_label: str = Field(..., min_length=1, max_length=255)
    sense_key: str = Field(default="", max_length=128)
    dictionary_dimension: str | None = Field(default=None, max_length=32)
    dictionary_entry_id: str | None = Field(default=None, max_length=128)
    is_provisional: bool = False
    metadata_payload: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConceptAliasCreateRequest(BaseModel):
    """Create one concept alias in a graph space."""

    model_config = ConfigDict(strict=False)

    concept_member_id: UUID
    domain_context: str = Field(..., min_length=1, max_length=64)
    alias_label: str = Field(..., min_length=1, max_length=255)
    alias_normalized: str = Field(..., min_length=1, max_length=255)
    source: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConceptPolicyUpsertRequest(BaseModel):
    """Upsert the active concept policy for one graph space."""

    model_config = ConfigDict(strict=False)

    mode: Literal["PRECISION", "BALANCED", "DISCOVERY"]
    minimum_edge_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    minimum_distinct_documents: int = Field(default=1, ge=1)
    allow_generic_relations: bool = True
    max_edges_per_document: int | None = Field(default=None, ge=1)
    policy_payload: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class ConceptDecisionProposeRequest(BaseModel):
    """Propose one concept governance decision in a graph space."""

    model_config = ConfigDict(strict=False)

    decision_type: Literal[
        "CREATE",
        "MAP",
        "MERGE",
        "SPLIT",
        "LINK",
        "PROMOTE",
        "DEMOTE",
    ]
    decision_payload: JSONObject = Field(default_factory=dict)
    evidence_payload: JSONObject = Field(default_factory=dict)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str | None = Field(default=None, max_length=4000)
    concept_set_id: UUID | None = None
    concept_member_id: UUID | None = None
    concept_link_id: UUID | None = None


def _verify_space_access(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
) -> None:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )


def _require_graph_researcher(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
) -> None:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )


def _require_graph_curator(
    *,
    space_id: UUID,
    current_user: User,
    space_access: SpaceAccessPort,
    session: Session,
) -> None:
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.CURATOR,
    )


@router.get(
    "/{space_id}/concepts/sets",
    response_model=ConceptSetListResponse,
    summary="List concept sets in one graph space",
)
def list_concept_sets(
    space_id: UUID,
    *,
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptSetListResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    concept_sets = concept_service.list_concept_sets(
        research_space_id=str(space_id),
        include_inactive=include_inactive,
    )
    return ConceptSetListResponse(
        concept_sets=[ConceptSetResponse.from_model(item) for item in concept_sets],
        total=len(concept_sets),
    )


@router.post(
    "/{space_id}/concepts/sets",
    response_model=ConceptSetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one concept set in a graph space",
)
def create_concept_set(
    space_id: UUID,
    request: ConceptSetCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptSetResponse:
    _require_graph_researcher(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        concept_set = concept_service.create_concept_set(
            research_space_id=str(space_id),
            name=request.name,
            slug=request.slug,
            domain_context=request.domain_context,
            description=request.description,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concept set conflicts with an existing active record",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ConceptSetResponse.from_model(concept_set)


@router.get(
    "/{space_id}/concepts/members",
    response_model=ConceptMemberListResponse,
    summary="List concept members in one graph space",
)
def list_concept_members(
    space_id: UUID,
    *,
    concept_set_id: UUID | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptMemberListResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    concept_members = concept_service.list_concept_members(
        research_space_id=str(space_id),
        concept_set_id=str(concept_set_id) if concept_set_id is not None else None,
        include_inactive=include_inactive,
        offset=offset,
        limit=limit,
    )
    return ConceptMemberListResponse(
        concept_members=[
            ConceptMemberResponse.from_model(item) for item in concept_members
        ],
        total=len(concept_members),
    )


@router.post(
    "/{space_id}/concepts/members",
    response_model=ConceptMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one concept member in a graph space",
)
def create_concept_member(
    space_id: UUID,
    request: ConceptMemberCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptMemberResponse:
    _require_graph_researcher(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        concept_member = concept_service.create_concept_member(
            concept_set_id=str(request.concept_set_id),
            research_space_id=str(space_id),
            domain_context=request.domain_context,
            canonical_label=request.canonical_label,
            normalized_label=request.normalized_label,
            sense_key=request.sense_key,
            dictionary_dimension=request.dictionary_dimension,
            dictionary_entry_id=request.dictionary_entry_id,
            is_provisional=request.is_provisional,
            metadata_payload=request.metadata_payload,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concept member conflicts with existing scoped uniqueness rules",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ConceptMemberResponse.from_model(concept_member)


@router.get(
    "/{space_id}/concepts/aliases",
    response_model=ConceptAliasListResponse,
    summary="List concept aliases in one graph space",
)
def list_concept_aliases(
    space_id: UUID,
    *,
    concept_member_id: UUID | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptAliasListResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    concept_aliases = concept_service.list_concept_aliases(
        research_space_id=str(space_id),
        concept_member_id=(
            str(concept_member_id) if concept_member_id is not None else None
        ),
        include_inactive=include_inactive,
        offset=offset,
        limit=limit,
    )
    return ConceptAliasListResponse(
        concept_aliases=[
            ConceptAliasResponse.from_model(item) for item in concept_aliases
        ],
        total=len(concept_aliases),
    )


@router.post(
    "/{space_id}/concepts/aliases",
    response_model=ConceptAliasResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one concept alias in a graph space",
)
def create_concept_alias(
    space_id: UUID,
    request: ConceptAliasCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptAliasResponse:
    _require_graph_researcher(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        concept_alias = concept_service.create_concept_alias(
            concept_member_id=str(request.concept_member_id),
            research_space_id=str(space_id),
            domain_context=request.domain_context,
            alias_label=request.alias_label,
            alias_normalized=request.alias_normalized,
            source=request.source,
            created_by=f"manual:{current_user.id}",
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Alias conflicts with existing active alias scope",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ConceptAliasResponse.from_model(concept_alias)


@router.get(
    "/{space_id}/concepts/policy",
    response_model=ConceptPolicyResponse | None,
    summary="Get the active concept policy for one graph space",
)
def get_active_policy(
    space_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptPolicyResponse | None:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    policy = concept_service.get_active_policy(research_space_id=str(space_id))
    if policy is None:
        return None
    return ConceptPolicyResponse.from_model(policy)


@router.put(
    "/{space_id}/concepts/policy",
    response_model=ConceptPolicyResponse,
    summary="Upsert the active concept policy for one graph space",
)
def upsert_active_policy(
    space_id: UUID,
    request: ConceptPolicyUpsertRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptPolicyResponse:
    _require_graph_researcher(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        policy = concept_service.upsert_active_policy(
            research_space_id=str(space_id),
            mode=request.mode,
            created_by=f"manual:{current_user.id}",
            minimum_edge_confidence=request.minimum_edge_confidence,
            minimum_distinct_documents=request.minimum_distinct_documents,
            allow_generic_relations=request.allow_generic_relations,
            max_edges_per_document=request.max_edges_per_document,
            policy_payload=request.policy_payload,
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concept policy conflicts with active policy uniqueness",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ConceptPolicyResponse.from_model(policy)


@router.get(
    "/{space_id}/concepts/decisions",
    response_model=ConceptDecisionListResponse,
    summary="List concept decisions in one graph space",
)
def list_concept_decisions(
    space_id: UUID,
    *,
    decision_status: (
        Literal["PROPOSED", "NEEDS_REVIEW", "APPROVED", "REJECTED", "APPLIED"] | None
    ) = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptDecisionListResponse:
    _verify_space_access(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    decisions = concept_service.list_decisions(
        research_space_id=str(space_id),
        decision_status=decision_status,
        offset=offset,
        limit=limit,
    )
    return ConceptDecisionListResponse(
        concept_decisions=[
            ConceptDecisionResponse.from_model(item) for item in decisions
        ],
        total=len(decisions),
    )


@router.post(
    "/{space_id}/concepts/decisions/propose",
    response_model=ConceptDecisionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose one concept decision in a graph space",
)
def propose_concept_decision(
    space_id: UUID,
    request: ConceptDecisionProposeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptDecisionResponse:
    _require_graph_researcher(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        decision = concept_service.propose_decision(
            research_space_id=str(space_id),
            decision_type=request.decision_type,
            proposed_by=f"manual:{current_user.id}",
            decision_payload=request.decision_payload,
            evidence_payload=request.evidence_payload,
            confidence=request.confidence,
            rationale=request.rationale,
            concept_set_id=(
                str(request.concept_set_id)
                if request.concept_set_id is not None
                else None
            ),
            concept_member_id=(
                str(request.concept_member_id)
                if request.concept_member_id is not None
                else None
            ),
            concept_link_id=(
                str(request.concept_link_id)
                if request.concept_link_id is not None
                else None
            ),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Concept decision conflicts with existing records",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ConceptDecisionResponse.from_model(decision)


@router.patch(
    "/{space_id}/concepts/decisions/{decision_id}/status",
    response_model=ConceptDecisionResponse,
    summary="Update one concept decision status in a graph space",
)
def set_concept_decision_status(
    space_id: UUID,
    decision_id: str,
    request: ConceptDecisionStatusRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    concept_service: ConceptPort = Depends(get_concept_service),
    session: Session = Depends(get_session),
) -> ConceptDecisionResponse:
    _require_graph_curator(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    try:
        decision = concept_service.set_decision_status(
            decision_id,
            decision_status=request.decision_status,
            decided_by=f"manual:{current_user.id}",
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ConceptDecisionResponse.from_model(decision)
