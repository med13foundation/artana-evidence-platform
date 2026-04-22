"""Integration coverage for Artana-backed graph-harness runtime paths."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event, Lock
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

import artana_evidence_api.sqlalchemy_stores as sqlalchemy_stores_module
import pytest
from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    GraphConnectionContract,
    GraphSearchContract,
    GraphSearchGroundingLevel,
    GraphSearchResultEntry,
    OnboardingAssistantContract,
    OnboardingQuestion,
    OnboardingSection,
    OnboardingStatePatch,
    OnboardingSuggestedAction,
    build_graph_search_assessment_from_confidence,
)
from artana_evidence_api.app import create_app
from artana_evidence_api.approval_store import HarnessApprovalAction
from artana_evidence_api.artana_stores import (
    ArtanaBackedHarnessArtifactStore,
    ArtanaBackedHarnessRunRegistry,
)
from artana_evidence_api.claim_curation_workflow import ClaimCurationRunExecution
from artana_evidence_api.config import get_settings
from artana_evidence_api.continuous_learning_runtime import (
    ContinuousLearningExecutionResult,
)
from artana_evidence_api.database import engine
from artana_evidence_api.dependencies import (
    get_approval_store,
    get_artifact_store,
    get_chat_session_store,
    get_document_store,
    get_graph_api_gateway,
    get_graph_connection_runner,
    get_graph_search_runner,
    get_graph_snapshot_store,
    get_harness_execution_services,
    get_proposal_store,
    get_research_onboarding_runner,
    get_research_space_store,
    get_research_state_store,
    get_run_registry,
    get_schedule_store,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.graph_chat_runtime import HarnessGraphChatRunner
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionResult,
    HarnessGraphConnectionRunner,
    execute_graph_connection_run,
)
from artana_evidence_api.graph_search_runtime import (
    HarnessGraphSearchRequest,
    HarnessGraphSearchResult,
    HarnessGraphSearchRunner,
    execute_graph_search_run,
)
from artana_evidence_api.harness_runtime import (
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from artana_evidence_api.hypothesis_runtime import execute_hypothesis_run
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.research_bootstrap_runtime import (
    ResearchBootstrapExecutionResult,
)
from artana_evidence_api.research_onboarding_agent_runtime import (
    HarnessResearchOnboardingContinuationRequest,
    HarnessResearchOnboardingInitialRequest,
    HarnessResearchOnboardingResult,
    HarnessResearchOnboardingRunner,
    OnboardingAgentExecutionError,
)
from artana_evidence_api.research_onboarding_runtime import (
    ResearchOnboardingContinuationRequest,
    execute_research_onboarding_continuation,
    execute_research_onboarding_run,
)
from artana_evidence_api.routers.graph_curation_runs import (
    build_claim_curation_run_response,
)
from artana_evidence_api.routers.research_bootstrap_runs import (
    build_research_bootstrap_run_response,
)
from artana_evidence_api.routers.supervisor_runs import build_supervisor_run_response
from artana_evidence_api.run_budget import (
    HarnessRunBudgetStatus,
    HarnessRunBudgetUsage,
    budget_from_json,
    resolve_continuous_learning_run_budget,
)
from artana_evidence_api.run_registry import HarnessRunRecord
from artana_evidence_api.schedule_store import HarnessScheduleStore
from artana_evidence_api.scheduler import SchedulerTickResult, run_scheduler_tick
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
    FakeEvent,
    FakeGraphApiGateway,
    FakeKernelRuntime,
    FakeSummary,
    PermissiveHarnessResearchSpaceStore,
    auth_headers,
)
from artana_evidence_api.tool_catalog import RunPubMedSearchToolArgs
from artana_evidence_api.transparency import (
    append_manual_review_decision,
    append_skill_activity,
)
from artana_evidence_api.worker import list_queued_worker_runs, run_worker_tick
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from src.domain.agents.contracts.fact_assessment import (
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    build_fact_assessment_from_confidence,
)

if TYPE_CHECKING:
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService


@contextmanager
def _fake_pubmed_discovery_context() -> Iterator[PubMedDiscoveryService]:
    yield cast("PubMedDiscoveryService", object())


ExecutionOverride = Callable[
    [HarnessRunRecord, HarnessExecutionServices],
    Awaitable[HarnessExecutionResult],
]

_APP_BUILD_LOCK = Lock()


@pytest.fixture
def short_sync_wait(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Trim sync wait budgets for tests that intentionally leave runs active."""
    monkeypatch.setenv("ARTANA_EVIDENCE_API_SYNC_WAIT_TIMEOUT_SECONDS", "0.05")
    monkeypatch.setenv("ARTANA_EVIDENCE_API_SYNC_WAIT_POLL_SECONDS", "0.01")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


class _RestartableExpiringKernelRuntime(FakeKernelRuntime):
    """Fake runtime that preserves state across restarts and expires leases."""

    def __init__(
        self,
        *,
        now_seconds: int = 0,
        runs: set[tuple[str, str]] | None = None,
        summaries: dict[tuple[str, str, str], FakeSummary] | None = None,
        events: dict[tuple[str, str], list[FakeEvent]] | None = None,
        leases: dict[tuple[str, str], str] | None = None,
        lease_expirations: dict[tuple[str, str], int] | None = None,
    ) -> None:
        super().__init__()
        self._now_seconds = now_seconds
        self._lease_expirations = (
            dict(lease_expirations) if lease_expirations is not None else {}
        )
        if runs is not None:
            self._runs = set(runs)
        if summaries is not None:
            self._summaries = dict(summaries)
        if events is not None:
            self._events = {key: list(value) for key, value in events.items()}
        if leases is not None:
            self._leases = dict(leases)

    def restart(self) -> _RestartableExpiringKernelRuntime:
        return _RestartableExpiringKernelRuntime(
            now_seconds=self._now_seconds,
            runs=self._runs,
            summaries=self._summaries,
            events=self._events,
            leases=self._leases,
            lease_expirations=self._lease_expirations,
        )

    def advance(self, *, seconds: int) -> None:
        self._now_seconds += seconds

    def acquire_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        key = (tenant_id, run_id)
        existing_expiration = self._lease_expirations.get(key)
        if existing_expiration is not None and existing_expiration <= self._now_seconds:
            self._leases.pop(key, None)
            del self._lease_expirations[key]
        existing = self._leases.get(key)
        if existing is not None and existing != worker_id:
            return False
        self._leases[key] = worker_id
        self._lease_expirations[key] = self._now_seconds + ttl_seconds
        return True

    def release_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
    ) -> bool:
        key = (tenant_id, run_id)
        released = super().release_run_lease(
            run_id=run_id,
            tenant_id=tenant_id,
            worker_id=worker_id,
        )
        if released:
            self._lease_expirations.pop(key, None)
        return released


class _FailingGraphSearchRunner:
    async def run(
        self,
        request: HarnessGraphSearchRequest,
    ) -> HarnessGraphSearchResult:
        del request
        raise RuntimeError("Synthetic integration graph-search failure.")


class _FailingGraphConnectionRunner:
    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> HarnessGraphConnectionResult:
        del request
        raise RuntimeError("Synthetic integration graph-connection failure.")


class _FailingInitialResearchOnboardingRunner:
    async def run_initial(
        self,
        request: HarnessResearchOnboardingInitialRequest,
    ) -> HarnessResearchOnboardingResult:
        del request
        raise OnboardingAgentExecutionError(
            "Synthetic integration onboarding initial failure.",
        )

    async def run_continuation(
        self,
        request: HarnessResearchOnboardingContinuationRequest,
    ) -> HarnessResearchOnboardingResult:
        del request
        raise AssertionError("Continuation should not be invoked in this test.")


class _FailingContinuationResearchOnboardingRunner:
    async def run_initial(
        self,
        request: HarnessResearchOnboardingInitialRequest,
    ) -> HarnessResearchOnboardingResult:
        del request
        raise AssertionError("Initial onboarding should not be invoked in this test.")

    async def run_continuation(
        self,
        request: HarnessResearchOnboardingContinuationRequest,
    ) -> HarnessResearchOnboardingResult:
        del request
        raise OnboardingAgentExecutionError(
            "Synthetic integration onboarding continuation failure.",
        )


class _SuccessfulGraphSearchRunner:
    async def run(
        self,
        request: HarnessGraphSearchRequest,
    ) -> HarnessGraphSearchResult:
        entity_id = str(uuid4())
        assessment = build_graph_search_assessment_from_confidence(
            0.88,
            confidence_rationale="Synthetic integration graph-search result.",
            grounding_level=GraphSearchGroundingLevel.AGGREGATED,
        )
        contract = GraphSearchContract(
            decision="generated",
            assessment=assessment,
            rationale="Synthetic integration graph-search result.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"entity:{entity_id}",
                    excerpt="Synthetic integration graph-search evidence.",
                    relevance=0.9,
                ),
            ],
            research_space_id=request.research_space_id,
            original_query=request.question,
            interpreted_intent=request.question,
            query_plan_summary="Synthetic integration graph-search plan.",
            total_results=1,
            results=[
                GraphSearchResultEntry(
                    entity_id=entity_id,
                    entity_type="gene",
                    display_label="MED13",
                    relevance_score=0.88,
                    assessment=assessment,
                    matching_observation_ids=["obs-integration-1"],
                    matching_relation_ids=["rel-integration-1"],
                    evidence_chain=[],
                    explanation="Synthetic integration graph-search explanation.",
                    support_summary="Synthetic integration graph-search support.",
                ),
            ],
            executed_path="agent",
            warnings=[],
            agent_run_id="integration-graph-search",
        )
        return HarnessGraphSearchResult(
            contract=contract,
            agent_run_id=contract.agent_run_id,
            active_skill_names=("graph_harness.graph_grounding",),
        )


class _SuccessfulGraphConnectionRunner:
    async def run(
        self,
        request: HarnessGraphConnectionRequest,
    ) -> HarnessGraphConnectionResult:
        contract = GraphConnectionContract(
            decision="generated",
            confidence_score=0.81,
            rationale="Synthetic integration graph-connection result.",
            evidence=[
                EvidenceItem(
                    source_type="db",
                    locator=f"seed:{request.seed_entity_id}",
                    excerpt="Synthetic integration graph-connection evidence.",
                    relevance=0.82,
                ),
            ],
            source_type=request.source_type or "pubmed",
            research_space_id=request.research_space_id,
            seed_entity_id=request.seed_entity_id,
            proposed_relations=[
                {
                    "source_id": request.seed_entity_id,
                    "relation_type": "SUGGESTS",
                    "target_id": str(uuid4()),
                    "assessment": build_fact_assessment_from_confidence(
                        confidence=0.81,
                        confidence_rationale=(
                            "Synthetic integration graph-connection hypothesis."
                        ),
                        grounding_level=GroundingLevel.GRAPH_INFERENCE,
                        mapping_status=MappingStatus.NOT_APPLICABLE,
                        speculation_level=SpeculationLevel.NOT_APPLICABLE,
                    ).model_dump(mode="json"),
                    "evidence_summary": (
                        "Synthetic integration graph-connection hypothesis."
                    ),
                    "supporting_document_count": 1,
                    "reasoning": "Synthetic integration graph-connection reasoning.",
                },
            ],
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id="integration-graph-connection",
        )
        return HarnessGraphConnectionResult(
            contract=contract,
            agent_run_id=contract.agent_run_id,
            active_skill_names=("graph_harness.relation_discovery",),
        )


class _SuccessfulResearchOnboardingRunner:
    async def run_initial(
        self,
        request: HarnessResearchOnboardingInitialRequest,
    ) -> HarnessResearchOnboardingResult:
        prompt = f"What evidence type should {request.research_title} prioritize first?"
        contract = OnboardingAssistantContract(
            message_type="clarification_request",
            title=f"{request.research_title}: synthetic onboarding intake",
            summary="Synthetic integration onboarding response.",
            sections=[
                OnboardingSection(
                    heading="Objective",
                    body=request.primary_objective or "No explicit objective yet.",
                ),
            ],
            questions=[OnboardingQuestion(id="q-1", prompt=prompt)],
            suggested_actions=[
                OnboardingSuggestedAction(
                    id="answer-question",
                    label="Answer question",
                    action_type="reply",
                ),
            ],
            artifacts=[],
            state_patch=OnboardingStatePatch(
                thread_status="your_turn",
                onboarding_status="awaiting_researcher_reply",
                pending_question_count=1,
                objective=request.primary_objective or None,
                explored_questions=[],
                pending_questions=[prompt],
                current_hypotheses=[],
            ),
            confidence_score=0.83,
            rationale="Synthetic integration onboarding rationale.",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator="research_onboarding_intake",
                    excerpt=request.research_title,
                    relevance=0.9,
                ),
            ],
            agent_run_id="integration-onboarding",
        )
        return HarnessResearchOnboardingResult(
            contract=contract,
            agent_run_id="integration-onboarding",
            active_skill_names=(),
        )

    async def run_continuation(
        self,
        request: HarnessResearchOnboardingContinuationRequest,
    ) -> HarnessResearchOnboardingResult:
        del request
        raise AssertionError("Continuation is not used in the mixed soak test.")


