"""FastAPI route handlers for ontology-normalized convergence queries."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.dependencies import get_proposal_store
from artana_evidence_api.proposal_store import HarnessProposalStore
from fastapi import Depends

from .contracts import (
    OntologyConvergenceQueryRequest,
    OntologyConvergenceQueryResponse,
)
from .runtime import run_ontology_convergence_query

_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)


async def create_convergence_query(
    space_id: UUID,
    request: OntologyConvergenceQueryRequest,
    *,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
) -> OntologyConvergenceQueryResponse:
    """Run a native convergence query over promoted claim proposals."""

    return run_ontology_convergence_query(
        space_id=space_id,
        request=request,
        proposal_store=proposal_store,
    )


__all__ = ["create_convergence_query"]
