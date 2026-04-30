# mypy: disable-error-code="attr-defined,has-type,no-any-return"
"""Progress-state persistence mixin for the full-AI orchestrator runtime."""

from __future__ import annotations

import time
from copy import deepcopy
from typing import Literal

from artana_evidence_api.full_ai_orchestrator_common_support import (
    _chase_round_action_input_from_workspace,
    _chase_round_metadata_from_workspace,
    _chase_round_stop_reason,
    _planner_mode_value,
    _source_decision_status,
    _workspace_list,
    _workspace_object,
)
from artana_evidence_api.full_ai_orchestrator_contracts import (
    FullAIOrchestratorPlannerMode,
    ResearchOrchestratorActionType,
    ResearchOrchestratorGuardedDecisionProof,
)
from artana_evidence_api.full_ai_orchestrator_guarded_rollout import (
    _guarded_rollout_policy_summary,
)
from artana_evidence_api.full_ai_orchestrator_guarded_support import (
    _build_guarded_decision_proof,
    _guarded_decision_proof_summary,
    _guarded_execution_summary,
    _guarded_readiness_summary,
    _put_decision_history_artifact,
    _put_guarded_decision_proof_artifacts,
    _put_guarded_execution_artifact,
    _put_guarded_readiness_artifact,
)
from artana_evidence_api.full_ai_orchestrator_runtime_artifacts import (
    _build_live_bootstrap_summary,
    _build_live_brief_metadata,
    _build_live_chase_rounds_artifact,
    _build_live_driven_terms_artifact,
    _build_live_pubmed_summary,
    _build_live_source_execution_summary,
)
from artana_evidence_api.full_ai_orchestrator_runtime_constants import (
    _BOOTSTRAP_ARTIFACT_KEY,
    _BRIEF_METADATA_ARTIFACT_KEY,
    _CHASE_ROUNDS_ARTIFACT_KEY,
    _DRIVEN_TERMS_ARTIFACT_KEY,
    _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY,
    _GUARDED_EXECUTION_ARTIFACT_KEY,
    _GUARDED_READINESS_ARTIFACT_KEY,
    _LOGGER,
    _PROGRESS_PERSISTENCE_BACKOFF_SECONDS,
    _PUBMED_ARTIFACT_KEY,
    _SOURCE_EXECUTION_ARTIFACT_KEY,
    _STRUCTURED_ENRICHMENT_SOURCES,
)
from artana_evidence_api.types.common import JSONObject