async def _complete_run(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    if run.harness_id == "graph-search":
        return await execute_graph_search_run(
            space_id=UUID(run.space_id),
            run=run,
            question=str(run.input_payload.get("question", "")),
            model_id=(
                run.input_payload.get("model_id")
                if isinstance(run.input_payload.get("model_id"), str)
                else None
            ),
            max_depth=int(run.input_payload.get("max_depth", 2)),
            top_k=int(run.input_payload.get("top_k", 25)),
            curation_statuses=(
                run.input_payload.get("curation_statuses")
                if isinstance(run.input_payload.get("curation_statuses"), list)
                else None
            ),
            include_evidence_chains=bool(
                run.input_payload.get("include_evidence_chains", True),
            ),
            artifact_store=services.artifact_store,
            run_registry=services.run_registry,
            runtime=services.runtime,
            graph_search_runner=services.graph_search_runner,
        )
    if run.harness_id == "graph-connections":
        return await execute_graph_connection_run(
            space_id=UUID(run.space_id),
            run=run,
            seed_entity_ids=[
                item
                for item in run.input_payload.get("seed_entity_ids", [])
                if isinstance(item, str)
            ],
            source_type=(
                run.input_payload.get("source_type")
                if isinstance(run.input_payload.get("source_type"), str)
                else None
            ),
            source_id=(
                run.input_payload.get("source_id")
                if isinstance(run.input_payload.get("source_id"), str)
                else None
            ),
            model_id=(
                run.input_payload.get("model_id")
                if isinstance(run.input_payload.get("model_id"), str)
                else None
            ),
            relation_types=(
                run.input_payload.get("relation_types")
                if isinstance(run.input_payload.get("relation_types"), list)
                else None
            ),
            max_depth=int(run.input_payload.get("max_depth", 2)),
            shadow_mode=bool(run.input_payload.get("shadow_mode", True)),
            pipeline_run_id=(
                run.input_payload.get("pipeline_run_id")
                if isinstance(run.input_payload.get("pipeline_run_id"), str)
                else None
            ),
            artifact_store=services.artifact_store,
            run_registry=services.run_registry,
            runtime=services.runtime,
            graph_connection_runner=services.graph_connection_runner,
        )
    if run.harness_id == "hypotheses":
        return await execute_hypothesis_run(
            space_id=UUID(run.space_id),
            run=run,
            seed_entity_ids=[
                item
                for item in run.input_payload.get("seed_entity_ids", [])
                if isinstance(item, str)
            ],
            source_type=str(run.input_payload.get("source_type", "pubmed")),
            relation_types=(
                run.input_payload.get("relation_types")
                if isinstance(run.input_payload.get("relation_types"), list)
                else None
            ),
            max_depth=int(run.input_payload.get("max_depth", 2)),
            max_hypotheses=int(run.input_payload.get("max_hypotheses", 20)),
            model_id=(
                run.input_payload.get("model_id")
                if isinstance(run.input_payload.get("model_id"), str)
                else None
            ),
            artifact_store=services.artifact_store,
            run_registry=services.run_registry,
            proposal_store=services.proposal_store,
            runtime=services.runtime,
            graph_connection_runner=services.graph_connection_runner,
        )
    if run.harness_id == "research-onboarding":
        payload = run.input_payload
        if isinstance(payload.get("reply_text"), str):
            return await asyncio.to_thread(
                execute_research_onboarding_continuation,
                space_id=UUID(run.space_id),
                research_title="",
                request=ResearchOnboardingContinuationRequest(
                    thread_id=str(payload.get("thread_id", "")),
                    message_id=str(payload.get("message_id", "")),
                    intent=str(payload.get("intent", "")),
                    mode=str(payload.get("mode", "")),
                    reply_text=str(payload.get("reply_text", "")),
                    reply_html=str(payload.get("reply_html", "")),
                    attachments=(
                        list(payload.get("attachments"))
                        if isinstance(payload.get("attachments"), list)
                        else []
                    ),
                    contextual_anchor=(
                        payload.get("contextual_anchor")
                        if isinstance(payload.get("contextual_anchor"), dict)
                        else None
                    ),
                ),
                run_registry=services.run_registry,
                artifact_store=services.artifact_store,
                graph_api_gateway=services.graph_api_gateway_factory(),
                research_state_store=services.research_state_store,
                onboarding_runner=services.research_onboarding_runner,
                existing_run=run,
            )
        return await asyncio.to_thread(
            execute_research_onboarding_run,
            space_id=UUID(run.space_id),
            research_title=str(payload.get("research_title", "")),
            primary_objective=str(payload.get("primary_objective", "")),
            space_description=str(payload.get("space_description", "")),
            run_registry=services.run_registry,
            artifact_store=services.artifact_store,
            graph_api_gateway=services.graph_api_gateway_factory(),
            research_state_store=services.research_state_store,
            onboarding_runner=services.research_onboarding_runner,
            existing_run=run,
        )
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="running",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="execute",
        message="Worker executed the queued run.",
        progress_percent=0.6,
        completed_steps=1,
        total_steps=2,
        metadata={"executor": "integration-test"},
    )
    services.run_registry.record_event(
        space_id=run.space_id,
        run_id=run.id,
        event_type="run.executed",
        message="Integration worker execution completed.",
        payload={"executor": "integration-test"},
        progress_percent=0.6,
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="integration_result",
        media_type="application/json",
        content={"run_id": run.id, "harness_id": run.harness_id},
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={
            "status": "completed",
            "integration_result_key": "integration_result",
        },
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
        message="Run completed through the Artana-backed worker path.",
        progress_percent=1.0,
        completed_steps=2,
        total_steps=2,
        clear_resume_point=True,
        metadata={"executor": "integration-test", "result_key": "integration_result"},
    )
    return services.run_registry.get_run(space_id=run.space_id, run_id=run.id) or run


