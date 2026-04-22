"""Deterministic HTTP server for cross-service research inbox E2E tests."""

from __future__ import annotations

import asyncio
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast
from uuid import UUID

import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[3]
for candidate in (REPO_ROOT, REPO_ROOT / "services"):
    resolved = str(candidate)
    if resolved not in sys.path:
        sys.path.insert(0, resolved)

from artana_evidence_api.agent_contracts import (  # noqa: E402
    EvidenceItem,
    OnboardingAssistantContract,
    OnboardingQuestion,
    OnboardingSection,
    OnboardingStatePatch,
    OnboardingSuggestedAction,
)
from artana_evidence_api.app import create_app  # noqa: E402
from artana_evidence_api.approval_store import HarnessApprovalStore  # noqa: E402
from artana_evidence_api.artana_stores import (  # noqa: E402
    ArtanaBackedHarnessRunRegistry,
)
from artana_evidence_api.artifact_store import HarnessArtifactStore  # noqa: E402
from artana_evidence_api.chat_sessions import HarnessChatSessionStore  # noqa: E402
from artana_evidence_api.composition import GraphHarnessKernelRuntime  # noqa: E402
from artana_evidence_api.database import SessionLocal  # noqa: E402
from artana_evidence_api.dependencies import (  # noqa: E402
    get_artifact_store,
    get_graph_api_gateway,
    get_harness_execution_services,
    get_research_onboarding_runner,
    get_research_space_store,
    get_research_state_store,
    get_run_registry,
)
from artana_evidence_api.document_store import HarnessDocumentStore  # noqa: E402
from artana_evidence_api.graph_chat_runtime import HarnessGraphChatRunner  # noqa: E402
from artana_evidence_api.graph_client import GraphServiceHealthResponse  # noqa: E402
from artana_evidence_api.graph_connection_runtime import (  # noqa: E402
    HarnessGraphConnectionRunner,
)
from artana_evidence_api.graph_search_runtime import (
    HarnessGraphSearchRunner,  # noqa: E402
)
from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore  # noqa: E402
from artana_evidence_api.harness_runtime import (  # noqa: E402
    HarnessExecutionResult,
    HarnessExecutionServices,
)
from artana_evidence_api.proposal_store import HarnessProposalStore  # noqa: E402
from artana_evidence_api.research_onboarding_agent_runtime import (  # noqa: E402
    HarnessResearchOnboardingContinuationRequest,
    HarnessResearchOnboardingInitialRequest,
    HarnessResearchOnboardingResult,
    HarnessResearchOnboardingRunner,
)
from artana_evidence_api.research_onboarding_runtime import (  # noqa: E402
    ResearchOnboardingContinuationRequest,
    execute_research_onboarding_continuation,
    execute_research_onboarding_run,
)
from artana_evidence_api.research_space_store import (
    HarnessResearchSpaceStore,
)  # noqa: E402
from artana_evidence_api.routers import (
    research_onboarding_runs as onboarding_routes,  # noqa: E402
)
from artana_evidence_api.schedule_store import HarnessScheduleStore  # noqa: E402
from artana_evidence_api.sqlalchemy_stores import (  # noqa: E402
    SqlAlchemyHarnessResearchSpaceStore,
    SqlAlchemyHarnessResearchStateStore,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
    from artana_evidence_api.run_registry import HarnessRunRecord

    from src.domain.entities.research_space import ResearchSpace


class _StubGraphApiGateway:
    """Minimal graph gateway used by deterministic onboarding E2E tests."""

    def get_health(self) -> GraphServiceHealthResponse:
        return GraphServiceHealthResponse(status="ok", version="e2e-stub")

    def close(self) -> None:
        return None


@dataclass(frozen=True)
class _FakeRunSummary:
    """Minimal summary record compatible with Artana-backed run registry helpers."""

    summary_json: str


class _NoOpSpaceLifecycleSync:
    """Skip graph tenant sync in deterministic onboarding E2E runs."""

    def sync_space(self, space: ResearchSpace) -> None:
        del space


_SPACE_LIFECYCLE_SYNC = _NoOpSpaceLifecycleSync()


def _graph_sync_enabled_for_e2e() -> bool:
    return os.getenv("ARTANA_EVIDENCE_API_E2E_ENABLE_GRAPH_SYNC") == "1"


def _get_e2e_research_space_store() -> Iterator[HarnessResearchSpaceStore]:
    session = SessionLocal()
    try:
        yield SqlAlchemyHarnessResearchSpaceStore(
            session,
            space_lifecycle_sync=_SPACE_LIFECYCLE_SYNC,
        )
    finally:
        session.close()


class _DeterministicOnboardingRunner:
    """Predictable onboarding runner used for cross-service tests."""

    async def run_initial(
        self,
        request: HarnessResearchOnboardingInitialRequest,
    ) -> HarnessResearchOnboardingResult:
        prompt = "Which evidence type matters most for the first pass?"
        objective = request.primary_objective.strip() or request.research_title.strip()
        contract = OnboardingAssistantContract(
            message_type="clarification_request",
            title="Need one more answer",
            summary="I need one more clarification before drafting the first plan.",
            sections=[
                OnboardingSection(
                    heading="Missing context",
                    body=(
                        "Tell me which evidence source should anchor the first "
                        "review pass."
                    ),
                ),
            ],
            questions=[
                OnboardingQuestion(
                    id="evidence-priority",
                    prompt=prompt,
                    helper_text="Choose the evidence source you trust most right now.",
                ),
            ],
            suggested_actions=[
                OnboardingSuggestedAction(
                    id="reply-evidence-priority",
                    label="Answer question",
                    action_type="reply",
                ),
            ],
            artifacts=[],
            state_patch=OnboardingStatePatch(
                thread_status="your_turn",
                onboarding_status="awaiting_researcher_reply",
                pending_question_count=1,
                objective=objective,
                explored_questions=[],
                pending_questions=[prompt],
                current_hypotheses=[],
            ),
            confidence_score=0.94,
            rationale="Deterministic E2E onboarding stub requested one clarification.",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator="research-inbox:e2e:onboarding-initial",
                    excerpt="Synthetic onboarding clarification request.",
                    relevance=0.94,
                ),
            ],
            agent_run_id="research-inbox-e2e-initial",
            warnings=[],
        )
        return HarnessResearchOnboardingResult(
            contract=contract,
            agent_run_id="research-inbox-e2e-initial",
            active_skill_names=(),
        )

    async def run_continuation(
        self,
        request: HarnessResearchOnboardingContinuationRequest,
    ) -> HarnessResearchOnboardingResult:
        objective = (
            request.objective.strip() if isinstance(request.objective, str) else ""
        )
        contract = OnboardingAssistantContract(
            message_type="plan_ready",
            title="Initial plan ready",
            summary="The first evidence-backed onboarding plan is ready for review.",
            sections=[
                OnboardingSection(
                    heading="Initial plan",
                    body=(
                        "Start with the evidence source the researcher prioritized, "
                        "capture the strongest grounded findings, and defer broader "
                        "exploration until after the first review."
                    ),
                ),
            ],
            questions=[],
            suggested_actions=[
                OnboardingSuggestedAction(
                    id="review-first-plan",
                    label="Review draft",
                    action_type="review",
                ),
            ],
            artifacts=[],
            state_patch=OnboardingStatePatch(
                thread_status="review_needed",
                onboarding_status="plan_ready",
                pending_question_count=0,
                objective=objective or None,
                explored_questions=[
                    "Which evidence type matters most for the first pass?",
                ],
                pending_questions=[],
                current_hypotheses=[
                    "The first review should prioritize the researcher-selected evidence source.",
                ],
            ),
            confidence_score=0.91,
            rationale="Deterministic E2E onboarding stub produced a reviewable first plan.",
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator="research-inbox:e2e:onboarding-continuation",
                    excerpt="Synthetic onboarding continuation produced a draft plan.",
                    relevance=0.91,
                ),
            ],
            agent_run_id="research-inbox-e2e-continuation",
            warnings=[],
        )
        return HarnessResearchOnboardingResult(
            contract=contract,
            agent_run_id="research-inbox-e2e-continuation",
            active_skill_names=(),
        )


