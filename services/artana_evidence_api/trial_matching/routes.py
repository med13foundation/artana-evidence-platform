"""FastAPI route handlers for request-time trial matching."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.dependencies import get_clinicaltrials_source_gateway
from artana_evidence_api.source_enrichment_bridges import ClinicalTrialsGatewayProtocol
from fastapi import Depends, HTTPException, Query, status

from .contracts import TrialMatchingQuery, TrialMatchingResponse
from .matching import (
    TrialMatchingGatewayUnavailableError,
    match_clinical_trials,
    parse_list_parameter,
    parse_status_parameter,
)

_CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY = Depends(
    get_clinicaltrials_source_gateway,
)


async def match_trials(
    space_id: UUID,
    condition: str = Query(..., min_length=1, max_length=256),
    age: int | None = Query(default=None, ge=0, le=130),
    country: str | None = Query(default=None, min_length=1, max_length=64),
    within_miles: int | None = Query(default=None, ge=1, le=500),
    reference_city: str | None = Query(default=None, min_length=1, max_length=128),
    status_filter: str | None = Query(
        default="RECRUITING|NOT_YET_RECRUITING",
        alias="status",
    ),
    molecular_markers: str | None = Query(default=None, max_length=512),
    prior_treatments: str | None = Query(default=None, max_length=512),
    max_results: int = Query(default=20, ge=1, le=100),
    reference_latitude: float | None = Query(default=None, ge=-90, le=90),
    reference_longitude: float | None = Query(default=None, ge=-180, le=180),
    *,
    clinicaltrials_gateway: ClinicalTrialsGatewayProtocol | None = (
        _CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY
    ),
) -> TrialMatchingResponse:
    """Return request-time live ClinicalTrials.gov matches for patient context."""

    if clinicaltrials_gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ClinicalTrials.gov gateway is not available.",
        )
    query = TrialMatchingQuery(
        condition=condition,
        age=age,
        country=country,
        within_miles=within_miles,
        reference_city=reference_city,
        reference_latitude=reference_latitude,
        reference_longitude=reference_longitude,
        statuses=parse_status_parameter(status_filter),
        molecular_markers=parse_list_parameter(molecular_markers),
        prior_treatments=parse_list_parameter(prior_treatments),
        max_results=max_results,
    )
    try:
        return await match_clinical_trials(
            space_id=space_id,
            query=query,
            gateway=clinicaltrials_gateway,
        )
    except TrialMatchingGatewayUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


__all__ = ["match_trials"]
