"""Entity routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_db.auth import get_current_active_user
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_kernel_entity_embedding_status_service,
    get_kernel_entity_service,
    get_space_access_port,
    require_space_role,
    verify_space_membership,
)
from artana_evidence_db.kernel_entity_errors import (
    KernelEntityConflictError,
    KernelEntityValidationError,
)
from artana_evidence_db.kernel_services import (
    KernelEntityEmbeddingStatusService,
    KernelEntityService,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.service_contracts import (
    KernelEntityBatchCreateRequest,
    KernelEntityBatchCreateResponse,
    KernelEntityCreateRequest,
    KernelEntityEmbeddingRefreshRequest,
    KernelEntityEmbeddingRefreshResponse,
    KernelEntityEmbeddingStatusListResponse,
    KernelEntityEmbeddingStatusResponse,
    KernelEntityListResponse,
    KernelEntityResponse,
    KernelEntityUpdateRequest,
    KernelEntityUpsertResponse,
)
from artana_evidence_db.space_membership import MembershipRole
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/spaces", tags=["entities"])


def _parse_entity_ids_param(
    entity_ids: list[str] | None,
) -> tuple[list[str], list[str]]:
    if entity_ids is None:
        return [], []

    normalized: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []
    invalid_seen: set[str] = set()
    for raw in entity_ids:
        for token in raw.split(","):
            trimmed = token.strip()
            if not trimmed:
                continue
            try:
                normalized_id = str(UUID(trimmed))
            except ValueError:
                if trimmed not in invalid_seen:
                    invalid_seen.add(trimmed)
                    invalid.append(trimmed)
                continue
            if normalized_id in seen:
                continue
            seen.add(normalized_id)
            normalized.append(normalized_id)

    return normalized, invalid


@router.get(
    "/{space_id}/entities",
    response_model=KernelEntityListResponse,
    summary="List entities in one graph space",
)
def list_entities(
    space_id: UUID,
    *,
    entity_type: str | None = Query(default=None, alias="type"),
    q: str | None = Query(default=None),
    ids: list[str] | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityListResponse:
    """List entities in one graph space."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    entity_ids, invalid_entity_ids = _parse_entity_ids_param(ids)
    if invalid_entity_ids:
        invalid_preview = ", ".join(invalid_entity_ids[:3])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity id(s): {invalid_preview}",
        )

    if ids is not None:
        paged_ids = entity_ids[offset : offset + limit]
        entities = []
        for entity_id in paged_ids:
            entity = entity_service.get_entity(entity_id)
            if entity is None or str(entity.research_space_id) != str(space_id):
                continue
            entities.append(entity)
    elif q:
        batch = entity_service.search(
            str(space_id),
            q,
            entity_type=entity_type,
            limit=offset + limit,
        )
        entities = batch[offset : offset + limit]
    else:
        if entity_type is None or not entity_type.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Provide either 'type' or 'q' when listing entities.",
            )
        entities = entity_service.list_by_type(
            str(space_id),
            entity_type,
            limit=limit,
            offset=offset,
        )

    return KernelEntityListResponse(
        entities=[KernelEntityResponse.from_model(entity) for entity in entities],
        total=len(entities),
        offset=offset,
        limit=limit,
    )


@router.post(
    "/{space_id}/entities",
    response_model=KernelEntityUpsertResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or resolve one entity",
)
def create_entity(
    space_id: UUID,
    request: KernelEntityCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityUpsertResponse:
    """Create or resolve one graph entity."""
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )

    try:
        entity, created = entity_service.create_or_resolve(
            research_space_id=str(space_id),
            entity_type=request.entity_type,
            identifiers=request.identifiers or None,
            display_label=request.display_label,
            aliases=request.aliases,
            metadata=request.metadata,
        )
        session.commit()
    except KernelEntityConflictError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except KernelEntityValidationError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entity identifiers already exist for another entity.",
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
            detail=f"Failed to create entity: {exc!s}",
        ) from exc

    return KernelEntityUpsertResponse(
        entity=KernelEntityResponse.from_model(entity),
        created=created,
    )


@router.post(
    "/{space_id}/entities/batch",
    response_model=KernelEntityBatchCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create or resolve a batch of entities",
)
def create_entities_batch(
    space_id: UUID,
    request: KernelEntityBatchCreateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityBatchCreateResponse:
    """Create or resolve up to 500 entities in a single transaction.

    Designed for ontology loaders (MONDO has ~26k terms; HPO/UBERON/GO/CL
    each have several thousand) where the per-entity HTTP + commit
    overhead of the single-entity endpoint dominates load times.
    Processing is sequential within the batch so identifier and exact-match
    resolution semantics stay aligned with the single-entity path. Newly
    created rows skip conflicting aliases instead of aborting the whole
    chunk; validation failures still roll the batch back atomically.
    """
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )

    try:
        entity_inputs: list[dict[str, object]] = [
            {
                "entity_type": item.entity_type,
                "identifiers": item.identifiers or None,
                "display_label": item.display_label,
                "aliases": item.aliases,
                "metadata": item.metadata,
            }
            for item in request.entities
        ]
        results = entity_service.create_or_resolve_many(
            research_space_id=str(space_id),
            entity_inputs=entity_inputs,
        )
        session.commit()
    except KernelEntityConflictError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except KernelEntityValidationError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Entity identifiers already exist for another entity.",
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
            detail=f"Failed to create entity batch: {exc!s}",
        ) from exc

    upsert_responses = [
        KernelEntityUpsertResponse(
            entity=KernelEntityResponse.from_model(entity),
            created=created,
        )
        for entity, created in results
    ]
    created_count = sum(1 for _, created in results if created)
    return KernelEntityBatchCreateResponse(
        results=upsert_responses,
        created_count=created_count,
        resolved_count=len(results) - created_count,
    )