async def _leave_run_running(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    if run.harness_id != "continuous-learning":
        return await _complete_run(run, services)
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="running",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="execute",
        message="Run is intentionally left active for idempotency coverage.",
        progress_percent=0.5,
        completed_steps=1,
        total_steps=2,
        metadata={"executor": "integration-test", "mode": "leave_running"},
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={"status": "running"},
    )
    updated_run = services.run_registry.get_run(space_id=run.space_id, run_id=run.id)
    if updated_run is None:
        updated_run = run
    run_budget = resolve_continuous_learning_run_budget(
        budget_from_json(updated_run.input_payload.get("run_budget")),
    )
    return ContinuousLearningExecutionResult(
        run=updated_run,
        candidates=[],
        proposal_records=[],
        delta_report={"status": "running"},
        next_questions=[],
        errors=[],
        run_budget=run_budget,
        budget_status=HarnessRunBudgetStatus(
            status="active",
            limits=run_budget,
            usage=HarnessRunBudgetUsage(runtime_seconds=0.0),
            message="Run intentionally left active for idempotency coverage.",
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


async def _bootstrap_execution_override(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    if run.harness_id != "research-bootstrap":
        return await _complete_run(run, services)
    objective = run.input_payload.get("objective")
    objective_text = objective if isinstance(objective, str) else "Synthetic objective"
    seed_entity_id = str(uuid4())
    target_entity_id = str(uuid4())
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="running",
    )
    graph_snapshot = services.graph_snapshot_store.create_snapshot(
        space_id=run.space_id,
        source_run_id=run.id,
        claim_ids=["claim-bootstrap-1"],
        relation_ids=["relation-bootstrap-1"],
        graph_document_hash="bootstrap-hash",
        summary={
            "objective": objective_text,
            "claim_count": 1,
            "relation_count": 1,
        },
        metadata={"source": "integration-bootstrap"},
    )
    research_state = services.research_state_store.upsert_state(
        space_id=run.space_id,
        objective=objective_text,
        pending_questions=["What should be validated next?"],
        current_hypotheses=["MED13 regulates transcription."],
        last_graph_snapshot_id=graph_snapshot.id,
        metadata={"source": "integration-bootstrap"},
    )
    proposal_records = services.proposal_store.create_proposals(
        space_id=run.space_id,
        run_id=run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="research_bootstrap",
                source_key=f"{seed_entity_id}:REGULATES:{target_entity_id}",
                title="MED13 regulates transcription",
                summary="Synthetic bootstrap proposal.",
                confidence=0.82,
                ranking_score=0.91,
                reasoning_path={"reasoning": "Synthetic bootstrap reasoning."},
                evidence_bundle=[{"source_type": "db", "locator": seed_entity_id}],
                payload=_candidate_claim_payload(
                    source_entity_id=seed_entity_id,
                    target_entity_id=target_entity_id,
                ),
                metadata={"agent_run_id": "integration-bootstrap"},
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
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=run.id,
        status="completed",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=run.id,
        phase="completed",
        message="Research bootstrap completed.",
        progress_percent=1.0,
        completed_steps=4,
        total_steps=4,
        clear_resume_point=True,
        metadata={"proposal_count": len(proposal_records)},
    )
    completed_run = services.run_registry.get_run(space_id=run.space_id, run_id=run.id)
    if completed_run is None:
        msg = "Failed to reload completed research-bootstrap run."
        raise RuntimeError(msg)
    result = ResearchBootstrapExecutionResult(
        run=completed_run,
        graph_snapshot=graph_snapshot,
        research_state=research_state,
        research_brief={"objective": objective_text},
        graph_summary={"claim_count": 1, "relation_count": 1},
        source_inventory={"source_type": "pubmed", "source_count": 1},
        proposal_records=proposal_records,
        pending_questions=["What should be validated next?"],
        errors=[],
    )
    store_primary_result_artifact(
        artifact_store=services.artifact_store,
        space_id=run.space_id,
        run_id=run.id,
        artifact_key="research_bootstrap_response",
        content=build_research_bootstrap_run_response(result).model_dump(mode="json"),
        status_value="completed",
        result_keys=[
            "graph_context_snapshot",
            "research_brief",
            "graph_summary",
            "source_inventory",
            "candidate_claim_pack",
        ],
        workspace_patch={
            "graph_snapshot_id": graph_snapshot.id,
            "proposal_count": len(proposal_records),
        },
    )
    return result


async def _supervisor_execution_override(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    if run.harness_id != "supervisor":
        return await _complete_run(run, services)
    workspace = services.artifact_store.get_workspace(
        space_id=run.space_id,
        run_id=run.id,
    )
    workspace_snapshot = workspace.snapshot if workspace is not None else {}
    curation_run_id = workspace_snapshot.get("curation_run_id")
    if not isinstance(curation_run_id, str) or curation_run_id == "":
        bootstrap_parent_run = HarnessRunRecord(
            id=run.id,
            space_id=run.space_id,
            harness_id="research-bootstrap",
            title="Supervisor Bootstrap",
            status="queued",
            input_payload={"objective": run.input_payload.get("objective")},
            graph_service_status=run.graph_service_status,
            graph_service_version=run.graph_service_version,
            created_at=run.created_at,
            updated_at=run.updated_at,
        )
        bootstrap_result = cast(
            "ResearchBootstrapExecutionResult",
            await _bootstrap_execution_override(bootstrap_parent_run, services),
        )
        curation_run = services.run_registry.create_run(
            space_id=run.space_id,
            harness_id="claim-curation",
            title="Supervisor Curation",
            input_payload={"workflow": "claim_curation", "proposal_ids": []},
            graph_service_status="ok",
            graph_service_version="test-graph",
        )
        services.artifact_store.seed_for_run(run=curation_run)
        selected_proposal = bootstrap_result.proposal_records[0]
        approval_key = f"promote:{selected_proposal.id}"
        review_plan = {
            "proposals": [
                {
                    "proposal_id": selected_proposal.id,
                    "title": selected_proposal.title,
                    "summary": selected_proposal.summary,
                    "source_key": selected_proposal.source_key,
                    "confidence": selected_proposal.confidence,
                    "ranking_score": selected_proposal.ranking_score,
                    "approval_key": approval_key,
                    "duplicate_selected_count": 0,
                    "existing_promoted_proposal_ids": [],
                    "graph_duplicate_claim_ids": [],
                    "conflicting_relation_ids": [],
                    "invariant_issues": [],
                    "blocker_reasons": [],
                    "eligible_for_approval": True,
                },
            ],
        }
        curation_packet = {"proposal_ids": [selected_proposal.id]}
        approval_intent = {"summary": "Review supervisor curation."}
        services.approval_store.upsert_intent(
            space_id=run.space_id,
            run_id=curation_run.id,
            summary="Review supervisor curation.",
            proposed_actions=(
                HarnessApprovalAction(
                    approval_key=approval_key,
                    title="Promote bootstrap proposal",
                    risk_level="high",
                    target_type="proposal",
                    target_id=selected_proposal.id,
                    requires_approval=True,
                    metadata={"proposal_id": selected_proposal.id},
                ),
            ),
            metadata={"workflow": "claim_curation"},
        )
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=curation_run.id,
            artifact_key="curation_packet",
            media_type="application/json",
            content=curation_packet,
        )
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=curation_run.id,
            artifact_key="review_plan",
            media_type="application/json",
            content=review_plan,
        )
        services.artifact_store.put_artifact(
            space_id=run.space_id,
            run_id=curation_run.id,
            artifact_key="approval_intent",
            media_type="application/json",
            content=approval_intent,
        )
        services.artifact_store.patch_workspace(
            space_id=run.space_id,
            run_id=curation_run.id,
            patch={"status": "paused", "pending_approvals": 1},
        )
        services.run_registry.set_run_status(
            space_id=run.space_id,
            run_id=curation_run.id,
            status="paused",
        )
        services.run_registry.set_progress(
            space_id=run.space_id,
            run_id=curation_run.id,
            phase="approval",
            message="Child curation paused pending approval.",
            progress_percent=0.5,
            completed_steps=1,
            total_steps=2,
            resume_point="approval_gate",
            metadata={"pending_approvals": 1},
        )
        curation_execution = ClaimCurationRunExecution(
            run=services.run_registry.get_run(
                space_id=run.space_id,
                run_id=curation_run.id,
            )
            or curation_run,
            curation_packet=curation_packet,
            review_plan=review_plan,
            approval_intent=approval_intent,
            proposal_count=1,
            blocked_proposal_count=0,
            pending_approval_count=1,
        )
        store_primary_result_artifact(
            artifact_store=services.artifact_store,
            space_id=run.space_id,
            run_id=curation_run.id,
            artifact_key="claim_curation_response",
            content=build_claim_curation_run_response(curation_execution).model_dump(
                mode="json",
            ),
            status_value="paused",
            result_keys=[
                "curation_packet",
                "review_plan",
                "approval_intent",
            ],
            workspace_patch={"pending_approvals": 1},
        )
        services.artifact_store.patch_workspace(
            space_id=run.space_id,
            run_id=run.id,
            patch={
                "status": "paused",
                "curation_run_id": curation_run.id,
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
            message="Supervisor paused pending child approval.",
            progress_percent=0.75,
            completed_steps=2,
            total_steps=3,
            resume_point="supervisor_child_approval_gate",
            metadata={"curation_run_id": curation_run.id},
        )
        paused_parent = services.run_registry.get_run(
            space_id=run.space_id,
            run_id=run.id,
        )
        if paused_parent is None:
            msg = "Failed to reload paused supervisor run."
            raise RuntimeError(msg)
        result = SupervisorExecutionResult(
            run=paused_parent,
            bootstrap=bootstrap_result,
            chat_session=None,
            chat=None,
            curation=curation_execution,
            briefing_question=None,
            curation_source="bootstrap",
            chat_graph_write=None,
            selected_curation_proposal_ids=(selected_proposal.id,),
            steps=(
                {
                    "step": "bootstrap",
                    "status": "completed",
                    "harness_id": "research-bootstrap",
                    "run_id": bootstrap_result.run.id,
                    "detail": "Bootstrap finished.",
                },
                {
                    "step": "curation",
                    "status": "paused",
                    "harness_id": "claim-curation",
                    "run_id": curation_run.id,
                    "detail": "Awaiting approval.",
                },
            ),
        )
        store_primary_result_artifact(
            artifact_store=services.artifact_store,
            space_id=run.space_id,
            run_id=run.id,
            artifact_key="supervisor_run_response",
            content=build_supervisor_run_response(result).model_dump(mode="json"),
            status_value="paused",
            workspace_patch={
                "curation_run_id": curation_run.id,
                "selected_curation_proposal_ids": [selected_proposal.id],
            },
        )
        return result
    approvals = services.approval_store.list_approvals(
        space_id=run.space_id,
        run_id=curation_run_id,
    )
    pending_approval_keys = [
        approval.approval_key for approval in approvals if approval.status == "pending"
    ]
    if pending_approval_keys:
        msg = f"Supervisor child approvals still pending: {', '.join(pending_approval_keys)}"
        raise RuntimeError(msg)
    services.run_registry.set_run_status(
        space_id=run.space_id,
        run_id=curation_run_id,
        status="completed",
    )
    services.run_registry.set_progress(
        space_id=run.space_id,
        run_id=curation_run_id,
        phase="completed",
        message="Child curation completed.",
        progress_percent=1.0,
        completed_steps=2,
        total_steps=2,
        clear_resume_point=True,
        metadata={"pending_approvals": 0},
    )
    services.artifact_store.put_artifact(
        space_id=run.space_id,
        run_id=curation_run_id,
        artifact_key="curation_summary",
        media_type="application/json",
        content={"applied": True},
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=curation_run_id,
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
        message="Supervisor completed after child approval resolution.",
        progress_percent=1.0,
        completed_steps=3,
        total_steps=3,
        clear_resume_point=True,
        metadata={"curation_run_id": curation_run_id},
    )
    services.artifact_store.patch_workspace(
        space_id=run.space_id,
        run_id=run.id,
        patch={"status": "completed"},
    )
    return services.run_registry.get_run(space_id=run.space_id, run_id=run.id) or run


def _build_services(
    *,
    session: Session,
    runtime: FakeKernelRuntime,
    graph_connection_runner: object | None = None,
    graph_search_runner: HarnessGraphSearchRunner | None = None,
    research_onboarding_runner: object | None = None,
    execution_override: ExecutionOverride = _complete_run,
) -> HarnessExecutionServices:
    resolved_graph_connection_runner = (
        graph_connection_runner
        if graph_connection_runner is not None
        else HarnessGraphConnectionRunner()
    )
    resolved_graph_search_runner = (
        graph_search_runner
        if graph_search_runner is not None
        else HarnessGraphSearchRunner()
    )
    resolved_research_onboarding_runner = (
        research_onboarding_runner
        if research_onboarding_runner is not None
        else _SuccessfulResearchOnboardingRunner()
    )
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
        graph_connection_runner=cast(
            "HarnessGraphConnectionRunner",
            resolved_graph_connection_runner,
        ),
        graph_search_runner=resolved_graph_search_runner,
        graph_chat_runner=HarnessGraphChatRunner(),
        research_onboarding_runner=cast(
            "HarnessResearchOnboardingRunner",
            resolved_research_onboarding_runner,
        ),
        graph_api_gateway_factory=FakeGraphApiGateway,
        pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
        execution_override=execution_override,
    )


def _build_client(
    *,
    session: Session,
    runtime: FakeKernelRuntime,
    services: HarnessExecutionServices | None = None,
    execution_override: ExecutionOverride = _complete_run,
    graph_api_gateway_override: Callable[[], object] | type[FakeGraphApiGateway] = (
        FakeGraphApiGateway
    ),
    graph_connection_runner_override: object | None = None,
    graph_search_runner_override: object | None = None,
    research_onboarding_runner_override: object | None = None,
) -> TestClient:
    resolved_graph_connection_runner = (
        graph_connection_runner_override()
        if callable(graph_connection_runner_override)
        else (
            graph_connection_runner_override
            if graph_connection_runner_override is not None
            else None
        )
    )
    resolved_graph_search_runner = (
        graph_search_runner_override()
        if callable(graph_search_runner_override)
        else (
            graph_search_runner_override
            if graph_search_runner_override is not None
            else None
        )
    )
    resolved_research_onboarding_runner = (
        research_onboarding_runner_override()
        if callable(research_onboarding_runner_override)
        else (
            research_onboarding_runner_override
            if research_onboarding_runner_override is not None
            else None
        )
    )
    resolved_services = services or _build_services(
        session=session,
        runtime=runtime,
        graph_connection_runner=resolved_graph_connection_runner,
        graph_search_runner=cast(
            "HarnessGraphSearchRunner | None",
            resolved_graph_search_runner,
        ),
        research_onboarding_runner=resolved_research_onboarding_runner,
        execution_override=execution_override,
    )
    if services is not None and resolved_graph_connection_runner is not None:
        resolved_services = replace(
            resolved_services,
            graph_connection_runner=cast(
                "HarnessGraphConnectionRunner",
                resolved_graph_connection_runner,
            ),
        )
    if services is not None and resolved_graph_search_runner is not None:
        resolved_services = replace(
            resolved_services,
            graph_search_runner=cast(
                "HarnessGraphSearchRunner",
                resolved_graph_search_runner,
            ),
        )
    if services is not None and resolved_research_onboarding_runner is not None:
        resolved_services = replace(
            resolved_services,
            research_onboarding_runner=cast(
                "HarnessResearchOnboardingRunner",
                resolved_research_onboarding_runner,
            ),
        )
    # These tests exercise concurrent requests, not concurrent FastAPI app
    # construction. Building apps in parallel can trigger FastAPI/Pydantic
    # schema-generation warnings unrelated to the runtime behavior under test.
    with _APP_BUILD_LOCK:
        app = create_app()
    app.dependency_overrides[get_run_registry] = lambda: resolved_services.run_registry
    app.dependency_overrides[get_artifact_store] = (
        lambda: resolved_services.artifact_store
    )
    app.dependency_overrides[get_approval_store] = (
        lambda: resolved_services.approval_store
    )
    app.dependency_overrides[get_chat_session_store] = lambda: (
        resolved_services.chat_session_store
    )
    app.dependency_overrides[get_document_store] = (
        lambda: resolved_services.document_store
    )
    app.dependency_overrides[get_graph_api_gateway] = graph_api_gateway_override
    if graph_connection_runner_override is not None:
        app.dependency_overrides[get_graph_connection_runner] = (
            graph_connection_runner_override
        )
    if graph_search_runner_override is not None:
        app.dependency_overrides[get_graph_search_runner] = graph_search_runner_override
    app.dependency_overrides[get_graph_snapshot_store] = (
        lambda: resolved_services.graph_snapshot_store
    )
    app.dependency_overrides[get_harness_execution_services] = lambda: resolved_services
    app.dependency_overrides[get_proposal_store] = (
        lambda: resolved_services.proposal_store
    )
    if research_onboarding_runner_override is not None:
        app.dependency_overrides[get_research_onboarding_runner] = (
            research_onboarding_runner_override
        )
    app.dependency_overrides[get_research_space_store] = (
        lambda: PermissiveHarnessResearchSpaceStore()
    )
    app.dependency_overrides[get_research_state_store] = (
        lambda: resolved_services.research_state_store
    )
    app.dependency_overrides[get_schedule_store] = (
        lambda: resolved_services.schedule_store
    )
    return TestClient(app)


def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
        class_=Session,
    )


@contextmanager
def _verifier_services(
    *,
    runtime: FakeKernelRuntime,
) -> Iterator[HarnessExecutionServices]:
    session = _session_factory()()
    try:
        yield _build_services(session=session, runtime=runtime)
    finally:
        session.rollback()
        session.close()


def _freeze_schedule_claim_clock(
    monkeypatch: pytest.MonkeyPatch,
    *,
    frozen_now: datetime,
) -> None:
    normalized_now = (
        frozen_now.replace(tzinfo=UTC)
        if frozen_now.tzinfo is None
        else frozen_now.astimezone(UTC)
    ).replace(tzinfo=None)

    def _frozen_normalized_utc_datetime(value: datetime | None = None) -> datetime:
        if value is None:
            return normalized_now
        normalized_value = (
            value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
        )
        return normalized_value.replace(tzinfo=None)

    monkeypatch.setattr(
        sqlalchemy_stores_module,
        "_normalized_utc_datetime",
        _frozen_normalized_utc_datetime,
    )


@pytest.mark.integration
def test_run_api_uses_artana_backed_lifecycle_for_create_list_progress_events_and_resume(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    client = _build_client(session=db_session, runtime=runtime)
    space_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
        json={
            "harness_id": "graph-chat",
            "title": "Integration Chat Run",
            "input_payload": {
                "session_id": str(uuid4()),
                "question": "What is known about MED13?",
            },
        },
    )
    assert create_response.status_code == 201
    run_payload = create_response.json()
    run_id = run_payload["id"]

    list_response = client.get(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
    )
    assert list_response.status_code == 200
    assert list_response.json()["total"] == 1

    detail_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}",
        headers=auth_headers(),
    )
    assert detail_response.status_code == 200
    assert detail_response.json()["status"] == "queued"

    progress_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/progress",
        headers=auth_headers(),
    )
    assert progress_response.status_code == 200
    assert progress_response.json()["phase"] == "queued"

    events_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/events",
        headers=auth_headers(),
    )
    assert events_response.status_code == 200
    assert [event["event_type"] for event in events_response.json()["events"]] == [
        "run.created",
    ]

    services.run_registry.set_run_status(
        space_id=space_id,
        run_id=run_id,
        status="paused",
    )
    services.run_registry.set_progress(
        space_id=space_id,
        run_id=run_id,
        phase="approval",
        message="Paused pending resume.",
        progress_percent=0.4,
        completed_steps=1,
        total_steps=2,
        resume_point="approval_gate",
        metadata={"paused_by": "integration-test"},
    )

    resume_response = client.post(
        f"/v1/spaces/{space_id}/runs/{run_id}/resume",
        headers=auth_headers(),
        json={"reason": "integration resume", "metadata": {"source": "test"}},
    )
    assert resume_response.status_code == 200
    assert resume_response.json()["run"]["status"] == "completed"
    assert resume_response.json()["progress"]["progress_percent"] == 1.0

    final_events = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/events",
        headers=auth_headers(),
    )
    assert final_events.status_code == 200
    assert [event["event_type"] for event in final_events.json()["events"]] == [
        "run.created",
        "run.status_changed",
        "run.progress",
        "run.status_changed",
        "run.progress",
        "run.resumed",
        "run.status_changed",
        "run.progress",
        "run.executed",
        "run.status_changed",
        "run.progress",
    ]


