"""Domain-pack introspection routes for the standalone graph service."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_db.auth import (
    get_current_active_user,
    to_graph_principal,
    to_graph_rls_session_context,
)
from artana_evidence_db.database import get_session, set_graph_rls_session_context
from artana_evidence_db.dependencies import get_space_registry_port
from artana_evidence_db.graph_access import evaluate_graph_admin_access
from artana_evidence_db.graph_api_schemas.domain_pack_schemas import (
    GraphDomainPackListResponse,
    GraphDomainPackSummaryResponse,
    GraphPackSeedOperationResponse,
    GraphPackSeedStatusResponse,
)
from artana_evidence_db.pack_seed_models import GraphPackSeedStatusModel
from artana_evidence_db.pack_seed_service import (
    GraphPackSeedOperationResult,
    GraphPackSeedService,
)
from artana_evidence_db.ports import SpaceRegistryPort
from artana_evidence_db.product_contract import GRAPH_API_PREFIX
from artana_evidence_db.runtime.contracts import GraphDomainPack
from artana_evidence_db.runtime.pack_registry import (
    create_graph_domain_pack,
    list_graph_domain_packs,
    resolve_graph_domain_pack,
)
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

router = APIRouter(prefix=f"{GRAPH_API_PREFIX}/domain-packs", tags=["domain-packs"])


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


def _require_space_exists(
    *,
    space_id: UUID,
    space_registry: SpaceRegistryPort,
) -> None:
    if space_registry.get_by_id(space_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Graph space not found",
        )


def _resolve_pack_or_404(pack_name: str) -> GraphDomainPack:
    try:
        return resolve_graph_domain_pack(pack_name)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


def _enum_or_text(value: object) -> str:
    enum_value = getattr(value, "value", None)
    return enum_value if isinstance(enum_value, str) else str(value)


def _seed_status_response(
    model: GraphPackSeedStatusModel,
) -> GraphPackSeedStatusResponse:
    return GraphPackSeedStatusResponse(
        id=model.id,
        research_space_id=model.research_space_id,
        pack_name=str(model.pack_name),
        pack_version=str(model.pack_version),
        status=_enum_or_text(model.status),
        last_operation=_enum_or_text(model.last_operation),
        seed_count=int(model.seed_count),
        repair_count=int(model.repair_count),
        metadata=dict(model.metadata_payload),
        seeded_at=model.seeded_at,
        repaired_at=model.repaired_at,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _operation_response(
    result: GraphPackSeedOperationResult,
) -> GraphPackSeedOperationResponse:
    return GraphPackSeedOperationResponse(
        applied=result.applied,
        operation=result.operation,
        status=_seed_status_response(result.status),
    )


def _pack_summary(pack_name: str) -> GraphDomainPackSummaryResponse:
    for pack in list_graph_domain_packs():
        if pack.name == pack_name:
            return GraphDomainPackSummaryResponse(
                name=pack.name,
                version=pack.version,
                service_name=pack.runtime_identity.service_name,
                jwt_issuer=pack.runtime_identity.jwt_issuer,
                domain_contexts=[
                    context.id
                    for context in pack.dictionary_loading_extension.builtin_domain_contexts
                ],
                entity_types=[
                    entity.entity_type
                    for entity in pack.dictionary_loading_extension.builtin_entity_types
                ],
                relation_types=[
                    relation.relation_type
                    for relation in pack.dictionary_loading_extension.builtin_relation_types
                ],
                agent_capabilities={
                    "entity_recognition": list(
                        pack.agent_capabilities.entity_recognition.supported_source_types,
                    ),
                    "extraction": list(
                        pack.agent_capabilities.extraction.supported_source_types,
                    ),
                    "graph_connection": list(
                        pack.agent_capabilities.graph_connection.supported_source_types,
                    ),
                    "graph_search": list(
                        pack.agent_capabilities.graph_search.supported_source_types,
                    ),
                },
            )
    msg = f"Registered graph domain pack '{pack_name}' was not found"
    raise RuntimeError(msg)


@router.get("", response_model=GraphDomainPackListResponse)
def list_domain_packs() -> GraphDomainPackListResponse:
    """List registered graph domain packs and the active pack."""
    active_pack = create_graph_domain_pack()
    return GraphDomainPackListResponse(
        active_pack=active_pack.name,
        packs=[_pack_summary(pack.name) for pack in list_graph_domain_packs()],
    )


@router.get("/active", response_model=GraphDomainPackSummaryResponse)
def get_active_domain_pack() -> GraphDomainPackSummaryResponse:
    """Return the active graph domain pack."""
    active_pack = create_graph_domain_pack()
    return _pack_summary(active_pack.name)


@router.get("/{pack_name}", response_model=GraphDomainPackSummaryResponse)
def get_domain_pack(pack_name: str) -> GraphDomainPackSummaryResponse:
    """Return one registered graph domain pack by name."""
    pack = _resolve_pack_or_404(pack_name)
    return _pack_summary(pack.name)


@router.get(
    "/{pack_name}/spaces/{space_id}/seed-status",
    response_model=GraphPackSeedStatusResponse,
)
def get_pack_seed_status(
    pack_name: str,
    space_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    session: Session = Depends(get_session),
) -> GraphPackSeedStatusResponse:
    """Return versioned seed status for one graph space and pack."""
    _require_graph_admin(current_user=current_user, session=session)
    _require_space_exists(space_id=space_id, space_registry=space_registry)
    pack = _resolve_pack_or_404(pack_name)
    seed_service = GraphPackSeedService(session)
    seed_status = seed_service.get_status(research_space_id=space_id, pack=pack)
    if seed_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Pack has not been seeded into this graph space",
        )
    return _seed_status_response(seed_status)


@router.post(
    "/{pack_name}/spaces/{space_id}/seed",
    response_model=GraphPackSeedOperationResponse,
)
def seed_pack_for_space(
    pack_name: str,
    space_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    session: Session = Depends(get_session),
) -> GraphPackSeedOperationResponse:
    """Explicitly seed one graph space with a registered domain pack."""
    _require_graph_admin(current_user=current_user, session=session)
    _require_space_exists(space_id=space_id, space_registry=space_registry)
    pack = _resolve_pack_or_404(pack_name)
    result = GraphPackSeedService(session).seed_space(
        research_space_id=space_id,
        pack=pack,
    )
    session.commit()
    return _operation_response(result)


@router.post(
    "/{pack_name}/spaces/{space_id}/repair",
    response_model=GraphPackSeedOperationResponse,
)
def repair_pack_for_space(
    pack_name: str,
    space_id: UUID,
    *,
    current_user: User = Depends(get_current_active_user),
    space_registry: SpaceRegistryPort = Depends(get_space_registry_port),
    session: Session = Depends(get_session),
) -> GraphPackSeedOperationResponse:
    """Re-run one pack seed idempotently to repair missing pack-owned rows."""
    _require_graph_admin(current_user=current_user, session=session)
    _require_space_exists(space_id=space_id, space_registry=space_registry)
    pack = _resolve_pack_or_404(pack_name)
    result = GraphPackSeedService(session).repair_space(
        research_space_id=space_id,
        pack=pack,
    )
    session.commit()
    return _operation_response(result)


__all__ = [
    "GraphDomainPackListResponse",
    "GraphDomainPackSummaryResponse",
    "GraphPackSeedOperationResponse",
    "GraphPackSeedStatusResponse",
    "get_active_domain_pack",
    "get_domain_pack",
    "get_pack_seed_status",
    "list_domain_packs",
    "repair_pack_for_space",
    "router",
    "seed_pack_for_space",
]
