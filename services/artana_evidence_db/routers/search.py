"""Unified search routes for the standalone graph service."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from uuid import UUID

from artana_evidence_db.auth import get_current_active_user
from artana_evidence_db.composition import build_entity_repository
from artana_evidence_db.database import get_session
from artana_evidence_db.dependencies import (
    get_space_access_port,
    verify_space_membership,
)
from artana_evidence_db.kernel_runtime_factories import build_relation_repository
from artana_evidence_db.observation_repository import (
    SqlAlchemyKernelObservationRepository,
)
from artana_evidence_db.ports import SpaceAccessPort
from artana_evidence_db.search_service import (
    SearchEntity,
    SearchResultType,
    UnifiedSearchService,
)
from artana_evidence_db.user_models import User
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

router = APIRouter(prefix="/v1/search", tags=["search"])


class SearchResultItem(BaseModel):
    """Typed representation of a unified graph-search result."""

    entity_type: SearchResultType
    entity_id: str
    title: str
    description: str
    relevance_score: float = Field(ge=0.0)
    metadata: dict[str, object]


class UnifiedSearchResponse(BaseModel):
    """Unified graph-search response payload."""

    query: str
    total_results: int
    entity_breakdown: dict[str, int]
    results: list[SearchResultItem]


class SearchSuggestionResponse(BaseModel):
    """Search suggestion payload."""

    query: str
    suggestions: list[str]
    total_suggestions: int


class SearchStatisticsResponse(BaseModel):
    """Search statistics payload."""

    total_entities: dict[str, int]
    searchable_fields: dict[str, list[str]]
    last_updated: str | None = None


def get_search_service(
    db: Session = Depends(get_session),
) -> UnifiedSearchService:
    """Resolve the graph-owned unified search service."""
    return UnifiedSearchService(
        entity_repo=build_entity_repository(db),
        observation_repo=SqlAlchemyKernelObservationRepository(db),
        relation_repo=build_relation_repository(db),
    )


@router.post(
    "",
    summary="Unified search across graph entities, observations, and relations",
    response_model=UnifiedSearchResponse,
)
def unified_search(
    space_id: UUID = Query(..., description="Graph space scope"),
    query: str = Query(..., min_length=1, max_length=200, description="Search query"),
    *,
    entity_types: list[SearchEntity] | None = Query(
        None,
        description="Entity scopes to search (defaults to all)",
    ),
    limit: int = Query(20, ge=1, le=100, description="Maximum results per scope"),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    session: Session = Depends(get_session),
    service: UnifiedSearchService = Depends(get_search_service),
) -> UnifiedSearchResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    raw = service.search(
        research_space_id=str(space_id),
        query=query,
        entity_types=entity_types,
        limit=limit,
    )

    payload = raw if isinstance(raw, Mapping) else {}
    result_items = _build_search_results(payload.get("results"))
    query_value = payload.get("query")
    total_results_value = payload.get("total_results")
    breakdown_value = payload.get("entity_breakdown")

    return UnifiedSearchResponse(
        query=query_value if isinstance(query_value, str) else query,
        total_results=(
            int(total_results_value)
            if isinstance(total_results_value, int | float)
            else len(result_items)
        ),
        entity_breakdown=(
            _ensure_breakdown(breakdown_value)
            if isinstance(breakdown_value, Mapping)
            else {}
        ),
        results=result_items,
    )


@router.get(
    "/suggest",
    summary="Graph search suggestions",
    response_model=SearchSuggestionResponse,
)
def search_suggestions(
    query: str = Query(
        ...,
        min_length=1,
        max_length=50,
        description="Partial search query",
    ),
    limit: int = Query(10, ge=1, le=20, description="Maximum suggestions"),
) -> SearchSuggestionResponse:
    suggestions = [
        f"{query} entities",
        f"{query} observations",
        f"{query} relations",
    ][:limit]
    return SearchSuggestionResponse(
        query=query,
        suggestions=suggestions,
        total_suggestions=len(suggestions),
    )


@router.get(
    "/stats",
    summary="Graph search statistics",
    response_model=SearchStatisticsResponse,
)
def search_statistics(
    space_id: UUID = Query(..., description="Graph space scope"),
    current_user: User = Depends(get_current_active_user),
    space_access: SpaceAccessPort = Depends(get_space_access_port),
    session: Session = Depends(get_session),
    service: UnifiedSearchService = Depends(get_search_service),
) -> SearchStatisticsResponse:
    verify_space_membership(
        space_id=space_id,
        current_user=current_user,
        space_access=space_access,
        session=session,
    )
    stats = service.get_statistics(str(space_id))
    return _build_statistics_response(stats)


def _build_search_results(raw_results: object) -> list[SearchResultItem]:
    if not isinstance(raw_results, Sequence):
        return []

    items: list[SearchResultItem] = []
    for entry in raw_results:
        if not isinstance(entry, Mapping):
            continue

        entity_type_value = entry.get("entity_type")
        try:
            entity_type = SearchResultType(str(entity_type_value))
        except ValueError:
            continue

        title_value = entry.get("title")
        description_value = entry.get("description")
        if not isinstance(title_value, str) or not isinstance(description_value, str):
            continue

        relevance_value = entry.get("relevance_score")
        if isinstance(relevance_value, int | float | str):
            try:
                relevance_score = float(relevance_value)
            except (TypeError, ValueError):
                relevance_score = 0.0
        else:
            relevance_score = 0.0

        metadata_value = entry.get("metadata")
        items.append(
            SearchResultItem(
                entity_type=entity_type,
                entity_id=str(entry.get("entity_id")),
                title=title_value,
                description=description_value,
                relevance_score=relevance_score,
                metadata=metadata_value if isinstance(metadata_value, dict) else {},
            ),
        )

    return items


def _ensure_breakdown(raw_breakdown: Mapping[str, object]) -> dict[str, int]:
    breakdown: dict[str, int] = {}
    for key, value in raw_breakdown.items():
        if isinstance(key, str) and isinstance(value, int | float):
            breakdown[key] = int(value)
    return breakdown


def _build_statistics_response(
    stats: Mapping[str, object],
) -> SearchStatisticsResponse:
    total_entities_raw = stats.get("total_entities")
    searchable_fields_raw = stats.get("searchable_fields")
    last_updated = stats.get("last_updated")

    total_entities = (
        {
            key: int(value)
            for key, value in total_entities_raw.items()
            if isinstance(key, str) and isinstance(value, int | float)
        }
        if isinstance(total_entities_raw, Mapping)
        else {}
    )
    searchable_fields = (
        {
            key: [str(item) for item in value if isinstance(item, str)]
            for key, value in searchable_fields_raw.items()
            if isinstance(key, str) and isinstance(value, Sequence)
        }
        if isinstance(searchable_fields_raw, Mapping)
        else {}
    )

    return SearchStatisticsResponse(
        total_entities=total_entities,
        searchable_fields=searchable_fields,
        last_updated=last_updated if isinstance(last_updated, str) else None,
    )


__all__ = [
    "SearchResultItem",
    "SearchStatisticsResponse",
    "SearchSuggestionResponse",
    "UnifiedSearchResponse",
    "get_search_service",
    "router",
    "search_statistics",
    "search_suggestions",
    "unified_search",
]