@pytest.mark.integration
def test_transparency_endpoints_return_capabilities_and_policy_history(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    client = _build_client(session=db_session, runtime=runtime, services=services)
    space_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
        json={
            "harness_id": "graph-chat",
            "title": "Transparency chat run",
            "input_payload": {
                "session_id": str(uuid4()),
                "question": "What is known about MED13?",
            },
        },
    )
    assert create_response.status_code == 201
    run_id = create_response.json()["id"]

    runtime.step_tool(
        run_id=run_id,
        tenant_id=space_id,
        tool_name="run_pubmed_search",
        arguments=RunPubMedSearchToolArgs(
            search_term="MED13 congenital heart disease",
            max_results=5,
        ),
        step_key="integration.pubmed_search",
    )
    append_manual_review_decision(
        space_id=UUID(space_id),
        run_id=run_id,
        tool_name="create_graph_claim",
        decision="promote",
        reason="Approved after integration review",
        artifact_key="graph_write_candidate_suggestions",
        metadata={"proposal_id": "proposal-integration-1"},
        artifact_store=services.artifact_store,
        run_registry=services.run_registry,
        runtime=runtime,
    )
    append_skill_activity(
        space_id=UUID(space_id),
        run_id=run_id,
        skill_names=(
            "graph_harness.graph_grounding",
            "graph_harness.literature_refresh",
        ),
        source_run_id="integration:graph-chat-search",
        source_kind="graph_chat",
        artifact_store=services.artifact_store,
        run_registry=services.run_registry,
        runtime=runtime,
    )

    capabilities_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/capabilities",
        headers=auth_headers(role="viewer"),
    )
    assert capabilities_response.status_code == 200
    capabilities_payload = capabilities_response.json()
    assert capabilities_payload["artifact_key"] == "run_capabilities"
    assert capabilities_payload["preloaded_skill_names"] == [
        "graph_harness.graph_grounding",
        "graph_harness.graph_write_review",
    ]
    assert capabilities_payload["active_skill_names"] == [
        "graph_harness.graph_grounding",
        "graph_harness.literature_refresh",
    ]
    visible_tool_names = {
        tool["tool_name"] for tool in capabilities_payload["visible_tools"]
    }
    assert "run_pubmed_search" in visible_tool_names

    policy_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/policy-decisions",
        headers=auth_headers(role="viewer"),
    )
    assert policy_response.status_code == 200
    policy_payload = policy_response.json()
    assert policy_payload["summary"]["tool_record_count"] == 1
    assert policy_payload["summary"]["manual_review_count"] == 1
    assert policy_payload["summary"]["skill_record_count"] == 2
    assert {record["decision_source"] for record in policy_payload["records"]} == {
        "tool",
        "manual_review",
        "skill",
    }


@pytest.mark.integration
def test_scheduler_tick_queues_runs_and_worker_executes_them_through_artana_lifecycle(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    schedule_store = cast("HarnessScheduleStore", services.schedule_store)
    run_registry = cast("ArtanaBackedHarnessRunRegistry", services.run_registry)
    artifact_store = cast("ArtanaBackedHarnessArtifactStore", services.artifact_store)
    space_id = str(uuid4())

    schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Nightly refresh",
        cadence="daily",
        created_by=str(uuid4()),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={"owner": "integration-test"},
    )

    scheduler_result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=datetime(2026, 3, 14, 12, 0, tzinfo=UTC),
        ),
    )
    assert scheduler_result.due_schedule_count == 1
    assert len(scheduler_result.triggered_runs) == 1

    queued_runs = [
        run
        for run in list_queued_worker_runs(
            session=db_session,
            run_registry=run_registry,
        )
        if run.space_id == space_id
    ]
    assert len(queued_runs) == 1
    assert queued_runs[0].harness_id == "continuous-learning"

    worker_result = asyncio.run(
        run_worker_tick(
            candidate_runs=queued_runs,
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
        ),
    )
    assert worker_result.executed_run_count == 1
    assert worker_result.completed_run_count == 1
    assert worker_result.failed_run_count == 0

    refreshed_run = run_registry.get_run(
        space_id=space_id,
        run_id=queued_runs[0].id,
    )
    assert refreshed_run is not None
    assert refreshed_run.status == "completed"

    workspace = artifact_store.get_workspace(
        space_id=space_id,
        run_id=queued_runs[0].id,
    )
    assert workspace is not None
    assert workspace.snapshot["status"] == "completed"

    refreshed_schedule = schedule_store.get_schedule(
        space_id=space_id,
        schedule_id=schedule.id,
    )
    assert refreshed_schedule is not None
    assert refreshed_schedule.last_run_id == queued_runs[0].id


@pytest.mark.integration
def test_scheduler_tick_burst_queues_each_due_schedule_once_and_worker_drains_all(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    schedule_store = cast("HarnessScheduleStore", services.schedule_store)
    run_registry = cast("ArtanaBackedHarnessRunRegistry", services.run_registry)
    artifact_store = cast("ArtanaBackedHarnessArtifactStore", services.artifact_store)
    space_id = str(uuid4())
    tick_time = datetime(2026, 3, 14, 12, 0, tzinfo=UTC)

    schedule_ids: list[str] = []
    for index in range(4):
        schedule = schedule_store.create_schedule(
            space_id=space_id,
            harness_id="continuous-learning",
            title=f"Burst refresh {index + 1}",
            cadence="daily",
            created_by=str(uuid4()),
            configuration={
                "seed_entity_ids": [f"entity-{index + 1}"],
                "source_type": "pubmed",
            },
            metadata={"owner": "integration-test", "batch_index": index},
        )
        schedule_store.update_schedule(
            space_id=space_id,
            schedule_id=schedule.id,
            last_run_at=tick_time - timedelta(days=2),
        )
        schedule_ids.append(schedule.id)

    scheduler_result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=tick_time,
        ),
    )

    assert scheduler_result.scanned_schedule_count == 4
    assert scheduler_result.due_schedule_count == 4
    assert scheduler_result.errors == ()
    assert len(scheduler_result.triggered_runs) == 4
    assert {trigger.schedule_id for trigger in scheduler_result.triggered_runs} == set(
        schedule_ids,
    )
    assert len({trigger.run_id for trigger in scheduler_result.triggered_runs}) == 4

    queued_runs = [
        run
        for run in list_queued_worker_runs(
            session=db_session,
            run_registry=run_registry,
        )
        if run.space_id == space_id
    ]
    assert len(queued_runs) == 4

    worker_result = asyncio.run(
        run_worker_tick(
            candidate_runs=queued_runs,
            runtime=cast("GraphHarnessKernelRuntime", runtime),
            services=services,
        ),
    )

    assert worker_result.scanned_run_count == 4
    assert worker_result.executed_run_count == 4
    assert worker_result.completed_run_count == 4
    assert worker_result.failed_run_count == 0
    assert worker_result.skipped_run_count == 0
    assert {result.outcome for result in worker_result.results} == {"completed"}

    triggered_run_ids = {trigger.run_id for trigger in scheduler_result.triggered_runs}
    for schedule_id in schedule_ids:
        refreshed_schedule = schedule_store.get_schedule(
            space_id=space_id,
            schedule_id=schedule_id,
        )
        assert refreshed_schedule is not None
        assert refreshed_schedule.last_run_id in triggered_run_ids


@pytest.mark.integration
def test_scheduler_tick_does_not_double_queue_after_service_restart(
    db_session: Session,
) -> None:
    runtime = _RestartableExpiringKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    schedule_store = cast("HarnessScheduleStore", services.schedule_store)
    run_registry = cast("ArtanaBackedHarnessRunRegistry", services.run_registry)
    artifact_store = cast("ArtanaBackedHarnessArtifactStore", services.artifact_store)
    space_id = str(uuid4())
    first_tick_time = datetime.now(UTC)

    schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Restart-safe refresh",
        cadence="daily",
        created_by=str(uuid4()),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={"owner": "integration-test"},
    )
    schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=schedule.id,
        last_run_at=first_tick_time - timedelta(days=2),
    )

    first_result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=first_tick_time,
        ),
    )
    assert first_result.due_schedule_count == 1
    assert len(first_result.triggered_runs) == 1
    first_run_id = first_result.triggered_runs[0].run_id

    restarted_runtime = runtime.restart()
    restarted_services = _build_services(session=db_session, runtime=restarted_runtime)
    restarted_schedule_store = cast(
        "HarnessScheduleStore",
        restarted_services.schedule_store,
    )
    restarted_run_registry = cast(
        "ArtanaBackedHarnessRunRegistry",
        restarted_services.run_registry,
    )
    restarted_artifact_store = cast(
        "ArtanaBackedHarnessArtifactStore",
        restarted_services.artifact_store,
    )

    second_result = asyncio.run(
        run_scheduler_tick(
            schedule_store=restarted_schedule_store,
            run_registry=restarted_run_registry,
            artifact_store=restarted_artifact_store,
            now=first_tick_time,
        ),
    )

    assert second_result.scanned_schedule_count == 1
    assert second_result.due_schedule_count == 0
    assert second_result.triggered_runs == ()
    assert second_result.errors == ()
    queued_runs = restarted_run_registry.list_runs(space_id=space_id)
    assert [run.id for run in queued_runs] == [first_run_id]
    refreshed_schedule = restarted_schedule_store.get_schedule(
        space_id=space_id,
        schedule_id=schedule.id,
    )
    assert refreshed_schedule is not None
    assert refreshed_schedule.last_run_id == first_run_id


@pytest.mark.integration
def test_scheduler_tick_does_not_queue_a_second_active_schedule_run(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    schedule_store = cast("HarnessScheduleStore", services.schedule_store)
    run_registry = cast("ArtanaBackedHarnessRunRegistry", services.run_registry)
    artifact_store = cast("ArtanaBackedHarnessArtifactStore", services.artifact_store)
    space_id = str(uuid4())
    first_tick_time = datetime.now(UTC)

    schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="No duplicate active schedule runs",
        cadence="daily",
        created_by=str(uuid4()),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={"owner": "integration-test"},
    )
    schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=schedule.id,
        last_run_at=first_tick_time - timedelta(days=2),
    )

    first_result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=first_tick_time,
        ),
    )
    assert len(first_result.triggered_runs) == 1
    first_run_id = first_result.triggered_runs[0].run_id

    second_result = asyncio.run(
        run_scheduler_tick(
            schedule_store=schedule_store,
            run_registry=run_registry,
            artifact_store=artifact_store,
            now=first_tick_time + timedelta(days=1),
        ),
    )

    assert second_result.due_schedule_count == 1
    assert second_result.triggered_runs == ()
    assert second_result.errors == ()
    queued_runs = run_registry.list_runs(space_id=space_id)
    assert [run.id for run in queued_runs] == [first_run_id]


@pytest.mark.integration
def test_worker_tick_recovers_after_restart_once_stale_lease_expires(
    db_session: Session,
) -> None:
    runtime = _RestartableExpiringKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    space_id = str(uuid4())
    run = services.run_registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="Restart recovery run",
        input_payload={"question": "What survives a restart?"},
        graph_service_status="ok",
        graph_service_version="test-graph",
    )
    services.artifact_store.seed_for_run(run=run)

    runtime.acquire_run_lease(
        run_id=run.id,
        tenant_id=space_id,
        worker_id="crashed-worker",
        ttl_seconds=30,
    )

    restarted_runtime = runtime.restart()
    restarted_services = _build_services(session=db_session, runtime=restarted_runtime)
    queued_runs = [
        queued_run
        for queued_run in list_queued_worker_runs(
            session=db_session,
            run_registry=restarted_services.run_registry,
        )
        if queued_run.space_id == space_id
    ]

    skipped_result = asyncio.run(
        run_worker_tick(
            candidate_runs=queued_runs,
            runtime=cast("GraphHarnessKernelRuntime", restarted_runtime),
            services=restarted_services,
            worker_id="worker-1",
            lease_ttl_seconds=30,
        ),
    )
    assert skipped_result.scanned_run_count == 1
    assert skipped_result.leased_run_count == 0
    assert skipped_result.executed_run_count == 0
    assert skipped_result.completed_run_count == 0
    assert skipped_result.failed_run_count == 0
    assert skipped_result.results[0].outcome == "lease_skipped"

    recovered_runtime = restarted_runtime.restart()
    recovered_runtime.advance(seconds=31)
    recovered_services = _build_services(session=db_session, runtime=recovered_runtime)
    recovered_runs = [
        queued_run
        for queued_run in list_queued_worker_runs(
            session=db_session,
            run_registry=recovered_services.run_registry,
        )
        if queued_run.space_id == space_id
    ]

    recovered_result = asyncio.run(
        run_worker_tick(
            candidate_runs=recovered_runs,
            runtime=cast("GraphHarnessKernelRuntime", recovered_runtime),
            services=recovered_services,
            worker_id="worker-1",
            lease_ttl_seconds=30,
        ),
    )
    assert recovered_result.scanned_run_count == 1
    assert recovered_result.leased_run_count == 1
    assert recovered_result.executed_run_count == 1
    assert recovered_result.completed_run_count == 1
    assert recovered_result.failed_run_count == 0
    assert recovered_result.results[0].outcome == "completed"

    refreshed_run = recovered_services.run_registry.get_run(
        space_id=space_id,
        run_id=run.id,
    )
    assert refreshed_run is not None
    assert refreshed_run.status == "completed"
    workspace = recovered_services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["status"] == "completed"


