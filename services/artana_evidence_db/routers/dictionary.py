"""Dictionary governance routes for the standalone graph service."""

from __future__ import annotations

from typing import Literal

from artana_evidence_db.auth import (
    get_current_active_user,
)
from artana_evidence_db.database import (
    get_session,
)
from artana_evidence_db.dependencies import get_dictionary_service
from artana_evidence_db.dictionary_router_support import (
    RelationConstraintCreateRequest,
    _manual_actor,
    _require_graph_admin,
)
from artana_evidence_db.semantic_ports import DictionaryPort
from artana_evidence_db.service_contracts import (
    DictionaryChangelogListResponse,
    DictionaryChangelogResponse,
    DictionaryDomainContextListResponse,
    DictionaryDomainContextResponse,
    DictionaryEntityTypeCreateRequest,
    DictionaryEntityTypeListResponse,
    DictionaryEntityTypeResponse,
    DictionaryMergeRequest,
    DictionaryRelationSynonymCreateRequest,
    DictionaryRelationSynonymListResponse,
    DictionaryRelationSynonymResponse,
    DictionaryRelationTypeCreateRequest,
    DictionaryRelationTypeListResponse,
    DictionaryRelationTypeResponse,
    DictionarySearchListResponse,
    DictionarySearchResultResponse,
    EntityResolutionPolicyListResponse,
    EntityResolutionPolicyResponse,
    RelationConstraintListResponse,
    RelationConstraintResponse,
    ValueSetCreateRequest,
    ValueSetItemActiveRequest,
    ValueSetItemCreateRequest,
    ValueSetItemListResponse,
    ValueSetItemResponse,
    ValueSetListResponse,
    ValueSetResponse,
    VariableDefinitionCreateRequest,
    VariableDefinitionListResponse,
    VariableDefinitionResponse,
    VariableDefinitionReviewStatusRequest,
    VariableDefinitionRevokeRequest,
)
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/dictionary", tags=["dictionary"])


