"""Document deletion endpoints for the standalone harness service."""

from __future__ import annotations

from uuid import UUID  # noqa: TC003

from artana_evidence_api.artifact_store import HarnessArtifactStore  # noqa: TC001
from artana_evidence_api.auth import (
    HarnessUser,  # noqa: TC001
    get_current_harness_user,
)
from artana_evidence_api.dependencies import (
    get_artifact_store,
    get_document_store,
    get_proposal_store,
    get_review_item_store,
    get_run_registry,
    get_study_outcome_store,
    require_harness_space_write_access,
)
from artana_evidence_api.document_deletion import (
    DocumentDeletionNotFoundError,
    DocumentDeletionScopeError,
    HarnessDocumentDeleteScope,
    delete_documents_for_scope,
)
from artana_evidence_api.document_store import HarnessDocumentStore  # noqa: TC001
from artana_evidence_api.proposal_store import HarnessProposalStore  # noqa: TC001
from artana_evidence_api.review_item_store import HarnessReviewItemStore  # noqa: TC001
from artana_evidence_api.routers.document_models import HarnessDocumentDeleteResponse
from artana_evidence_api.run_registry import HarnessRunRegistry  # noqa: TC001
from artana_evidence_api.study_outcomes import HarnessStudyOutcomeStore  # noqa: TC001
from fastapi import APIRouter, Depends, HTTPException, Query, status

router = APIRouter(
    prefix="/v1/spaces",
    tags=["documents"],
)

_RUN_REGISTRY_DEPENDENCY = Depends(get_run_registry)
_ARTIFACT_STORE_DEPENDENCY = Depends(get_artifact_store)
_DOCUMENT_STORE_DEPENDENCY = Depends(get_document_store)
_PROPOSAL_STORE_DEPENDENCY = Depends(get_proposal_store)
_REVIEW_ITEM_STORE_DEPENDENCY = Depends(get_review_item_store)
_STUDY_OUTCOME_STORE_DEPENDENCY = Depends(get_study_outcome_store)
_CURRENT_USER_DEPENDENCY = Depends(get_current_harness_user)


def _optional_scope_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@router.delete(
    "/{space_id}/documents/{document_id}",
    response_model=HarnessDocumentDeleteResponse,
    summary="Delete one tracked document",
    dependencies=[Depends(require_harness_space_write_access)],
)
def delete_document(
    space_id: UUID,
    document_id: UUID,
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    study_outcome_store: HarnessStudyOutcomeStore = _STUDY_OUTCOME_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessDocumentDeleteResponse:
    try:
        return HarnessDocumentDeleteResponse.from_result(
            delete_documents_for_scope(
                space_id=space_id,
                scope=HarnessDocumentDeleteScope(document_id=str(document_id)),
                current_user=current_user,
                document_store=document_store,
                proposal_store=proposal_store,
                review_item_store=review_item_store,
                study_outcome_store=study_outcome_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
            ),
        )
    except DocumentDeletionNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.delete(
    "/{space_id}/documents",
    response_model=HarnessDocumentDeleteResponse,
    summary="Delete tracked documents by scope",
    dependencies=[Depends(require_harness_space_write_access)],
)
def delete_documents(
    space_id: UUID,
    source: str | None = Query(default=None),
    title_prefix: str | None = Query(default=None),
    ingestion_run_id: str | None = Query(default=None),
    *,
    current_user: HarnessUser = _CURRENT_USER_DEPENDENCY,
    document_store: HarnessDocumentStore = _DOCUMENT_STORE_DEPENDENCY,
    proposal_store: HarnessProposalStore = _PROPOSAL_STORE_DEPENDENCY,
    review_item_store: HarnessReviewItemStore = _REVIEW_ITEM_STORE_DEPENDENCY,
    study_outcome_store: HarnessStudyOutcomeStore = _STUDY_OUTCOME_STORE_DEPENDENCY,
    run_registry: HarnessRunRegistry = _RUN_REGISTRY_DEPENDENCY,
    artifact_store: HarnessArtifactStore = _ARTIFACT_STORE_DEPENDENCY,
) -> HarnessDocumentDeleteResponse:
    try:
        return HarnessDocumentDeleteResponse.from_result(
            delete_documents_for_scope(
                space_id=space_id,
                scope=HarnessDocumentDeleteScope(
                    source=_optional_scope_text(source),
                    title_prefix=_optional_scope_text(title_prefix),
                    ingestion_run_id=_optional_scope_text(ingestion_run_id),
                ),
                current_user=current_user,
                document_store=document_store,
                proposal_store=proposal_store,
                review_item_store=review_item_store,
                study_outcome_store=study_outcome_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
            ),
        )
    except DocumentDeletionScopeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