@pytest.mark.integration
def test_competing_worker_ticks_do_not_double_execute_same_queued_run(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    setup_services = _build_services(session=db_session, runtime=runtime)
    space_id = str(uuid4())
    run = setup_services.run_registry.create_run(
        space_id=space_id,
        harness_id="graph-chat",
        title="Competing workers",
        input_payload={"question": "Who owns the lease?"},
        graph_service_status="ok",
        graph_service_version="test-graph",
    )
    setup_services.artifact_store.seed_for_run(run=run)

    execution_started = Event()
    allow_completion = Event()
    execution_lock = Lock()
    execution_count = 0

    async def _blocking_complete_run(
        run: HarnessRunRecord,
        services: HarnessExecutionServices,
    ) -> HarnessExecutionResult:
        nonlocal execution_count
        with execution_lock:
            execution_count += 1
        execution_started.set()
        await asyncio.to_thread(allow_completion.wait)
        return await _complete_run(run, services)

    def _run_worker(worker_id: str):
        session = _session_factory()()
        try:
            services = _build_services(
                session=session,
                runtime=runtime,
                execution_override=_blocking_complete_run,
            )
            candidate_runs = [
                queued_run
                for queued_run in list_queued_worker_runs(
                    session=session,
                    run_registry=services.run_registry,
                )
                if queued_run.space_id == space_id
            ]
            return asyncio.run(
                run_worker_tick(
                    candidate_runs=candidate_runs,
                    runtime=cast("GraphHarnessKernelRuntime", runtime),
                    services=services,
                    worker_id=worker_id,
                ),
            )
        finally:
            session.rollback()
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(_run_worker, "worker-1")
        assert execution_started.wait(timeout=10)
        second_future = executor.submit(_run_worker, "worker-2")
        second_result = second_future.result(timeout=20)
        allow_completion.set()
        first_result = first_future.result(timeout=20)

    assert execution_count == 1
    assert first_result.executed_run_count == 1
    assert first_result.completed_run_count == 1
    assert first_result.failed_run_count == 0
    assert second_result.executed_run_count == 0
    assert second_result.completed_run_count == 0
    assert second_result.failed_run_count == 0
    assert second_result.skipped_run_count == 1
    assert second_result.results[0].outcome == "lease_skipped"

    refreshed_run = setup_services.run_registry.get_run(
        space_id=space_id,
        run_id=run.id,
    )
    assert refreshed_run is not None
    assert refreshed_run.status == "completed"


@pytest.mark.integration
def test_schedule_run_now_rejects_duplicate_active_schedule_runs(
    db_session: Session,
    short_sync_wait: None,
) -> None:
    del short_sync_wait
    runtime = FakeKernelRuntime()
    services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_leave_run_running,
    )
    client = _build_client(session=db_session, runtime=runtime, services=services)
    space_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/schedules",
        headers=auth_headers(),
        json={
            "cadence": "daily",
            "seed_entity_ids": [str(uuid4())],
            "source_type": "pubmed",
        },
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]

    first_run_now_response = client.post(
        f"/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
        headers=auth_headers(),
    )
    assert first_run_now_response.status_code == 202
    first_payload = first_run_now_response.json()
    active_run_id = first_payload["run"]["id"]
    assert first_payload["run"]["status"] == "running"

    second_run_now_response = client.post(
        f"/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
        headers=auth_headers(),
    )
    assert second_run_now_response.status_code == 409
    assert schedule_id in second_run_now_response.json()["detail"]
    assert active_run_id in second_run_now_response.json()["detail"]

    runs_response = client.get(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
    )
    assert runs_response.status_code == 200
    assert runs_response.json()["total"] == 1
    assert runs_response.json()["runs"][0]["id"] == active_run_id


@pytest.mark.integration
def test_schedule_run_now_recovers_after_stale_trigger_claim_expires(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    short_sync_wait: None,
) -> None:
    del short_sync_wait
    runtime = FakeKernelRuntime()
    setup_services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_leave_run_running,
    )
    setup_client = _build_client(
        session=db_session,
        runtime=runtime,
        services=setup_services,
    )
    space_id = str(uuid4())

    create_response = setup_client.post(
        f"/v1/spaces/{space_id}/schedules",
        headers=auth_headers(),
        json={
            "cadence": "daily",
            "seed_entity_ids": [str(uuid4())],
            "source_type": "pubmed",
        },
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]
    claim_started_at = datetime(2026, 3, 26, 12, 0, tzinfo=UTC)
    claim_id = str(uuid4())

    claimant_session = _session_factory()()
    try:
        claimant_store = SqlAlchemyHarnessScheduleStore(claimant_session)
        claimed_schedule = claimant_store.acquire_trigger_claim(
            space_id=space_id,
            schedule_id=schedule_id,
            claim_id=claim_id,
            claimed_at=claim_started_at,
            ttl_seconds=30,
        )
        assert claimed_schedule is not None
        assert claimed_schedule.active_trigger_claim_id == claim_id
    finally:
        claimant_session.rollback()
        claimant_session.close()

    blocked_session = _session_factory()()
    blocked_client: TestClient | None = None
    try:
        blocked_services = _build_services(
            session=blocked_session,
            runtime=runtime,
            execution_override=_leave_run_running,
        )
        blocked_client = _build_client(
            session=blocked_session,
            runtime=runtime,
            services=blocked_services,
        )
        _freeze_schedule_claim_clock(
            monkeypatch,
            frozen_now=claim_started_at + timedelta(seconds=29),
        )
        blocked_response = blocked_client.post(
            f"/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
            headers=auth_headers(),
        )
        assert blocked_response.status_code == 409
        blocked_detail = blocked_response.json()["detail"]
        assert schedule_id in blocked_detail
        assert "already being triggered by another caller" in blocked_detail
    finally:
        if blocked_client is not None:
            blocked_client.close()
        blocked_session.rollback()
        blocked_session.close()

    recovered_session = _session_factory()()
    recovered_client: TestClient | None = None
    try:
        recovered_services = _build_services(
            session=recovered_session,
            runtime=runtime,
            execution_override=_leave_run_running,
        )
        recovered_client = _build_client(
            session=recovered_session,
            runtime=runtime,
            services=recovered_services,
        )
        _freeze_schedule_claim_clock(
            monkeypatch,
            frozen_now=claim_started_at + timedelta(seconds=31),
        )
        recovered_response = recovered_client.post(
            f"/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
            headers=auth_headers(),
        )
        assert recovered_response.status_code == 202
        recovered_payload = recovered_response.json()
        recovered_run_id = recovered_payload["run"]["id"]
    finally:
        if recovered_client is not None:
            recovered_client.close()
        recovered_session.rollback()
        recovered_session.close()

    runs_response = setup_client.get(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
    )
    assert runs_response.status_code == 200
    assert runs_response.json()["total"] == 1
    assert runs_response.json()["runs"][0]["id"] == recovered_run_id

    verifier_session = _session_factory()()
    try:
        verifier_schedule_store = SqlAlchemyHarnessScheduleStore(verifier_session)
        refreshed_schedule = verifier_schedule_store.get_schedule(
            space_id=space_id,
            schedule_id=schedule_id,
        )
        assert refreshed_schedule is not None
        assert refreshed_schedule.last_run_id is None
        assert refreshed_schedule.last_run_at is None
        assert refreshed_schedule.active_trigger_claim_id is None
        assert refreshed_schedule.active_trigger_claimed_at is None
    finally:
        verifier_session.rollback()
        verifier_session.close()


@pytest.mark.integration
def test_parallel_schedule_run_now_requests_only_create_one_active_run(
    db_session: Session,
    short_sync_wait: None,
) -> None:
    del short_sync_wait
    runtime = FakeKernelRuntime()
    setup_services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_leave_run_running,
    )
    setup_client = _build_client(
        session=db_session,
        runtime=runtime,
        services=setup_services,
    )
    space_id = str(uuid4())

    create_response = setup_client.post(
        f"/v1/spaces/{space_id}/schedules",
        headers=auth_headers(),
        json={
            "cadence": "daily",
            "seed_entity_ids": [str(uuid4())],
            "source_type": "pubmed",
        },
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]
    request_barrier = Barrier(4)

    def _trigger_run_now() -> tuple[int, str]:
        session = _session_factory()()
        client: TestClient | None = None
        try:
            services = _build_services(
                session=session,
                runtime=runtime,
                execution_override=_leave_run_running,
            )
            client = _build_client(
                session=session,
                runtime=runtime,
                services=services,
            )
            request_barrier.wait(timeout=10)
            response = client.post(
                f"/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
                headers=auth_headers(),
            )
            return response.status_code, response.text
        finally:
            if client is not None:
                client.close()
            session.rollback()
            session.close()

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = [
            future.result(timeout=30)
            for future in [executor.submit(_trigger_run_now) for _ in range(4)]
        ]

    status_codes = [status_code for status_code, _ in results]
    assert status_codes.count(202) == 1
    assert status_codes.count(409) == 3

    success_payload = json.loads(
        next(body for status_code, body in results if status_code == 202),
    )
    active_run_id = success_payload["run"]["id"]
    assert success_payload["run"]["status"] == "running"

    for status_code, body in results:
        if status_code != 409:
            continue
        detail = json.loads(body)["detail"]
        assert schedule_id in detail
        assert (
            active_run_id in detail
            or "already being triggered by another caller" in detail
        )

    runs_response = setup_client.get(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
    )
    assert runs_response.status_code == 200
    assert runs_response.json()["total"] == 1
    assert runs_response.json()["runs"][0]["id"] == active_run_id


@pytest.mark.integration
def test_scheduler_tick_recovers_after_stale_trigger_claim_expires(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = FakeKernelRuntime()
    setup_services = _build_services(session=db_session, runtime=runtime)
    space_id = str(uuid4())
    claim_started_at = datetime(2026, 3, 26, 12, 0, tzinfo=UTC)
    tick_time = claim_started_at + timedelta(days=1)
    schedule_store = cast("HarnessScheduleStore", setup_services.schedule_store)

    schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Recovered scheduler refresh",
        cadence="daily",
        created_by=str(uuid4()),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={"owner": "integration-test"},
    )
    schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=schedule.id,
        last_run_at=tick_time - timedelta(days=2),
    )
    claim_id = str(uuid4())

    claimant_session = _session_factory()()
    try:
        claimant_store = SqlAlchemyHarnessScheduleStore(claimant_session)
        claimed_schedule = claimant_store.acquire_trigger_claim(
            space_id=space_id,
            schedule_id=schedule.id,
            claim_id=claim_id,
            claimed_at=claim_started_at,
            ttl_seconds=30,
        )
        assert claimed_schedule is not None
        assert claimed_schedule.active_trigger_claim_id == claim_id
    finally:
        claimant_session.rollback()
        claimant_session.close()

    blocked_session = _session_factory()()
    try:
        blocked_services = _build_services(session=blocked_session, runtime=runtime)
        _freeze_schedule_claim_clock(
            monkeypatch,
            frozen_now=claim_started_at + timedelta(seconds=29),
        )
        blocked_result = asyncio.run(
            run_scheduler_tick(
                schedule_store=cast(
                    "HarnessScheduleStore",
                    blocked_services.schedule_store,
                ),
                run_registry=cast(
                    "ArtanaBackedHarnessRunRegistry",
                    blocked_services.run_registry,
                ),
                artifact_store=cast(
                    "ArtanaBackedHarnessArtifactStore",
                    blocked_services.artifact_store,
                ),
                now=tick_time,
            ),
        )
        assert blocked_result.due_schedule_count == 1
        assert blocked_result.triggered_runs == ()
        assert blocked_result.errors == ()
    finally:
        blocked_session.rollback()
        blocked_session.close()

    recovered_session = _session_factory()()
    try:
        recovered_services = _build_services(session=recovered_session, runtime=runtime)
        _freeze_schedule_claim_clock(
            monkeypatch,
            frozen_now=claim_started_at + timedelta(seconds=31),
        )
        recovered_result = asyncio.run(
            run_scheduler_tick(
                schedule_store=cast(
                    "HarnessScheduleStore",
                    recovered_services.schedule_store,
                ),
                run_registry=cast(
                    "ArtanaBackedHarnessRunRegistry",
                    recovered_services.run_registry,
                ),
                artifact_store=cast(
                    "ArtanaBackedHarnessArtifactStore",
                    recovered_services.artifact_store,
                ),
                now=tick_time,
            ),
        )
        assert recovered_result.due_schedule_count == 1
        assert recovered_result.errors == ()
        assert len(recovered_result.triggered_runs) == 1
        recovered_run_id = recovered_result.triggered_runs[0].run_id
    finally:
        recovered_session.rollback()
        recovered_session.close()

    verifier_session = _session_factory()()
    try:
        verifier_services = _build_services(session=verifier_session, runtime=runtime)
        verifier_schedule_store = SqlAlchemyHarnessScheduleStore(verifier_session)
        queued_runs = cast(
            "ArtanaBackedHarnessRunRegistry",
            verifier_services.run_registry,
        ).list_runs(space_id=space_id)
        assert [run.id for run in queued_runs] == [recovered_run_id]
        refreshed_schedule = verifier_schedule_store.get_schedule(
            space_id=space_id,
            schedule_id=schedule.id,
        )
        assert refreshed_schedule is not None
        assert refreshed_schedule.last_run_id == recovered_run_id
        assert refreshed_schedule.active_trigger_claim_id is None
        assert refreshed_schedule.active_trigger_claimed_at is None
    finally:
        verifier_session.rollback()
        verifier_session.close()