@router.get(
    "/domain-contexts",
    response_model=DictionaryDomainContextListResponse,
    summary="List graph dictionary domain contexts",
    description=(
        "Returns the approved `domain_context` ids accepted by dictionary mutation "
        "routes such as `POST /v1/dictionary/entity-types`. Dictionary governance "
        "routes require a bearer token with `graph_admin=true`."
    ),
)
def list_dictionary_domain_contexts(
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryDomainContextListResponse:
    """Return the approved graph dictionary domain contexts."""
    _require_graph_admin(current_user=current_user, session=session)
    domain_contexts = dictionary_service.list_domain_contexts()
    return DictionaryDomainContextListResponse(
        domain_contexts=[
            DictionaryDomainContextResponse.from_model(domain_context)
            for domain_context in domain_contexts
        ],
        total=len(domain_contexts),
    )


@router.get(
    "/search/by-domain/{domain_context}",
    response_model=DictionarySearchListResponse,
    summary="List graph dictionary entries by domain",
)
def search_dictionary_entries_by_domain(
    domain_context: str,
    *,
    limit: int = Query(default=200, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionarySearchListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        results = dictionary_service.dictionary_search_by_domain(
            domain_context=domain_context,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionarySearchListResponse(
        results=[
            DictionarySearchResultResponse.from_model(result) for result in results
        ],
        total=len(results),
    )


@router.get(
    "/resolution-policies",
    response_model=EntityResolutionPolicyListResponse,
    summary="List graph dictionary entity resolution policies",
)
def list_entity_resolution_policies(
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> EntityResolutionPolicyListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    policies = dictionary_service.list_resolution_policies()
    return EntityResolutionPolicyListResponse(
        policies=[
            EntityResolutionPolicyResponse.from_model(policy) for policy in policies
        ],
        total=len(policies),
    )


@router.get(
    "/relation-constraints",
    response_model=RelationConstraintListResponse,
    summary="List graph dictionary relation constraints",
)
def list_relation_constraints(
    *,
    source_type: str | None = Query(default=None),
    relation_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> RelationConstraintListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    constraints = dictionary_service.get_constraints(
        source_type=source_type,
        relation_type=relation_type,
    )
    return RelationConstraintListResponse(
        constraints=[
            RelationConstraintResponse.from_model(constraint)
            for constraint in constraints
        ],
        total=len(constraints),
    )


@router.get(
    "/changelog",
    response_model=DictionaryChangelogListResponse,
    summary="List graph dictionary changelog entries",
)
def list_dictionary_changelog_entries(
    *,
    table_name: str | None = Query(default=None),
    record_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryChangelogListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    changelog_entries = dictionary_service.list_changelog_entries(
        table_name=table_name,
        record_id=record_id,
        limit=limit,
    )
    return DictionaryChangelogListResponse(
        changelog_entries=[
            DictionaryChangelogResponse.from_model(entry) for entry in changelog_entries
        ],
        total=len(changelog_entries),
    )


@router.post(
    "/relation-constraints",
    response_model=RelationConstraintResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one graph dictionary relation constraint",
)
def create_relation_constraint(
    request: RelationConstraintCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> RelationConstraintResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        constraint = dictionary_service.create_relation_constraint(
            source_type=request.source_type,
            relation_type=request.relation_type,
            target_type=request.target_type,
            is_allowed=request.is_allowed,
            requires_evidence=request.requires_evidence,
            profile=request.profile,
            created_by=_manual_actor(current_user),
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Relation constraint already exists or references invalid dictionary types",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return RelationConstraintResponse.from_model(constraint)


@router.get(
    "/variables",
    response_model=VariableDefinitionListResponse,
    summary="List graph dictionary variables",
)
def list_dictionary_variables(
    *,
    domain_context: str | None = Query(default=None),
    data_type: str | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> VariableDefinitionListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    variables = dictionary_service.list_variables(
        domain_context=domain_context,
        data_type=data_type,
    )
    return VariableDefinitionListResponse(
        variables=[
            VariableDefinitionResponse.from_model(variable) for variable in variables
        ],
        total=len(variables),
    )


@router.post(
    "/variables",
    response_model=VariableDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one graph dictionary variable",
)
def create_dictionary_variable(
    request: VariableDefinitionCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> VariableDefinitionResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        variable = dictionary_service.create_variable(
            variable_id=request.id,
            canonical_name=request.canonical_name,
            display_name=request.display_name,
            data_type=request.data_type.value,
            domain_context=request.domain_context,
            sensitivity=request.sensitivity.value,
            preferred_unit=request.preferred_unit,
            constraints=dict(request.constraints),
            description=request.description,
            created_by=_manual_actor(current_user),
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Variable already exists",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return VariableDefinitionResponse.from_model(variable)


@router.patch(
    "/variables/{variable_id}/review-status",
    response_model=VariableDefinitionResponse,
    summary="Set graph dictionary variable review status",
)
def set_dictionary_variable_review_status(
    variable_id: str,
    request: VariableDefinitionReviewStatusRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> VariableDefinitionResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        variable = dictionary_service.set_review_status(
            variable_id,
            review_status=request.review_status.value,
            reviewed_by=_manual_actor(current_user),
            revocation_reason=request.revocation_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return VariableDefinitionResponse.from_model(variable)


@router.post(
    "/variables/{variable_id}/revoke",
    response_model=VariableDefinitionResponse,
    summary="Revoke one graph dictionary variable",
)
def revoke_dictionary_variable(
    variable_id: str,
    request: VariableDefinitionRevokeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> VariableDefinitionResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        variable = dictionary_service.revoke_variable(
            variable_id,
            reason=request.reason,
            reviewed_by=_manual_actor(current_user),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return VariableDefinitionResponse.from_model(variable)


@router.post(
    "/variables/{variable_id}/merge",
    response_model=VariableDefinitionResponse,
    summary="Merge one graph dictionary variable into another",
)
def merge_dictionary_variable(
    variable_id: str,
    request: DictionaryMergeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> VariableDefinitionResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        variable = dictionary_service.merge_variable_definition(
            variable_id,
            request.target_id,
            reason=request.reason,
            reviewed_by=_manual_actor(current_user),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return VariableDefinitionResponse.from_model(variable)


@router.get(
    "/value-sets",
    response_model=ValueSetListResponse,
    summary="List graph dictionary value sets",
)
def list_dictionary_value_sets(
    *,
    variable_id: str | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> ValueSetListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    value_sets = dictionary_service.list_value_sets(variable_id=variable_id)
    return ValueSetListResponse(
        value_sets=[ValueSetResponse.from_model(value_set) for value_set in value_sets],
        total=len(value_sets),
    )


@router.post(
    "/value-sets",
    response_model=ValueSetResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one graph dictionary value set",
)
def create_dictionary_value_set(
    request: ValueSetCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> ValueSetResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        value_set = dictionary_service.create_value_set(
            value_set_id=request.id,
            variable_id=request.variable_id,
            name=request.name,
            description=request.description,
            external_ref=request.external_ref,
            is_extensible=request.is_extensible,
            created_by=_manual_actor(current_user),
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Value set already exists or references invalid variable",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ValueSetResponse.from_model(value_set)


@router.get(
    "/value-sets/{value_set_id}/items",
    response_model=ValueSetItemListResponse,
    summary="List graph dictionary value set items",
)
def list_dictionary_value_set_items(
    value_set_id: str,
    *,
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> ValueSetItemListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    items = dictionary_service.list_value_set_items(
        value_set_id=value_set_id,
        include_inactive=include_inactive,
    )
    return ValueSetItemListResponse(
        items=[ValueSetItemResponse.from_model(item) for item in items],
        total=len(items),
    )


@router.post(
    "/value-sets/{value_set_id}/items",
    response_model=ValueSetItemResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one graph dictionary value set item",
)
def create_dictionary_value_set_item(
    value_set_id: str,
    request: ValueSetItemCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> ValueSetItemResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        item = dictionary_service.create_value_set_item(
            value_set_id=value_set_id,
            code=request.code,
            display_label=request.display_label,
            synonyms=request.synonyms,
            external_ref=request.external_ref,
            sort_order=request.sort_order,
            is_active=request.is_active,
            created_by=_manual_actor(current_user),
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Value set item already exists or references invalid value set",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ValueSetItemResponse.from_model(item)


@router.patch(
    "/value-set-items/{value_set_item_id}/active",
    response_model=ValueSetItemResponse,
    summary="Activate or deactivate one graph dictionary value set item",
)
def set_dictionary_value_set_item_active(
    value_set_item_id: int,
    request: ValueSetItemActiveRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> ValueSetItemResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        item = dictionary_service.set_value_set_item_active(
            value_set_item_id,
            is_active=request.is_active,
            reviewed_by=_manual_actor(current_user),
            revocation_reason=request.revocation_reason,
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ValueSetItemResponse.from_model(item)


@router.get(
    "/entity-types",
    response_model=DictionaryEntityTypeListResponse,
    summary="List graph dictionary entity types",
    description=(
        "List entity types scoped to one optional dictionary domain context. "
        "Use `GET /v1/dictionary/domain-contexts` to discover valid domain "
        "context ids. Requires `graph_admin=true`."
    ),
)
def list_dictionary_entity_types(
    *,
    domain_context: str | None = Query(
        default=None,
        description=(
            "Optional approved domain-context id, such as `general`, "
            "`clinical`, or `genomics`."
        ),
    ),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryEntityTypeListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    entity_types = dictionary_service.list_entity_types(domain_context=domain_context)
    return DictionaryEntityTypeListResponse(
        entity_types=[
            DictionaryEntityTypeResponse.from_model(entity_type)
            for entity_type in entity_types
        ],
        total=len(entity_types),
    )


@router.get(
    "/entity-types/{entity_type_id}",
    response_model=DictionaryEntityTypeResponse,
    summary="Get one graph dictionary entity type",
)
def get_dictionary_entity_type(
    entity_type_id: str,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryEntityTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    entity_type = dictionary_service.get_entity_type(entity_type_id)
    if entity_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entity type '{entity_type_id}' not found",
        )
    return DictionaryEntityTypeResponse.from_model(entity_type)


@router.post(
    "/entity-types",
    response_model=DictionaryEntityTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one graph dictionary entity type",
    description=(
        "Create one dictionary entity type. Requires a bearer token with "
        "`graph_admin=true`. The `domain_context` field must be one of the ids "
        "returned by `GET /v1/dictionary/domain-contexts`."
    ),
)
def create_dictionary_entity_type(
    request: DictionaryEntityTypeCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryEntityTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        entity_type = dictionary_service.create_entity_type(
            entity_type=request.id,
            display_name=request.display_name,
            description=request.description,
            domain_context=request.domain_context,
            external_ontology_ref=request.external_ontology_ref,
            expected_properties=dict(request.expected_properties),
            created_by=_manual_actor(current_user),
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entity type already exists or references invalid domain context",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryEntityTypeResponse.from_model(entity_type)


@router.patch(
    "/entity-types/{entity_type_id}/review-status",
    response_model=DictionaryEntityTypeResponse,
    summary="Set graph dictionary entity type review status",
)
def set_dictionary_entity_type_review_status(
    entity_type_id: str,
    request: VariableDefinitionReviewStatusRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryEntityTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        entity_type = dictionary_service.set_entity_type_review_status(
            entity_type_id,
            review_status=request.review_status.value,
            reviewed_by=_manual_actor(current_user),
            revocation_reason=request.revocation_reason,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Entity type review-status update conflicts with active graph references "
                "or dictionary constraints"
            ),
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryEntityTypeResponse.from_model(entity_type)


@router.post(
    "/entity-types/{entity_type_id}/revoke",
    response_model=DictionaryEntityTypeResponse,
    summary="Revoke one graph dictionary entity type",
)
def revoke_dictionary_entity_type(
    entity_type_id: str,
    request: VariableDefinitionRevokeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryEntityTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        entity_type = dictionary_service.revoke_entity_type(
            entity_type_id,
            reason=request.reason,
            reviewed_by=_manual_actor(current_user),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Entity type revoke conflicts with active graph references or dictionary constraints"
            ),
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryEntityTypeResponse.from_model(entity_type)


@router.post(
    "/entity-types/{entity_type_id}/merge",
    response_model=DictionaryEntityTypeResponse,
    summary="Merge one graph dictionary entity type into another",
)
def merge_dictionary_entity_type(
    entity_type_id: str,
    request: DictionaryMergeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryEntityTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        entity_type = dictionary_service.merge_entity_type(
            entity_type_id,
            request.target_id,
            reason=request.reason,
            reviewed_by=_manual_actor(current_user),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryEntityTypeResponse.from_model(entity_type)


@router.get(
    "/relation-types",
    response_model=DictionaryRelationTypeListResponse,
    summary="List graph dictionary relation types",
)
def list_dictionary_relation_types(
    *,
    domain_context: str | None = Query(default=None),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationTypeListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    relation_types = dictionary_service.list_relation_types(
        domain_context=domain_context,
    )
    return DictionaryRelationTypeListResponse(
        relation_types=[
            DictionaryRelationTypeResponse.from_model(relation_type)
            for relation_type in relation_types
        ],
        total=len(relation_types),
    )


@router.get(
    "/relation-types/{relation_type_id}",
    response_model=DictionaryRelationTypeResponse,
    summary="Get one graph dictionary relation type",
)
def get_dictionary_relation_type(
    relation_type_id: str,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    relation_type = dictionary_service.get_relation_type(relation_type_id)
    if relation_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relation type '{relation_type_id}' not found",
        )
    return DictionaryRelationTypeResponse.from_model(relation_type)


@router.post(
    "/relation-types",
    response_model=DictionaryRelationTypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one graph dictionary relation type",
)
def create_dictionary_relation_type(
    request: DictionaryRelationTypeCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        relation_type = dictionary_service.create_relation_type(
            relation_type=request.id,
            display_name=request.display_name,
            description=request.description,
            domain_context=request.domain_context,
            is_directional=request.is_directional,
            inverse_label=request.inverse_label,
            created_by=_manual_actor(current_user),
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Relation type already exists or references invalid domain context",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryRelationTypeResponse.from_model(relation_type)


@router.patch(
    "/relation-types/{relation_type_id}/review-status",
    response_model=DictionaryRelationTypeResponse,
    summary="Set graph dictionary relation type review status",
)
def set_dictionary_relation_type_review_status(
    relation_type_id: str,
    request: VariableDefinitionReviewStatusRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        relation_type = dictionary_service.set_relation_type_review_status(
            relation_type_id,
            review_status=request.review_status.value,
            reviewed_by=_manual_actor(current_user),
            revocation_reason=request.revocation_reason,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Relation type review-status update conflicts with active graph references "
                "or dictionary constraints"
            ),
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryRelationTypeResponse.from_model(relation_type)


@router.post(
    "/relation-types/{relation_type_id}/revoke",
    response_model=DictionaryRelationTypeResponse,
    summary="Revoke one graph dictionary relation type",
)
def revoke_dictionary_relation_type(
    relation_type_id: str,
    request: VariableDefinitionRevokeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        relation_type = dictionary_service.revoke_relation_type(
            relation_type_id,
            reason=request.reason,
            reviewed_by=_manual_actor(current_user),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Relation type revoke conflicts with active graph references or dictionary constraints"
            ),
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryRelationTypeResponse.from_model(relation_type)


@router.post(
    "/relation-types/{relation_type_id}/merge",
    response_model=DictionaryRelationTypeResponse,
    summary="Merge one graph dictionary relation type into another",
)
def merge_dictionary_relation_type(
    relation_type_id: str,
    request: DictionaryMergeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        relation_type = dictionary_service.merge_relation_type(
            relation_type_id,
            request.target_id,
            reason=request.reason,
            reviewed_by=_manual_actor(current_user),
        )
        session.commit()
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryRelationTypeResponse.from_model(relation_type)


@router.get(
    "/relation-synonyms",
    response_model=DictionaryRelationSynonymListResponse,
    summary="List graph dictionary relation synonyms",
)
def list_dictionary_relation_synonyms(
    *,
    relation_type_id: str | None = Query(default=None),
    review_status: Literal["ACTIVE", "PENDING_REVIEW", "REVOKED"] | None = Query(
        default=None,
    ),
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationSynonymListResponse:
    _require_graph_admin(current_user=current_user, session=session)
    relation_synonyms = dictionary_service.list_relation_synonyms(
        relation_type_id=relation_type_id,
        review_status=review_status,
        include_inactive=include_inactive,
    )
    return DictionaryRelationSynonymListResponse(
        relation_synonyms=[
            DictionaryRelationSynonymResponse.from_model(relation_synonym)
            for relation_synonym in relation_synonyms
        ],
        total=len(relation_synonyms),
    )


@router.get(
    "/relation-synonyms/resolve",
    response_model=DictionaryRelationTypeResponse,
    summary="Resolve one graph dictionary relation synonym",
)
def resolve_dictionary_relation_synonym(
    *,
    synonym: str = Query(..., min_length=1),
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationTypeResponse:
    _require_graph_admin(current_user=current_user, session=session)
    relation_type = dictionary_service.resolve_relation_synonym(
        synonym,
        include_inactive=include_inactive,
    )
    if relation_type is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Relation synonym '{synonym}' not found",
        )
    return DictionaryRelationTypeResponse.from_model(relation_type)


@router.post(
    "/relation-synonyms",
    response_model=DictionaryRelationSynonymResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create one graph dictionary relation synonym",
)
def create_dictionary_relation_synonym(
    request: DictionaryRelationSynonymCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationSynonymResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        relation_synonym = dictionary_service.create_relation_synonym(
            relation_type_id=request.relation_type_id,
            synonym=request.synonym,
            source=request.source,
            created_by=_manual_actor(current_user),
            source_ref=request.source_ref,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Relation synonym already exists, conflicts with another canonical relation "
                "type, or references an invalid relation type"
            ),
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryRelationSynonymResponse.from_model(relation_synonym)


@router.patch(
    "/relation-synonyms/{synonym_id}/review-status",
    response_model=DictionaryRelationSynonymResponse,
    summary="Set graph dictionary relation synonym review status",
)
def set_dictionary_relation_synonym_review_status(
    synonym_id: int,
    request: VariableDefinitionReviewStatusRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationSynonymResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        relation_synonym = dictionary_service.set_relation_synonym_review_status(
            synonym_id,
            review_status=request.review_status.value,
            reviewed_by=_manual_actor(current_user),
            revocation_reason=request.revocation_reason,
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Relation synonym review-status update conflicts with dictionary constraints",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryRelationSynonymResponse.from_model(relation_synonym)


@router.post(
    "/relation-synonyms/{synonym_id}/revoke",
    response_model=DictionaryRelationSynonymResponse,
    summary="Revoke one graph dictionary relation synonym",
)
def revoke_dictionary_relation_synonym(
    synonym_id: int,
    request: VariableDefinitionRevokeRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    dictionary_service: DictionaryPort = Depends(get_dictionary_service),
    session: Session = Depends(get_session),
) -> DictionaryRelationSynonymResponse:
    _require_graph_admin(current_user=current_user, session=session)
    try:
        relation_synonym = dictionary_service.revoke_relation_synonym(
            synonym_id,
            reason=request.reason,
            reviewed_by=_manual_actor(current_user),
        )
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Relation synonym revoke conflicts with dictionary constraints",
        ) from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return DictionaryRelationSynonymResponse.from_model(relation_synonym)
