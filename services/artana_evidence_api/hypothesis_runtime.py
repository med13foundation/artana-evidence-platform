"""Harness-owned hypothesis exploration runtime."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionRunner,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.ranking import rank_candidate_claim
from artana_evidence_api.response_serialization import serialize_run_record

if TYPE_CHECKING:
    from artana_evidence_api.agent_contracts import (
        GraphConnectionContract,
        ProposedRelation,
    )
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
    from artana_evidence_api.types.common import JSONObject


@dataclass(frozen=True, slots=True)
class HypothesisCandidateRecord:
    """One hypothesis candidate staged by the harness layer."""

    seed_entity_id: str
    source_entity_id: str
    relation_type: str
    target_entity_id: str
    confidence: float
    evidence_summary: str
    reasoning: str
    agent_run_id: str | None
    source_type: str

    @classmethod
    def from_relation(
        cls,
        *,
        seed_entity_id: str,
        relation: ProposedRelation,
        agent_run_id: str | None,
        source_type: str,
    ) -> HypothesisCandidateRecord:
        """Build one candidate record from a proposed relation."""
        return cls(
            seed_entity_id=seed_entity_id,
            source_entity_id=relation.source_id,
            relation_type=relation.relation_type,
            target_entity_id=relation.target_id,
            confidence=relation.confidence,
            evidence_summary=relation.evidence_summary,
            reasoning=relation.reasoning,
            agent_run_id=agent_run_id,
            source_type=source_type,
        )

    def to_json(self) -> JSONObject:
        """Return the persisted JSON shape for one candidate record."""
        return {
            "seed_entity_id": self.seed_entity_id,
            "source_entity_id": self.source_entity_id,
            "relation_type": self.relation_type,
            "target_entity_id": self.target_entity_id,
            "confidence": self.confidence,
            "evidence_summary": self.evidence_summary,
            "reasoning": self.reasoning,
            "agent_run_id": self.agent_run_id,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class HypothesisExecutionResult:
    """One completed hypothesis run persisted to durable stores."""

    run: HarnessRunRecord
    candidates: tuple[HypothesisCandidateRecord, ...]
    errors: tuple[str, ...]


def _collect_candidates(
    outcomes: list[GraphConnectionContract],
    *,
    max_hypotheses: int,
) -> tuple[list[HypothesisCandidateRecord], list[str]]:
    candidates: list[HypothesisCandidateRecord] = []
    errors: list[str] = []
    for outcome in outcomes:
        if outcome.decision != "generated" and not outcome.proposed_relations:
            errors.append(
                f"seed:{outcome.seed_entity_id}:no_generated_relations:{outcome.decision}",
            )
        for relation in outcome.proposed_relations:
            if len(candidates) >= max_hypotheses:
                break
            candidates.append(
                HypothesisCandidateRecord.from_relation(
                    seed_entity_id=outcome.seed_entity_id,
                    relation=relation,
                    agent_run_id=outcome.agent_run_id,
                    source_type=outcome.source_type,
                ),
            )
    return candidates, errors


def _build_candidate_claim_proposals(
    outcomes: list[GraphConnectionContract],
    *,
    max_hypotheses: int,
) -> tuple[HarnessProposalDraft, ...]:
    proposals: list[HarnessProposalDraft] = []
    for outcome in outcomes:
        for relation in outcome.proposed_relations:
            if len(proposals) >= max_hypotheses:
                break
            ranking = rank_candidate_claim(
                confidence=relation.confidence,
                supporting_document_count=relation.supporting_document_count,
                evidence_reference_count=len(relation.supporting_provenance_ids),
            )
            evidence_bundle: list[JSONObject] = [
                evidence.model_dump(mode="json") for evidence in outcome.evidence
            ]
            evidence_bundle.append(
                {
                    "source_type": "hypothesis_relation",
                    "locator": (
                        f"{relation.source_id}:{relation.relation_type}:{relation.target_id}"
                    ),
                    "excerpt": relation.evidence_summary,
                    "relevance": relation.confidence,
                },
            )
            proposals.append(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="hypothesis_run",
                    source_key=(
                        f"{outcome.seed_entity_id}:{relation.source_id}:"
                        f"{relation.relation_type}:{relation.target_id}"
                    ),
                    title=(
                        f"Candidate claim: {relation.source_id} "
                        f"{relation.relation_type} {relation.target_id}"
                    ),
                    summary=relation.evidence_summary,
                    confidence=relation.confidence,
                    ranking_score=ranking.score,
                    reasoning_path={
                        "seed_entity_id": outcome.seed_entity_id,
                        "source_entity_id": relation.source_id,
                        "relation_type": relation.relation_type,
                        "target_entity_id": relation.target_id,
                        "reasoning": relation.reasoning,
                        "agent_run_id": outcome.agent_run_id,
                    },
                    evidence_bundle=evidence_bundle,
                    payload={
                        "proposed_claim_type": relation.relation_type,
                        "proposed_subject": relation.source_id,
                        "proposed_object": relation.target_id,
                        "evidence_tier": relation.evidence_tier,
                        "supporting_document_count": relation.supporting_document_count,
                        "supporting_provenance_ids": relation.supporting_provenance_ids,
                    },
                    metadata={
                        "seed_entity_id": outcome.seed_entity_id,
                        "agent_run_id": outcome.agent_run_id,
                        "source_type": outcome.source_type,
                        **ranking.metadata,
                    },
                ),
            )
    return tuple(proposals)


def _proposal_artifact_payload(
    proposals: list[HarnessProposalRecord],
) -> JSONObject:
    return {
        "proposal_count": len(proposals),
        "proposal_ids": [proposal.id for proposal in proposals],
        "proposals": [
            {
                "id": proposal.id,
                "run_id": proposal.run_id,
                "proposal_type": proposal.proposal_type,
                "source_kind": proposal.source_kind,
                "source_key": proposal.source_key,
                "title": proposal.title,
                "summary": proposal.summary,
                "status": proposal.status,
                "confidence": proposal.confidence,
                "ranking_score": proposal.ranking_score,
                "payload": proposal.payload,
                "metadata": proposal.metadata,
                "created_at": proposal.created_at.isoformat(),
            }
            for proposal in proposals
        ],
    }


async def execute_hypothesis_run(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    artifact_store: HarnessArtifactStore,
    run_registry: HarnessRunRegistry,
    proposal_store: HarnessProposalStore,
    runtime: GraphHarnessKernelRuntime,
    graph_connection_runner: HarnessGraphConnectionRunner,
) -> HypothesisExecutionResult:
    """Execute one queued hypothesis run and persist durable outputs."""
    from artana_evidence_api.transparency import append_skill_activity

    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="running")
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "running"},
    )
    try:
        outcome_results = []
        for seed_entity_id in seed_entity_ids:
            outcome_result = await graph_connection_runner.run(
                HarnessGraphConnectionRequest(
                    harness_id=run.harness_id,
                    seed_entity_id=seed_entity_id,
                    research_space_id=str(space_id),
                    source_type=source_type,
                    source_id=None,
                    model_id=model_id,
                    relation_types=relation_types,
                    max_depth=max_depth,
                    shadow_mode=True,
                    pipeline_run_id=None,
                    research_space_settings={},
                ),
            )
            append_skill_activity(
                space_id=space_id,
                run_id=run.id,
                skill_names=outcome_result.active_skill_names,
                source_run_id=outcome_result.agent_run_id,
                source_kind="hypothesis_run",
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=runtime,
            )
            outcome_results.append(outcome_result)
        outcomes = [result.contract for result in outcome_results]
    except Exception as exc:  # noqa: BLE001
        run_registry.set_run_status(space_id=space_id, run_id=run.id, status="failed")
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={"status": "failed", "error": str(exc)},
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="hypothesis_error",
            media_type="application/json",
            content={"error": str(exc)},
        )
        raise

    candidates, errors = _collect_candidates(
        outcomes,
        max_hypotheses=max_hypotheses,
    )
    proposal_records = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run.id,
        proposals=_build_candidate_claim_proposals(
            outcomes,
            max_hypotheses=max_hypotheses,
        ),
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="hypothesis_candidates",
        media_type="application/json",
        content={
            "candidates": [candidate.to_json() for candidate in candidates],
            "errors": errors,
        },
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="proposal_pack",
        media_type="application/json",
        content=_proposal_artifact_payload(proposal_records),
    )
    final_run = (
        run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status="completed",
        )
        or run
    )
    run_registry.record_event(
        space_id=space_id,
        run_id=run.id,
        event_type="run.proposals_staged",
        message=f"Staged {len(proposal_records)} proposal(s) for review.",
        payload={
            "proposal_count": len(proposal_records),
            "artifact_key": "proposal_pack",
        },
    )
    store_primary_result_artifact(
        artifact_store=artifact_store,
        space_id=space_id,
        run_id=run.id,
        artifact_key="hypothesis_result",
        content={
            "run": serialize_run_record(run=final_run),
            "candidates": [candidate.to_json() for candidate in candidates],
            "candidate_count": len(candidates),
            "errors": errors,
        },
        status_value="completed",
        result_keys=("hypothesis_candidates", "proposal_pack"),
        workspace_patch={
            "last_hypothesis_candidates_key": "hypothesis_candidates",
            "last_proposal_pack_key": "proposal_pack",
            "hypothesis_candidate_count": len(candidates),
            "proposal_count": len(proposal_records),
            "proposal_counts": {
                "pending_review": len(proposal_records),
                "promoted": 0,
                "rejected": 0,
            },
        },
    )
    return HypothesisExecutionResult(
        run=final_run,
        candidates=tuple(candidates),
        errors=tuple(errors),
    )


__all__ = [
    "HypothesisCandidateRecord",
    "HypothesisExecutionResult",
    "execute_hypothesis_run",
]