@pytest.mark.integration
def test_parallel_scheduler_ticks_only_queue_one_schedule_run_across_sessions(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    setup_services = _build_services(session=db_session, runtime=runtime)
    schedule_store = cast("HarnessScheduleStore", setup_services.schedule_store)
    run_registry = cast("ArtanaBackedHarnessRunRegistry", setup_services.run_registry)
    space_id = str(uuid4())
    tick_time = datetime(2026, 3, 26, 12, 0, tzinfo=UTC)

    schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Replica-safe refresh",
        cadence="daily",
        created_by=str(uuid4()),
        configuration={"seed_entity_ids": ["entity-1"], "source_type": "pubmed"},
        metadata={"owner": "integration-test"},
    )
    schedule_store.update_schedule(
        space_id=space_id,
        schedule_id=schedule.id,
        last_run_at=tick_time - timedelta(days=2),
    )
    request_barrier = Barrier(2)

    def _run_scheduler() -> SchedulerTickResult:
        session = _session_factory()()
        try:
            services = _build_services(session=session, runtime=runtime)
            request_barrier.wait(timeout=10)
            return asyncio.run(
                run_scheduler_tick(
                    schedule_store=cast(
                        "HarnessScheduleStore",
                        services.schedule_store,
                    ),
                    run_registry=cast(
                        "ArtanaBackedHarnessRunRegistry",
                        services.run_registry,
                    ),
                    artifact_store=cast(
                        "ArtanaBackedHarnessArtifactStore",
                        services.artifact_store,
                    ),
                    now=tick_time,
                ),
            )
        finally:
            session.rollback()
            session.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [
            future.result(timeout=30)
            for future in [executor.submit(_run_scheduler) for _ in range(2)]
        ]

    triggered_run_ids = {
        trigger.run_id for result in results for trigger in result.triggered_runs
    }
    assert len(triggered_run_ids) == 1
    assert all(result.errors == () for result in results)

    queued_runs = run_registry.list_runs(space_id=space_id)
    assert [run.id for run in queued_runs] == list(triggered_run_ids)
    refreshed_schedule = schedule_store.get_schedule(
        space_id=space_id,
        schedule_id=schedule.id,
    )
    assert refreshed_schedule is not None
    assert refreshed_schedule.last_run_id in triggered_run_ids
    assert refreshed_schedule.active_trigger_claim_id is None


@pytest.mark.integration
def test_repeated_scheduler_and_worker_cycles_converge_without_leaking_claims(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    schedule_store = cast("HarnessScheduleStore", services.schedule_store)
    run_registry = cast("ArtanaBackedHarnessRunRegistry", services.run_registry)
    artifact_store = cast("ArtanaBackedHarnessArtifactStore", services.artifact_store)
    space_id = str(uuid4())
    cycle_count = 4
    schedule_count = 3
    started_at = datetime.now(UTC).replace(microsecond=0)

    schedule_ids: list[str] = []
    for index in range(schedule_count):
        schedule = schedule_store.create_schedule(
            space_id=space_id,
            harness_id="continuous-learning",
            title=f"Soak refresh {index + 1}",
            cadence="daily",
            created_by=str(uuid4()),
            configuration={
                "seed_entity_ids": [f"entity-{index + 1}"],
                "source_type": "pubmed",
            },
            metadata={"owner": "integration-test", "batch_index": index},
        )
        schedule_store.update_schedule(
            space_id=space_id,
            schedule_id=schedule.id,
            last_run_at=started_at - timedelta(days=2),
        )
        schedule_ids.append(schedule.id)

    all_triggered_run_ids: set[str] = set()
    for cycle_index in range(cycle_count):
        tick_time = started_at + timedelta(days=cycle_index)
        scheduler_result = asyncio.run(
            run_scheduler_tick(
                schedule_store=schedule_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                now=tick_time,
            ),
        )
        assert scheduler_result.scanned_schedule_count == schedule_count
        assert scheduler_result.due_schedule_count == schedule_count
        assert scheduler_result.errors == ()
        assert len(scheduler_result.triggered_runs) == schedule_count

        cycle_run_ids = {trigger.run_id for trigger in scheduler_result.triggered_runs}
        assert len(cycle_run_ids) == schedule_count
        all_triggered_run_ids.update(cycle_run_ids)

        queued_runs = [
            run
            for run in list_queued_worker_runs(
                session=db_session,
                run_registry=run_registry,
            )
            if run.space_id == space_id
        ]
        assert {run.id for run in queued_runs} == cycle_run_ids

        worker_result = asyncio.run(
            run_worker_tick(
                candidate_runs=queued_runs,
                runtime=cast("GraphHarnessKernelRuntime", runtime),
                services=services,
            ),
        )
        assert worker_result.scanned_run_count == schedule_count
        assert worker_result.executed_run_count == schedule_count
        assert worker_result.completed_run_count == schedule_count
        assert worker_result.failed_run_count == 0
        assert worker_result.skipped_run_count == 0

        remaining_queued_runs = [
            run
            for run in list_queued_worker_runs(
                session=db_session,
                run_registry=run_registry,
            )
            if run.space_id == space_id
        ]
        assert remaining_queued_runs == []

        verifier_session = _session_factory()()
        try:
            verifier_schedule_store = SqlAlchemyHarnessScheduleStore(verifier_session)
            for schedule_id in schedule_ids:
                refreshed_schedule = verifier_schedule_store.get_schedule(
                    space_id=space_id,
                    schedule_id=schedule_id,
                )
                assert refreshed_schedule is not None
                assert refreshed_schedule.last_run_id in cycle_run_ids
                assert refreshed_schedule.last_run_at is not None
                assert refreshed_schedule.active_trigger_claim_id is None
                assert refreshed_schedule.active_trigger_claimed_at is None
        finally:
            verifier_session.rollback()
            verifier_session.close()

    all_runs = run_registry.list_runs(space_id=space_id)
    assert len(all_runs) == schedule_count * cycle_count
    assert {run.id for run in all_runs} == all_triggered_run_ids
    assert {run.status for run in all_runs} == {"completed"}


@pytest.mark.integration
def test_parallel_run_now_requests_are_isolated_per_schedule_under_mixed_load(
    db_session: Session,
    short_sync_wait: None,
) -> None:
    del short_sync_wait
    runtime = FakeKernelRuntime()
    setup_services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_leave_run_running,
    )
    setup_client = _build_client(
        session=db_session,
        runtime=runtime,
        services=setup_services,
    )
    space_id = str(uuid4())

    schedule_ids: list[str] = []
    for _ in range(3):
        create_response = setup_client.post(
            f"/v1/spaces/{space_id}/schedules",
            headers=auth_headers(),
            json={
                "cadence": "daily",
                "seed_entity_ids": [str(uuid4())],
                "source_type": "pubmed",
            },
        )
        assert create_response.status_code == 201
        schedule_ids.append(create_response.json()["id"])

    request_schedule_ids = [
        schedule_ids[0],
        schedule_ids[0],
        schedule_ids[1],
        schedule_ids[2],
    ]
    request_barrier = Barrier(len(request_schedule_ids))

    def _trigger_run_now(schedule_id: str) -> tuple[str, int, str]:
        session = _session_factory()()
        client: TestClient | None = None
        try:
            services = _build_services(
                session=session,
                runtime=runtime,
                execution_override=_leave_run_running,
            )
            client = _build_client(
                session=session,
                runtime=runtime,
                services=services,
            )
            request_barrier.wait(timeout=10)
            response = client.post(
                f"/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
                headers=auth_headers(),
            )
            return schedule_id, response.status_code, response.text
        finally:
            if client is not None:
                client.close()
            session.rollback()
            session.close()

    with ThreadPoolExecutor(max_workers=len(request_schedule_ids)) as executor:
        results = [
            future.result(timeout=30)
            for future in [
                executor.submit(_trigger_run_now, schedule_id)
                for schedule_id in request_schedule_ids
            ]
        ]

    grouped_status_codes: dict[str, list[int]] = {
        schedule_id: [] for schedule_id in schedule_ids
    }
    active_run_ids_by_schedule: dict[str, str] = {}
    for schedule_id, status_code, body in results:
        grouped_status_codes[schedule_id].append(status_code)
        if status_code != 202:
            continue
        payload = json.loads(body)
        active_run_ids_by_schedule[schedule_id] = payload["run"]["id"]
        assert payload["run"]["status"] == "running"

    assert sorted(grouped_status_codes[schedule_ids[0]]) == [202, 409]
    assert grouped_status_codes[schedule_ids[1]] == [202]
    assert grouped_status_codes[schedule_ids[2]] == [202]
    assert set(active_run_ids_by_schedule) == set(schedule_ids)
    assert len(set(active_run_ids_by_schedule.values())) == len(schedule_ids)

    for schedule_id, status_code, body in results:
        if status_code != 409:
            continue
        detail = json.loads(body)["detail"]
        assert schedule_id == schedule_ids[0]
        assert schedule_id in detail
        assert (
            active_run_ids_by_schedule[schedule_id] in detail
            or "already being triggered by another caller" in detail
        )

    runs_response = setup_client.get(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
    )
    assert runs_response.status_code == 200
    runs_payload = runs_response.json()
    assert runs_payload["total"] == len(schedule_ids)
    assert {run["id"] for run in runs_payload["runs"]} == set(
        active_run_ids_by_schedule.values(),
    )

    verifier_session = _session_factory()()
    try:
        verifier_schedule_store = SqlAlchemyHarnessScheduleStore(verifier_session)
        for schedule_id in schedule_ids:
            refreshed_schedule = verifier_schedule_store.get_schedule(
                space_id=space_id,
                schedule_id=schedule_id,
            )
            assert refreshed_schedule is not None
            assert refreshed_schedule.last_run_id is None
            assert refreshed_schedule.last_run_at is None
            assert refreshed_schedule.active_trigger_claim_id is None
            assert refreshed_schedule.active_trigger_claimed_at is None
    finally:
        verifier_session.rollback()
        verifier_session.close()


@pytest.mark.integration
def test_repeated_mixed_inline_and_worker_cycles_converge_without_cross_run_state_leaks(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    schedule_store = cast("HarnessScheduleStore", services.schedule_store)
    run_registry = cast("ArtanaBackedHarnessRunRegistry", services.run_registry)
    client = _build_client(
        session=db_session,
        runtime=runtime,
        services=services,
        graph_connection_runner_override=_SuccessfulGraphConnectionRunner,
        graph_search_runner_override=_SuccessfulGraphSearchRunner,
        research_onboarding_runner_override=_SuccessfulResearchOnboardingRunner,
    )
    space_id = str(uuid4())
    cycle_count = 3
    schedule = schedule_store.create_schedule(
        space_id=space_id,
        harness_id="continuous-learning",
        title="Mixed soak refresh",
        cadence="daily",
        created_by=str(uuid4()),
        configuration={"seed_entity_ids": ["entity-soak"], "source_type": "pubmed"},
        metadata={"owner": "integration-mixed-soak"},
    )

    graph_search_run_ids: list[str] = []
    graph_connection_run_ids: list[str] = []
    onboarding_run_ids: list[str] = []
    worker_run_ids: list[str] = []

    for cycle_index in range(cycle_count):
        cycle_number = cycle_index + 1
        tick_time = datetime(2026, 3, 18, 12, 0, tzinfo=UTC) + timedelta(
            days=cycle_index,
        )

        graph_search_response = client.post(
            f"/v1/spaces/{space_id}/agents/graph-search/runs",
            headers=auth_headers(),
            json={
                "question": f"What does MED13 suggest in mixed soak cycle {cycle_number}?",
            },
        )
        assert graph_search_response.status_code == 201
        graph_search_run_ids.append(graph_search_response.json()["run"]["id"])

        graph_connection_response = client.post(
            f"/v1/spaces/{space_id}/agents/graph-connections/runs",
            headers=auth_headers(),
            json={
                "seed_entity_ids": [str(uuid4())],
                "source_type": "pubmed",
            },
        )
        assert graph_connection_response.status_code == 201
        graph_connection_run_ids.append(graph_connection_response.json()["run"]["id"])

        onboarding_response = client.post(
            f"/v1/spaces/{space_id}/agents/research-onboarding/runs",
            headers=auth_headers(),
            json={
                "research_title": f"Mixed soak cycle {cycle_number}",
                "primary_objective": "Track durable isolation under repeated mixed load.",
                "space_description": "Repeated inline and worker harness coverage.",
            },
        )
        assert onboarding_response.status_code == 201
        onboarding_run_ids.append(onboarding_response.json()["run"]["id"])

        scheduler_result = asyncio.run(
            run_scheduler_tick(
                schedule_store=schedule_store,
                run_registry=run_registry,
                artifact_store=cast(
                    "ArtanaBackedHarnessArtifactStore",
                    services.artifact_store,
                ),
                now=tick_time,
            ),
        )
        assert scheduler_result.scanned_schedule_count == 1
        assert scheduler_result.due_schedule_count == 1
        assert len(scheduler_result.triggered_runs) == 1

        queued_runs = [
            run
            for run in list_queued_worker_runs(
                session=db_session,
                run_registry=run_registry,
            )
            if run.space_id == space_id
        ]
        assert len(queued_runs) == 1
        worker_run_ids.append(queued_runs[0].id)

        worker_result = asyncio.run(
            run_worker_tick(
                candidate_runs=queued_runs,
                runtime=cast("GraphHarnessKernelRuntime", runtime),
                services=services,
            ),
        )
        assert worker_result.scanned_run_count == 1
        assert worker_result.executed_run_count == 1
        assert worker_result.completed_run_count == 1
        assert worker_result.failed_run_count == 0

        refreshed_schedule = schedule_store.get_schedule(
            space_id=space_id,
            schedule_id=schedule.id,
        )
        assert refreshed_schedule is not None
        assert refreshed_schedule.last_run_id == queued_runs[0].id
        assert refreshed_schedule.active_trigger_claim_id is None
        assert refreshed_schedule.active_trigger_claimed_at is None

    with _verifier_services(runtime=runtime) as verifier_services:
        verifier_run_registry = cast(
            "ArtanaBackedHarnessRunRegistry",
            verifier_services.run_registry,
        )
        verifier_artifact_store = cast(
            "ArtanaBackedHarnessArtifactStore",
            verifier_services.artifact_store,
        )
        verifier_schedule_store = cast(
            "HarnessScheduleStore",
            verifier_services.schedule_store,
        )
        verifier_state_store = cast(
            "SqlAlchemyHarnessResearchStateStore",
            verifier_services.research_state_store,
        )
        all_runs = verifier_run_registry.list_runs(space_id=space_id)
        assert len(all_runs) == cycle_count * 4
        harness_counts = {
            harness_id: len(
                [run for run in all_runs if run.harness_id == harness_id],
            )
            for harness_id in (
                "graph-search",
                "graph-connections",
                "research-onboarding",
                "continuous-learning",
            )
        }
        assert harness_counts == {
            "graph-search": cycle_count,
            "graph-connections": cycle_count,
            "research-onboarding": cycle_count,
            "continuous-learning": cycle_count,
        }
        assert {run.status for run in all_runs} == {"completed"}

        graph_search_workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=graph_search_run_ids[-1],
        )
        assert graph_search_workspace is not None
        graph_search_artifact_keys = graph_search_workspace.snapshot.get(
            "artifact_keys",
        )
        assert isinstance(graph_search_artifact_keys, list)
        assert "graph_search_result" in graph_search_artifact_keys
        assert "graph_connection_result" not in graph_search_artifact_keys
        assert (
            graph_search_workspace.snapshot["last_graph_search_result_key"]
            == "graph_search_result"
        )

        graph_connection_workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=graph_connection_run_ids[-1],
        )
        assert graph_connection_workspace is not None
        graph_connection_artifact_keys = graph_connection_workspace.snapshot.get(
            "artifact_keys",
        )
        assert isinstance(graph_connection_artifact_keys, list)
        assert "graph_connection_result" in graph_connection_artifact_keys
        assert "graph_search_result" not in graph_connection_artifact_keys
        assert (
            graph_connection_workspace.snapshot["last_graph_connection_result_key"]
            == "graph_connection_result"
        )

        onboarding_workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=onboarding_run_ids[-1],
        )
        assert onboarding_workspace is not None
        assert onboarding_workspace.snapshot["status"] == "completed"
        assert (
            onboarding_workspace.snapshot["last_onboarding_message_key"]
            == "onboarding_assistant_message"
        )
        assert (
            onboarding_workspace.snapshot["last_onboarding_contract_key"]
            == "onboarding_agent_contract"
        )

        worker_workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=worker_run_ids[-1],
        )
        assert worker_workspace is not None
        assert worker_workspace.snapshot["status"] == "completed"
        assert worker_workspace.snapshot["integration_result_key"] == (
            "integration_result"
        )

        preserved_state = verifier_state_store.get_state(space_id=space_id)
        assert preserved_state is not None
        assert (
            preserved_state.metadata["last_onboarding_run_id"] == onboarding_run_ids[-1]
        )
        assert preserved_state.metadata["research_title"] == (
            f"Mixed soak cycle {cycle_count}"
        )

        refreshed_schedule = verifier_schedule_store.get_schedule(
            space_id=space_id,
            schedule_id=schedule.id,
        )
        assert refreshed_schedule is not None
        assert refreshed_schedule.last_run_id == worker_run_ids[-1]
        assert refreshed_schedule.active_trigger_claim_id is None
        assert refreshed_schedule.active_trigger_claimed_at is None


