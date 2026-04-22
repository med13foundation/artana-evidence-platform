"""Dictionary proposal governance routes."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast

from artana_evidence_db.auth import (
    get_current_active_user,
    to_graph_principal,
    to_graph_rls_session_context,
)
from artana_evidence_db.common_types import JSONObject
from artana_evidence_db.database import get_session, set_graph_rls_session_context
from artana_evidence_db.dependencies import get_dictionary_service
from artana_evidence_db.dictionary_models import DictionaryProposal
from artana_evidence_db.dictionary_proposal_service import DictionaryProposalService
from artana_evidence_db.graph_access import evaluate_graph_admin_access
from artana_evidence_db.graph_api_schemas.dictionary_schema_common import (
    KernelDataType,
    KernelSensitivity,
)
from artana_evidence_db.graph_api_schemas.dictionary_schema_entities_relations import (
    DictionaryEntityTypeResponse,
    DictionaryRelationSynonymResponse,
    DictionaryRelationTypeResponse,
    RelationConstraintResponse,
)
from artana_evidence_db.graph_api_schemas.dictionary_schema_search_misc import (
    DictionaryDomainContextResponse,
)
from artana_evidence_db.graph_api_schemas.dictionary_schema_value_sets import (
    ValueSetItemResponse,
    ValueSetResponse,
)
from artana_evidence_db.graph_api_schemas.dictionary_schema_variables import (
    VariableDefinitionResponse,
)
from artana_evidence_db.kernel_domain_models import (
    DictionaryDomainContext,
    DictionaryEntityType,
    DictionaryRelationSynonym,
    DictionaryRelationType,
    RelationConstraint,
    ValueSet,
    ValueSetItem,
    VariableDefinition,
)
from artana_evidence_db.semantic_ports import DictionaryPort
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/dictionary/proposals", tags=["dictionary"])

ProposalStatus = Literal[
    "SUBMITTED",
    "CHANGES_REQUESTED",
    "APPROVED",
    "REJECTED",
    "MERGED",
]
ProposalType = Literal[
    "DOMAIN_CONTEXT",
    "ENTITY_TYPE",
    "VARIABLE",
    "RELATION_TYPE",
    "RELATION_CONSTRAINT",
    "RELATION_SYNONYM",
    "VALUE_SET",
    "VALUE_SET_ITEM",
]
ConstraintProfile = Literal["EXPECTED", "ALLOWED", "REVIEW_ONLY", "FORBIDDEN"]


class DomainContextProposalCreateRequest(BaseModel):
    """Create a governed domain-context proposal."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str | None = None
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class EntityTypeProposalCreateRequest(BaseModel):
    """Create a governed entity-type proposal."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    external_ontology_ref: str | None = Field(default=None, max_length=255)
    expected_properties: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class RelationTypeProposalCreateRequest(BaseModel):
    """Create a governed relation-type proposal."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    display_name: str = Field(..., min_length=1, max_length=128)
    description: str = Field(..., min_length=1)
    domain_context: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    is_directional: bool = True
    inverse_label: str | None = Field(default=None, max_length=128)
    source_ref: str | None = Field(default=None, max_length=1024)