class _UnusedGraphConnectionRunner:
    """Placeholder graph-connection runner for onboarding-only test execution."""


class _UnusedGraphChatRunner:
    """Placeholder graph-chat runner for onboarding-only test execution."""


class _FakeKernelRuntime:
    """Minimal runtime lease shim for deterministic worker-owned E2E runs."""

    def __init__(self) -> None:
        self._leases: set[tuple[str, str, str]] = set()
        self._summaries: dict[tuple[str, str], list[_FakeRunSummary]] = {}

    def acquire_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
        ttl_seconds: int,
    ) -> bool:
        _ = ttl_seconds
        lease = (run_id, tenant_id, worker_id)
        if lease in self._leases:
            return False
        self._leases.add(lease)
        return True

    def release_run_lease(
        self,
        *,
        run_id: str,
        tenant_id: str,
        worker_id: str,
    ) -> None:
        self._leases.discard((run_id, tenant_id, worker_id))

    def ensure_run(self, *, run_id: str, tenant_id: str) -> None:
        del run_id, tenant_id

    def append_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        summary_json: str,
        step_key: str,
    ) -> None:
        del tenant_id, step_key
        key = (run_id, summary_type)
        self._summaries.setdefault(key, []).append(_FakeRunSummary(summary_json))

    def get_latest_run_summary(
        self,
        *,
        run_id: str,
        tenant_id: str,
        summary_type: str,
        timeout_seconds: float | None = None,
    ) -> _FakeRunSummary | None:
        del tenant_id, timeout_seconds
        summaries = self._summaries.get((run_id, summary_type))
        if not summaries:
            return None
        return summaries[-1]

    def get_run_progress(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        del run_id, tenant_id, timeout_seconds

    def get_run_status(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        del run_id, tenant_id, timeout_seconds

    def get_resume_point(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> None:
        del run_id, tenant_id, timeout_seconds

    def get_events(
        self,
        *,
        run_id: str,
        tenant_id: str,
        timeout_seconds: float | None = None,
    ) -> list[object]:
        del run_id, tenant_id, timeout_seconds
        return []


@contextmanager
def _fake_pubmed_discovery_context() -> Iterator[PubMedDiscoveryService]:
    yield cast("PubMedDiscoveryService", object())


@contextmanager
def _e2e_store_context() -> (
    Iterator[tuple[ArtanaBackedHarnessRunRegistry, SqlAlchemyHarnessResearchStateStore]]
):
    session = SessionLocal()
    try:
        yield (
            ArtanaBackedHarnessRunRegistry(
                session=session,
                runtime=cast("GraphHarnessKernelRuntime", _FAKE_RUNTIME),
            ),
            SqlAlchemyHarnessResearchStateStore(session),
        )
    finally:
        session.close()


def _execute_test_onboarding_run_sync(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    with _e2e_store_context() as (run_registry, research_state_store):
        payload = run.input_payload
        if isinstance(payload.get("reply_text"), str):
            return execute_research_onboarding_continuation(
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
                run_registry=run_registry,
                artifact_store=services.artifact_store,
                graph_api_gateway=services.graph_api_gateway_factory(),
                research_state_store=research_state_store,
                onboarding_runner=services.research_onboarding_runner,
                existing_run=run,
            )
        return execute_research_onboarding_run(
            space_id=UUID(run.space_id),
            research_title=str(payload.get("research_title", "")),
            primary_objective=str(payload.get("primary_objective", "")),
            space_description=str(payload.get("space_description", "")),
            run_registry=run_registry,
            artifact_store=services.artifact_store,
            graph_api_gateway=services.graph_api_gateway_factory(),
            research_state_store=research_state_store,
            onboarding_runner=services.research_onboarding_runner,
            existing_run=run,
        )


async def _execute_test_onboarding_run(
    run: HarnessRunRecord,
    services: HarnessExecutionServices,
) -> HarnessExecutionResult:
    return await asyncio.to_thread(
        _execute_test_onboarding_run_sync,
        run,
        services,
    )


async def _execute_test_onboarding_route_run(
    *,
    run: HarnessRunRecord,
    services: object,
) -> None:
    execution_override = getattr(services, "execution_override", None)
    if execution_override is None:
        return
    typed_services = cast("HarnessExecutionServices", services)
    try:
        await execution_override(run, typed_services)
    except Exception as exc:  # noqa: BLE001
        typed_services.artifact_store.patch_workspace(
            space_id=run.space_id,
            run_id=run.id,
            patch={
                "status": "failed",
                "error": str(exc) or exc.__class__.__name__,
                "e2e_execution_exception": {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            },
        )
        raise


_FAKE_RUNTIME = _FakeKernelRuntime()
_ARTIFACT_STORE = HarnessArtifactStore()
_ONBOARDING_RUNNER = _DeterministicOnboardingRunner()
_APP = create_app()


def _get_e2e_run_registry() -> Iterator[ArtanaBackedHarnessRunRegistry]:
    with _e2e_store_context() as (run_registry, _):
        yield run_registry


def _get_e2e_research_state_store() -> Iterator[SqlAlchemyHarnessResearchStateStore]:
    with _e2e_store_context() as (_, research_state_store):
        yield research_state_store


def _get_e2e_execution_services() -> Iterator[HarnessExecutionServices]:
    with _e2e_store_context() as (run_registry, research_state_store):
        yield HarnessExecutionServices(
            runtime=cast("GraphHarnessKernelRuntime", _FAKE_RUNTIME),
            run_registry=run_registry,
            artifact_store=_ARTIFACT_STORE,
            chat_session_store=HarnessChatSessionStore(),
            document_store=HarnessDocumentStore(),
            proposal_store=HarnessProposalStore(),
            approval_store=HarnessApprovalStore(),
            research_state_store=research_state_store,
            graph_snapshot_store=HarnessGraphSnapshotStore(),
            schedule_store=HarnessScheduleStore(),
            graph_connection_runner=cast(
                "HarnessGraphConnectionRunner",
                _UnusedGraphConnectionRunner(),
            ),
            graph_chat_runner=cast(
                "HarnessGraphChatRunner",
                _UnusedGraphChatRunner(),
            ),
            graph_search_runner=HarnessGraphSearchRunner(),
            graph_api_gateway_factory=_StubGraphApiGateway,
            pubmed_discovery_service_factory=_fake_pubmed_discovery_context,
            research_onboarding_runner=cast(
                "HarnessResearchOnboardingRunner",
                _ONBOARDING_RUNNER,
            ),
            execution_override=_execute_test_onboarding_run,
        )


_APP.dependency_overrides[get_run_registry] = _get_e2e_run_registry
_APP.dependency_overrides[get_artifact_store] = lambda: _ARTIFACT_STORE
_APP.dependency_overrides[get_research_state_store] = _get_e2e_research_state_store
_APP.dependency_overrides[get_graph_api_gateway] = _StubGraphApiGateway
_APP.dependency_overrides[get_research_onboarding_runner] = lambda: _ONBOARDING_RUNNER
if not _graph_sync_enabled_for_e2e():
    _APP.dependency_overrides[get_research_space_store] = _get_e2e_research_space_store
_APP.dependency_overrides[get_harness_execution_services] = _get_e2e_execution_services
onboarding_routes.maybe_execute_test_worker_run = _execute_test_onboarding_route_run


def main() -> None:
    """Run the deterministic Artana Evidence API E2E server."""
    host = os.getenv("ARTANA_EVIDENCE_API_SERVICE_HOST", "127.0.0.1")
    port = int(os.getenv("ARTANA_EVIDENCE_API_SERVICE_PORT", "8091"))
    uvicorn.run(_APP, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