@pytest.mark.integration
def test_parallel_mixed_harness_burst_preserves_isolation_with_contended_schedule_run_now(
    db_session: Session,
    short_sync_wait: None,
) -> None:
    del short_sync_wait
    runtime = FakeKernelRuntime()
    setup_services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_leave_run_running,
    )
    setup_client = _build_client(
        session=db_session,
        runtime=runtime,
        services=setup_services,
        graph_connection_runner_override=_SuccessfulGraphConnectionRunner,
        graph_search_runner_override=_SuccessfulGraphSearchRunner,
        research_onboarding_runner_override=_SuccessfulResearchOnboardingRunner,
    )
    space_id = str(uuid4())

    create_response = setup_client.post(
        f"/v1/spaces/{space_id}/schedules",
        headers=auth_headers(),
        json={
            "cadence": "daily",
            "seed_entity_ids": [str(uuid4())],
            "source_type": "pubmed",
        },
    )
    assert create_response.status_code == 201
    schedule_id = create_response.json()["id"]

    request_labels = (
        "schedule-primary",
        "schedule-duplicate",
        "graph-search",
        "graph-connections",
        "research-onboarding",
    )
    request_barrier = Barrier(len(request_labels))

    def _dispatch_request(request_label: str) -> tuple[str, int, str]:
        session = _session_factory()()
        client: TestClient | None = None
        try:
            services = _build_services(
                session=session,
                runtime=runtime,
                execution_override=_leave_run_running,
            )
            client = _build_client(
                session=session,
                runtime=runtime,
                services=services,
                graph_connection_runner_override=_SuccessfulGraphConnectionRunner,
                graph_search_runner_override=_SuccessfulGraphSearchRunner,
                research_onboarding_runner_override=_SuccessfulResearchOnboardingRunner,
            )
            request_barrier.wait(timeout=10)
            if request_label.startswith("schedule"):
                response = client.post(
                    f"/v1/spaces/{space_id}/schedules/{schedule_id}/run-now",
                    headers=auth_headers(),
                )
            elif request_label == "graph-search":
                response = client.post(
                    f"/v1/spaces/{space_id}/agents/graph-search/runs",
                    headers=auth_headers(),
                    json={"question": "What does MED13 suggest under burst load?"},
                )
            elif request_label == "graph-connections":
                response = client.post(
                    f"/v1/spaces/{space_id}/agents/graph-connections/runs",
                    headers=auth_headers(),
                    json={
                        "seed_entity_ids": [str(uuid4())],
                        "source_type": "pubmed",
                    },
                )
            else:
                response = client.post(
                    f"/v1/spaces/{space_id}/agents/research-onboarding/runs",
                    headers=auth_headers(),
                    json={
                        "research_title": "Burst isolation",
                        "primary_objective": (
                            "Confirm concurrent inline and worker runs stay isolated."
                        ),
                        "space_description": (
                            "Parallel mixed-burst integration coverage."
                        ),
                    },
                )
            return request_label, response.status_code, response.text
        finally:
            if client is not None:
                client.close()
            session.rollback()
            session.close()

    with ThreadPoolExecutor(max_workers=len(request_labels)) as executor:
        results = [
            future.result(timeout=30)
            for future in [
                executor.submit(_dispatch_request, request_label)
                for request_label in request_labels
            ]
        ]

    schedule_results = [
        (status_code, body)
        for request_label, status_code, body in results
        if request_label.startswith("schedule")
    ]
    assert sorted(status_code for status_code, _ in schedule_results) == [202, 409]

    schedule_success_payload = json.loads(
        next(body for status_code, body in schedule_results if status_code == 202),
    )
    schedule_run_id = schedule_success_payload["run"]["id"]
    assert schedule_success_payload["run"]["status"] == "running"

    schedule_conflict_body = json.loads(
        next(body for status_code, body in schedule_results if status_code == 409),
    )
    schedule_conflict_detail = schedule_conflict_body["detail"]
    assert schedule_id in schedule_conflict_detail
    assert (
        schedule_run_id in schedule_conflict_detail
        or "already being triggered by another caller" in schedule_conflict_detail
    )

    graph_search_run_id = ""
    graph_connection_run_id = ""
    onboarding_run_id = ""
    for request_label, status_code, body in results:
        if request_label.startswith("schedule"):
            continue
        assert status_code == 201
        payload = json.loads(body)
        run_id = payload["run"]["id"]
        if request_label == "graph-search":
            graph_search_run_id = run_id
        elif request_label == "graph-connections":
            graph_connection_run_id = run_id
        else:
            onboarding_run_id = run_id

    assert all(
        run_id
        for run_id in (
            graph_search_run_id,
            graph_connection_run_id,
            onboarding_run_id,
        )
    )
    assert (
        len(
            {
                schedule_run_id,
                graph_search_run_id,
                graph_connection_run_id,
                onboarding_run_id,
            },
        )
        == 4
    )

    runs_response = setup_client.get(
        f"/v1/spaces/{space_id}/runs",
        headers=auth_headers(),
    )
    assert runs_response.status_code == 200
    runs_payload = runs_response.json()
    assert runs_payload["total"] == 4
    runs_by_harness = {run["harness_id"]: run for run in runs_payload["runs"]}
    assert set(runs_by_harness) == {
        "continuous-learning",
        "graph-search",
        "graph-connections",
        "research-onboarding",
    }
    assert runs_by_harness["continuous-learning"]["id"] == schedule_run_id
    assert runs_by_harness["continuous-learning"]["status"] == "running"
    assert runs_by_harness["graph-search"]["id"] == graph_search_run_id
    assert runs_by_harness["graph-search"]["status"] == "completed"
    assert runs_by_harness["graph-connections"]["id"] == graph_connection_run_id
    assert runs_by_harness["graph-connections"]["status"] == "completed"
    assert runs_by_harness["research-onboarding"]["id"] == onboarding_run_id
    assert runs_by_harness["research-onboarding"]["status"] == "completed"

    with _verifier_services(runtime=runtime) as verifier_services:
        verifier_run_registry = cast(
            "ArtanaBackedHarnessRunRegistry",
            verifier_services.run_registry,
        )
        verifier_artifact_store = cast(
            "ArtanaBackedHarnessArtifactStore",
            verifier_services.artifact_store,
        )
        verifier_schedule_store = cast(
            "HarnessScheduleStore",
            verifier_services.schedule_store,
        )
        verifier_state_store = cast(
            "SqlAlchemyHarnessResearchStateStore",
            verifier_services.research_state_store,
        )

        all_runs = verifier_run_registry.list_runs(space_id=space_id)
        assert len(all_runs) == 4
        assert {run.id for run in all_runs} == {
            schedule_run_id,
            graph_search_run_id,
            graph_connection_run_id,
            onboarding_run_id,
        }
        assert {(run.harness_id, run.status) for run in all_runs} == {
            ("continuous-learning", "running"),
            ("graph-search", "completed"),
            ("graph-connections", "completed"),
            ("research-onboarding", "completed"),
        }

        graph_search_workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=graph_search_run_id,
        )
        assert graph_search_workspace is not None
        graph_search_artifact_keys = graph_search_workspace.snapshot.get(
            "artifact_keys",
        )
        assert isinstance(graph_search_artifact_keys, list)
        assert "graph_search_result" in graph_search_artifact_keys
        assert "graph_connection_result" not in graph_search_artifact_keys
        assert (
            graph_search_workspace.snapshot.get("last_onboarding_message_key") is None
        )

        graph_connection_workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=graph_connection_run_id,
        )
        assert graph_connection_workspace is not None
        graph_connection_artifact_keys = graph_connection_workspace.snapshot.get(
            "artifact_keys",
        )
        assert isinstance(graph_connection_artifact_keys, list)
        assert "graph_connection_result" in graph_connection_artifact_keys
        assert "graph_search_result" not in graph_connection_artifact_keys
        assert (
            graph_connection_workspace.snapshot.get("last_onboarding_message_key")
            is None
        )

        onboarding_workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=onboarding_run_id,
        )
        assert onboarding_workspace is not None
        onboarding_artifact_keys = onboarding_workspace.snapshot.get("artifact_keys")
        assert isinstance(onboarding_artifact_keys, list)
        assert "onboarding_assistant_message" in onboarding_artifact_keys
        assert "onboarding_agent_contract" in onboarding_artifact_keys
        assert "graph_search_result" not in onboarding_artifact_keys
        assert "graph_connection_result" not in onboarding_artifact_keys
        assert (
            onboarding_workspace.snapshot["last_onboarding_message_key"]
            == "onboarding_assistant_message"
        )
        assert (
            onboarding_workspace.snapshot["last_onboarding_contract_key"]
            == "onboarding_agent_contract"
        )

        schedule_workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=schedule_run_id,
        )
        assert schedule_workspace is not None
        assert schedule_workspace.snapshot["status"] == "running"
        schedule_artifact_keys = schedule_workspace.snapshot.get("artifact_keys")
        assert isinstance(schedule_artifact_keys, list)
        assert "graph_search_result" not in schedule_artifact_keys
        assert "graph_connection_result" not in schedule_artifact_keys
        assert "onboarding_assistant_message" not in schedule_artifact_keys
        assert schedule_workspace.snapshot.get("last_graph_search_result_key") is None
        assert (
            schedule_workspace.snapshot.get("last_graph_connection_result_key") is None
        )
        assert schedule_workspace.snapshot.get("last_onboarding_message_key") is None

        preserved_state = verifier_state_store.get_state(space_id=space_id)
        assert preserved_state is not None
        assert preserved_state.metadata["last_onboarding_run_id"] == onboarding_run_id
        assert preserved_state.metadata["research_title"] == "Burst isolation"

        refreshed_schedule = verifier_schedule_store.get_schedule(
            space_id=space_id,
            schedule_id=schedule_id,
        )
        assert refreshed_schedule is not None
        assert refreshed_schedule.last_run_id is None
        assert refreshed_schedule.last_run_at is None
        assert refreshed_schedule.active_trigger_claim_id is None
        assert refreshed_schedule.active_trigger_claimed_at is None