@router.get(
    "/{space_id}/entities/{entity_id}",
    response_model=KernelEntityResponse,
    summary="Get one entity",
)
def get_entity(
    space_id: UUID,
    entity_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityResponse:
    """Get one entity in one graph space."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    entity = entity_service.get_entity(str(entity_id))
    if entity is None or str(entity.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    return KernelEntityResponse.from_model(entity)


@router.get(
    "/{space_id}/entities/embeddings/status",
    response_model=KernelEntityEmbeddingStatusListResponse,
    summary="List graph-owned embedding readiness for entities in one graph space",
)
def list_entity_embedding_status(
    space_id: UUID,
    *,
    entity_ids: list[str] | None = Query(default=None, alias="entity_ids"),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    embedding_status_service: KernelEntityEmbeddingStatusService = Depends(
        get_kernel_entity_embedding_status_service,
    ),
    session: Session = Depends(get_session),
) -> KernelEntityEmbeddingStatusListResponse:
    """Return graph-owned embedding readiness records for one graph space."""
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )

    normalized_entity_ids, invalid_entity_ids = _parse_entity_ids_param(entity_ids)
    if invalid_entity_ids:
        invalid_preview = ", ".join(invalid_entity_ids[:3])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid entity id(s): {invalid_preview}",
        )

    statuses = embedding_status_service.list_statuses(
        research_space_id=str(space_id),
        entity_ids=normalized_entity_ids or None,
        limit=max(1, len(normalized_entity_ids)) if normalized_entity_ids else None,
    )
    return KernelEntityEmbeddingStatusListResponse(
        statuses=[
            KernelEntityEmbeddingStatusResponse.model_validate(
                status_row.model_dump(mode="python"),
            )
            for status_row in statuses
        ],
        total=len(statuses),
    )


@router.post(
    "/{space_id}/entities/embeddings/refresh",
    response_model=KernelEntityEmbeddingRefreshResponse,
    summary="Refresh graph-owned entity embedding projections",
)
def refresh_entity_embeddings(
    space_id: UUID,
    request: KernelEntityEmbeddingRefreshRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    embedding_status_service: KernelEntityEmbeddingStatusService = Depends(
        get_kernel_entity_embedding_status_service,
    ),
    session: Session = Depends(get_session),
) -> KernelEntityEmbeddingRefreshResponse:
    """Refresh graph-owned entity embedding projections for one graph space."""
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )

    try:
        summary = embedding_status_service.refresh_embeddings(
            research_space_id=str(space_id),
            entity_ids=(
                [str(entity_id) for entity_id in request.entity_ids]
                if request.entity_ids is not None
                else None
            ),
            limit=request.limit,
            model_name=request.model_name,
            embedding_version=request.embedding_version,
        )
        session.commit()
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
            detail=f"Failed to refresh entity embeddings: {exc!s}",
        ) from exc

    return KernelEntityEmbeddingRefreshResponse.model_validate(
        summary.model_dump(mode="python"),
    )


@router.put(
    "/{space_id}/entities/{entity_id}",
    response_model=KernelEntityResponse,
    summary="Update one entity",
)
def update_entity(
    space_id: UUID,
    entity_id: UUID,
    request: KernelEntityUpdateRequest,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> KernelEntityResponse:
    """Update one entity in one graph space."""
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )

    entity = entity_service.get_entity(str(entity_id))
    if entity is None or str(entity.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    try:
        updated_entity = entity
        if (
            request.display_label is not None
            or request.aliases is not None
            or request.metadata is not None
        ):
            maybe_updated = entity_service.update_entity(
                str(entity_id),
                display_label=request.display_label,
                aliases=request.aliases,
                metadata=request.metadata,
            )
            if maybe_updated is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Entity not found",
                )
            updated_entity = maybe_updated

        if request.identifiers:
            for namespace, value in request.identifiers.items():
                entity_service.add_identifier(
                    entity_id=str(entity_id),
                    namespace=namespace,
                    identifier_value=value,
                )
            refreshed_entity = entity_service.get_entity(str(entity_id))
            if refreshed_entity is not None:
                updated_entity = refreshed_entity

        session.commit()
        return KernelEntityResponse.from_model(updated_entity)
    except HTTPException:
        session.rollback()
        raise
    except KernelEntityConflictError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except KernelEntityValidationError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Identifier already exists",
        ) from exc
    except Exception as exc:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update entity: {exc!s}",
        ) from exc


@router.delete(
    "/{space_id}/entities/{entity_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one entity",
)
def delete_entity(
    space_id: UUID,
    entity_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    entity_service: KernelEntityService = Depends(get_kernel_entity_service),
    session: Session = Depends(get_session),
) -> None:
    """Delete one entity in one graph space."""
    require_space_role(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
        required_role=MembershipRole.RESEARCHER,
    )

    entity = entity_service.get_entity(str(entity_id))
    if entity is None or str(entity.research_space_id) != str(space_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )

    if not entity_service.delete_entity(str(entity_id)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Entity not found",
        )
    session.commit()


__all__ = [
    "router",
    "create_entity",
    "delete_entity",
    "get_entity",
    "list_entities",
    "update_entity",
]