class _FullAIOrchestratorProgressStateMixin:
    @staticmethod
    def _backoff_active(resume_at: float | None) -> bool:
        return resume_at is not None and time.monotonic() < resume_at

    @staticmethod
    def _activate_backoff() -> float:
        return time.monotonic() + _PROGRESS_PERSISTENCE_BACKOFF_SECONDS

    def on_progress(
        self,
        *,
        phase: str,
        message: str,
        progress_percent: float,
        completed_steps: int,
        metadata: JSONObject,
        workspace_snapshot: JSONObject,
    ) -> None:
        del message, progress_percent, completed_steps
        if phase == "pubmed_discovery":
            self._update_decision(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                round_number=0,
                source_key="pubmed",
                status="running",
                metadata={"sources": metadata.get("sources", {})},
            )
            self._put_progress_artifact(
                artifact_key=_PUBMED_ARTIFACT_KEY,
                content=_build_live_pubmed_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
        elif phase == "document_ingestion":
            self._update_decision(
                action_type=ResearchOrchestratorActionType.QUERY_PUBMED,
                round_number=0,
                source_key="pubmed",
                status="completed",
                metadata={
                    "pubmed_source_summary": self._source_summary(
                        workspace_snapshot,
                        "pubmed",
                    ),
                },
            )
            self._update_decision(
                action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
                round_number=0,
                source_key="pubmed",
                status="running",
                metadata={"candidate_count": metadata.get("candidate_count", 0)},
            )
            self._put_progress_artifact(
                artifact_key=_PUBMED_ARTIFACT_KEY,
                content=_build_live_pubmed_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
        elif phase == "structured_enrichment":
            self._update_decision(
                action_type=ResearchOrchestratorActionType.DERIVE_DRIVEN_TERMS,
                round_number=0,
                status="completed",
                metadata={
                    "driven_terms": _workspace_list(workspace_snapshot, "driven_terms"),
                    "driven_genes_from_pubmed": _workspace_list(
                        workspace_snapshot,
                        "driven_genes_from_pubmed",
                    ),
                },
            )
            for source_key in _STRUCTURED_ENRICHMENT_SOURCES:
                if not self.sources.get(source_key, False):
                    continue
                self._update_decision(
                    action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                    round_number=0,
                    source_key=source_key,
                    status="running",
                    metadata={
                        "source_summary": self._source_summary(
                            workspace_snapshot, source_key
                        )
                    },
                )
            self._put_progress_artifact(
                artifact_key=_DRIVEN_TERMS_ARTIFACT_KEY,
                content=_build_live_driven_terms_artifact(
                    objective=self.objective,
                    seed_terms=self.seed_terms,
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
                content=_build_live_source_execution_summary(
                    selected_sources=self.sources,
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
        elif phase == "document_extraction":
            self._update_decision(
                action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
                round_number=0,
                source_key="pubmed",
                status="running",
                metadata={
                    "documents_ingested": workspace_snapshot.get(
                        "documents_ingested", 0
                    ),
                    "selected_document_count": metadata.get(
                        "selected_document_count", 0
                    ),
                },
            )
            self._update_structured_source_decisions(
                workspace_snapshot=workspace_snapshot,
                pending_status="running",
            )
            self._put_progress_artifact(
                artifact_key=_PUBMED_ARTIFACT_KEY,
                content=_build_live_pubmed_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_DRIVEN_TERMS_ARTIFACT_KEY,
                content=_build_live_driven_terms_artifact(
                    objective=self.objective,
                    seed_terms=self.seed_terms,
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
                content=_build_live_source_execution_summary(
                    selected_sources=self.sources,
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
        elif phase == "bootstrap":
            self._update_decision(
                action_type=ResearchOrchestratorActionType.INGEST_AND_EXTRACT_PUBMED,
                round_number=0,
                source_key="pubmed",
                status="completed",
                metadata={
                    "documents_ingested": workspace_snapshot.get(
                        "documents_ingested", 0
                    ),
                    "proposal_count": workspace_snapshot.get("proposal_count", 0),
                },
            )
            self._update_structured_source_decisions(
                workspace_snapshot=workspace_snapshot,
                pending_status="running",
            )
            self._update_decision(
                action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                round_number=0,
                status="running",
                metadata={
                    "created_entity_count": metadata.get("created_entity_count", 0),
                    "bootstrap_source_type": workspace_snapshot.get(
                        "bootstrap_source_type"
                    ),
                },
            )
            self._put_progress_artifact(
                artifact_key=_PUBMED_ARTIFACT_KEY,
                content=_build_live_pubmed_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
                content=_build_live_source_execution_summary(
                    selected_sources=self.sources,
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
        elif phase.startswith("chase_round_"):
            round_number = int(phase.removeprefix("chase_round_"))
            self._update_decision(
                action_type=ResearchOrchestratorActionType.RUN_BOOTSTRAP,
                round_number=0,
                status="completed",
                metadata={
                    "bootstrap_run_id": workspace_snapshot.get("bootstrap_run_id"),
                    "bootstrap_summary": _workspace_object(
                        workspace_snapshot,
                        "bootstrap_summary",
                    ),
                },
                stop_reason=(
                    None
                    if workspace_snapshot.get("bootstrap_run_id") is not None
                    else "bootstrap_not_triggered"
                ),
            )
            self._update_chase_round_decisions(
                workspace_snapshot=workspace_snapshot,
                active_round=round_number,
            )
            self._put_progress_artifact(
                artifact_key=_BOOTSTRAP_ARTIFACT_KEY,
                content=_build_live_bootstrap_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_CHASE_ROUNDS_ARTIFACT_KEY,
                content=_build_live_chase_rounds_artifact(
                    workspace_snapshot=workspace_snapshot,
                    status="running",
                ),
            )
        elif phase == "deferred_mondo":
            self._update_chase_round_decisions(
                workspace_snapshot=workspace_snapshot,
                active_round=None,
            )
            self._put_progress_artifact(
                artifact_key=_CHASE_ROUNDS_ARTIFACT_KEY,
                content=_build_live_chase_rounds_artifact(
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_SOURCE_EXECUTION_ARTIFACT_KEY,
                content=_build_live_source_execution_summary(
                    selected_sources=self.sources,
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
        elif phase == "completed":
            self._update_chase_round_decisions(
                workspace_snapshot=workspace_snapshot,
                active_round=None,
            )
            self._update_decision(
                action_type=ResearchOrchestratorActionType.GENERATE_BRIEF,
                round_number=0,
                status=(
                    "completed"
                    if _build_live_brief_metadata(
                        workspace_snapshot=workspace_snapshot,
                    ).get("present")
                    else "skipped"
                ),
                metadata=_build_live_brief_metadata(
                    workspace_snapshot=workspace_snapshot
                ),
                stop_reason=(
                    None
                    if _build_live_brief_metadata(
                        workspace_snapshot=workspace_snapshot,
                    ).get("present")
                    else "brief_not_available"
                ),
            )
            self._put_progress_artifact(
                artifact_key=_BOOTSTRAP_ARTIFACT_KEY,
                content=_build_live_bootstrap_summary(
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_CHASE_ROUNDS_ARTIFACT_KEY,
                content=_build_live_chase_rounds_artifact(
                    workspace_snapshot=workspace_snapshot,
                    status="completed",
                ),
            )
            self._put_progress_artifact(
                artifact_key=_BRIEF_METADATA_ARTIFACT_KEY,
                content=_build_live_brief_metadata(
                    workspace_snapshot=workspace_snapshot
                ),
            )
        self._record_phase(phase=phase, workspace_snapshot=workspace_snapshot)
        self._persist_progress()
        self._enqueue_shadow_checkpoint_updates(
            phase=phase,
            workspace_snapshot=workspace_snapshot,
        )

    def _source_summary(
        self,
        workspace_snapshot: JSONObject,
        source_key: str,
    ) -> JSONObject:
        source_results = _workspace_object(workspace_snapshot, "source_results")
        value = source_results.get(source_key)
        return dict(value) if isinstance(value, dict) else {}

    def _update_decision(
        self,
        *,
        action_type: ResearchOrchestratorActionType,
        round_number: int,
        status: str,
        source_key: str | None = None,
        metadata: JSONObject | None = None,
        stop_reason: str | None = None,
    ) -> None:
        for index, decision in enumerate(self.decisions):
            if (
                decision.action_type == action_type
                and decision.round_number == round_number
                and decision.source_key == source_key
            ):
                merged_metadata = dict(decision.metadata)
                if metadata is not None:
                    merged_metadata.update(metadata)
                updated_fields: dict[str, object] = {
                    "status": status,
                    "metadata": merged_metadata,
                }
                if stop_reason is not None or decision.stop_reason is not None:
                    updated_fields["stop_reason"] = stop_reason
                self.decisions[index] = decision.model_copy(update=updated_fields)
                return

    def _update_structured_source_decisions(
        self,
        *,
        workspace_snapshot: JSONObject,
        pending_status: str,
    ) -> None:
        for source_key in _STRUCTURED_ENRICHMENT_SOURCES:
            if not self.sources.get(source_key, False):
                continue
            source_summary = self._source_summary(workspace_snapshot, source_key)
            decision_status, stop_reason = _source_decision_status(
                source_summary=source_summary,
                pending_status=pending_status,
            )
            self._update_decision(
                action_type=ResearchOrchestratorActionType.RUN_STRUCTURED_ENRICHMENT,
                round_number=0,
                source_key=source_key,
                status=decision_status,
                metadata={"source_summary": source_summary},
                stop_reason=stop_reason,
            )

    def _update_chase_round_decisions(
        self,
        *,
        workspace_snapshot: JSONObject,
        active_round: int | None,
    ) -> None:
        for chase_round in range(1, min(self.max_depth, 2) + 1):
            chase_summary = workspace_snapshot.get(f"chase_round_{chase_round}")
            if isinstance(chase_summary, dict):
                self._update_decision(
                    action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                    round_number=chase_round,
                    status="completed",
                    metadata=_chase_round_metadata_from_workspace(
                        workspace_snapshot=workspace_snapshot,
                        round_number=chase_round,
                    ),
                )
                for index, decision in enumerate(self.decisions):
                    if (
                        decision.action_type
                        == ResearchOrchestratorActionType.RUN_CHASE_ROUND
                        and decision.round_number == chase_round
                    ):
                        self.decisions[index] = decision.model_copy(
                            update={
                                "action_input": _chase_round_action_input_from_workspace(
                                    workspace_snapshot=workspace_snapshot,
                                    round_number=chase_round,
                                )
                            }
                        )
                        break
                continue
            chase_action_input = _chase_round_action_input_from_workspace(
                workspace_snapshot=workspace_snapshot,
                round_number=chase_round,
            )
            chase_metadata = _chase_round_metadata_from_workspace(
                workspace_snapshot=workspace_snapshot,
                round_number=chase_round,
            )
            if active_round == chase_round:
                self._update_decision(
                    action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                    round_number=chase_round,
                    status="running",
                    metadata=(
                        chase_metadata
                        if chase_metadata
                        else {"round_number": chase_round}
                    ),
                )
            else:
                self._update_decision(
                    action_type=ResearchOrchestratorActionType.RUN_CHASE_ROUND,
                    round_number=chase_round,
                    status="skipped",
                    metadata=chase_metadata,
                    stop_reason=_chase_round_stop_reason(chase_metadata),
                )
            for index, decision in enumerate(self.decisions):
                if (
                    decision.action_type
                    == ResearchOrchestratorActionType.RUN_CHASE_ROUND
                    and decision.round_number == chase_round
                ):
                    self.decisions[index] = decision.model_copy(
                        update={"action_input": chase_action_input}
                    )
                    break

    def _put_artifact(self, *, artifact_key: str, content: JSONObject) -> None:
        self.artifact_store.put_artifact(
            space_id=self.space_id,
            run_id=self.run_id,
            artifact_key=artifact_key,
            media_type="application/json",
            content=content,
        )

    def _put_progress_artifact(self, *, artifact_key: str, content: JSONObject) -> None:
        if self._backoff_active(self._progress_artifact_backoff_until):
            return
        try:
            self._put_artifact(artifact_key=artifact_key, content=content)
            self._progress_artifact_backoff_until = None
        except TimeoutError:
            self._progress_artifact_backoff_until = self._activate_backoff()
            _LOGGER.info(
                "Entering full AI orchestrator progress artifact backoff after timeout",
                extra={
                    "run_id": self.run_id,
                    "artifact_key": artifact_key,
                },
            )

    def _record_guarded_decision_proof(
        self,
        *,
        checkpoint_key: str,
        guarded_strategy: str,
        decision_outcome: Literal["allowed", "blocked", "ignored"],
        outcome_reason: str,
        recommendation_payload: JSONObject,
        comparison: JSONObject,
        guarded_action: JSONObject | None = None,
        policy_allowed: bool = False,
        disabled_source_violation: bool = False,
    ) -> ResearchOrchestratorGuardedDecisionProof:
        proof = _build_guarded_decision_proof(
            proof_id=(
                f"guarded-proof-{len(self.guarded_decision_proofs) + 1:03d}-"
                f"{checkpoint_key}"
            ),
            checkpoint_key=checkpoint_key,
            guarded_strategy=guarded_strategy,
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            decision_outcome=decision_outcome,
            outcome_reason=outcome_reason,
            recommendation_payload=recommendation_payload,
            comparison=comparison,
            guarded_action=guarded_action,
            policy_allowed=policy_allowed,
            disabled_source_violation=disabled_source_violation,
        )
        self.guarded_decision_proofs.append(proof)
        self._persist_guarded_decision_proof_state()
        return proof

    def _persist_guarded_decision_proof_state(self) -> None:
        if self.planner_mode is not FullAIOrchestratorPlannerMode.GUARDED:
            return
        guarded_readiness = _guarded_readiness_summary(
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            actions=self.guarded_execution_log,
            proofs=self.guarded_decision_proofs,
        )
        _put_guarded_readiness_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            actions=self.guarded_execution_log,
            proofs=self.guarded_decision_proofs,
        )
        _put_guarded_decision_proof_artifacts(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            proofs=self.guarded_decision_proofs,
        )
        self.artifact_store.patch_workspace(
            space_id=self.space_id,
            run_id=self.run_id,
            patch={
                "guarded_decision_proofs_key": (
                    _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY
                ),
                "guarded_decision_proofs": _guarded_decision_proof_summary(
                    planner_mode=self.planner_mode,
                    guarded_rollout_profile=self.guarded_rollout_profile,
                    guarded_rollout_profile_source=self.guarded_rollout_profile_source,
                    proofs=self.guarded_decision_proofs,
                ),
                "guarded_readiness": guarded_readiness,
            },
        )

    def _persist_guarded_execution_state(
        self,
        *,
        extra_patch: JSONObject | None = None,
    ) -> None:
        _put_guarded_execution_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            actions=self.guarded_execution_log,
        )
        _put_guarded_readiness_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            actions=self.guarded_execution_log,
            proofs=self.guarded_decision_proofs,
        )
        guarded_readiness = _guarded_readiness_summary(
            planner_mode=self.planner_mode,
            guarded_rollout_profile=self.guarded_rollout_profile,
            guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            actions=self.guarded_execution_log,
            proofs=self.guarded_decision_proofs,
        )
        workspace_patch: JSONObject = {
            "shadow_planner_mode": _planner_mode_value(self.planner_mode),
            "planner_execution_mode": _planner_mode_value(self.planner_mode),
            "guarded_rollout_profile": self.guarded_rollout_profile,
            "guarded_rollout_profile_source": self.guarded_rollout_profile_source,
            "guarded_rollout_policy": _guarded_rollout_policy_summary(
                planner_mode=self.planner_mode,
                guarded_rollout_profile=self.guarded_rollout_profile,
                guarded_rollout_profile_source=self.guarded_rollout_profile_source,
            ),
            "guarded_chase_rollout_enabled": self.guarded_chase_rollout_enabled,
            "guarded_execution_log_key": _GUARDED_EXECUTION_ARTIFACT_KEY,
            "guarded_readiness_key": _GUARDED_READINESS_ARTIFACT_KEY,
            "guarded_execution": _guarded_execution_summary(
                planner_mode=self.planner_mode,
                actions=self.guarded_execution_log,
            ),
            "guarded_readiness": guarded_readiness,
        }
        if self.planner_mode is FullAIOrchestratorPlannerMode.GUARDED:
            workspace_patch["guarded_decision_proofs_key"] = (
                _GUARDED_DECISION_PROOF_SUMMARY_ARTIFACT_KEY
            )
            workspace_patch["guarded_decision_proofs"] = (
                _guarded_decision_proof_summary(
                    planner_mode=self.planner_mode,
                    guarded_rollout_profile=self.guarded_rollout_profile,
                    guarded_rollout_profile_source=self.guarded_rollout_profile_source,
                    proofs=self.guarded_decision_proofs,
                )
            )
        if extra_patch is not None:
            workspace_patch.update(extra_patch)
        self.artifact_store.patch_workspace(
            space_id=self.space_id,
            run_id=self.run_id,
            patch=workspace_patch,
        )
        self._persist_guarded_decision_proof_state()

    def _update_guarded_action_verification(
        self,
        *,
        action_type: ResearchOrchestratorActionType,
        verification_status: str,
        verification_reason: str,
        verification_summary: JSONObject,
        verified_at_phase: str,
        guarded_strategy: str | None = None,
        stop_reason: str | None = None,
    ) -> bool:
        for index in range(len(self.guarded_execution_log) - 1, -1, -1):
            action = self.guarded_execution_log[index]
            if action.get("applied_action_type") != action_type.value:
                continue
            if action.get("verification_status") != "pending":
                continue
            if (
                guarded_strategy is not None
                and action.get("guarded_strategy") != guarded_strategy
            ):
                continue
            if stop_reason is not None and action.get("stop_reason") != stop_reason:
                continue
            updated_action = dict(action)
            updated_action["verification_status"] = verification_status
            updated_action["verification_reason"] = verification_reason
            updated_action["verification_summary"] = verification_summary
            updated_action["verified_at_phase"] = verified_at_phase
            self.guarded_execution_log[index] = updated_action
            self._update_guarded_decision_proof_verification(
                updated_action=updated_action,
                verification_status=verification_status,
                verification_reason=verification_reason,
            )
            self._persist_guarded_execution_state()
            return True
        return False

    def _update_guarded_decision_proof_verification(
        self,
        *,
        updated_action: JSONObject,
        verification_status: str,
        verification_reason: str,
    ) -> None:
        action_decision_id = updated_action.get("decision_id")
        action_checkpoint_key = updated_action.get("checkpoint_key")
        action_type = updated_action.get("applied_action_type")
        for index, proof in enumerate(self.guarded_decision_proofs):
            if proof.decision_outcome != "allowed":
                continue
            if (
                proof.decision_id == action_decision_id
                and proof.checkpoint_key == action_checkpoint_key
                and proof.applied_action_type == action_type
            ):
                self.guarded_decision_proofs[index] = proof.model_copy(
                    update={
                        "verification_status": verification_status,
                        "verification_reason": verification_reason,
                        "guarded_action": dict(updated_action),
                    },
                )
                return

    def _persist(self) -> None:
        _put_decision_history_artifact(
            artifact_store=self.artifact_store,
            space_id=self.space_id,
            run_id=self.run_id,
            decisions=self.decisions,
        )
        self.artifact_store.patch_workspace(
            space_id=self.space_id,
            run_id=self.run_id,
            patch={
                "decision_count": len(self.decisions),
                "last_decision_id": self.decisions[-1].decision_id,
            },
        )

    def _persist_progress(self) -> None:
        if self._backoff_active(self._progress_decision_backoff_until):
            return
        try:
            self._persist()
            self._progress_decision_backoff_until = None
        except TimeoutError:
            self._progress_decision_backoff_until = self._activate_backoff()
            _LOGGER.info(
                "Entering full AI orchestrator progress decision backoff after timeout",
                extra={"run_id": self.run_id},
            )

    def _record_phase(self, *, phase: str, workspace_snapshot: JSONObject) -> None:
        self.phase_records.setdefault(phase, []).append(
            {
                "phase": phase,
                "workspace_snapshot": deepcopy(workspace_snapshot),
                "decisions": [
                    decision.model_dump(mode="json") for decision in self.decisions
                ],
            }
        )