@pytest.mark.integration
def test_research_bootstrap_route_captures_graph_snapshot_and_stages_proposals(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_bootstrap_execution_override,
    )
    client = _build_client(session=db_session, runtime=runtime, services=services)
    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/research-bootstrap/runs",
        headers=auth_headers(),
        json={
            "objective": "Bootstrap MED13 regulation evidence",
            "seed_entity_ids": [seed_entity_id],
        },
    )
    assert response.status_code == 201
    payload = response.json()
    run_id = payload["run"]["id"]
    assert payload["proposal_count"] == 1
    assert payload["graph_snapshot"]["source_run_id"] == run_id
    assert (
        payload["research_state"]["last_graph_snapshot_id"]
        == payload["graph_snapshot"]["id"]
    )
    artifacts_response = client.get(
        f"/v1/spaces/{space_id}/runs/{run_id}/artifacts",
        headers=auth_headers(),
    )
    assert artifacts_response.status_code == 200
    artifact_keys = {
        artifact["key"] for artifact in artifacts_response.json()["artifacts"]
    }
    assert {
        "graph_context_snapshot",
        "research_brief",
        "graph_summary",
        "source_inventory",
        "candidate_claim_pack",
    }.issubset(artifact_keys)


@pytest.mark.integration
def test_graph_search_route_persists_failed_state_in_durable_stores_when_runner_crashes(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(
        session=db_session,
        runtime=runtime,
        graph_search_runner=_FailingGraphSearchRunner(),
    )
    client = _build_client(session=db_session, runtime=runtime, services=services)
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/graph-search/runs",
        headers=auth_headers(),
        json={"question": "What does the graph suggest about MED13?"},
    )

    assert response.status_code == 500
    assert "Synthetic integration graph-search failure." in response.text

    with _verifier_services(runtime=runtime) as verifier_services:
        verifier_run_registry = cast(
            "ArtanaBackedHarnessRunRegistry",
            verifier_services.run_registry,
        )
        verifier_artifact_store = cast(
            "ArtanaBackedHarnessArtifactStore",
            verifier_services.artifact_store,
        )
        runs = verifier_run_registry.list_runs(space_id=space_id)
        assert len(runs) == 1
        failed_run = runs[0]
        assert failed_run.harness_id == "graph-search"
        assert failed_run.status == "failed"

        error_artifact = verifier_artifact_store.get_artifact(
            space_id=space_id,
            run_id=failed_run.id,
            artifact_key="graph_search_error",
        )
        assert error_artifact is not None
        assert error_artifact.content["error"] == (
            "Synthetic integration graph-search failure."
        )
        assert (
            verifier_artifact_store.get_artifact(
                space_id=space_id,
                run_id=failed_run.id,
                artifact_key="graph_search_result",
            )
            is None
        )
        workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=failed_run.id,
        )
        assert workspace is not None
        assert workspace.snapshot["status"] == "failed"
        assert (
            workspace.snapshot["error"] == "Synthetic integration graph-search failure."
        )


@pytest.mark.integration
def test_graph_connection_route_persists_failed_state_in_durable_stores_when_runner_crashes(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    client = _build_client(
        session=db_session,
        runtime=runtime,
        services=services,
        graph_connection_runner_override=_FailingGraphConnectionRunner,
    )
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/graph-connections/runs",
        headers=auth_headers(),
        json={
            "seed_entity_ids": [str(uuid4())],
            "source_type": "pubmed",
        },
    )

    assert response.status_code == 500
    assert "Synthetic integration graph-connection failure." in response.text

    with _verifier_services(runtime=runtime) as verifier_services:
        verifier_run_registry = cast(
            "ArtanaBackedHarnessRunRegistry",
            verifier_services.run_registry,
        )
        verifier_artifact_store = cast(
            "ArtanaBackedHarnessArtifactStore",
            verifier_services.artifact_store,
        )
        runs = verifier_run_registry.list_runs(space_id=space_id)
        assert len(runs) == 1
        failed_run = runs[0]
        assert failed_run.harness_id == "graph-connections"
        assert failed_run.status == "failed"

        error_artifact = verifier_artifact_store.get_artifact(
            space_id=space_id,
            run_id=failed_run.id,
            artifact_key="graph_connection_error",
        )
        assert error_artifact is not None
        assert error_artifact.content["error"] == (
            "Synthetic integration graph-connection failure."
        )
        assert (
            verifier_artifact_store.get_artifact(
                space_id=space_id,
                run_id=failed_run.id,
                artifact_key="graph_connection_result",
            )
            is None
        )
        workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=failed_run.id,
        )
        assert workspace is not None
        assert workspace.snapshot["status"] == "failed"
        assert (
            workspace.snapshot["error"]
            == "Synthetic integration graph-connection failure."
        )


@pytest.mark.integration
def test_research_onboarding_run_persists_failed_state_in_durable_stores_when_agent_crashes(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    client = _build_client(
        session=db_session,
        runtime=runtime,
        services=services,
        research_onboarding_runner_override=_FailingInitialResearchOnboardingRunner,
    )
    space_id = str(uuid4())

    response = client.post(
        f"/v1/spaces/{space_id}/agents/research-onboarding/runs",
        headers=auth_headers(),
        json={
            "research_title": "Durable onboarding test",
            "primary_objective": "Collect contradictory evidence.",
            "space_description": "Integration onboarding durability check.",
        },
    )

    assert response.status_code == 503
    assert "Synthetic integration onboarding initial failure." in response.text

    with _verifier_services(runtime=runtime) as verifier_services:
        verifier_run_registry = cast(
            "ArtanaBackedHarnessRunRegistry",
            verifier_services.run_registry,
        )
        verifier_artifact_store = cast(
            "ArtanaBackedHarnessArtifactStore",
            verifier_services.artifact_store,
        )
        verifier_state_store = cast(
            "SqlAlchemyHarnessResearchStateStore",
            verifier_services.research_state_store,
        )
        runs = verifier_run_registry.list_runs(space_id=space_id)
        assert len(runs) == 1
        failed_run = runs[0]
        assert failed_run.harness_id == "research-onboarding"
        assert failed_run.status == "failed"

        failure_artifact = verifier_artifact_store.get_artifact(
            space_id=space_id,
            run_id=failed_run.id,
            artifact_key="onboarding_agent_error",
        )
        assert failure_artifact is not None
        assert failure_artifact.content["error"] == (
            "Synthetic integration onboarding initial failure."
        )
        intake_artifact = verifier_artifact_store.get_artifact(
            space_id=space_id,
            run_id=failed_run.id,
            artifact_key="research_onboarding_intake",
        )
        assert intake_artifact is not None
        assert (
            verifier_artifact_store.get_artifact(
                space_id=space_id,
                run_id=failed_run.id,
                artifact_key="onboarding_assistant_message",
            )
            is None
        )
        workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=failed_run.id,
        )
        assert workspace is not None
        assert workspace.snapshot["status"] == "failed"
        assert (
            workspace.snapshot["error"]
            == "Synthetic integration onboarding initial failure."
        )
        assert verifier_state_store.get_state(space_id=space_id) is None


@pytest.mark.integration
def test_research_onboarding_turn_preserves_durable_state_when_agent_crashes(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    research_state_store = cast(
        "SqlAlchemyHarnessResearchStateStore",
        services.research_state_store,
    )
    space_id = str(uuid4())
    research_state_store.upsert_state(
        space_id=space_id,
        objective="Collect contradictory evidence.",
        explored_questions=["What disease area matters most?"],
        pending_questions=["Which evidence sources should be authoritative?"],
        metadata={
            "research_title": "Durable onboarding test",
            "onboarding_status": "awaiting_researcher_reply",
            "last_onboarding_run_id": "seed-onboarding-run",
        },
    )
    client = _build_client(
        session=db_session,
        runtime=runtime,
        services=services,
        research_onboarding_runner_override=_FailingContinuationResearchOnboardingRunner,
    )

    response = client.post(
        f"/v1/spaces/{space_id}/agents/research-onboarding/turns",
        headers=auth_headers(),
        json={
            "thread_id": "thread-1",
            "message_id": "message-1",
            "intent": "reply",
            "mode": "answer_question",
            "reply_text": "Prioritize contradictory human evidence first.",
            "reply_html": "<p>Prioritize contradictory human evidence first.</p>",
            "attachments": [],
            "contextual_anchor": None,
        },
    )

    assert response.status_code == 503
    assert "Synthetic integration onboarding continuation failure." in response.text

    with _verifier_services(runtime=runtime) as verifier_services:
        verifier_run_registry = cast(
            "ArtanaBackedHarnessRunRegistry",
            verifier_services.run_registry,
        )
        verifier_artifact_store = cast(
            "ArtanaBackedHarnessArtifactStore",
            verifier_services.artifact_store,
        )
        verifier_state_store = cast(
            "SqlAlchemyHarnessResearchStateStore",
            verifier_services.research_state_store,
        )
        runs = verifier_run_registry.list_runs(space_id=space_id)
        assert len(runs) == 1
        failed_run = runs[0]
        assert failed_run.harness_id == "research-onboarding"
        assert failed_run.status == "failed"

        failure_artifact = verifier_artifact_store.get_artifact(
            space_id=space_id,
            run_id=failed_run.id,
            artifact_key="onboarding_agent_error",
        )
        assert failure_artifact is not None
        assert failure_artifact.content["error"] == (
            "Synthetic integration onboarding continuation failure."
        )
        assert (
            verifier_artifact_store.get_artifact(
                space_id=space_id,
                run_id=failed_run.id,
                artifact_key="onboarding_assistant_message",
            )
            is None
        )
        workspace = verifier_artifact_store.get_workspace(
            space_id=space_id,
            run_id=failed_run.id,
        )
        assert workspace is not None
        assert workspace.snapshot["status"] == "failed"
        assert (
            workspace.snapshot["error"]
            == "Synthetic integration onboarding continuation failure."
        )
        preserved_state = verifier_state_store.get_state(space_id=space_id)
        assert preserved_state is not None
        assert preserved_state.objective == "Collect contradictory evidence."
        assert preserved_state.explored_questions == [
            "What disease area matters most?",
        ]
        assert preserved_state.pending_questions == [
            "Which evidence sources should be authoritative?",
        ]
        assert preserved_state.metadata["last_onboarding_run_id"] == (
            "seed-onboarding-run"
        )


@pytest.mark.integration
def test_promote_proposal_creates_graph_claim_and_updates_artana_workspace(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(session=db_session, runtime=runtime)
    client = _build_client(session=db_session, runtime=runtime, services=services)
    space_id = str(uuid4())
    source_entity_id = str(uuid4())
    target_entity_id = str(uuid4())
    source_run = services.run_registry.create_run(
        space_id=space_id,
        harness_id="hypotheses",
        title="Promotion Source",
        input_payload={"seed_entity_ids": [source_entity_id]},
        graph_service_status="ok",
        graph_service_version="test-graph",
    )
    services.artifact_store.seed_for_run(run=source_run)
    proposal = services.proposal_store.create_proposals(
        space_id=space_id,
        run_id=source_run.id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="integration_test",
                source_key=f"{source_entity_id}:REGULATES:{target_entity_id}",
                title="Promote MED13 claim",
                summary="Synthetic promotion proposal.",
                confidence=0.88,
                ranking_score=0.95,
                reasoning_path={"reasoning": "Synthetic promotion reasoning."},
                evidence_bundle=[{"source_type": "db", "locator": source_entity_id}],
                payload=_candidate_claim_payload(
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                ),
                metadata={"agent_run_id": "integration-promotion"},
            ),
        ),
    )[0]

    response = client.post(
        f"/v1/spaces/{space_id}/proposals/{proposal.id}/promote",
        headers=auth_headers(),
        json={"reason": "Integration promotion"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "promoted"
    graph_claim_id = payload["metadata"].get("graph_claim_id")
    assert isinstance(graph_claim_id, str)
    assert graph_claim_id != ""
    workspace = services.artifact_store.get_workspace(
        space_id=space_id,
        run_id=source_run.id,
    )
    assert workspace is not None
    assert workspace.snapshot["last_promoted_graph_claim_id"] == graph_claim_id


@pytest.mark.integration
def test_supervisor_parent_child_pause_and_resume_complete_through_child_approval(
    db_session: Session,
) -> None:
    runtime = FakeKernelRuntime()
    services = _build_services(
        session=db_session,
        runtime=runtime,
        execution_override=_supervisor_execution_override,
    )
    client = _build_client(session=db_session, runtime=runtime, services=services)
    space_id = str(uuid4())
    seed_entity_id = str(uuid4())

    create_response = client.post(
        f"/v1/spaces/{space_id}/agents/supervisor/runs",
        headers=auth_headers(),
        json={
            "objective": "Compose bootstrap and governed review",
            "seed_entity_ids": [seed_entity_id],
            "include_chat": False,
            "include_curation": True,
            "curation_source": "bootstrap",
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.json()
    parent_run_id = created_payload["run"]["id"]
    child_curation_run_id = created_payload["curation"]["run"]["id"]
    assert created_payload["run"]["status"] == "paused"
    assert created_payload["curation"]["pending_approval_count"] == 1

    approvals_response = client.get(
        f"/v1/spaces/{space_id}/runs/{child_curation_run_id}/approvals",
        headers=auth_headers(),
    )
    assert approvals_response.status_code == 200
    approval_key = approvals_response.json()["approvals"][0]["approval_key"]

    decide_response = client.post(
        f"/v1/spaces/{space_id}/runs/{child_curation_run_id}/approvals/{approval_key}",
        headers=auth_headers(),
        json={"decision": "approved", "reason": "Integration child approval"},
    )
    assert decide_response.status_code == 200

    resume_response = client.post(
        f"/v1/spaces/{space_id}/runs/{parent_run_id}/resume",
        headers=auth_headers(),
        json={"reason": "Resume parent after child approval"},
    )
    assert resume_response.status_code == 200
    assert resume_response.json()["run"]["status"] == "completed"
    child_run = services.run_registry.get_run(
        space_id=space_id,
        run_id=child_curation_run_id,
    )
    assert child_run is not None
    assert child_run.status == "completed"
