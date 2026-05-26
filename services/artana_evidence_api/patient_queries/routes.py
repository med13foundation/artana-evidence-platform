"""FastAPI route handlers for patient-context query runs."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.dependencies import (
    get_clinicaltrials_source_gateway,
    get_proposal_store,
    get_study_outcome_store,
)
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.source_enrichment_bridges import ClinicalTrialsGatewayProtocol
from artana_evidence_api.study_outcomes import HarnessStudyOutcomeStore
from artana_evidence_api.trial_matching import TrialMatchingGatewayUnavailableError
from fastapi import Depends, HTTPException, status

from .contracts import PatientQueryRunRequest, PatientQueryRunResponse
from .runtime import create_patient_query_run_async

_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_STUDY_OUTCOME_STORE_DEPENDENCY = Depends(get_study_outcome_store)
_CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY = Depends(
    get_clinicaltrials_source_gateway,
)


async def create_query_run(
    space_id: UUID,
    request: PatientQueryRunRequest,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    study_outcome_store: HarnessStudyOutcomeStore = _STUDY_OUTCOME_STORE_DEPENDENCY,
    clinicaltrials_gateway: ClinicalTrialsGatewayProtocol | None = (
        _CLINICALTRIALS_SOURCE_GATEWAY_DEPENDENCY
    ),
) -> PatientQueryRunResponse:
    """Run a patient-context query over reviewed evidence and live trials."""

    if clinicaltrials_gateway is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ClinicalTrials.gov gateway is not available.",
        )
    try:
        return await create_patient_query_run_async(
            space_id=space_id,
            request=request,
            proposal_store=proposal_store,
            study_outcome_store=study_outcome_store,
            clinicaltrials_gateway=clinicaltrials_gateway,
        )
    except TrialMatchingGatewayUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


__all__ = ["create_query_run"]
