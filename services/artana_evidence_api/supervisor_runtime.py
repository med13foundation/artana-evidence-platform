"""Supervisor harness runtime for composed research workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.chat_graph_write_workflow import (
    ChatGraphWriteArtifactError,
    ChatGraphWriteCandidateError,
    ChatGraphWriteProposalExecution,
    ChatGraphWriteVerificationError,
    derive_chat_graph_write_candidates,
    stage_chat_graph_write_proposals,
)
from artana_evidence_api.chat_workflow import (
    DEFAULT_CHAT_SESSION_TITLE,
    GraphChatMessageExecution,
    execute_graph_chat_message,
)
from artana_evidence_api.claim_curation_workflow import (
    ClaimCurationNoEligibleProposalsError,
    ClaimCurationRunExecution,
    execute_claim_curation_run_for_proposals,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.research_bootstrap_runtime import (
    ResearchBootstrapExecutionResult,
    execute_research_bootstrap_run,
)
from artana_evidence_api.supervisor_child_activity import (
    _propagate_child_skill_activity,
)
from artana_evidence_api.supervisor_payloads import (
    _SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY,
    _SUPERVISOR_RESUME_POINT,
    _SUPERVISOR_SUMMARY_ARTIFACT_KEY,
    _SUPERVISOR_WORKFLOW,
    _chat_run_response_payload,
    _claim_curation_response_payload,
    _json_object_sequence,
    _mark_failed_supervisor_run,
    _progress_percent,
    _research_bootstrap_response_payload,
    _supervisor_run_response_payload,
    _write_supervisor_artifacts,
    build_supervisor_run_input_payload,
)
from artana_evidence_api.supervisor_resume import resume_supervisor_run
from artana_evidence_api.transparency import (
    append_skill_activity,
    ensure_run_transparency_seed,
)

if TYPE_CHECKING:
    from artana_evidence_api.approval_store import HarnessApprovalStore
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.chat_sessions import (
        HarnessChatSessionRecord,
        HarnessChatSessionStore,
    )
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.graph_chat_runtime import HarnessGraphChatRunner
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.graph_connection_runtime import (
        HarnessGraphConnectionRunner,
    )
    from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotStore
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.pubmed_discovery import PubMedDiscoveryService
    from artana_evidence_api.research_state import HarnessResearchStateStore
    from artana_evidence_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from artana_evidence_api.schedule_store import HarnessScheduleStore
    from artana_evidence_api.types.common import JSONObject

@dataclass(frozen=True, slots=True)
class SupervisorExecutionResult:
    """One completed supervisor orchestration result."""

    run: HarnessRunRecord
    bootstrap: ResearchBootstrapExecutionResult
    chat_session: HarnessChatSessionRecord | None
    chat: GraphChatMessageExecution | None
    curation: ClaimCurationRunExecution | None
    briefing_question: str | None
    curation_source: str
    chat_graph_write: ChatGraphWriteProposalExecution | None
    selected_curation_proposal_ids: tuple[str, ...]
    steps: tuple[JSONObject, ...]


def is_supervisor_workflow(run: HarnessRunRecord) -> bool:
    """Return whether one run belongs to the supervisor workflow."""
    workflow = run.input_payload.get("workflow")
    return run.harness_id == "supervisor" and workflow == _SUPERVISOR_WORKFLOW


def _derived_briefing_question(
    *,
    objective: str | None,
    pending_questions: list[str],
    top_proposal_title: str | None,
) -> str:
    if pending_questions:
        return pending_questions[0]
    if objective is not None and objective.strip() != "":
        return f"What should a researcher review next to advance: {objective.strip()}?"
    if top_proposal_title is not None and top_proposal_title.strip() != "":
        return (
            f"What evidence should be reviewed first for: {top_proposal_title.strip()}?"
        )
    return "What should be reviewed next in this research space?"


def queue_supervisor_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    include_chat: bool,
    include_curation: bool,
    curation_source: str,
    briefing_question: str | None,
    chat_max_depth: int,
    chat_top_k: int,
    chat_include_evidence_chains: bool,
    curation_proposal_limit: int,
    current_user_id: UUID | str,
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="supervisor",
        title=title,
        input_payload=build_supervisor_run_input_payload(
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            model_id=model_id,
            include_chat=include_chat,
            include_curation=include_curation,
            curation_source=curation_source,
            briefing_question=briefing_question,
            chat_max_depth=chat_max_depth,
            chat_top_k=chat_top_k,
            chat_include_evidence_chains=chat_include_evidence_chains,
            curation_proposal_limit=curation_proposal_limit,
            current_user_id=str(current_user_id),
        ),
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "queued",
            "workflow": _SUPERVISOR_WORKFLOW,
            "include_chat": include_chat,
            "include_curation": include_curation,
            "curation_source": curation_source,
            "selected_curation_proposal_ids": [],
            "chat_graph_write_proposal_ids": [],
            "skipped_steps": [],
        },
    )
    return run


async def execute_supervisor_run(  # noqa: C901, PLR0912, PLR0913, PLR0915
    *,
    space_id: UUID,
    title: str,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    include_chat: bool,
    include_curation: bool,
    curation_source: str,
    briefing_question: str | None,
    chat_max_depth: int,
    chat_top_k: int,
    chat_include_evidence_chains: bool,
    curation_proposal_limit: int,
    current_user_id: UUID | str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    chat_session_store: HarnessChatSessionStore,
    proposal_store: HarnessProposalStore,
    approval_store: HarnessApprovalStore,
    research_state_store: HarnessResearchStateStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    schedule_store: HarnessScheduleStore,
    graph_connection_runner: HarnessGraphConnectionRunner,
    graph_chat_runner: HarnessGraphChatRunner,
    pubmed_discovery_service: PubMedDiscoveryService,
    runtime: GraphHarnessKernelRuntime,
    parent_graph_api_gateway: GraphTransportBundle,
    bootstrap_graph_api_gateway: GraphTransportBundle,
    chat_graph_api_gateway: GraphTransportBundle,
    curation_graph_api_gateway: GraphTransportBundle,
    existing_run: HarnessRunRecord | None = None,
) -> SupervisorExecutionResult:
    """Run the composed supervisor workflow across bootstrap, chat, and curation."""
    total_steps = 1 + int(include_chat) + int(include_curation)
    completed_steps = 0
    steps: list[JSONObject] = []
    try:
        parent_graph_health = parent_graph_api_gateway.get_health()
    finally:
        parent_graph_api_gateway.close()

    if existing_run is None:
        run = queue_supervisor_run(
            space_id=space_id,
            title=title,
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            model_id=model_id,
            include_chat=include_chat,
            include_curation=include_curation,
            curation_source=curation_source,
            briefing_question=briefing_question,
            chat_max_depth=chat_max_depth,
            chat_top_k=chat_top_k,
            chat_include_evidence_chains=chat_include_evidence_chains,
            curation_proposal_limit=curation_proposal_limit,
            current_user_id=current_user_id,
            graph_service_status=parent_graph_health.status,
            graph_service_version=parent_graph_health.version,
            run_registry=run_registry,
            artifact_store=artifact_store,
        )
        ensure_run_transparency_seed(
            run=run,
            artifact_store=artifact_store,
            runtime=runtime,
        )
    else:
        run = existing_run
        if artifact_store.get_workspace(space_id=space_id, run_id=run.id) is None:
            artifact_store.seed_for_run(run=run)
        ensure_run_transparency_seed(
            run=run,
            artifact_store=artifact_store,
            runtime=runtime,
        )
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="bootstrap",
        message="Running bootstrap step.",
        progress_percent=0.0,
        completed_steps=0,
        total_steps=total_steps,
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="supervisor_plan",
        media_type="application/json",
        content={
            "workflow": _SUPERVISOR_WORKFLOW,
            "include_chat": include_chat,
            "include_curation": include_curation,
            "curation_source": curation_source,
            "briefing_question": briefing_question,
            "curation_proposal_limit": curation_proposal_limit,
        },
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "running",
            "workflow": _SUPERVISOR_WORKFLOW,
            "include_chat": include_chat,
            "include_curation": include_curation,
            "curation_source": curation_source,
            "selected_curation_proposal_ids": [],
            "chat_graph_write_proposal_ids": [],
            "skipped_steps": [],
        },
    )
    append_skill_activity(
        space_id=space_id,
        run_id=run.id,
        skill_names=("graph_harness.supervisor_coordination",),
        source_run_id=run.id,
        source_kind="supervisor",
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=runtime,
    )

    try:
        bootstrap = await execute_research_bootstrap_run(
            space_id=space_id,
            title="Research Bootstrap Harness",
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            model_id=model_id,
            run_registry=run_registry,
            artifact_store=artifact_store,
            graph_api_gateway=bootstrap_graph_api_gateway,
            graph_connection_runner=graph_connection_runner,
            proposal_store=proposal_store,
            research_state_store=research_state_store,
            graph_snapshot_store=graph_snapshot_store,
            schedule_store=schedule_store,
            runtime=runtime,
        )
    except Exception as exc:
        _mark_failed_supervisor_run(
            space_id=space_id,
            run_id=run.id,
            error_message=f"Supervisor bootstrap step failed: {exc}",
            run_registry=run_registry,
            artifact_store=artifact_store,
            completed_steps=completed_steps,
            total_steps=total_steps,
        )
        bootstrap_graph_api_gateway.close()
        raise
    bootstrap_graph_api_gateway.close()

    completed_steps += 1
    steps.append(
        {
            "step": "bootstrap",
            "status": "completed",
            "harness_id": bootstrap.run.harness_id,
            "run_id": bootstrap.run.id,
            "detail": f"Bootstrap completed with {len(bootstrap.proposal_records)} proposal(s).",
        },
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="supervisor.bootstrap_completed",
        message="Supervisor bootstrap step completed.",
        payload={
            "bootstrap_run_id": bootstrap.run.id,
            "proposal_count": len(bootstrap.proposal_records),
            "graph_snapshot_id": bootstrap.graph_snapshot.id,
        },
        progress_percent=_progress_percent(
            completed_steps=completed_steps,
            total_steps=total_steps,
        ),
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "bootstrap_run_id": bootstrap.run.id,
            "last_graph_snapshot_id": bootstrap.graph_snapshot.id,
            "bootstrap_proposal_count": len(bootstrap.proposal_records),
        },
    )
    _propagate_child_skill_activity(
        space_id=space_id,
        parent_run_id=run.id,
        child_run_id=bootstrap.run.id,
        source_kind="research_bootstrap",
        artifact_store=artifact_store,
        run_registry=run_registry,
        runtime=runtime,
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="bootstrap",
        message="Bootstrap step completed.",
        progress_percent=_progress_percent(
            completed_steps=completed_steps,
            total_steps=total_steps,
        ),
        completed_steps=completed_steps,
        total_steps=total_steps,
        metadata={"bootstrap_run_id": bootstrap.run.id},
    )

    chat_session: HarnessChatSessionRecord | None = None
    chat_execution: GraphChatMessageExecution | None = None
    chat_graph_write_execution: ChatGraphWriteProposalExecution | None = None
    resolved_briefing_question: str | None = None
    skipped_steps: list[str] = []
    if include_chat:
        resolved_briefing_question = (
            briefing_question.strip()
            if isinstance(briefing_question, str) and briefing_question.strip() != ""
            else _derived_briefing_question(
                objective=bootstrap.research_state.objective,
                pending_questions=bootstrap.pending_questions,
                top_proposal_title=(
                    bootstrap.proposal_records[0].title
                    if bootstrap.proposal_records
                    else None
                ),
            )
        )
        chat_session = chat_session_store.create_session(
            space_id=space_id,
            title=DEFAULT_CHAT_SESSION_TITLE,
            created_by=current_user_id,
        )
        try:
            chat_execution = await execute_graph_chat_message(
                space_id=space_id,
                session=chat_session,
                content=resolved_briefing_question,
                model_id=model_id,
                max_depth=chat_max_depth,
                top_k=chat_top_k,
                include_evidence_chains=chat_include_evidence_chains,
                current_user_id=current_user_id,
                chat_session_store=chat_session_store,
                run_registry=run_registry,
                artifact_store=artifact_store,
                runtime=runtime,
                graph_api_gateway=chat_graph_api_gateway,
                graph_chat_runner=graph_chat_runner,
                graph_snapshot_store=graph_snapshot_store,
                _pubmed_discovery_service=pubmed_discovery_service,
                research_state_store=research_state_store,
                proposal_store=proposal_store,
                referenced_documents=(),
                refresh_pubmed_if_needed=True,
            )
        except Exception as exc:
            _mark_failed_supervisor_run(
                space_id=space_id,
                run_id=run.id,
                error_message=f"Supervisor chat step failed: {exc}",
                run_registry=run_registry,
                artifact_store=artifact_store,
                completed_steps=completed_steps,
                total_steps=total_steps,
            )
            raise
        completed_steps += 1
        steps.append(
            {
                "step": "chat",
                "status": "completed",
                "harness_id": chat_execution.run.harness_id,
                "run_id": chat_execution.run.id,
                "detail": "Briefing chat completed.",
            },
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="supervisor.chat_completed",
            message="Supervisor chat step completed.",
            payload={
                "chat_run_id": chat_execution.run.id,
                "chat_session_id": chat_execution.session.id,
                "question": resolved_briefing_question,
            },
            progress_percent=_progress_percent(
                completed_steps=completed_steps,
                total_steps=total_steps,
            ),
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "chat_run_id": chat_execution.run.id,
                "chat_session_id": chat_execution.session.id,
                "briefing_question": resolved_briefing_question,
            },
        )
        _propagate_child_skill_activity(
            space_id=space_id,
            parent_run_id=run.id,
            child_run_id=chat_execution.run.id,
            source_kind="graph_chat",
            artifact_store=artifact_store,
            run_registry=run_registry,
            runtime=runtime,
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="chat",
            message="Chat step completed.",
            progress_percent=_progress_percent(
                completed_steps=completed_steps,
                total_steps=total_steps,
            ),
            completed_steps=completed_steps,
            total_steps=total_steps,
            metadata={"chat_run_id": chat_execution.run.id},
        )
    else:
        chat_graph_api_gateway.close()
        skipped_steps.append("chat")
        steps.append(
            {
                "step": "chat",
                "status": "skipped",
                "harness_id": None,
                "run_id": None,
                "detail": "Chat step disabled for this supervisor run.",
            },
        )

    curation_execution: ClaimCurationRunExecution | None = None
    selected_curation_proposal_ids: tuple[str, ...] = ()
    chat_graph_write_proposals = []
    if include_curation and curation_source == "chat_graph_write":
        if chat_execution is None or chat_session is None:
            error_message = (
                "Supervisor chat graph-write curation requires a completed chat step"
            )
            _mark_failed_supervisor_run(
                space_id=space_id,
                run_id=run.id,
                error_message=error_message,
                run_registry=run_registry,
                artifact_store=artifact_store,
                completed_steps=completed_steps,
                total_steps=total_steps,
            )
            raise RuntimeError(error_message)
        try:
            derived_chat_graph_write_candidates = derive_chat_graph_write_candidates(
                space_id=space_id,
                run=chat_execution.run,
                result=chat_execution.result,
                runtime=runtime,
            )
            artifact_store.patch_workspace(
                space_id=space_id,
                run_id=run.id,
                patch={
                    "chat_graph_write_candidate_count": len(
                        derived_chat_graph_write_candidates,
                    ),
                },
            )
            if not derived_chat_graph_write_candidates:
                run_registry.record_event(
                    space_id=space_id,
                    run_id=run.id,
                    event_type="supervisor.chat_graph_write_candidates_derived",
                    message="Supervisor found no chat-derived graph-write suggestions.",
                    payload={
                        "chat_run_id": chat_execution.run.id,
                        "candidate_count": 0,
                    },
                    progress_percent=_progress_percent(
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                    ),
                )
            else:
                run_registry.record_event(
                    space_id=space_id,
                    run_id=run.id,
                    event_type="supervisor.chat_graph_write_candidates_derived",
                    message="Supervisor derived chat graph-write suggestions.",
                    payload={
                        "chat_run_id": chat_execution.run.id,
                        "candidate_count": len(derived_chat_graph_write_candidates),
                    },
                    progress_percent=_progress_percent(
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                    ),
                )
            chat_graph_write_execution = stage_chat_graph_write_proposals(
                space_id=space_id,
                session_id=UUID(chat_session.id),
                run_id=chat_execution.run.id,
                candidates=list(derived_chat_graph_write_candidates),
                artifact_store=artifact_store,
                proposal_store=proposal_store,
                run_registry=run_registry,
            )
        except (
            ChatGraphWriteArtifactError,
            ChatGraphWriteCandidateError,
            ChatGraphWriteVerificationError,
        ) as exc:
            _mark_failed_supervisor_run(
                space_id=space_id,
                run_id=run.id,
                error_message=f"Supervisor chat graph-write staging failed: {exc}",
                run_registry=run_registry,
                artifact_store=artifact_store,
                completed_steps=completed_steps,
                total_steps=total_steps,
            )
            curation_graph_api_gateway.close()
            raise
        chat_graph_write_proposals = list(chat_graph_write_execution.proposals)
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="supervisor.chat_graph_write_staged",
            message="Supervisor staged chat-derived graph-write proposals.",
            payload={
                "chat_run_id": chat_execution.run.id,
                "proposal_ids": [
                    proposal.id for proposal in chat_graph_write_execution.proposals
                ],
            },
            progress_percent=_progress_percent(
                completed_steps=completed_steps,
                total_steps=total_steps,
            ),
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "chat_graph_write_run_id": chat_execution.run.id,
                "chat_graph_write_proposal_ids": [
                    proposal.id for proposal in chat_graph_write_execution.proposals
                ],
                "chat_graph_write_proposal_count": len(
                    chat_graph_write_execution.proposals,
                ),
            },
        )
    if include_curation:
        proposal_source_records = (
            chat_graph_write_proposals
            if curation_source == "chat_graph_write"
            else bootstrap.proposal_records
        )
        curatable_proposals = sorted(
            [
                proposal
                for proposal in proposal_source_records
                if proposal.status == "pending_review"
            ],
            key=lambda proposal: proposal.ranking_score,
            reverse=True,
        )[:curation_proposal_limit]
        selected_curation_proposal_ids = tuple(
            proposal.id for proposal in curatable_proposals
        )
        if not curatable_proposals:
            curation_graph_api_gateway.close()
            skipped_steps.append("curation")
            steps.append(
                {
                    "step": "curation",
                    "status": "skipped",
                    "harness_id": None,
                    "run_id": None,
                    "detail": (
                        "No pending-review proposals were available for claim "
                        f"curation from source '{curation_source}'."
                    ),
                },
            )
        else:
            try:
                curation_execution = execute_claim_curation_run_for_proposals(
                    space_id=space_id,
                    proposals=curatable_proposals,
                    title="Claim Curation Harness",
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    proposal_store=proposal_store,
                    approval_store=approval_store,
                    graph_api_gateway=curation_graph_api_gateway,
                    runtime=runtime,
                )
            except ClaimCurationNoEligibleProposalsError as exc:
                skipped_steps.append("curation")
                steps.append(
                    {
                        "step": "curation",
                        "status": "skipped",
                        "harness_id": None,
                        "run_id": None,
                        "detail": str(exc),
                    },
                )
            except Exception as exc:
                _mark_failed_supervisor_run(
                    space_id=space_id,
                    run_id=run.id,
                    error_message=f"Supervisor curation step failed: {exc}",
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                )
                raise
            else:
                steps.append(
                    {
                        "step": "curation",
                        "status": "paused",
                        "harness_id": curation_execution.run.harness_id,
                        "run_id": curation_execution.run.id,
                        "detail": "Claim-curation run created and paused for approval.",
                    },
                )
                run_registry.record_event(
                    space_id=space_id,
                    run_id=run.id,
                    event_type="supervisor.curation_created",
                    message="Supervisor curation step created a paused review run.",
                    payload={
                        "curation_run_id": curation_execution.run.id,
                        "proposal_ids": list(selected_curation_proposal_ids),
                        "pending_approvals": curation_execution.pending_approval_count,
                    },
                    progress_percent=_progress_percent(
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                    ),
                )
                artifact_store.patch_workspace(
                    space_id=space_id,
                    run_id=run.id,
                    patch={
                        "curation_run_id": curation_execution.run.id,
                        "selected_curation_proposal_ids": list(
                            selected_curation_proposal_ids,
                        ),
                        "curation_source": curation_source,
                        "pending_approvals": curation_execution.pending_approval_count,
                        "curation_status": curation_execution.run.status,
                    },
                )
                _propagate_child_skill_activity(
                    space_id=space_id,
                    parent_run_id=run.id,
                    child_run_id=curation_execution.run.id,
                    source_kind="claim_curation",
                    artifact_store=artifact_store,
                    run_registry=run_registry,
                    runtime=runtime,
                )
                run_registry.set_progress(
                    space_id=space_id,
                    run_id=run.id,
                    phase="approval",
                    message="Supervisor workflow paused pending child curation approval.",
                    progress_percent=_progress_percent(
                        completed_steps=completed_steps,
                        total_steps=total_steps,
                    ),
                    completed_steps=completed_steps,
                    total_steps=total_steps,
                    resume_point=_SUPERVISOR_RESUME_POINT,
                    metadata={"curation_run_id": curation_execution.run.id},
                )
    else:
        curation_graph_api_gateway.close()
        skipped_steps.append("curation")
        steps.append(
            {
                "step": "curation",
                "status": "skipped",
                "harness_id": None,
                "run_id": None,
                "detail": "Curation step disabled for this supervisor run.",
            },
        )

    summary_content: JSONObject = {
        "workflow": _SUPERVISOR_WORKFLOW,
        "bootstrap_run_id": bootstrap.run.id,
        "bootstrap_response": _research_bootstrap_response_payload(result=bootstrap),
        "chat_run_id": chat_execution.run.id if chat_execution is not None else None,
        "chat_response": (
            _chat_run_response_payload(execution=chat_execution)
            if chat_execution is not None
            else None
        ),
        "chat_graph_write_run_id": (
            chat_graph_write_execution.run_id
            if chat_graph_write_execution is not None
            else None
        ),
        "chat_graph_write_proposal_ids": [
            proposal.id
            for proposal in (
                chat_graph_write_execution.proposals
                if chat_graph_write_execution is not None
                else []
            )
        ],
        "chat_session_id": (
            chat_execution.session.id
            if chat_execution is not None
            else (chat_session.id if chat_session is not None else None)
        ),
        "curation_run_id": (
            curation_execution.run.id if curation_execution is not None else None
        ),
        "curation_response": (
            _claim_curation_response_payload(
                run=curation_execution.run,
                review_plan=curation_execution.review_plan,
                pending_approval_count=curation_execution.pending_approval_count,
            )
            if curation_execution is not None
            else None
        ),
        "briefing_question": resolved_briefing_question,
        "curation_source": curation_source,
        "selected_curation_proposal_ids": list(selected_curation_proposal_ids),
        "skipped_steps": skipped_steps,
        "curation_status": (
            curation_execution.run.status if curation_execution is not None else None
        ),
        "completed_at": None,
        "steps": steps,
    }
    _write_supervisor_artifacts(
        space_id=space_id,
        run_id=run.id,
        bootstrap_run_id=bootstrap.run.id,
        chat_run_id=chat_execution.run.id if chat_execution is not None else None,
        chat_session_id=(
            chat_execution.session.id
            if chat_execution is not None
            else (chat_session.id if chat_session is not None else None)
        ),
        curation_run_id=(
            curation_execution.run.id if curation_execution is not None else None
        ),
        curation_status=(
            curation_execution.run.status if curation_execution is not None else None
        ),
        summary_content=summary_content,
        artifact_store=artifact_store,
    )
    if curation_execution is not None:
        paused_run = run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status="paused",
        )
        paused_progress = run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="approval",
            message="Supervisor workflow paused pending child curation approval.",
            progress_percent=_progress_percent(
                completed_steps=completed_steps,
                total_steps=total_steps,
            ),
            completed_steps=completed_steps,
            total_steps=total_steps,
            resume_point=_SUPERVISOR_RESUME_POINT,
            metadata={
                "curation_run_id": curation_execution.run.id,
                "pending_approvals": curation_execution.pending_approval_count,
            },
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "paused",
                "resume_point": _SUPERVISOR_RESUME_POINT,
                "pending_approvals": curation_execution.pending_approval_count,
                "last_supervisor_summary_key": _SUPERVISOR_SUMMARY_ARTIFACT_KEY,
                "last_child_run_links_key": _SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY,
                "briefing_question": resolved_briefing_question,
                "curation_source": curation_source,
                "selected_curation_proposal_ids": list(selected_curation_proposal_ids),
                "skipped_steps": skipped_steps,
            },
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="supervisor.paused",
            message="Supervisor workflow paused at the child curation approval gate.",
            payload={
                "curation_run_id": curation_execution.run.id,
                "pending_approvals": curation_execution.pending_approval_count,
            },
            progress_percent=(
                paused_progress.progress_percent
                if paused_progress is not None
                else None
            ),
        )
        final_run = paused_run or run
        store_primary_result_artifact(
            artifact_store=artifact_store,
            space_id=space_id,
            run_id=run.id,
            artifact_key="supervisor_run_response",
            content=_supervisor_run_response_payload(
                run=final_run,
                bootstrap=bootstrap,
                chat=chat_execution,
                curation=curation_execution,
                briefing_question=resolved_briefing_question,
                curation_source=curation_source,
                chat_graph_write_proposal_ids=[
                    proposal.id
                    for proposal in (
                        chat_graph_write_execution.proposals
                        if chat_graph_write_execution is not None
                        else []
                    )
                ],
                selected_curation_proposal_ids=list(selected_curation_proposal_ids),
                steps=steps,
            ),
            status_value="paused",
            result_keys=("supervisor_summary", "child_run_links"),
        )
        return SupervisorExecutionResult(
            run=final_run,
            bootstrap=bootstrap,
            chat_session=chat_session,
            chat=chat_execution,
            curation=curation_execution,
            briefing_question=resolved_briefing_question,
            curation_source=curation_source,
            chat_graph_write=chat_graph_write_execution,
            selected_curation_proposal_ids=selected_curation_proposal_ids,
            steps=_json_object_sequence(summary_content.get("steps")),
        )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={
            "status": "completed",
            "last_supervisor_summary_key": _SUPERVISOR_SUMMARY_ARTIFACT_KEY,
            "last_child_run_links_key": _SUPERVISOR_CHILD_LINKS_ARTIFACT_KEY,
            "briefing_question": resolved_briefing_question,
            "curation_source": curation_source,
            "selected_curation_proposal_ids": list(selected_curation_proposal_ids),
            "skipped_steps": skipped_steps,
        },
    )
    completed_run = run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="completed",
    )
    final_run = completed_run or run
    summary_content["completed_at"] = (
        completed_run.updated_at.isoformat() if completed_run is not None else None
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key=_SUPERVISOR_SUMMARY_ARTIFACT_KEY,
        media_type="application/json",
        content=summary_content,
    )
    store_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key="supervisor_run_response",
        content=_supervisor_run_response_payload(
            run=final_run,
            bootstrap=bootstrap,
            chat=chat_execution,
            curation=curation_execution,
            briefing_question=resolved_briefing_question,
            curation_source=curation_source,
            chat_graph_write_proposal_ids=[
                proposal.id
                for proposal in (
                    chat_graph_write_execution.proposals
                    if chat_graph_write_execution is not None
                    else []
                )
            ],
            selected_curation_proposal_ids=list(selected_curation_proposal_ids),
            steps=steps,
        ),
        status_value="completed",
        result_keys=("supervisor_summary", "child_run_links"),
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="completed",
        message="Supervisor workflow completed.",
        progress_percent=1.0,
        completed_steps=total_steps,
        total_steps=total_steps,
        metadata={"skipped_steps": skipped_steps},
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="supervisor.completed",
        message="Supervisor workflow completed.",
        payload=summary_content,
        progress_percent=1.0,
    )
    return SupervisorExecutionResult(
        run=final_run,
        bootstrap=bootstrap,
        chat_session=chat_session,
        chat=chat_execution,
        curation=curation_execution,
        briefing_question=resolved_briefing_question,
        curation_source=curation_source,
        chat_graph_write=chat_graph_write_execution,
        selected_curation_proposal_ids=selected_curation_proposal_ids,
        steps=_json_object_sequence(summary_content.get("steps")),
    )


__all__ = [
    "SupervisorExecutionResult",
    "execute_supervisor_run",
    "is_supervisor_workflow",
    "resume_supervisor_run",
]
