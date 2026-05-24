"""Runtime logic for scoped document deletion."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.artifact_store import HarnessArtifactStore
from artana_evidence_api.auth import HarnessUser
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
)
from artana_evidence_api.proposal_store import HarnessProposalStore
from artana_evidence_api.review_item_store import HarnessReviewItemStore
from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
from artana_evidence_api.study_outcomes import HarnessStudyOutcomeStore
from artana_evidence_api.types.common import JSONObject

from .contracts import HarnessDocumentDeleteResult, HarnessDocumentDeleteScope


class DocumentDeletionScopeError(ValueError):
    """Raised when a bulk delete request is not safely scoped."""


class DocumentDeletionNotFoundError(ValueError):
    """Raised when a requested single document does not exist."""


def delete_documents_for_scope(  # noqa: PLR0913
    *,
    space_id: UUID,
    scope: HarnessDocumentDeleteScope,
    current_user: HarnessUser,
    document_store: HarnessDocumentStore,
    proposal_store: HarnessProposalStore,
    review_item_store: HarnessReviewItemStore,
    study_outcome_store: HarnessStudyOutcomeStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessDocumentDeleteResult:
    """Delete documents and their document-linked children for one safe scope."""

    target_documents = _resolve_target_documents(
        space_id=space_id,
        scope=scope,
        document_store=document_store,
    )
    run = _create_audit_run(
        space_id=space_id,
        scope=scope,
        current_user=current_user,
        target_documents=target_documents,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    document_ids = tuple(document.id for document in target_documents)
    deleted_proposal_count = proposal_store.delete_proposals_for_documents(
        space_id=space_id,
        document_ids=document_ids,
    )
    deleted_review_item_count = review_item_store.delete_review_items_for_documents(
        space_id=space_id,
        document_ids=document_ids,
    )
    deleted_study_outcome_count = study_outcome_store.delete_outcomes_for_documents(
        space_id=space_id,
        document_ids=document_ids,
    )
    deleted_documents = document_store.delete_documents(
        space_id=space_id,
        document_ids=document_ids,
    )
    completed_run = _complete_audit_run(
        space_id=space_id,
        run=run,
        scope=scope,
        current_user=current_user,
        deleted_documents=deleted_documents,
        deleted_proposal_count=deleted_proposal_count,
        deleted_review_item_count=deleted_review_item_count,
        deleted_study_outcome_count=deleted_study_outcome_count,
        run_registry=run_registry,
        artifact_store=artifact_store,
    )
    return HarnessDocumentDeleteResult(
        run=completed_run,
        scope=scope,
        deleted_documents=deleted_documents,
        deleted_document_count=len(deleted_documents),
        deleted_proposal_count=deleted_proposal_count,
        deleted_review_item_count=deleted_review_item_count,
        deleted_study_outcome_count=deleted_study_outcome_count,
    )


def _resolve_target_documents(
    *,
    space_id: UUID,
    scope: HarnessDocumentDeleteScope,
    document_store: HarnessDocumentStore,
) -> list[HarnessDocumentRecord]:
    if scope.document_id is not None:
        document = document_store.get_document(
            space_id=space_id,
            document_id=scope.document_id,
        )
        if document is None:
            msg = f"Document '{scope.document_id}' not found in space '{space_id}'"
            raise DocumentDeletionNotFoundError(msg)
        return [document]
    _require_bulk_scope(scope)
    return [
        document
        for document in document_store.list_documents(space_id=space_id)
        if _matches_scope(document=document, scope=scope)
    ]


def _require_bulk_scope(scope: HarnessDocumentDeleteScope) -> None:
    if any(
        value is not None
        for value in (scope.source, scope.title_prefix, scope.ingestion_run_id)
    ):
        return
    msg = "At least one delete scope is required: source, title_prefix, or ingestion_run_id."
    raise DocumentDeletionScopeError(msg)


def _matches_scope(
    *,
    document: HarnessDocumentRecord,
    scope: HarnessDocumentDeleteScope,
) -> bool:
    if (
        scope.source is not None
        and document.source_type.casefold() != scope.source.casefold()
    ):
        return False
    if scope.title_prefix is not None and not document.title.casefold().startswith(
        scope.title_prefix.casefold(),
    ):
        return False
    return (
        scope.ingestion_run_id is None
        or document.ingestion_run_id == scope.ingestion_run_id
    )


def _create_audit_run(
    *,
    space_id: UUID,
    scope: HarnessDocumentDeleteScope,
    current_user: HarnessUser,
    target_documents: list[HarnessDocumentRecord],
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="document-deletion",
        title="Document Deletion",
        input_payload={
            "actor_id": str(current_user.id),
            "scope": scope.model_dump(mode="json"),
            "target_document_count": len(target_documents),
        },
        graph_service_status="not_checked",
        graph_service_version="not_checked",
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "running", "scope": scope.model_dump(mode="json")},
    )
    return run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="running",
    ) or run


def _complete_audit_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    scope: HarnessDocumentDeleteScope,
    current_user: HarnessUser,
    deleted_documents: list[HarnessDocumentRecord],
    deleted_proposal_count: int,
    deleted_review_item_count: int,
    deleted_study_outcome_count: int,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    audit_content: JSONObject = {
        "actor_id": str(current_user.id),
        "scope": scope.model_dump(mode="json"),
        "deleted_document_count": len(deleted_documents),
        "deleted_proposal_count": deleted_proposal_count,
        "deleted_review_item_count": deleted_review_item_count,
        "deleted_study_outcome_count": deleted_study_outcome_count,
        "deleted_documents": [
            {
                "id": str(document.id),
                "title": document.title,
                "source_type": document.source_type,
                "ingestion_run_id": document.ingestion_run_id,
            }
            for document in deleted_documents
        ],
    }
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="document_deletion_audit",
        media_type="application/json",
        content=audit_content,
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "completed", **audit_content},
    )
    return run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    ) or run


__all__ = [
    "DocumentDeletionNotFoundError",
    "DocumentDeletionScopeError",
    "delete_documents_for_scope",
]
