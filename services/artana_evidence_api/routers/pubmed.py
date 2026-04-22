"""PubMed search endpoints for the standalone harness service."""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from artana_evidence_api.auth import (
    HarnessUser,  # noqa: TC001
    get_current_harness_user,
)
from artana_evidence_api.dependencies import (
    get_pubmed_discovery_service,
    require_harness_space_read_access,
    require_harness_space_write_access,
)
from artana_evidence_api.pubmed_discovery import (
    AdvancedQueryParameters,
    DiscoverySearchJob,
    PubMedDiscoveryService,  # noqa: TC001
    PubMedSearchRateLimitError,
    RunPubmedSearchRequest,
)
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict

router = APIRouter(
    prefix="/v1/spaces",
    tags=["pubmed"],
)

_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)
_PUBMED_DISCOVERY_SERVICE_DEPENDENCY = Depends(get_pubmed_discovery_service)


class PubMedSearchRequest(BaseModel):
    """Request payload for one explicit PubMed search."""

    model_config = ConfigDict(strict=True)

    parameters: AdvancedQueryParameters


def _require_owned_job(
    *,
    space_id: UUID,
    job_id: UUID,
    current_user: HarnessUser,
    pubmed_discovery_service: PubMedDiscoveryService,
) -> DiscoverySearchJob:
    try:
        job = pubmed_discovery_service.get_search_job(
            owner_id=current_user.id,
            job_id=job_id,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PubMed discovery unavailable: {exc}",
        ) from exc
    if job is None or job.session_id != space_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PubMed search job '{job_id}' not found in space '{space_id}'",
        )
    return job


@router.post(
    "/{space_id}/pubmed/searches",
    response_model=DiscoverySearchJob,
    status_code=status.HTTP_201_CREATED,
    summary="Run one PubMed search for a research space",
    dependencies=[Depends(require_harness_space_write_access)],
)
async def create_pubmed_search(
    space_id: UUID,
    request: PubMedSearchRequest,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    pubmed_discovery_service: PubMedDiscoveryService = _PUBMED_DISCOVERY_SERVICE_DEPENDENCY,
) -> DiscoverySearchJob:
    try:
        return await pubmed_discovery_service.run_pubmed_search(
            owner_id=current_user.id,
            request=RunPubmedSearchRequest(
                session_id=space_id,
                parameters=request.parameters,
            ),
        )
    except PubMedSearchRateLimitError as exc:
        headers: dict[str, str] = {}
        if exc.retry_after_seconds is not None:
            headers["Retry-After"] = str(exc.retry_after_seconds)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers=headers or None,
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"PubMed discovery unavailable: {exc}",
        ) from exc


@router.get(
    "/{space_id}/pubmed/searches/{job_id}",
    response_model=DiscoverySearchJob,
    summary="Get one PubMed search job",
    dependencies=[Depends(require_harness_space_read_access)],
)
def get_pubmed_search(
    space_id: UUID,
    job_id: UUID,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    pubmed_discovery_service: PubMedDiscoveryService = _PUBMED_DISCOVERY_SERVICE_DEPENDENCY,
) -> DiscoverySearchJob:
    return _require_owned_job(
        space_id=space_id,
        job_id=job_id,
        current_user=current_user,
        pubmed_discovery_service=pubmed_discovery_service,
    )


__all__ = [
    "PubMedSearchRequest",
    "create_pubmed_search",
    "get_pubmed_search",
    "router",
]
