"""Shared Artana tool-step helpers for graph-harness workflows."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from artana_evidence_api.pubmed_discovery import DiscoverySearchJob
from artana_evidence_api.runtime_errors import (
    GraphHarnessToolReconciliationRequiredError,
)
from artana_evidence_api.tool_catalog import (
    CaptureGraphSnapshotToolArgs,
    CreateGraphClaimToolArgs,
    CreateManualHypothesisToolArgs,
    GetReasoningPathToolArgs,
    GraphDocumentToolArgs,
    ListClaimEvidenceToolArgs,
    ListClaimParticipantsToolArgs,
    ListClaimsByEntityToolArgs,
    ListGraphClaimsToolArgs,
    ListGraphHypothesesToolArgs,
    ListReasoningPathsToolArgs,
    ListRelationConflictsToolArgs,
    RunPubMedSearchToolArgs,
    SuggestRelationsToolArgs,
)
from artana_evidence_api.types.graph_contracts import (
    ClaimParticipantListResponse,
    HypothesisListResponse,
    HypothesisResponse,
    KernelClaimEvidenceListResponse,
    KernelGraphDocumentResponse,
    KernelReasoningPathDetailResponse,
    KernelReasoningPathListResponse,
    KernelRelationClaimListResponse,
    KernelRelationClaimResponse,
    KernelRelationConflictListResponse,
    KernelRelationSuggestionListResponse,
)

if TYPE_CHECKING:
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.run_registry import HarnessRunRecord
    from artana_evidence_api.types.common import JSONObject
    from pydantic import BaseModel


class GraphHarnessToolExecutionError(RuntimeError):
    """Raised when a shared Artana tool step cannot be executed or decoded."""


logger = logging.getLogger(__name__)


def _decode_json_result(result_json: str) -> JSONObject:
    try:
        decoded = json.loads(result_json)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive validation
        msg = f"Graph-harness tool result was not valid JSON: {exc}"
        raise GraphHarnessToolExecutionError(msg) from exc
    if not isinstance(decoded, dict):
        msg = "Graph-harness tool result must decode to one JSON object."
        raise GraphHarnessToolExecutionError(msg)
    return decoded


def _execute_tool_result_json(  # noqa: PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    tool_name: str,
    arguments: BaseModel,
    step_key: str,
    parent_step_key: str | None = None,
) -> str:
    try:
        result = runtime.step_tool(
            run_id=run.id,
            tenant_id=run.space_id,
            tool_name=tool_name,
            arguments=arguments,
            step_key=step_key,
            parent_step_key=parent_step_key,
        )
    except GraphHarnessToolReconciliationRequiredError as exc:
        logger.info(
            "Reconciling graph-harness tool after ambiguous outcome",
            extra={
                "artana_run_id": run.id,
                "artana_space_id": run.space_id,
                "artana_tool_name": tool_name,
                "artana_step_key": step_key,
                "artana_reconcile_reason": "typed_runtime_signal",
                "artana_tool_outcome": exc.outcome,
            },
        )
    else:
        return result.result_json
    try:
        return runtime.reconcile_tool(
            run_id=run.id,
            tenant_id=run.space_id,
            tool_name=tool_name,
            arguments=arguments,
            step_key=f"{step_key}_reconcile",
            parent_step_key=parent_step_key,
        )
    except Exception:
        logger.warning(
            "Graph-harness tool reconciliation failed",
            extra={
                "artana_run_id": run.id,
                "artana_space_id": run.space_id,
                "artana_tool_name": tool_name,
                "artana_step_key": step_key,
            },
            exc_info=True,
        )
        raise


def _execute_tool_json(  # noqa: PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    tool_name: str,
    arguments: BaseModel,
    step_key: str,
    parent_step_key: str | None = None,
) -> JSONObject:
    return _decode_json_result(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name=tool_name,
            arguments=arguments,
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_get_graph_document(  # noqa: PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    space_id: str,
    seed_entity_ids: list[str],
    depth: int,
    top_k: int,
    step_key: str,
    parent_step_key: str | None = None,
) -> KernelGraphDocumentResponse:
    return KernelGraphDocumentResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="get_graph_document",
            arguments=GraphDocumentToolArgs(
                space_id=space_id,
                seed_entity_ids=seed_entity_ids,
                depth=depth,
                top_k=top_k,
            ),
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_list_graph_claims(  # noqa: PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    space_id: str,
    claim_status: str | None,
    limit: int,
    step_key: str,
    parent_step_key: str | None = None,
) -> KernelRelationClaimListResponse:
    return KernelRelationClaimListResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="list_graph_claims",
            arguments=ListGraphClaimsToolArgs(
                space_id=space_id,
                claim_status=claim_status,
                limit=limit,
            ),
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_list_graph_hypotheses(  # noqa: PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    space_id: str,
    limit: int,
    step_key: str,
    parent_step_key: str | None = None,
) -> HypothesisListResponse:
    return HypothesisListResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="list_graph_hypotheses",
            arguments=ListGraphHypothesesToolArgs(space_id=space_id, limit=limit),
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_capture_graph_snapshot(  # noqa: PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    space_id: str,
    seed_entity_ids: list[str],
    depth: int,
    top_k: int,
    step_key: str,
    parent_step_key: str | None = None,
) -> JSONObject:
    return _execute_tool_json(
        runtime=runtime,
        run=run,
        tool_name="capture_graph_snapshot",
        arguments=CaptureGraphSnapshotToolArgs(
            space_id=space_id,
            seed_entity_ids=seed_entity_ids,
            depth=depth,
            top_k=top_k,
        ),
        step_key=step_key,
        parent_step_key=parent_step_key,
    )


def run_suggest_relations(  # noqa: PLR0913
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    space_id: str,
    source_entity_ids: list[str],
    allowed_relation_types: list[str] | None,
    target_entity_types: list[str] | None,
    limit_per_source: int,
    min_score: float,
    step_key: str,
    parent_step_key: str | None = None,
) -> KernelRelationSuggestionListResponse:
    return KernelRelationSuggestionListResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="suggest_relations",
            arguments=SuggestRelationsToolArgs(
                space_id=space_id,
                source_entity_ids=source_entity_ids,
                allowed_relation_types=allowed_relation_types,
                target_entity_types=target_entity_types,
                limit_per_source=limit_per_source,
                min_score=min_score,
            ),
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_pubmed_search(
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    request: RunPubMedSearchToolArgs,
    step_key: str,
    parent_step_key: str | None = None,
) -> DiscoverySearchJob:
    return DiscoverySearchJob.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="run_pubmed_search",
            arguments=request,
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_list_reasoning_paths(
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    arguments: ListReasoningPathsToolArgs,
    step_key: str,
    parent_step_key: str | None = None,
) -> KernelReasoningPathListResponse:
    return KernelReasoningPathListResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="list_reasoning_paths",
            arguments=arguments,
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_get_reasoning_path(
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    arguments: GetReasoningPathToolArgs,
    step_key: str,
    parent_step_key: str | None = None,
) -> KernelReasoningPathDetailResponse:
    return KernelReasoningPathDetailResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="get_reasoning_path",
            arguments=arguments,
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_list_claims_by_entity(
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    arguments: ListClaimsByEntityToolArgs,
    step_key: str,
    parent_step_key: str | None = None,
) -> KernelRelationClaimListResponse:
    return KernelRelationClaimListResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="list_claims_by_entity",
            arguments=arguments,
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_list_claim_participants(
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    arguments: ListClaimParticipantsToolArgs,
    step_key: str,
    parent_step_key: str | None = None,
) -> ClaimParticipantListResponse:
    return ClaimParticipantListResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="list_claim_participants",
            arguments=arguments,
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_list_claim_evidence(
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    arguments: ListClaimEvidenceToolArgs,
    step_key: str,
    parent_step_key: str | None = None,
) -> KernelClaimEvidenceListResponse:
    return KernelClaimEvidenceListResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="list_claim_evidence",
            arguments=arguments,
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_list_relation_conflicts(
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    arguments: ListRelationConflictsToolArgs,
    step_key: str,
    parent_step_key: str | None = None,
) -> KernelRelationConflictListResponse:
    return KernelRelationConflictListResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="list_relation_conflicts",
            arguments=arguments,
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_create_graph_claim(
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    arguments: CreateGraphClaimToolArgs,
    step_key: str,
    parent_step_key: str | None = None,
) -> KernelRelationClaimResponse:
    return KernelRelationClaimResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="create_graph_claim",
            arguments=arguments,
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


def run_create_manual_hypothesis(
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    arguments: CreateManualHypothesisToolArgs,
    step_key: str,
    parent_step_key: str | None = None,
) -> HypothesisResponse:
    return HypothesisResponse.model_validate_json(
        _execute_tool_result_json(
            runtime=runtime,
            run=run,
            tool_name="create_manual_hypothesis",
            arguments=arguments,
            step_key=step_key,
            parent_step_key=parent_step_key,
        ),
    )


__all__ = [
    "GraphHarnessToolExecutionError",
    "run_capture_graph_snapshot",
    "run_create_graph_claim",
    "run_create_manual_hypothesis",
    "run_get_graph_document",
    "run_get_reasoning_path",
    "run_list_claim_evidence",
    "run_list_claim_participants",
    "run_list_claims_by_entity",
    "run_list_graph_claims",
    "run_list_graph_hypotheses",
    "run_list_reasoning_paths",
    "run_list_relation_conflicts",
    "run_pubmed_search",
    "run_suggest_relations",
]
