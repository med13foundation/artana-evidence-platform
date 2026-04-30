"""Failure payload helpers for queued worker runs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.types.common import JSONObject
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.run_registry import HarnessRunRecord


def raise_for_failed_run(
    *,
    run: HarnessRunRecord,
    artifact_store: HarnessArtifactStore,
) -> None:
    """Raise an HTTPException based on the stored worker failure details."""
    worker_error = artifact_store.get_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="worker_error",
    )
    if worker_error is not None:
        status_code = worker_error.content.get("status_code")
        detail = worker_error.content.get("detail") or worker_error.content.get("error")
        if isinstance(status_code, int) and isinstance(detail, str):
            raise HTTPException(status_code=status_code, detail=detail)
        if isinstance(detail, str):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=detail,
            )
    workspace = artifact_store.get_workspace(space_id=run.space_id, run_id=run.id)
    if workspace is not None:
        raw_error = workspace.snapshot.get("error")
        raw_status_code = workspace.snapshot.get("error_status_code")
        if isinstance(raw_error, str) and raw_error.strip() != "":
            if isinstance(raw_status_code, int):
                raise HTTPException(
                    status_code=raw_status_code,
                    detail=raw_error,
                )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=raw_error,
            )
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"Run '{run.id}' failed without a persisted error payload.",
    )


def worker_failure_payload(*, exc: Exception) -> JSONObject:
    """Return a structured persisted worker failure payload."""
    if isinstance(exc, HTTPException):
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return {
            "error": detail,
            "detail": detail,
            "status_code": exc.status_code,
            "error_type": type(exc).__name__,
        }
    if isinstance(exc, GraphServiceClientError):
        detail = exc.detail or str(exc)
        return {
            "error": detail,
            "detail": detail,
            "status_code": exc.status_code or status.HTTP_503_SERVICE_UNAVAILABLE,
            "error_type": type(exc).__name__,
        }
    status_code = _specialized_worker_failure_status_code(exc=exc)
    if status_code is not None:
        detail = str(exc)
        return {
            "error": detail,
            "detail": detail,
            "status_code": status_code,
            "error_type": type(exc).__name__,
        }
    return {
        "error": str(exc),
        "detail": str(exc),
        "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "error_type": type(exc).__name__,
    }


def _specialized_worker_failure_status_code(*, exc: Exception) -> int | None:
    """Return legacy route semantics for domain-specific worker failures."""
    from artana_evidence_api.chat_graph_write_workflow import (
        ChatGraphWriteArtifactError,
        ChatGraphWriteCandidateError,
        ChatGraphWriteVerificationError,
    )
    from artana_evidence_api.claim_curation_workflow import (
        ClaimCurationNoEligibleProposalsError,
    )
    from artana_evidence_api.research_onboarding_agent_runtime import (
        OnboardingAgentExecutionError,
    )
    from artana_evidence_api.run_budget import HarnessRunBudgetExceededError

    if isinstance(exc, OnboardingAgentExecutionError):
        return status.HTTP_503_SERVICE_UNAVAILABLE
    if isinstance(exc, HarnessRunBudgetExceededError):
        return status.HTTP_409_CONFLICT
    if isinstance(exc, ClaimCurationNoEligibleProposalsError):
        return status.HTTP_409_CONFLICT
    if isinstance(exc, ChatGraphWriteCandidateError):
        return status.HTTP_400_BAD_REQUEST
    if isinstance(exc, ChatGraphWriteArtifactError | ChatGraphWriteVerificationError):
        return status.HTTP_409_CONFLICT
    return None


__all__ = [
    "_specialized_worker_failure_status_code",
    "raise_for_failed_run",
    "worker_failure_payload",
]