class VariableProposalCreateRequest(BaseModel):
    """Create a governed variable proposal."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    canonical_name: str = Field(..., min_length=1, max_length=128)
    display_name: str = Field(..., min_length=1, max_length=128)
    data_type: KernelDataType
    domain_context: str = Field(default="general", min_length=1, max_length=64)
    sensitivity: KernelSensitivity = KernelSensitivity.INTERNAL
    preferred_unit: str | None = Field(default=None, max_length=64)
    constraints: JSONObject = Field(default_factory=dict)
    description: str | None = None
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    source_ref: str | None = Field(default=None, max_length=1024)


class RelationConstraintProposalCreateRequest(BaseModel):
    """Create a governed relation-constraint proposal."""

    model_config = ConfigDict(strict=False)

    source_type: str = Field(..., min_length=1, max_length=64)
    relation_type: str = Field(..., min_length=1, max_length=64)
    target_type: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    is_allowed: bool = True
    requires_evidence: bool = True
    profile: ConstraintProfile = "ALLOWED"
    source_ref: str | None = Field(default=None, max_length=1024)


class RelationSynonymProposalCreateRequest(BaseModel):
    """Create a governed relation-synonym proposal."""

    model_config = ConfigDict(strict=False)

    relation_type_id: str = Field(..., min_length=1, max_length=64)
    synonym: str = Field(..., min_length=1, max_length=64)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    source: str | None = Field(default=None, max_length=64)
    source_ref: str | None = Field(default=None, max_length=1024)


class ValueSetProposalCreateRequest(BaseModel):
    """Create a governed value-set proposal."""

    model_config = ConfigDict(strict=False)

    id: str = Field(..., min_length=1, max_length=64)
    variable_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    description: str | None = None
    external_ref: str | None = Field(default=None, max_length=255)
    is_extensible: bool = False
    source_ref: str | None = Field(default=None, max_length=1024)


class ValueSetItemProposalCreateRequest(BaseModel):
    """Create a governed value-set item proposal."""

    model_config = ConfigDict(strict=False)

    code: str = Field(..., min_length=1, max_length=128)
    display_label: str = Field(..., min_length=1, max_length=255)
    rationale: str = Field(..., min_length=1)
    evidence_payload: JSONObject = Field(default_factory=dict)
    synonyms: list[str] = Field(default_factory=list)
    external_ref: str | None = Field(default=None, max_length=255)
    sort_order: int = 0
    is_active: bool = True
    source_ref: str | None = Field(default=None, max_length=1024)


class DictionaryProposalDecisionRequest(BaseModel):
    """Approve or reject a dictionary proposal."""

    model_config = ConfigDict(strict=False)

    decision_reason: str | None = Field(default=None, max_length=4096)


class DictionaryProposalRejectRequest(BaseModel):
    """Reject a dictionary proposal with a required reason."""

    model_config = ConfigDict(strict=False)

    decision_reason: str = Field(..., min_length=1, max_length=4096)


class DictionaryProposalRequestChangesRequest(BaseModel):
    """Request changes on a dictionary proposal with a required reason."""

    model_config = ConfigDict(strict=False)

    decision_reason: str = Field(..., min_length=1, max_length=4096)


class DictionaryProposalMergeRequest(BaseModel):
    """Merge a proposal into an existing official dictionary entry."""

    model_config = ConfigDict(strict=False)

    target_id: str = Field(..., min_length=1, max_length=128)
    decision_reason: str = Field(..., min_length=1, max_length=4096)


class DictionaryProposalResponse(BaseModel):
    """Public dictionary proposal response."""

    model_config = ConfigDict(strict=True)

    id: str
    proposal_type: ProposalType
    status: ProposalStatus
    entity_type: str | None
    source_type: str | None
    relation_type: str | None
    target_type: str | None
    value_set_id: str | None
    variable_id: str | None
    canonical_name: str | None
    data_type: str | None
    preferred_unit: str | None
    constraints: JSONObject
    sensitivity: str | None
    code: str | None
    synonym: str | None
    source: str | None
    display_name: str | None
    name: str | None
    display_label: str | None
    description: str | None
    domain_context: str | None
    external_ontology_ref: str | None
    external_ref: str | None
    expected_properties: JSONObject
    synonyms: list[str]
    is_directional: bool | None
    inverse_label: str | None
    is_extensible: bool | None
    sort_order: int | None
    is_active_value: bool | None
    is_allowed: bool | None
    requires_evidence: bool | None
    profile: str | None
    rationale: str
    evidence_payload: JSONObject
    proposed_by: str
    reviewed_by: str | None
    reviewed_at: datetime | None
    decision_reason: str | None
    merge_target_type: str | None
    merge_target_id: str | None
    applied_domain_context_id: str | None
    applied_entity_type_id: str | None
    applied_variable_id: str | None
    applied_relation_type_id: str | None
    applied_constraint_id: int | None
    applied_relation_synonym_id: int | None
    applied_value_set_id: str | None
    applied_value_set_item_id: int | None
    source_ref: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, model: DictionaryProposal) -> DictionaryProposalResponse:
        return cls(
            id=model.id,
            proposal_type=model.proposal_type,
            status=model.status,
            entity_type=model.entity_type,
            source_type=model.source_type,
            relation_type=model.relation_type,
            target_type=model.target_type,
            value_set_id=model.value_set_id,
            variable_id=model.variable_id,
            canonical_name=model.canonical_name,
            data_type=model.data_type,
            preferred_unit=model.preferred_unit,
            constraints=dict(model.constraints),
            sensitivity=model.sensitivity,
            code=model.code,
            synonym=model.synonym,
            source=model.source,
            display_name=model.display_name,
            name=model.name,
            display_label=model.display_label,
            description=model.description,
            domain_context=model.domain_context,
            external_ontology_ref=model.external_ontology_ref,
            external_ref=model.external_ref,
            expected_properties=dict(model.expected_properties),
            synonyms=list(model.synonyms),
            is_directional=model.is_directional,
            inverse_label=model.inverse_label,
            is_extensible=model.is_extensible,
            sort_order=model.sort_order,
            is_active_value=model.is_active_value,
            is_allowed=model.is_allowed,
            requires_evidence=model.requires_evidence,
            profile=model.profile,
            rationale=model.rationale,
            evidence_payload=dict(model.evidence_payload),
            proposed_by=model.proposed_by,
            reviewed_by=model.reviewed_by,
            reviewed_at=model.reviewed_at,
            decision_reason=model.decision_reason,
            merge_target_type=model.merge_target_type,
            merge_target_id=model.merge_target_id,
            applied_domain_context_id=model.applied_domain_context_id,
            applied_entity_type_id=model.applied_entity_type_id,
            applied_variable_id=model.applied_variable_id,
            applied_relation_type_id=model.applied_relation_type_id,
            applied_constraint_id=model.applied_constraint_id,
            applied_relation_synonym_id=model.applied_relation_synonym_id,
            applied_value_set_id=model.applied_value_set_id,
            applied_value_set_item_id=model.applied_value_set_item_id,
            source_ref=model.source_ref,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class DictionaryProposalListResponse(BaseModel):
    """List response for dictionary proposals."""

    model_config = ConfigDict(strict=True)

    proposals: list[DictionaryProposalResponse]
    total: int


class DictionaryProposalApprovalResponse(BaseModel):
    """Approval response containing the proposal and applied dictionary object."""

    model_config = ConfigDict(strict=True)

    proposal: DictionaryProposalResponse
    applied_domain_context: DictionaryDomainContextResponse | None = None
    applied_entity_type: DictionaryEntityTypeResponse | None = None
    applied_variable: VariableDefinitionResponse | None = None
    applied_relation_type: DictionaryRelationTypeResponse | None = None
    applied_constraint: RelationConstraintResponse | None = None
    applied_relation_synonym: DictionaryRelationSynonymResponse | None = None
    applied_value_set: ValueSetResponse | None = None
    applied_value_set_item: ValueSetItemResponse | None = None


def _require_graph_admin(*, current_user: User, session: Session) -> None:
    if not evaluate_graph_admin_access(to_graph_principal(current_user)).allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Graph service admin access is required for this operation",
        )
    set_graph_rls_session_context(
        session,
        context=to_graph_rls_session_context(current_user, bypass_rls=True),
    )


def _manual_actor(current_user: User) -> str:
    return f"manual:{current_user.id}"


def _proposal_service(
    *,
    session: Session,
    dictionary_service: DictionaryPort,
) -> DictionaryProposalService:
    return DictionaryProposalService(
        session=session,
        dictionary_service=dictionary_service,
    )


def _resolve_proposal_source_ref(
    *,
    actor: str,
    request_source_ref: str | None,
    idempotency_key: str | None,
) -> str | None:
    normalized_request_ref = (
        request_source_ref.strip() if request_source_ref is not None else None
    )
    normalized_key = idempotency_key.strip() if idempotency_key is not None else None
    if normalized_request_ref and normalized_key:
        msg = "Use either source_ref or Idempotency-Key, not both."
        raise ValueError(msg)
    if normalized_request_ref:
        return normalized_request_ref
    if normalized_key:
        return f"idempotency-key:{actor}:{normalized_key}"
    return None


@router.post(
    "/domain-contexts",
    response_model=DictionaryProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose one domain context for governed review",
)
def create_domain_context_proposal(
    request: DomainContextProposalCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.create_domain_context_proposal(
            domain_context_id=request.id,
            display_name=request.display_name,
            description=request.description,
            rationale=request.rationale,
            evidence_payload=request.evidence_payload,
            proposed_by=_manual_actor(current_user),
            source_ref=_resolve_proposal_source_ref(
                actor=_manual_actor(current_user),
                request_source_ref=request.source_ref,
                idempotency_key=idempotency_key,
            ),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.post(
    "/entity-types",
    response_model=DictionaryProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose one entity type for governed review",
)
def create_entity_type_proposal(
    request: EntityTypeProposalCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.create_entity_type_proposal(
            entity_type=request.id,
            display_name=request.display_name,
            description=request.description,
            domain_context=request.domain_context,
            rationale=request.rationale,
            evidence_payload=request.evidence_payload,
            external_ontology_ref=request.external_ontology_ref,
            expected_properties=request.expected_properties,
            proposed_by=_manual_actor(current_user),
            source_ref=_resolve_proposal_source_ref(
                actor=_manual_actor(current_user),
                request_source_ref=request.source_ref,
                idempotency_key=idempotency_key,
            ),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.post(
    "/relation-types",
    response_model=DictionaryProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose one relation type for governed review",
)
def create_relation_type_proposal(
    request: RelationTypeProposalCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.create_relation_type_proposal(
            relation_type=request.id,
            display_name=request.display_name,
            description=request.description,
            domain_context=request.domain_context,
            rationale=request.rationale,
            evidence_payload=request.evidence_payload,
            is_directional=request.is_directional,
            inverse_label=request.inverse_label,
            proposed_by=_manual_actor(current_user),
            source_ref=_resolve_proposal_source_ref(
                actor=_manual_actor(current_user),
                request_source_ref=request.source_ref,
                idempotency_key=idempotency_key,
            ),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.post(
    "/variables",
    response_model=DictionaryProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose one variable for governed review",
)
def create_variable_proposal(
    request: VariableProposalCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.create_variable_proposal(
            variable_id=request.id,
            canonical_name=request.canonical_name,
            display_name=request.display_name,
            data_type=request.data_type.value,
            domain_context=request.domain_context,
            sensitivity=request.sensitivity.value,
            preferred_unit=request.preferred_unit,
            constraints=request.constraints,
            description=request.description,
            rationale=request.rationale,
            evidence_payload=request.evidence_payload,
            proposed_by=_manual_actor(current_user),
            source_ref=_resolve_proposal_source_ref(
                actor=_manual_actor(current_user),
                request_source_ref=request.source_ref,
                idempotency_key=idempotency_key,
            ),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.post(
    "/relation-constraints",
    response_model=DictionaryProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose one relation constraint for governed review",
)
def create_relation_constraint_proposal(
    request: RelationConstraintProposalCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.create_relation_constraint_proposal(
            source_type=request.source_type,
            relation_type=request.relation_type,
            target_type=request.target_type,
            rationale=request.rationale,
            evidence_payload=request.evidence_payload,
            is_allowed=request.is_allowed,
            requires_evidence=request.requires_evidence,
            profile=request.profile,
            proposed_by=_manual_actor(current_user),
            source_ref=_resolve_proposal_source_ref(
                actor=_manual_actor(current_user),
                request_source_ref=request.source_ref,
                idempotency_key=idempotency_key,
            ),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.post(
    "/relation-synonyms",
    response_model=DictionaryProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose one relation synonym for governed review",
)
def create_relation_synonym_proposal(
    request: RelationSynonymProposalCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.create_relation_synonym_proposal(
            relation_type_id=request.relation_type_id,
            synonym=request.synonym,
            rationale=request.rationale,
            evidence_payload=request.evidence_payload,
            source=request.source,
            proposed_by=_manual_actor(current_user),
            source_ref=_resolve_proposal_source_ref(
                actor=_manual_actor(current_user),
                request_source_ref=request.source_ref,
                idempotency_key=idempotency_key,
            ),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.post(
    "/value-sets",
    response_model=DictionaryProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose one value set for governed review",
)
def create_value_set_proposal(
    request: ValueSetProposalCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.create_value_set_proposal(
            value_set_id=request.id,
            variable_id=request.variable_id,
            name=request.name,
            rationale=request.rationale,
            evidence_payload=request.evidence_payload,
            description=request.description,
            external_ref=request.external_ref,
            is_extensible=request.is_extensible,
            proposed_by=_manual_actor(current_user),
            source_ref=_resolve_proposal_source_ref(
                actor=_manual_actor(current_user),
                request_source_ref=request.source_ref,
                idempotency_key=idempotency_key,
            ),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.post(
    "/value-sets/{value_set_id}/items",
    response_model=DictionaryProposalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Propose one value-set item for governed review",
)
def create_value_set_item_proposal(
    value_set_id: str,
    request: ValueSetItemProposalCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.create_value_set_item_proposal(
            value_set_id=value_set_id,
            code=request.code,
            display_label=request.display_label,
            rationale=request.rationale,
            evidence_payload=request.evidence_payload,
            synonyms=request.synonyms,
            external_ref=request.external_ref,
            sort_order=request.sort_order,
            is_active=request.is_active,
            proposed_by=_manual_actor(current_user),
            source_ref=_resolve_proposal_source_ref(
                actor=_manual_actor(current_user),
                request_source_ref=request.source_ref,
                idempotency_key=idempotency_key,
            ),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.get(
    "",
    response_model=DictionaryProposalListResponse,
    summary="List dictionary proposals",
)
def list_dictionary_proposals(
    *,
    proposal_status: ProposalStatus | None = Query(default=None),
    proposal_type: ProposalType | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryProposalListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    proposals = service.list_proposals(
        status=proposal_status,
        proposal_type=proposal_type,
        limit=limit,
    )
    return DictionaryProposalListResponse(
        proposals=[
            DictionaryProposalResponse.from_model(proposal) for proposal in proposals
        ],
        total=len(proposals),
    )


@router.get(
    "/{proposal_id}",
    response_model=DictionaryProposalResponse,
    summary="Get one dictionary proposal",
)
def get_dictionary_proposal(
    proposal_id: str,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.get_proposal(proposal_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.post(
    "/{proposal_id}/approve",
    response_model=DictionaryProposalApprovalResponse,
    summary="Approve and apply a dictionary proposal",
)
def approve_dictionary_proposal(
    proposal_id: str,
    request: DictionaryProposalDecisionRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryProposalApprovalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal, applied = service.approve_proposal(
            proposal_id,
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Proposal approval conflicts with existing dictionary state",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    applied_domain_context = (
        DictionaryDomainContextResponse.from_model(
            cast("DictionaryDomainContext", applied),
        )
        if proposal.proposal_type == "DOMAIN_CONTEXT"
        else None
    )
    applied_entity_type = (
        DictionaryEntityTypeResponse.from_model(cast("DictionaryEntityType", applied))
        if proposal.proposal_type == "ENTITY_TYPE"
        else None
    )
    applied_variable = (
        VariableDefinitionResponse.from_model(cast("VariableDefinition", applied))
        if proposal.proposal_type == "VARIABLE"
        else None
    )
    applied_relation_type = (
        DictionaryRelationTypeResponse.from_model(
            cast("DictionaryRelationType", applied),
        )
        if proposal.proposal_type == "RELATION_TYPE"
        else None
    )
    applied_constraint = (
        RelationConstraintResponse.from_model(cast("RelationConstraint", applied))
        if proposal.proposal_type == "RELATION_CONSTRAINT"
        else None
    )
    applied_relation_synonym = (
        DictionaryRelationSynonymResponse.from_model(
            cast("DictionaryRelationSynonym", applied),
        )
        if proposal.proposal_type == "RELATION_SYNONYM"
        else None
    )
    applied_value_set = (
        ValueSetResponse.from_model(cast("ValueSet", applied))
        if proposal.proposal_type == "VALUE_SET"
        else None
    )
    applied_value_set_item = (
        ValueSetItemResponse.from_model(cast("ValueSetItem", applied))
        if proposal.proposal_type == "VALUE_SET_ITEM"
        else None
    )
    return DictionaryProposalApprovalResponse(
        proposal=DictionaryProposalResponse.from_model(proposal),
        applied_domain_context=applied_domain_context,
        applied_entity_type=applied_entity_type,
        applied_variable=applied_variable,
        applied_relation_type=applied_relation_type,
        applied_constraint=applied_constraint,
        applied_relation_synonym=applied_relation_synonym,
        applied_value_set=applied_value_set,
        applied_value_set_item=applied_value_set_item,
    )


@router.post(
    "/{proposal_id}/reject",
    response_model=DictionaryProposalResponse,
    summary="Reject a dictionary proposal",
)
def reject_dictionary_proposal(
    proposal_id: str,
    request: DictionaryProposalRejectRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.reject_proposal(
            proposal_id,
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.post(
    "/{proposal_id}/request-changes",
    response_model=DictionaryProposalResponse,
    summary="Request changes on a dictionary proposal",
)
def request_changes_dictionary_proposal(
    proposal_id: str,
    request: DictionaryProposalRequestChangesRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.request_changes(
            proposal_id,
            reviewed_by=_manual_actor(current_user),
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


@router.post(
    "/{proposal_id}/merge",
    response_model=DictionaryProposalResponse,
    summary="Merge a dictionary proposal into an existing official entry",
)
def merge_dictionary_proposal(
    proposal_id: str,
    request: DictionaryProposalMergeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryProposalResponse:
    _require_graph_admin(current_user=current_user, session=session)
    service = _proposal_service(
        session=session,
        dictionary_service=dictionary_service,
    )
    try:
        proposal = service.merge_proposal(
            proposal_id,
            reviewed_by=_manual_actor(current_user),
            target_id=request.target_id,
            decision_reason=request.decision_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    return DictionaryProposalResponse.from_model(proposal)


__all__ = [
    "DictionaryProposalApprovalResponse",
    "DictionaryProposalListResponse",
    "DictionaryProposalResponse",
    "create_domain_context_proposal",
    "create_entity_type_proposal",
    "create_relation_constraint_proposal",
    "create_relation_synonym_proposal",
    "create_relation_type_proposal",
    "create_variable_proposal",
    "create_value_set_item_proposal",
    "create_value_set_proposal",
    "get_dictionary_proposal",
    "list_dictionary_proposals",
    "merge_dictionary_proposal",
    "reject_dictionary_proposal",
    "request_changes_dictionary_proposal",
    "router",
]
