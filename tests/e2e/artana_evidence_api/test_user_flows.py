"""End-to-end harness API flows on top of the Artana-backed runtime adapters."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import uuid4

import pytest
import sqlalchemy as sa
from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    GraphSearchContract,
    GraphSearchResultEntry,
)
from artana_evidence_api.app import create_app
from artana_evidence_api.approval_store import HarnessApprovalAction
from artana_evidence_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from artana_evidence_api.chat_graph_write_models import (
    ChatGraphWriteCandidateRequest,
)
from artana_evidence_api.chat_workflow import GraphChatMessageExecution
from artana_evidence_api.claim_curation_workflow import ClaimCurationRunExecution
from artana_evidence_api.continuous_learning_runtime import (
    ContinuousLearningCandidateRecord,
    ContinuousLearningExecutionResult,
)
from artana_evidence_api.db_schema import harness_schema_name
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_chat_session_store,
    get_document_store,
    get_graph_api_gateway,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_proposal_store,
    get_research_space_store,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_chat_runtime import (
    GraphChatEvidenceItem,
    GraphChatResult,
    GraphChatVerification,
    HarnessGraphChatRunner,
)
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRunner,
)
from artana_evidence_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from artana_evidence_api.mechanism_discovery_runtime import (
    MechanismCandidateRecord,
    MechanismDiscoveryRunExecutionResult,
)
from artana_evidence_api.models import Base as HarnessBase
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.research_bootstrap_runtime import (
    ResearchBootstrapExecutionResult,
)
from artana_evidence_api.response_serialization import (
    serialize_continuous_learning_candidate,
    serialize_run_record,
)
from artana_evidence_api.routers.chat import build_chat_message_run_response
from artana_evidence_api.routers.graph_curation_runs import (
    build_claim_curation_run_response,
)
from artana_evidence_api.routers.mechanism_discovery_runs import (
    build_mechanism_discovery_run_response,
)
from artana_evidence_api.routers.research_bootstrap_runs import (
    build_research_bootstrap_run_response,
)
from artana_evidence_api.routers.supervisor_runs import build_supervisor_run_response
from artana_evidence_api.run_budget import (
    HarnessRunBudgetStatus,
    HarnessRunBudgetUsage,
    default_continuous_learning_run_budget,
)
from artana_evidence_api.run_registry import HarnessRunRecord
from artana_evidence_api.sqlalchemy_stores import (
    SqlAlchemyHarnessApprovalStore,
    SqlAlchemyHarnessChatSessionStore,
    SqlAlchemyHarnessGraphSnapshotStore,
    SqlAlchemyHarnessProposalStore,
    SqlAlchemyHarnessResearchStateStore,
    SqlAlchemyHarnessScheduleStore,
)
from artana_evidence_api.supervisor_runtime import SupervisorExecutionResult
from artana_evidence_api.tests.support import (
    FakeGraphApiGateway,
    FakeKernelRuntime,
    PermissiveHarnessResearchSpaceStore,
    auth_headers,
)
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from collections.abc import Iterator

    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
    from sqlalchemy.orm import Session


@contextmanager
def _fake_pubmed_discovery_context() -> Iterator[PubMedDiscoveryService]:
    yield cast("PubMedDiscoveryService", object())


def _graph_chat_result() -> GraphChatResult:
    source_entity_id = "11111111-1111-4111-8111-111111111111"
    target_entity_id = "22222222-2222-4222-8222-222222222222"
    return GraphChatResult(
        answer_text=(
            "Grounded graph answer:\n"
            "MED13 (GENE): Evidence supports a transcriptional regulation signal."
        ),
        chat_summary="MED13 has one verified grounded result.",
        evidence_bundle=[
            GraphChatEvidenceItem(
                entity_id=source_entity_id,
                entity_type="GENE",
                display_label="MED13",
                relevance_score=0.94,
                support_summary="Evidence supports a transcriptional regulation signal.",
                explanation="Synthetic grounded evidence for the e2e chat flow.",
            ),
        ],
        warnings=[],
        verification=GraphChatVerification(
            status="verified",
            reason="Synthetic verified chat answer.",
            grounded_match_count=1,
            top_relevance_score=0.94,
            warning_count=0,
            allows_graph_write=True,
        ),
        graph_write_candidates=[
            ChatGraphWriteCandidateRequest(
                source_entity_id=source_entity_id,
                relation_type="REGULATES",
                target_entity_id=target_entity_id,
                evidence_entity_ids=[source_entity_id],
                title="MED13 regulates transcription",
                summary="Promote the grounded chat finding into the graph.",
                rationale="Verified grounded answer produced this candidate.",
                ranking_score=0.93,
                ranking_metadata={"source": "e2e-chat"},
            ),
        ],
        search=GraphSearchContract(
            decision="generated",
            research_space_id="space",
            original_query="What is known about MED13?",
            interpreted_intent="Summarize grounded MED13 evidence.",
            query_plan_summary="Synthetic graph-search summary.",
            total_results=1,
            results=[
                GraphSearchResultEntry(
                    entity_id=source_entity_id,
                    entity_type="GENE",
                    display_label="MED13",
                    relevance_score=0.94,
                    matching_observation_ids=["obs-1"],
                    matching_relation_ids=["rel-1"],
                    evidence_chain=[],
                    explanation="Synthetic explanation.",
                    support_summary=(
                        "Evidence supports a transcriptional regulation signal."
                    ),
                ),
            ],
            executed_path="deterministic",
            warnings=[],
            agent_run_id="e2e-chat-search",
            confidence_score=0.94,
            rationale="Synthetic graph search result.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=source_entity_id,
                    excerpt="Synthetic MED13 excerpt",
                    relevance=0.94,
                ),
            ],
        ),
    )


def _candidate_claim_payload(
    *,
    source_entity_id: str,
    target_entity_id: str,
    relation_type: str = "REGULATES",
) -> dict[str, object]:
    return {
        "proposed_subject": source_entity_id,
        "proposed_object": target_entity_id,
        "proposed_claim_type": relation_type,
    }


def _completed_budget_status() -> HarnessRunBudgetStatus:
    budget = default_continuous_learning_run_budget()
    return HarnessRunBudgetStatus(
        status="completed",
        limits=budget,
        usage=HarnessRunBudgetUsage(
            tool_calls=3,
            external_queries=1,
            new_proposals=1,
            runtime_seconds=2.5,
            cost_usd=0.0,
        ),
        exhausted_limit=None,
        message="Synthetic continuous-learning run completed within budget.",
    )


def _complete_run_status(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
    phase: str,
    message: str,
    completed_steps: int,
    total_steps: int,
    metadata: dict[str, object] | None = None,
) -> HarnessRunRecord:
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="completed",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase=phase,
        message=message,
        progress_percent=1.0,
        completed_steps=completed_steps,
        total_steps=total_steps,
        clear_resume_point=True,
        metadata=metadata or {},
    )
    completed_run = services.run_registry.get_run(space_id=run.space_id, run_id=run.id)
    if completed_run is None:
        msg = f"Failed to reload completed run '{run.id}'."
        raise RuntimeError(msg)
    return completed_run


def _execute_bootstrap_result(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
    objective: str | None = None,
    source_kind: str = "research_bootstrap",
) -> ResearchBootstrapExecutionResult:
    objective_text = objective or "Synthetic MED13 bootstrap objective"
    seed_entity_id = str(uuid4())
    target_entity_id = str(uuid4())
    graph_snapshot = services.graph_snapshot_store.create_snapshot(
        space_id=run.space_id,
        source_run_id=run.id,
        claim_ids=["bootstrap-claim-1"],
        relation_ids=["bootstrap-relation-1"],
        graph_document_hash="bootstrap-hash",
        summary={"objective": objective_text, "claim_count": 1, "relation_count": 1},
        metadata={"source": source_kind},
    )
    research_state = services.research_state_store.upsert_state(
        space_id=run.space_id,
        objective=objective_text,
        current_hypotheses=["MED13 regulates transcription."],
        explored_questions=["How is MED13 connected to transcription control?"],
        pending_questions=["What evidence should be reviewed next?"],
        last_graph_snapshot_id=graph_snapshot.id,
        metadata={"source": source_kind},
    )
    proposal_records = services.proposal_store.create_proposals(
        space_id=run.space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind=source_kind,
                source_key=f"{seed_entity_id}:REGULATES:{target_entity_id}",
                title="MED13 regulates transcription",
                summary="Synthetic bootstrap claim proposal.",
                confidence=0.84,
                ranking_score=0.92,
                reasoning_path={"reasoning": "Synthetic bootstrap reasoning."},
                evidence_bundle=[{"source_type": "db", "locator": seed_entity_id}],
                payload=_candidate_claim_payload(
                    source_entity_id=seed_entity_id,
                    target_entity_id=target_entity_id,
                ),
                metadata={"agent_run_id": "e2e-bootstrap"},
            ),
        ),
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="graph_context_snapshot",
        media_type="application/json",
        content={
            "snapshot_id": graph_snapshot.id,
            "claim_ids": graph_snapshot.claim_ids,
            "relation_ids": graph_snapshot.relation_ids,
        },
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="research_brief",
        media_type="application/json",
        content={"objective": objective_text},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="graph_summary",
        media_type="application/json",
        content={"claim_count": 1, "relation_count": 1},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="source_inventory",
        media_type="application/json",
        content={"source_type": "pubmed", "source_count": 1},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="candidate_claim_pack",
        media_type="application/json",
        content={
            "proposal_count": len(proposal_records),
            "proposal_ids": [proposal.id for proposal in proposal_records],
        },
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={
            "status": "completed",
            "graph_snapshot_id": graph_snapshot.id,
            "proposal_count": len(proposal_records),
        },
    )
    completed_run = _complete_run_status(
        run=run,
        services=services,
        phase="completed",
        message="Research bootstrap finished.",
        completed_steps=4,
        total_steps=4,
        metadata={"proposal_count": len(proposal_records)},
    )
    execution_result = ResearchBootstrapExecutionResult(
        run=completed_run,
        graph_snapshot=graph_snapshot,
        research_state=research_state,
        research_brief={"objective": objective_text},
        graph_summary={"claim_count": 1, "relation_count": 1},
        source_inventory={"source_type": "pubmed", "source_count": 1},
        proposal_records=proposal_records,
        pending_questions=["What evidence should be reviewed next?"],
        errors=[],
    )
    store_primary_result_artifact(
        artifact_store=services.artifact_store,
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="research_bootstrap_response",
        content=build_research_bootstrap_run_response(
            execution_result,
        ).model_dump(mode="json"),
        status_value="completed",
        result_keys=(
            "graph_context_snapshot",
            "graph_summary",
            "research_brief",
            "source_inventory",
            "candidate_claim_pack",
        ),
    )
    return execution_result


def _execute_continuous_learning_result(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> ContinuousLearningExecutionResult:
    seed_entity_ids = run.input_payload.get("seed_entity_ids")
    seed_entity_id = (
        str(seed_entity_ids[0])
        if isinstance(seed_entity_ids, list)
        and seed_entity_ids
        and isinstance(seed_entity_ids[0], str)
        else str(uuid4())
    )
    target_entity_id = str(uuid4())
    graph_snapshot = services.graph_snapshot_store.create_snapshot(
        space_id=run.space_id,
        source_run_id=run.id,
        claim_ids=["learning-claim-1"],
        relation_ids=["learning-relation-1"],
        graph_document_hash="continuous-learning-hash",
        summary={"cycle": "daily", "delta_count": 1},
        metadata={"source": "continuous-learning"},
    )
    research_state = services.research_state_store.upsert_state(
        space_id=run.space_id,
        pending_questions=["What paper should be reviewed tomorrow?"],
        last_graph_snapshot_id=graph_snapshot.id,
        last_learning_cycle_at=datetime.now(UTC),
        metadata={"source": "continuous-learning"},
    )
    candidate = ContinuousLearningCandidateRecord(
        seed_entity_id=seed_entity_id,
        source_entity_id=seed_entity_id,
        relation_type="ASSOCIATED_WITH",
        target_entity_id=target_entity_id,
        confidence=0.78,
        evidence_summary="Synthetic continuous-learning evidence.",
        reasoning="Synthetic continuous-learning reasoning.",
        agent_run_id="e2e-continuous-learning",
        source_type="pubmed",
    )
    proposal_records = services.proposal_store.create_proposals(
        space_id=run.space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="continuous_learning",
                source_key=f"{seed_entity_id}:ASSOCIATED_WITH:{target_entity_id}",
                title="Continuous-learning proposal",
                summary="Synthetic continuous-learning proposal.",
                confidence=candidate.confidence,
                ranking_score=0.87,
                reasoning_path={"reasoning": candidate.reasoning},
                evidence_bundle=[{"source_type": "db", "locator": seed_entity_id}],
                payload=_candidate_claim_payload(
                    source_entity_id=seed_entity_id,
                    target_entity_id=target_entity_id,
                    relation_type=candidate.relation_type,
                ),
                metadata={"agent_run_id": "e2e-continuous-learning"},
            ),
        ),
    )
    delta_report = {"new_claim_count": 1, "updated_snapshot_id": graph_snapshot.id}
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="delta_report",
        media_type="application/json",
        content=delta_report,
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="new_paper_list",
        media_type="application/json",
        content={"papers": [{"pmid": "12345678", "title": "Synthetic MED13 paper"}]},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="candidate_claims",
        media_type="application/json",
        content={
            "proposal_ids": [proposal.id for proposal in proposal_records],
            "candidate_count": 1,
        },
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="next_questions",
        media_type="application/json",
        content={"questions": ["What paper should be reviewed tomorrow?"]},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="graph_context_snapshot",
        media_type="application/json",
        content={"snapshot_id": graph_snapshot.id},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="research_state_snapshot",
        media_type="application/json",
        content={
            "last_graph_snapshot_id": research_state.last_graph_snapshot_id,
            "pending_questions": research_state.pending_questions,
        },
    )
    budget_status = _completed_budget_status()
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={
            "status": "completed",
            "delta_report_key": "delta_report",
            "run_budget": budget_status.limits.model_dump(mode="json"),
            "budget_status": budget_status.model_dump(mode="json"),
        },
    )
    completed_run = _complete_run_status(
        run=run,
        services=services,
        phase="completed",
        message="Continuous-learning run finished.",
        completed_steps=4,
        total_steps=4,
        metadata={"proposal_count": len(proposal_records)},
    )
    execution_result = ContinuousLearningExecutionResult(
        run=completed_run,
        candidates=[candidate],
        proposal_records=proposal_records,
        delta_report=delta_report,
        next_questions=["What paper should be reviewed tomorrow?"],
        errors=[],
        run_budget=budget_status.limits,
        budget_status=budget_status,
    )
    store_primary_result_artifact(
        artifact_store=services.artifact_store,
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="continuous_learning_response",
        content={
            "run": serialize_run_record(run=completed_run),
            "candidates": [
                serialize_continuous_learning_candidate(candidate=item)
                for item in execution_result.candidates
            ],
            "candidate_count": len(execution_result.candidates),
            "proposal_count": len(execution_result.proposal_records),
            "next_questions": list(execution_result.next_questions),
            "delta_report": execution_result.delta_report,
            "errors": list(execution_result.errors),
            "run_budget": execution_result.run_budget.model_dump(mode="json"),
            "budget_status": execution_result.budget_status.model_dump(mode="json"),
        },
        status_value="completed",
        result_keys=(
            "delta_report",
            "new_paper_list",
            "candidate_claims",
            "next_questions",
            "graph_context_snapshot",
            "research_state_snapshot",
        ),
    )
    return execution_result


def _execute_mechanism_discovery_result(
    *,
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> MechanismDiscoveryRunExecutionResult:
    seed_entity_ids = run.input_payload.get("seed_entity_ids")
    seed_entity_id = (
        str(seed_entity_ids[0])
        if isinstance(seed_entity_ids, list)
        and seed_entity_ids
        and isinstance(seed_entity_ids[0], str)
        else str(uuid4())
    )
    end_entity_id = str(uuid4())
    candidate = MechanismCandidateRecord(
        seed_entity_ids=(seed_entity_id,),
        end_entity_id=end_entity_id,
        relation_type="MODULATES",
        source_label="MED13",
        target_label="Transcription Program",
        source_type="GENE",
        target_type="PROCESS",
        path_ids=("path-1", "path-2"),
        root_claim_ids=("claim-1",),
        supporting_claim_ids=("claim-1", "claim-2"),
        evidence_reference_count=2,
        max_path_confidence=0.86,
        average_path_confidence=0.81,
        average_path_length=2.5,
        ranking_score=0.9,
        ranking_metadata={"source": "e2e-mechanism"},
        summary="Synthetic converging mechanism candidate.",
        hypothesis_statement="MED13 modulates a transcription program.",
        hypothesis_rationale="Synthetic mechanism rationale.",
        evidence_bundle=(
            {"source_type": "db", "locator": seed_entity_id},
            {"source_type": "db", "locator": end_entity_id},
        ),
    )
    proposal_records = services.proposal_store.create_proposals(
        space_id=run.space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="mechanism_candidate",
                source_kind="mechanism_discovery",
                source_key=f"{seed_entity_id}:MODULATES:{end_entity_id}",
                title="Mechanism candidate",
                summary=candidate.summary,
                confidence=0.8,
                ranking_score=candidate.ranking_score,
                reasoning_path={"path_ids": list(candidate.path_ids)},
                evidence_bundle=list(candidate.evidence_bundle),
                payload={
                    "hypothesis_statement": candidate.hypothesis_statement,
                    "hypothesis_rationale": candidate.hypothesis_rationale,
                    "seed_entity_ids": [seed_entity_id],
                    "source_type": "pubmed",
                },
                metadata={"agent_run_id": "e2e-mechanism"},
            ),
        ),
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="mechanism_candidates",
        media_type="application/json",
        content={"candidate_count": 1},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="mechanism_score_report",
        media_type="application/json",
        content={"top_score": candidate.ranking_score},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="candidate_hypothesis_pack",
        media_type="application/json",
        content={
            "proposal_ids": [proposal.id for proposal in proposal_records],
            "candidate_count": 1,
        },
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={"status": "completed", "candidate_count": 1},
    )
    completed_run = _complete_run_status(
        run=run,
        services=services,
        phase="completed",
        message="Mechanism-discovery run finished.",
        completed_steps=3,
        total_steps=3,
        metadata={"proposal_count": len(proposal_records)},
    )
    execution_result = MechanismDiscoveryRunExecutionResult(
        run=completed_run,
        candidates=(candidate,),
        proposal_records=proposal_records,
        scanned_path_count=2,
    )
    store_primary_result_artifact(
        artifact_store=services.artifact_store,
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="mechanism_discovery_response",
        content=build_mechanism_discovery_run_response(
            execution_result,
        ).model_dump(mode="json"),
        status_value="completed",
        result_keys=(
            "mechanism_candidates",
            "mechanism_score_report",
            "candidate_hypothesis_pack",
        ),
    )
    return execution_result


async def _execute_e2e_run(  # noqa: PLR0912
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    if run.harness_id == "research-bootstrap":
        objective = run.input_payload.get("objective")
        objective_text = objective if isinstance(objective, str) else None
        return _execute_bootstrap_result(
            run=run,
            services=services,
            objective=objective_text,
        )

    if run.harness_id == "graph-chat":
        session_id = str(run.input_payload["session_id"])
        question = str(run.input_payload["question"])
        session = services.chat_session_store.get_session(
            space_id=run.space_id,
            session_id=session_id,
        )
        if session is None:
            msg = f"Chat session '{session_id}' not found."
            raise RuntimeError(msg)
        user_message = services.chat_session_store.add_message(
            space_id=run.space_id,
            session_id=session_id,
            role="user",
            content=question,
            run_id=run.id,
            metadata={"message_kind": "question"},
        )
        if user_message is None:
            msg = "Failed to persist user chat message."
            raise RuntimeError(msg)
        result = _graph_chat_result()
        assistant_message = services.chat_session_store.add_message(
            space_id=run.space_id,
            session_id=session_id,
            role="assistant",
            content=result.answer_text,
            run_id=run.id,
            metadata={"message_kind": "answer"},
        )
        if assistant_message is None:
            msg = "Failed to persist assistant chat message."
            raise RuntimeError(msg)
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="graph_chat_result",
            media_type="application/json",
            content=result.model_dump(mode="json"),
        )
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="chat_summary",
            media_type="application/json",
            content={"summary": result.chat_summary},
        )
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="grounded_answer_verification",
            media_type="application/json",
            content=result.verification.model_dump(mode="json"),
        )
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="graph_write_candidate_suggestions",
            media_type="application/json",
            content={
                "candidate_count": len(result.graph_write_candidates),
                "candidates": [
                    candidate.model_dump(mode="json")
                    for candidate in result.graph_write_candidates
                ],
            },
        )
        services.artifact_store.patch_workspace(
            space_id=run.space_id,
            run_id=run.id,
            patch={
                "status": "completed",
                "chat_session_id": session_id,
                "verification_status": result.verification.status,
                "graph_write_candidate_count": len(result.graph_write_candidates),
            },
        )
        updated_session = services.chat_session_store.update_session(
            space_id=run.space_id,
            session_id=session_id,
            last_run_id=run.id,
            status="active",
        )
        services.run_registry.set_run_status(
            space_id=run.space_id,
            run_id=run.id,
            status="completed",
        )
        services.run_registry.set_progress(
            space_id=run.space_id,
            run_id=run.id,
            phase="completed",
            message="Graph chat finished.",
            progress_percent=1.0,
            completed_steps=1,
            total_steps=1,
            metadata={"verification_status": result.verification.status},
            clear_resume_point=True,
        )
        completed_run = services.run_registry.get_run(
            space_id=run.space_id,
            run_id=run.id,
        )
        if completed_run is None or updated_session is None:
            msg = "Failed to reload completed graph-chat run state."
            raise RuntimeError(msg)
        execution_result = GraphChatMessageExecution(
            run=completed_run,
            session=updated_session,
            user_message=user_message,
            assistant_message=assistant_message,
            result=result,
        )
        store_primary_result_artifact(
            artifact_store=services.artifact_store,
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="chat_run_response",
            content=build_chat_message_run_response(
                execution_result,
            ).model_dump(mode="json"),
            status_value="completed",
            result_keys=(
                "graph_chat_result",
                "chat_summary",
                "grounded_answer_verification",
                "graph_write_candidate_suggestions",
            ),
        )
        return execution_result

    if run.harness_id == "continuous-learning":
        return _execute_continuous_learning_result(run=run, services=services)

    if run.harness_id == "mechanism-discovery":
        return _execute_mechanism_discovery_result(run=run, services=services)

    if run.harness_id == "claim-curation":
        proposal_ids_value = run.input_payload.get("proposal_ids")
        proposal_ids = (
            [str(value) for value in proposal_ids_value if isinstance(value, str)]
            if isinstance(proposal_ids_value, list)
            else []
        )
        approvals = services.approval_store.list_approvals(
            space_id=run.space_id,
            run_id=run.id,
        )
        if not approvals:
            proposals = [
                proposal
                for proposal in (
                    services.proposal_store.get_proposal(
                        space_id=run.space_id,
                        proposal_id=proposal_id,
                    )
                    for proposal_id in proposal_ids
                )
                if proposal is not None
            ]
            approval_actions = tuple(
                HarnessApprovalAction(
                    approval_key=f"promote:{proposal.id}",
                    title=f"Promote {proposal.title}",
                    risk_level="high",
                    target_type="proposal",
                    target_id=proposal.id,
                    requires_approval=True,
                    metadata={"proposal_id": proposal.id},
                )
                for proposal in proposals
            )
            services.approval_store.upsert_intent(
                space_id=run.space_id,
                run_id=run.id,
                summary="Review claim-curation candidates.",
                proposed_actions=approval_actions,
                metadata={"workflow": "claim_curation"},
            )
            review_plan = {
                "proposals": [
                    {
                        "proposal_id": proposal.id,
                        "title": proposal.title,
                        "summary": proposal.summary,
                        "source_key": proposal.source_key,
                        "confidence": proposal.confidence,
                        "ranking_score": proposal.ranking_score,
                        "approval_key": f"promote:{proposal.id}",
                        "duplicate_selected_count": 0,
                        "existing_promoted_proposal_ids": [],
                        "graph_duplicate_claim_ids": [],
                        "conflicting_relation_ids": [],
                        "invariant_issues": [],
                        "blocker_reasons": [],
                        "eligible_for_approval": True,
                    }
                    for proposal in proposals
                ],
            }
            curation_packet = {"proposal_ids": proposal_ids}
            approval_intent = {"summary": "Review claim-curation candidates."}
            services.artifact_store.put_artifact(
                space_id=run.space_id,
                run_id=run.id,
                artifact_key="curation_packet",
                media_type="application/json",
                content=curation_packet,
            )
            services.artifact_store.put_artifact(
                space_id=run.space_id,
                run_id=run.id,
                artifact_key="review_plan",
                media_type="application/json",
                content=review_plan,
            )
            services.artifact_store.put_artifact(
                space_id=run.space_id,
                run_id=run.id,
                artifact_key="approval_intent",
                media_type="application/json",
                content=approval_intent,
            )
            services.artifact_store.patch_workspace(
                space_id=run.space_id,
                run_id=run.id,
                patch={
                    "status": "paused",
                    "pending_approvals": len(proposals),
                    "review_plan_key": "review_plan",
                },
            )
            services.run_registry.set_run_status(
                space_id=run.space_id,
                run_id=run.id,
                status="paused",
            )
            services.run_registry.set_progress(
                space_id=run.space_id,
                run_id=run.id,
                phase="approval",
                message="Run paused pending approval.",
                progress_percent=0.5,
                completed_steps=1,
                total_steps=2,
                resume_point="approval_gate",
                metadata={"pending_approvals": len(proposals)},
            )
            paused_run = services.run_registry.get_run(
                space_id=run.space_id,
                run_id=run.id,
            )
            if paused_run is None:
                msg = "Failed to reload paused claim-curation run."
                raise RuntimeError(msg)
            execution_result = ClaimCurationRunExecution(
                run=paused_run,
                curation_packet=curation_packet,
                review_plan=review_plan,
                approval_intent=approval_intent,
                proposal_count=len(proposals),
                blocked_proposal_count=0,
                pending_approval_count=len(proposals),
            )
            store_primary_result_artifact(
                artifact_store=services.artifact_store,
                space_id=run.space_id,
                run_id=run.id,
                artifact_key="claim_curation_response",
                content=build_claim_curation_run_response(
                    execution_result,
                ).model_dump(mode="json"),
                status_value="paused",
                result_keys=("curation_packet", "review_plan", "approval_intent"),
            )
            return execution_result

        for approval in approvals:
            proposal_id = approval.metadata.get("proposal_id")
            if not isinstance(proposal_id, str):
                continue
            final_status = "promoted" if approval.status == "approved" else "rejected"
            services.proposal_store.decide_proposal(
                space_id=run.space_id,
                proposal_id=proposal_id,
                status=final_status,
                decision_reason="Applied during claim-curation resume.",
                metadata={"applied_by": "e2e-claim-curation"},
            )
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="curation_summary",
            media_type="application/json",
            content={"proposal_ids": proposal_ids, "applied": True},
        )
        services.artifact_store.patch_workspace(
            space_id=run.space_id,
            run_id=run.id,
            patch={"status": "completed", "pending_approvals": 0},
        )
        services.run_registry.set_run_status(
            space_id=run.space_id,
            run_id=run.id,
            status="completed",
        )
        services.run_registry.set_progress(
            space_id=run.space_id,
            run_id=run.id,
            phase="completed",
            message="Claim curation resume completed.",
            progress_percent=1.0,
            completed_steps=2,
            total_steps=2,
            clear_resume_point=True,
            metadata={"pending_approvals": 0},
        )
        completed_run = (
            services.run_registry.get_run(space_id=run.space_id, run_id=run.id) or run
        )
        review_plan_artifact = services.artifact_store.get_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="review_plan",
        )
        approval_intent_artifact = services.artifact_store.get_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="approval_intent",
        )
        execution_result = ClaimCurationRunExecution(
            run=completed_run,
            curation_packet={"proposal_ids": proposal_ids},
            review_plan=(
                review_plan_artifact.content if review_plan_artifact is not None else {}
            ),
            approval_intent=(
                approval_intent_artifact.content
                if approval_intent_artifact is not None
                else {}
            ),
            proposal_count=len(proposal_ids),
            blocked_proposal_count=0,
            pending_approval_count=0,
        )
        store_primary_result_artifact(
            artifact_store=services.artifact_store,
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="claim_curation_response",
            content=build_claim_curation_run_response(
                execution_result,
            ).model_dump(mode="json"),
            status_value="completed",
            result_keys=(
                "curation_packet",
                "review_plan",
                "approval_intent",
                "curation_summary",
            ),
        )
        return completed_run

    if run.harness_id == "supervisor":
        workspace = services.artifact_store.get_workspace(
            space_id=run.space_id,
            run_id=run.id,
        )
        workspace_snapshot = workspace.snapshot if workspace is not None else {}
        curation_run_id = workspace_snapshot.get("curation_run_id")
        if not isinstance(curation_run_id, str) or curation_run_id == "":
            objective = run.input_payload.get("objective")
            objective_text = (
                objective
                if isinstance(objective, str)
                else "Synthetic supervisor objective"
            )
            bootstrap_run = services.run_registry.create_run(
                space_id=run.space_id,
                harness_id="research-bootstrap",
                title="Supervisor Bootstrap",
                input_payload={"objective": objective_text},
                graph_service_status="ok",
                graph_service_version="test-graph",
            )
            services.artifact_store.seed_for_run(run=bootstrap_run)
            bootstrap_result = _execute_bootstrap_result(
                run=bootstrap_run,
                services=services,
                objective=objective_text,
                source_kind="supervisor_bootstrap",
            )

            chat_session = services.chat_session_store.create_session(
                space_id=run.space_id,
                title="Supervisor Briefing Chat",
                created_by=run.space_id,
            )
            briefing_question = "What should be reviewed next for MED13?"
            chat_run = services.run_registry.create_run(
                space_id=run.space_id,
                harness_id="graph-chat",
                title="Supervisor Briefing Chat",
                input_payload={
                    "session_id": chat_session.id,
                    "question": briefing_question,
                },
                graph_service_status="ok",
                graph_service_version="test-graph",
            )
            services.artifact_store.seed_for_run(run=chat_run)
            chat_execution = cast(
                "GraphChatMessageExecution",
                await _execute_e2e_run(chat_run, services),
            )

            selected_proposal = bootstrap_result.proposal_records[0]
            curation_run = services.run_registry.create_run(
                space_id=run.space_id,
                harness_id="claim-curation",
                title="Supervisor Curation",
                input_payload={
                    "workflow": "claim_curation",
                    "proposal_ids": [selected_proposal.id],
                },
                graph_service_status="ok",
                graph_service_version="test-graph",
            )
            services.artifact_store.seed_for_run(run=curation_run)
            curation_execution = cast(
                "ClaimCurationRunExecution",
                await _execute_e2e_run(curation_run, services),
            )
            steps = (
                {
                    "step": "bootstrap",
                    "status": "completed",
                    "harness_id": "research-bootstrap",
                    "run_id": bootstrap_result.run.id,
                    "detail": "Bootstrap finished.",
                },
                {
                    "step": "chat",
                    "status": "completed",
                    "harness_id": "graph-chat",
                    "run_id": chat_execution.run.id,
                    "detail": "Briefing chat finished.",
                },
                {
                    "step": "curation",
                    "status": "paused",
                    "harness_id": "claim-curation",
                    "run_id": curation_execution.run.id,
                    "detail": "Awaiting approval.",
                },
            )
            services.artifact_store.put_artifact(
                space_id=run.space_id,
                run_id=run.id,
                artifact_key="supervisor_plan",
                media_type="application/json",
                content={
                    "objective": objective_text,
                    "include_chat": True,
                    "include_curation": True,
                },
            )
            services.artifact_store.put_artifact(
                space_id=run.space_id,
                run_id=run.id,
                artifact_key="child_run_links",
                media_type="application/json",
                content={
                    "bootstrap_run_id": bootstrap_result.run.id,
                    "chat_run_id": chat_execution.run.id,
                    "chat_session_id": chat_execution.session.id,
                    "curation_run_id": curation_execution.run.id,
                },
            )
            services.artifact_store.put_artifact(
                space_id=run.space_id,
                run_id=run.id,
                artifact_key="supervisor_summary",
                media_type="application/json",
                content={
                    "workflow": "bootstrap_chat_curation",
                    "bootstrap_run_id": bootstrap_result.run.id,
                    "chat_run_id": chat_execution.run.id,
                    "chat_session_id": chat_execution.session.id,
                    "curation_run_id": curation_execution.run.id,
                    "briefing_question": briefing_question,
                    "curation_source": "bootstrap",
                    "curation_status": "paused",
                    "bootstrap_response": build_research_bootstrap_run_response(
                        bootstrap_result,
                    ).model_dump(mode="json"),
                    "chat_response": build_chat_message_run_response(
                        chat_execution,
                    ).model_dump(mode="json"),
                    "curation_response": build_claim_curation_run_response(
                        curation_execution,
                    ).model_dump(mode="json"),
                    "selected_curation_proposal_ids": [selected_proposal.id],
                    "chat_graph_write_proposal_ids": [],
                    "skipped_steps": [],
                    "steps": list(steps),
                },
            )
            services.artifact_store.patch_workspace(
                space_id=run.space_id,
                run_id=run.id,
                patch={
                    "status": "paused",
                    "bootstrap_run_id": bootstrap_result.run.id,
                    "chat_run_id": chat_execution.run.id,
                    "chat_session_id": chat_execution.session.id,
                    "curation_run_id": curation_execution.run.id,
                    "selected_curation_proposal_ids": [selected_proposal.id],
                },
            )
            services.run_registry.set_run_status(
                space_id=run.space_id,
                run_id=run.id,
                status="paused",
            )
            services.run_registry.set_progress(
                space_id=run.space_id,
                run_id=run.id,
                phase="approval",
                message="Supervisor paused pending child curation approval.",
                progress_percent=0.75,
                completed_steps=3,
                total_steps=4,
                resume_point="supervisor_child_approval_gate",
                metadata={"curation_run_id": curation_execution.run.id},
            )
            paused_run = services.run_registry.get_run(
                space_id=run.space_id,
                run_id=run.id,
            )
            if paused_run is None:
                msg = "Failed to reload paused supervisor run."
                raise RuntimeError(msg)
            execution_result = SupervisorExecutionResult(
                run=paused_run,
                bootstrap=bootstrap_result,
                chat_session=chat_execution.session,
                chat=chat_execution,
                curation=curation_execution,
                briefing_question=briefing_question,
                curation_source="bootstrap",
                chat_graph_write=None,
                selected_curation_proposal_ids=(selected_proposal.id,),
                steps=steps,
            )
            store_primary_result_artifact(
                artifact_store=services.artifact_store,
                space_id=run.space_id,
                run_id=run.id,
                artifact_key="supervisor_run_response",
                content=build_supervisor_run_response(
                    execution_result,
                ).model_dump(mode="json"),
                status_value="paused",
                result_keys=("supervisor_summary", "child_run_links"),
            )
            return execution_result

        child_run = services.run_registry.get_run(
            space_id=run.space_id,
            run_id=curation_run_id,
        )
        if child_run is None:
            msg = f"Supervisor child curation run '{curation_run_id}' not found."
            raise RuntimeError(msg)
        completed_curation_run = await _execute_e2e_run(child_run, services)
        if not isinstance(completed_curation_run, HarnessRunRecord):
            msg = "Expected claim-curation resume to return the completed child run."
            raise RuntimeError(msg)
        summary_artifact = services.artifact_store.get_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="supervisor_summary",
        )
        if summary_artifact is None:
            msg = "Supervisor summary artifact is missing."
            raise RuntimeError(msg)
        curation_workspace = services.artifact_store.get_workspace(
            space_id=run.space_id,
            run_id=curation_run_id,
        )
        review_plan_artifact = services.artifact_store.get_artifact(
            space_id=run.space_id,
            run_id=curation_run_id,
            artifact_key="review_plan",
        )
        approval_intent_artifact = services.artifact_store.get_artifact(
            space_id=run.space_id,
            run_id=curation_run_id,
            artifact_key="approval_intent",
        )
        curation_execution = ClaimCurationRunExecution(
            run=completed_curation_run,
            curation_packet={
                "proposal_ids": summary_artifact.content.get(
                    "selected_curation_proposal_ids",
                    [],
                ),
            },
            review_plan=(
                review_plan_artifact.content if review_plan_artifact is not None else {}
            ),
            approval_intent=(
                approval_intent_artifact.content
                if approval_intent_artifact is not None
                else {}
            ),
            proposal_count=1,
            blocked_proposal_count=0,
            pending_approval_count=0,
        )
        updated_summary = {
            **summary_artifact.content,
            "curation_status": "completed",
            "completed_at": datetime.now(UTC).isoformat(),
            "curation_response": build_claim_curation_run_response(
                curation_execution,
            ).model_dump(mode="json"),
            "curation_summary": {"applied": True},
            "curation_actions": {"promoted_count": 1},
            "steps": [
                {
                    "step": "bootstrap",
                    "status": "completed",
                    "harness_id": "research-bootstrap",
                    "run_id": summary_artifact.content["bootstrap_run_id"],
                    "detail": "Bootstrap finished.",
                },
                {
                    "step": "chat",
                    "status": "completed",
                    "harness_id": "graph-chat",
                    "run_id": summary_artifact.content["chat_run_id"],
                    "detail": "Briefing chat finished.",
                },
                {
                    "step": "curation",
                    "status": "completed",
                    "harness_id": "claim-curation",
                    "run_id": curation_run_id,
                    "detail": "Child curation completed after approval.",
                },
            ],
        }
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="supervisor_summary",
            media_type="application/json",
            content=updated_summary,
        )
        services.artifact_store.patch_workspace(
            space_id=run.space_id,
            run_id=run.id,
            patch={
                "status": "completed",
                "curation_status": "completed",
                "completed_at": updated_summary["completed_at"],
                "pending_approvals": (
                    curation_workspace.snapshot.get("pending_approvals", 0)
                    if curation_workspace is not None
                    else 0
                ),
            },
        )
        completed_run = _complete_run_status(
            run=run,
            services=services,
            phase="completed",
            message="Supervisor completed after child approval resolution.",
            completed_steps=4,
            total_steps=4,
            metadata={"curation_run_id": curation_run_id},
        )
        store_primary_result_artifact(
            artifact_store=services.artifact_store,
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="supervisor_run_response",
            content={
                "run": serialize_run_record(run=completed_run),
                "bootstrap": updated_summary.get("bootstrap_response"),
                "chat": updated_summary.get("chat_response"),
                "curation": updated_summary.get("curation_response"),
                "briefing_question": updated_summary.get("briefing_question"),
                "curation_source": updated_summary.get("curation_source"),
                "chat_graph_write_proposal_ids": updated_summary.get(
                    "chat_graph_write_proposal_ids",
                    [],
                ),
                "selected_curation_proposal_ids": updated_summary.get(
                    "selected_curation_proposal_ids",
                    [],
                ),
                "chat_graph_write_review_count": 0,
                "latest_chat_graph_write_review": None,
                "chat_graph_write_reviews": [],
                "steps": updated_summary.get("steps", []),
            },
            status_value="completed",
            result_keys=("supervisor_summary", "child_run_links"),
        )
        return completed_run

    msg = f"Unsupported e2e harness '{run.harness_id}'."
    raise RuntimeError(msg)


def _build_services(
    *,
    session: Session,
    runtime: FakeKernelRuntime,
) -> HarnessExecutionServices:
    return HarnessExecutionServices(
        runtime=cast("GraphHarnessKernelRuntime", runtime),
        run_registry=ArtanaBackedHarnessRunRegistry(
            session=session,
            runtime=cast("GraphHarnessKernelRuntime", runtime),
        ),
        artifact_store=ArtanaBackedHarnessArtifactStore(
            runtime=cast("GraphHarnessKernelRuntime", runtime),
        ),
        chat_session_store=SqlAlchemyHarnessChatSessionStore(session),
        document_store=HarnessDocumentStore(),
        proposal_store=SqlAlchemyHarnessProposalStore(session),
        approval_store=SqlAlchemyHarnessApprovalStore(session),
        research_state_store=SqlAlchemyHarnessResearchStateStore(session),
        graph_snapshot_store=SqlAlchemyHarnessGraphSnapshotStore(session),
        schedule_store=SqlAlchemyHarnessScheduleStore(session),
        graph_connection_runner=HarnessGraphConnectionRunner(),
        graph_chat_runner=HarnessGraphChatRunner(),
        graph_api_gateway_factory=FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
        execution_override=_execute_e2e_run,
    )


def _reset_harness_runtime_tables(bind: Session | sa.Connection) -> None:
    harness_tables = [
        table
        for table in HarnessBase.metadata.sorted_tables
        if table.name.startswith("harness_")
    ]
    if bind.dialect.name == "sqlite":
        bind.execute(sa.text("PRAGMA foreign_keys=OFF"))
    for table in reversed(harness_tables):
        table.drop(bind=bind, checkfirst=True)
    for table in harness_tables:
        table.create(bind=bind, checkfirst=True)
    if bind.dialect.name == "sqlite":
        bind.execute(sa.text("PRAGMA foreign_keys=ON"))


def _build_client(
    *,
    session: Session,
    runtime: FakeKernelRuntime,
) -> tuple[TestClient, HarnessExecutionServices]:
    engine = session.get_bind()
    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            schema = harness_schema_name()
            if schema is not None:
                connection.execute(sa.text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        _reset_harness_runtime_tables(connection)
    services = _build_services(session=session, runtime=runtime)
    app = create_app()
    app.dependency_overrides[get_run_registry] = lambda: services.run_registry
    app.dependency_overrides[get_artifact_store] = lambda: services.artifact_store
    app.dependency_overrides[get_approval_store] = lambda: services.approval_store
    app.dependency_overrides[get_chat_session_store] = (
        lambda: services.chat_session_store
    )
    app.dependency_overrides[get_document_store] = lambda: services.document_store
    app.dependency_overrides[get_graph_api_gateway] = FakeGraphApiGateway
    app.dependency_overrides[get_graph_snapshot_store] = (
        lambda: services.graph_snapshot_store
    )
    app.dependency_overrides[get_harness_execution_services] = lambda: services
    app.dependency_overrides[get_proposal_store] = lambda: services.proposal_store
    app.dependency_overrides[get_research_space_store] = (
        lambda: PermissiveHarnessResearchSpaceStore()
    )
    app.dependency_overrides[get_research_state_store] = (
        lambda: services.research_state_store
    )
    app.dependency_overrides[get_schedule_store] = lambda: services.schedule_store
    return TestClient(app), services


@pytest.mark.e2e
def test_chat_flow_runs_to_inline_graph_write_review_with_artana_backed_state(
    db_session: Session,
) -> None:
    client, _services = _build_client(session=db_session, runtime=FakeKernelRuntime())
    space_id = str(uuid4())

    session_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions",
        headers=auth_headers(),
        json={"title": "MED13 chat"},
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    message_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/messages",
        headers=auth_headers(),
        json={"content": "What is known about MED13?"},
    )
    assert message_response.status_code == 201
    message_payload = message_response.json()
    assert message_payload["run"]["status"] == "completed"
    assert message_payload["result"]["verification"]["status"] == "verified"
    assert len(message_payload["result"]["graph_write_candidates"]) == 1

    review_response = client.post(
        f"/v1/spaces/{space_id}/chat-sessions/{session_id}/graph-write-candidates/0/review",
        headers=auth_headers(),
        json={"decision": "promote", "reason": "Grounded evidence is sufficient"},
    )
    assert review_response.status_code == 200
    review_payload = review_response.json()
    assert review_payload["proposal"]["status"] == "promoted"
    assert review_payload["candidate"]["relation_type"] == "REGULATES"

    capabilities_response = client.get(
        f"/v1/spaces/{space_id}/runs/{message_payload['run']['id']}/capabilities",
        headers=auth_headers(role="viewer"),
    )
    assert capabilities_response.status_code == 200
    capabilities_payload = capabilities_response.json()
    visible_tool_names = {
        tool["tool_name"] for tool in capabilities_payload["visible_tools"]
    }
    assert "suggest_relations" in visible_tool_names

    policy_response = client.get(
        f"/v1/spaces/{space_id}/runs/{message_payload['run']['id']}/policy-decisions",
        headers=auth_headers(role="viewer"),
    )
    assert policy_response.status_code == 200
    policy_payload = policy_response.json()
    assert policy_payload["summary"]["manual_review_count"] == 1
    manual_records = [
        record
        for record in policy_payload["records"]
        if record["decision_source"] == "manual_review"
    ]
    assert len(manual_records) == 1
    assert manual_records[0]["tool_name"] == "create_graph_claim"


@pytest.mark.e2e
def test_claim_curation_flow_pauses_for_approval_and_completes_after_resume(
    db_session: Session,
) -> None:
    client, services = _build_client(session=db_session, runtime=FakeKernelRuntime())
    space_id = str(uuid4())
    source_run = services.run_registry.create_run(
        space_id=space_id,
        harness_id="hypotheses",
        title="Seeded proposals",
        input_payload={"seed_entity_ids": ["entity-med13"]},
        graph_service_status="ok",
        graph_service_version="graph-v1",
    )
    created_proposals = services.proposal_store.create_proposals(
        space_id=space_id,
        run_id=source_run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="hypothesis_run",
                source_key="entity-med13:REGULATES:entity-transcription",
                title="MED13 regulates transcription",
                summary="Synthetic proposal for curation.",
                confidence=0.81,
                ranking_score=0.92,
                reasoning_path={"seed_entity_id": "entity-med13"},
                evidence_bundle=[{"source_type": "db", "locator": "entity-med13"}],
                payload={"relation_type": "REGULATES"},
                metadata={"source": "e2e"},
            ),
        ),
    )

    curation_response = client.post(
        f"/v1/spaces/{space_id}/agents/graph-curation/runs",
        headers=auth_headers(),
        json={"proposal_ids": [created_proposals[0].id]},
    )
    assert curation_response.status_code == 201
    curation_payload = curation_response.json()
    assert curation_payload["run"]["status"] == "paused"
    assert curation_payload["pending_approval_count"] == 1

    run_id = curation_payload["run"]["id"]
    approval_key = curation_payload["proposals"][0]["approval_key"]

    approval_response = client.post(
        f"/v1/spaces/{space_id}/runs/{run_id}/approvals/{approval_key}",
        headers=auth_headers(),
        json={"decision": "approved", "reason": "Synthetic approval"},
    )
    assert approval_response.status_code == 200
    assert approval_response.json()["status"] == "approved"

    resume_response = client.post(
        f"/v1/spaces/{space_id}/runs/{run_id}/resume",
        headers=auth_headers(),
        json={"reason": "Continue after approval"},
    )
    assert resume_response.status_code == 200
    assert resume_response.json()["run"]["status"] == "completed"

    refreshed_proposal = services.proposal_store.get_proposal(
        space_id=space_id,
        proposal_id=created_proposals[0].id,
    )
    assert refreshed_proposal is not None
    assert refreshed_proposal.status == "promoted"


@pytest.mark.e2e
def test_research_bootstrap_flow_stages_proposals_and_allows_promotion(
    db_session: Session,
) -> None:
    client, _services = _build_client(session=db_session, runtime=FakeKernelRuntime())
    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    bootstrap_response = client.post(
        f"/v1/spaces/{space_id}/agents/research-bootstrap/runs",
        headers=auth_headers(),
        json={
            "objective": "Bootstrap MED13 knowledge",
            "seed_entity_ids": [seed_entity_id],
        },
    )
    assert bootstrap_response.status_code == 201
    bootstrap_payload = bootstrap_response.json()
    assert bootstrap_payload["proposal_count"] == 1

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals",
        headers=auth_headers(),
    )
    assert proposals_response.status_code == 200
    proposal_id = proposals_response.json()["proposals"][0]["id"]

    promote_response = client.post(
        f"/v1/spaces/{space_id}/proposals/{proposal_id}/promote",
        headers=auth_headers(),
        json={"reason": "Bootstrap evidence is sufficient"},
    )
    assert promote_response.status_code == 200
    assert promote_response.json()["status"] == "promoted"


@pytest.mark.e2e
def test_schedule_run_now_emits_delta_report_for_continuous_learning(
    db_session: Session,
) -> None:
    client, _services = _build_client(session=db_session, runtime=FakeKernelRuntime())
    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    schedule_response = client.post(
        f"/v1/spaces/{space_id}/schedules",
        headers=auth_headers(),
        json={
            "title": "Daily MED13 refresh",
            "cadence": "daily",
            "seed_entity_ids": [seed_entity_id],
        },
    )
    assert schedule_response.status_code == 201
    schedule_id = schedule_response.json()["id"]

    run_now_response = client.post(
        f"/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
        headers=auth_headers(),
    )
    assert run_now_response.status_code == 201
    run_now_payload = run_now_response.json()
    assert run_now_payload["result"]["run"]["status"] == "completed"
    assert run_now_payload["result"]["delta_report"]["new_claim_count"] == 1
    assert (
        run_now_payload["schedule"]["last_run_id"]
        == run_now_payload["result"]["run"]["id"]
    )


@pytest.mark.e2e
def test_mechanism_discovery_flow_returns_ranked_candidates_and_staged_proposals(
    db_session: Session,
) -> None:
    client, _services = _build_client(session=db_session, runtime=FakeKernelRuntime())
    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    mechanism_response = client.post(
        f"/v1/spaces/{space_id}/agents/mechanism-discovery/runs",
        headers=auth_headers(),
        json={"seed_entity_ids": [seed_entity_id]},
    )
    assert mechanism_response.status_code == 201
    mechanism_payload = mechanism_response.json()
    assert mechanism_payload["candidate_count"] == 1
    assert mechanism_payload["proposal_count"] == 1
    assert mechanism_payload["candidates"][0]["ranking_score"] == 0.9

    proposals_response = client.get(
        f"/v1/spaces/{space_id}/proposals?proposal_type=mechanism_candidate",
        headers=auth_headers(),
    )
    assert proposals_response.status_code == 200
    assert proposals_response.json()["total"] == 1
    assert proposals_response.json()["proposals"][0]["status"] == "pending_review"


@pytest.mark.e2e
def test_supervisor_flow_composes_bootstrap_chat_and_curation_then_resumes(
    db_session: Session,
) -> None:
    client, _services = _build_client(session=db_session, runtime=FakeKernelRuntime())
    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        headers=auth_headers(),
        json={
            "objective": "Coordinate MED13 review",
            "seed_entity_ids": [seed_entity_id],
            "include_chat": True,
            "include_curation": True,
            "curation_source": "bootstrap",
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.json()
    assert created_payload["run"]["status"] == "paused"
    assert created_payload["chat"] is not None
    assert created_payload["curation"] is not None
    assert created_payload["curation"]["pending_approval_count"] == 1

    parent_run_id = created_payload["run"]["id"]
    child_run_id = created_payload["curation"]["run"]["id"]
    approval_key = created_payload["curation"]["proposals"][0]["approval_key"]

    decide_response = client.post(
        f"/v1/spaces/{space_id}/runs/{child_run_id}/approvals/{approval_key}",
        headers=auth_headers(),
        json={"decision": "approved", "reason": "Supervisor e2e approval"},
    )
    assert decide_response.status_code == 200

    resume_response = client.post(
        f"/v1/spaces/{space_id}/runs/{parent_run_id}/resume",
        headers=auth_headers(),
        json={"reason": "Continue supervisor after approval"},
    )
    assert resume_response.status_code == 200
    assert resume_response.json()["run"]["status"] == "completed"

    detail_response = client.get(
        f"/v1/spaces/{space_id}/agents/supervisor/runs/{parent_run_id}",
        headers=auth_headers(),
    )
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["run"]["status"] == "completed"
    assert detail_payload["chat"] is not None
    assert detail_payload["curation"]["run"]["status"] == "completed"
    assert detail_payload["completed_at"] is not None
