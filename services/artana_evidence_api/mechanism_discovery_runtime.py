"""Harness-owned mechanism-discovery runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.proposal_store import HarnessProposalDraft
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.ranking import rank_mechanism_candidate
from artana_evidence_api.response_serialization import (
    serialize_mechanism_candidate,
    serialize_run_record,
)
from artana_evidence_api.tool_catalog import (
    GetReasoningPathToolArgs,
    ListReasoningPathsToolArgs,
)
from artana_evidence_api.tool_runtime import (
    run_get_reasoning_path,
    run_list_reasoning_paths,
)
from artana_evidence_api.transparency import (
    append_skill_activity,
    ensure_run_transparency_seed,
)
from fastapi import HTTPException, status

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.proposal_store import (
        HarnessProposalRecord,
        HarnessProposalStore,
    )
    from artana_evidence_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from artana_evidence_api.types.common import JSONObject
    from artana_evidence_api.types.graph_contracts import (
        KernelReasoningPathDetailResponse,
        KernelReasoningPathResponse,
    )

    from .graph_client import GraphTransportBundle


@dataclass(frozen=True, slots=True)
class HarnessMechanismDiscoveryRequest:
    """One mechanism-discovery execution request."""

    seed_entity_ids: tuple[str, ...]
    max_candidates: int
    max_reasoning_paths: int
    max_path_depth: int
    min_path_confidence: float


@dataclass(frozen=True, slots=True)
class MechanismCandidateRecord:
    """One ranked mechanism candidate."""

    seed_entity_ids: tuple[str, ...]
    end_entity_id: str
    relation_type: str
    source_label: str | None
    target_label: str | None
    source_type: str | None
    target_type: str | None
    path_ids: tuple[str, ...]
    root_claim_ids: tuple[str, ...]
    supporting_claim_ids: tuple[str, ...]
    evidence_reference_count: int
    max_path_confidence: float
    average_path_confidence: float
    average_path_length: float
    ranking_score: float
    ranking_metadata: JSONObject
    summary: str
    hypothesis_statement: str
    hypothesis_rationale: str
    evidence_bundle: tuple[JSONObject, ...]


@dataclass(frozen=True, slots=True)
class MechanismDiscoveryResult:
    """Structured outcome for one mechanism-discovery run."""

    candidates: tuple[MechanismCandidateRecord, ...]
    proposal_drafts: tuple[HarnessProposalDraft, ...]
    scanned_path_count: int


@dataclass(frozen=True, slots=True)
class MechanismDiscoveryRunExecutionResult:
    """Structured outcome for one completed mechanism-discovery run."""

    run: HarnessRunRecord
    candidates: tuple[MechanismCandidateRecord, ...]
    proposal_records: list[HarnessProposalRecord]
    scanned_path_count: int


@dataclass(frozen=True, slots=True)
class _MechanismPathObservation:
    """One reasoning-path observation normalized for ranking."""

    seed_entity_id: str
    path_id: str
    root_claim_id: str
    end_entity_id: str
    relation_type: str
    source_label: str | None
    target_label: str | None
    source_type: str | None
    target_type: str | None
    path_confidence: float
    path_length: int
    supporting_claim_ids: tuple[str, ...]
    evidence_bundle: tuple[JSONObject, ...]


@dataclass(slots=True)
class _CandidateAccumulator:
    """Mutable convergence bucket used while grouping path observations."""

    seed_entity_ids: set[str] = field(default_factory=set)
    path_ids: set[str] = field(default_factory=set)
    root_claim_ids: set[str] = field(default_factory=set)
    supporting_claim_ids: set[str] = field(default_factory=set)
    evidence_by_locator: dict[str, JSONObject] = field(default_factory=dict)
    source_label: str | None = None
    target_label: str | None = None
    source_type: str | None = None
    target_type: str | None = None
    max_path_confidence: float = 0.0
    total_path_confidence: float = 0.0
    total_path_length: int = 0
    path_count: int = 0


def _metadata_string(payload: JSONObject, key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip() != "":
        return value.strip()
    return None


def _candidate_artifact_entry(candidate: MechanismCandidateRecord) -> JSONObject:
    return {
        "seed_entity_ids": list(candidate.seed_entity_ids),
        "end_entity_id": candidate.end_entity_id,
        "relation_type": candidate.relation_type,
        "source_label": candidate.source_label,
        "target_label": candidate.target_label,
        "source_type": candidate.source_type,
        "target_type": candidate.target_type,
        "path_ids": list(candidate.path_ids),
        "root_claim_ids": list(candidate.root_claim_ids),
        "supporting_claim_ids": list(candidate.supporting_claim_ids),
        "evidence_reference_count": candidate.evidence_reference_count,
        "max_path_confidence": candidate.max_path_confidence,
        "average_path_confidence": candidate.average_path_confidence,
        "average_path_length": candidate.average_path_length,
        "ranking_score": candidate.ranking_score,
        "ranking_metadata": candidate.ranking_metadata,
        "summary": candidate.summary,
        "hypothesis_statement": candidate.hypothesis_statement,
        "hypothesis_rationale": candidate.hypothesis_rationale,
        "evidence_bundle": list(candidate.evidence_bundle),
    }


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


def _mark_failed_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    error_message: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> None:
    current_progress = run_registry.get_progress(space_id=space_id, run_id=run.id)
    run_registry.set_run_status(
        space_id=space_id,
        run_id=run.id,
        status="failed",
        existing_progress=current_progress,
    )
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="failed",
        message=error_message,
        progress_percent=(
            current_progress.progress_percent if current_progress is not None else 0.0
        ),
        completed_steps=(
            current_progress.completed_steps if current_progress is not None else 0
        ),
        total_steps=4,
        metadata={"error": error_message},
    )
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "failed", "error": error_message},
    )
    artifact_store.put_artifact(
        space_id=space_id,
        run_id=run.id,
        artifact_key="mechanism_discovery_error",
        media_type="application/json",
        content={"error": error_message},
    )


def build_mechanism_discovery_run_input_payload(
    *,
    seed_entity_ids: tuple[str, ...],
    max_candidates: int,
    max_reasoning_paths: int,
    max_path_depth: int,
    min_path_confidence: float,
) -> JSONObject:
    return {
        "seed_entity_ids": list(seed_entity_ids),
        "max_candidates": max_candidates,
        "max_reasoning_paths": max_reasoning_paths,
        "max_path_depth": max_path_depth,
        "min_path_confidence": min_path_confidence,
    }


def queue_mechanism_discovery_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    seed_entity_ids: tuple[str, ...],
    max_candidates: int,
    max_reasoning_paths: int,
    max_path_depth: int,
    min_path_confidence: float,
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> HarnessRunRecord:
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="mechanism-discovery",
        title=title,
        input_payload=build_mechanism_discovery_run_input_payload(
            seed_entity_ids=seed_entity_ids,
            max_candidates=max_candidates,
            max_reasoning_paths=max_reasoning_paths,
            max_path_depth=max_path_depth,
            min_path_confidence=min_path_confidence,
        ),
        graph_service_status=graph_service_status,
        graph_service_version=graph_service_version,
    )
    artifact_store.seed_for_run(run=run)
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run.id,
        patch={"status": "queued"},
    )
    return run


def _metadata_string_list(payload: JSONObject, key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        return ()
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        trimmed = item.strip()
        if trimmed == "":
            continue
        normalized.append(trimmed)
    return tuple(normalized)


def _candidate_key(observation: _MechanismPathObservation) -> tuple[str, str]:
    return (observation.end_entity_id, observation.relation_type)


def _supporting_claim_ids_from_detail(
    *,
    metadata: JSONObject,
    detail: KernelReasoningPathDetailResponse,
) -> tuple[str, ...]:
    supporting_claim_ids = _metadata_string_list(metadata, "supporting_claim_ids")
    if supporting_claim_ids:
        return supporting_claim_ids
    detail_claims = getattr(detail, "claims", [])
    return tuple(str(claim.id) for claim in detail_claims)


def _build_evidence_bundle(
    *,
    path_id: str,
    relation_type: str,
    target_label: str | None,
    detail: KernelReasoningPathDetailResponse,
) -> tuple[JSONObject, ...]:
    target_display = target_label or "the converging target"
    evidence_bundle: list[JSONObject] = [
        {
            "source_type": "reasoning_path",
            "locator": f"reasoning_path:{path_id}",
            "excerpt": (
                f"Reasoning path supporting a converging {relation_type} "
                f"mechanism around {target_display}."
            ),
            "relevance": detail.path.confidence,
        },
    ]
    for evidence in detail.evidence[:5]:
        sentence = evidence.sentence if isinstance(evidence.sentence, str) else None
        excerpt = sentence.strip() if sentence is not None else ""
        if excerpt == "":
            excerpt = (
                evidence.source_document_ref
                if isinstance(evidence.source_document_ref, str)
                else f"Evidence for {target_display}"
            )
        evidence_bundle.append(
            {
                "source_type": "claim_evidence",
                "locator": f"claim_evidence:{evidence.id}",
                "excerpt": excerpt,
                "relevance": evidence.confidence,
                "claim_id": str(evidence.claim_id),
                "source_document_ref": evidence.source_document_ref,
            },
        )
    return tuple(evidence_bundle)


def _build_path_observation(
    *,
    seed_entity_id: str,
    path: KernelReasoningPathResponse,
    detail: KernelReasoningPathDetailResponse,
) -> _MechanismPathObservation:
    claims = list(detail.claims)
    claims_by_id = {str(claim.id): claim for claim in claims}
    end_claim_id = _metadata_string(path.metadata, "end_claim_id")
    terminal_claim = (
        claims_by_id.get(end_claim_id) if end_claim_id is not None else None
    )
    if terminal_claim is None and claims:
        terminal_claim = claims[-1]
    root_claim = claims_by_id.get(str(path.root_claim_id))
    if root_claim is None and claims:
        root_claim = claims[0]
    relation_type = _metadata_string(path.metadata, "terminal_relation_type")
    if relation_type is None and terminal_claim is not None:
        relation_type = terminal_claim.relation_type
    normalized_relation_type = relation_type or "MECHANISM"
    target_label = (
        terminal_claim.target_label
        if terminal_claim is not None and terminal_claim.target_label is not None
        else None
    )
    return _MechanismPathObservation(
        seed_entity_id=seed_entity_id,
        path_id=str(path.id),
        root_claim_id=str(path.root_claim_id),
        end_entity_id=str(path.end_entity_id),
        relation_type=normalized_relation_type,
        source_label=(
            root_claim.source_label
            if root_claim is not None and root_claim.source_label is not None
            else None
        ),
        target_label=target_label,
        source_type=(
            root_claim.source_type
            if root_claim is not None and isinstance(root_claim.source_type, str)
            else None
        ),
        target_type=(
            terminal_claim.target_type
            if terminal_claim is not None
            and isinstance(terminal_claim.target_type, str)
            else None
        ),
        path_confidence=path.confidence,
        path_length=path.path_length,
        supporting_claim_ids=_supporting_claim_ids_from_detail(
            metadata=path.metadata,
            detail=detail,
        ),
        evidence_bundle=_build_evidence_bundle(
            path_id=str(path.id),
            relation_type=normalized_relation_type,
            target_label=target_label,
            detail=detail,
        ),
    )


def _statement_for_candidate(
    *,
    relation_type: str,
    target_display: str,
    source_label: str | None,
    seed_count: int,
) -> str:
    if seed_count == 1 and isinstance(source_label, str) and source_label.strip() != "":
        source_display = source_label.strip()
    else:
        source_display = "the selected seed entities"
    return (
        f"{target_display} is a plausible converging {relation_type.lower()} "
        f"mechanism for {source_display}."
    )


def _rationale_for_candidate(
    *,
    path_count: int,
    supporting_claim_count: int,
    evidence_reference_count: int,
    max_path_confidence: float,
    average_path_length: float,
) -> str:
    return (
        f"Supported by {path_count} reasoning path(s), "
        f"{supporting_claim_count} supporting claim(s), and "
        f"{evidence_reference_count} evidence reference(s); max path confidence "
        f"{max_path_confidence:.2f}, average path length {average_path_length:.2f}."
    )


def _build_candidate_record(
    *,
    end_entity_id: str,
    relation_type: str,
    accumulator: _CandidateAccumulator,
) -> MechanismCandidateRecord:
    path_count = max(accumulator.path_count, 1)
    average_path_confidence = accumulator.total_path_confidence / path_count
    average_path_length = accumulator.total_path_length / path_count
    ranking = rank_mechanism_candidate(
        confidence=accumulator.max_path_confidence,
        path_count=path_count,
        supporting_claim_count=len(accumulator.supporting_claim_ids),
        evidence_reference_count=len(accumulator.evidence_by_locator),
        average_path_length=average_path_length,
    )
    target_display = accumulator.target_label or end_entity_id
    summary = (
        f"{path_count} mechanism path(s) from "
        f"{len(accumulator.seed_entity_ids)} seed entity(ies) converge on "
        f"{target_display} via {relation_type}."
    )
    hypothesis_statement = _statement_for_candidate(
        relation_type=relation_type,
        target_display=target_display,
        source_label=accumulator.source_label,
        seed_count=len(accumulator.seed_entity_ids),
    )
    hypothesis_rationale = _rationale_for_candidate(
        path_count=path_count,
        supporting_claim_count=len(accumulator.supporting_claim_ids),
        evidence_reference_count=len(accumulator.evidence_by_locator),
        max_path_confidence=accumulator.max_path_confidence,
        average_path_length=average_path_length,
    )
    ordered_evidence = tuple(
        accumulator.evidence_by_locator[locator]
        for locator in sorted(accumulator.evidence_by_locator)
    )
    return MechanismCandidateRecord(
        seed_entity_ids=tuple(sorted(accumulator.seed_entity_ids)),
        end_entity_id=end_entity_id,
        relation_type=relation_type,
        source_label=accumulator.source_label,
        target_label=accumulator.target_label,
        source_type=accumulator.source_type,
        target_type=accumulator.target_type,
        path_ids=tuple(sorted(accumulator.path_ids)),
        root_claim_ids=tuple(sorted(accumulator.root_claim_ids)),
        supporting_claim_ids=tuple(sorted(accumulator.supporting_claim_ids)),
        evidence_reference_count=len(accumulator.evidence_by_locator),
        max_path_confidence=round(accumulator.max_path_confidence, 6),
        average_path_confidence=round(average_path_confidence, 6),
        average_path_length=round(average_path_length, 6),
        ranking_score=ranking.score,
        ranking_metadata=ranking.metadata,
        summary=summary,
        hypothesis_statement=hypothesis_statement,
        hypothesis_rationale=hypothesis_rationale,
        evidence_bundle=ordered_evidence,
    )


def _accumulate_candidates(
    observations: tuple[_MechanismPathObservation, ...],
) -> tuple[MechanismCandidateRecord, ...]:
    accumulators: dict[tuple[str, str], _CandidateAccumulator] = {}
    for observation in observations:
        key = _candidate_key(observation)
        accumulator = accumulators.setdefault(key, _CandidateAccumulator())
        accumulator.seed_entity_ids.add(observation.seed_entity_id)
        accumulator.path_ids.add(observation.path_id)
        accumulator.root_claim_ids.add(observation.root_claim_id)
        accumulator.supporting_claim_ids.update(observation.supporting_claim_ids)
        accumulator.path_count += 1
        accumulator.total_path_confidence += observation.path_confidence
        accumulator.total_path_length += observation.path_length
        accumulator.max_path_confidence = max(
            accumulator.max_path_confidence,
            observation.path_confidence,
        )
        if accumulator.source_label is None and observation.source_label is not None:
            accumulator.source_label = observation.source_label
        if accumulator.target_label is None and observation.target_label is not None:
            accumulator.target_label = observation.target_label
        if accumulator.source_type is None and observation.source_type is not None:
            accumulator.source_type = observation.source_type
        if accumulator.target_type is None and observation.target_type is not None:
            accumulator.target_type = observation.target_type
        for evidence_item in observation.evidence_bundle:
            locator = evidence_item.get("locator")
            if (
                isinstance(locator, str)
                and locator not in accumulator.evidence_by_locator
            ):
                accumulator.evidence_by_locator[locator] = evidence_item
    candidates = [
        _build_candidate_record(
            end_entity_id=end_entity_id,
            relation_type=relation_type,
            accumulator=accumulator,
        )
        for (end_entity_id, relation_type), accumulator in accumulators.items()
    ]
    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                -candidate.ranking_score,
                -candidate.max_path_confidence,
                -len(candidate.path_ids),
                candidate.average_path_length,
                candidate.end_entity_id,
                candidate.relation_type,
            ),
        ),
    )


def _proposal_draft_from_candidate(
    candidate: MechanismCandidateRecord,
) -> HarnessProposalDraft:
    target_display = candidate.target_label or candidate.end_entity_id
    return HarnessProposalDraft(
        proposal_type="mechanism_candidate",
        source_kind="mechanism_discovery_run",
        source_key=(
            f"{candidate.end_entity_id}:{candidate.relation_type}:"
            f"{','.join(candidate.seed_entity_ids)}"
        ),
        title=f"Mechanism candidate: {target_display} via {candidate.relation_type}",
        summary=candidate.summary,
        confidence=candidate.max_path_confidence,
        ranking_score=candidate.ranking_score,
        reasoning_path={
            "seed_entity_ids": list(candidate.seed_entity_ids),
            "end_entity_id": candidate.end_entity_id,
            "relation_type": candidate.relation_type,
            "path_ids": list(candidate.path_ids),
            "root_claim_ids": list(candidate.root_claim_ids),
            "supporting_claim_ids": list(candidate.supporting_claim_ids),
        },
        evidence_bundle=list(candidate.evidence_bundle),
        payload={
            "hypothesis_statement": candidate.hypothesis_statement,
            "hypothesis_rationale": candidate.hypothesis_rationale,
            "seed_entity_ids": list(candidate.seed_entity_ids),
            "source_type": "mechanism_discovery",
            "end_entity_id": candidate.end_entity_id,
            "relation_type": candidate.relation_type,
            "target_label": candidate.target_label,
        },
        metadata={
            "source_label": candidate.source_label,
            "target_label": candidate.target_label,
            "source_type": candidate.source_type,
            "target_type": candidate.target_type,
            "path_count": len(candidate.path_ids),
            "evidence_reference_count": candidate.evidence_reference_count,
            **candidate.ranking_metadata,
        },
    )


def execute_mechanism_discovery(
    *,
    runtime: GraphHarnessKernelRuntime,
    run: HarnessRunRecord,
    space_id: UUID,
    request: HarnessMechanismDiscoveryRequest,
) -> MechanismDiscoveryResult:
    """Read reasoning paths, rank converging mechanisms, and stage proposals."""
    detail_cache: dict[str, KernelReasoningPathDetailResponse] = {}
    observations: list[_MechanismPathObservation] = []
    for seed_entity_id in request.seed_entity_ids:
        path_response = run_list_reasoning_paths(
            runtime=runtime,
            run=run,
            arguments=ListReasoningPathsToolArgs(
                space_id=str(space_id),
                start_entity_id=seed_entity_id,
                status="ACTIVE",
                path_kind="MECHANISM",
                limit=request.max_reasoning_paths,
            ),
            step_key=f"mechanism_discovery.paths.{seed_entity_id}",
        )
        for path in path_response.paths:
            if path.confidence < request.min_path_confidence:
                continue
            if path.path_length > request.max_path_depth:
                continue
            path_id = str(path.id)
            detail = detail_cache.get(path_id)
            if detail is None:
                detail = run_get_reasoning_path(
                    runtime=runtime,
                    run=run,
                    arguments=GetReasoningPathToolArgs(
                        space_id=str(space_id),
                        path_id=str(path.id),
                    ),
                    step_key=f"mechanism_discovery.path_detail.{path_id}",
                )
                detail_cache[path_id] = detail
            observations.append(
                _build_path_observation(
                    seed_entity_id=seed_entity_id,
                    path=path,
                    detail=detail,
                ),
            )
    ranked_candidates = _accumulate_candidates(tuple(observations))
    selected_candidates = ranked_candidates[: request.max_candidates]
    return MechanismDiscoveryResult(
        candidates=selected_candidates,
        proposal_drafts=tuple(
            _proposal_draft_from_candidate(candidate)
            for candidate in selected_candidates
        ),
        scanned_path_count=len(observations),
    )


def execute_mechanism_discovery_run(  # noqa: PLR0913
    *,
    space_id: UUID,
    title: str,
    seed_entity_ids: tuple[str, ...],
    max_candidates: int,
    max_reasoning_paths: int,
    max_path_depth: int,
    min_path_confidence: float,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    graph_api_gateway: GraphTransportBundle,
    proposal_store: HarnessProposalStore,
    runtime: GraphHarnessKernelRuntime,
    existing_run: HarnessRunRecord | None = None,
) -> MechanismDiscoveryRunExecutionResult:
    """Execute one mechanism-discovery run against the supplied run id."""
    run: HarnessRunRecord | None = existing_run
    try:
        graph_health = graph_api_gateway.get_health()
        if existing_run is None:
            run = queue_mechanism_discovery_run(
                space_id=space_id,
                title=title,
                seed_entity_ids=seed_entity_ids,
                max_candidates=max_candidates,
                max_reasoning_paths=max_reasoning_paths,
                max_path_depth=max_path_depth,
                min_path_confidence=min_path_confidence,
                graph_service_status=graph_health.status,
                graph_service_version=graph_health.version,
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
            phase="reasoning_read",
            message="Reading reasoning paths for converging mechanisms.",
            progress_percent=0.15,
            completed_steps=0,
            total_steps=4,
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={"status": "running"},
        )

        result = execute_mechanism_discovery(
            runtime=runtime,
            run=run,
            space_id=space_id,
            request=HarnessMechanismDiscoveryRequest(
                seed_entity_ids=seed_entity_ids,
                max_candidates=max_candidates,
                max_reasoning_paths=max_reasoning_paths,
                max_path_depth=max_path_depth,
                min_path_confidence=min_path_confidence,
            ),
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="ranking",
            message="Ranking converging mechanism candidates.",
            progress_percent=0.7,
            completed_steps=2,
            total_steps=4,
            metadata={
                "scanned_path_count": result.scanned_path_count,
                "candidate_count": len(result.candidates),
            },
        )
        proposal_records = proposal_store.create_proposals(
            space_id=space_id,
            run_id=run.id,
            proposals=result.proposal_drafts,
        )
        active_skill_names = ["graph_harness.path_analysis"]
        if proposal_records:
            active_skill_names.append("graph_harness.hypothesis_staging")
        append_skill_activity(
            space_id=space_id,
            run_id=run.id,
            skill_names=tuple(active_skill_names),
            source_run_id=run.id,
            source_kind="mechanism_discovery",
            artifact_store=artifact_store,
            run_registry=run_registry,
            runtime=runtime,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="mechanism_candidates",
            media_type="application/json",
            content={
                "candidate_count": len(result.candidates),
                "scanned_path_count": result.scanned_path_count,
                "candidates": [
                    _candidate_artifact_entry(candidate)
                    for candidate in result.candidates
                ],
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="mechanism_score_report",
            media_type="application/json",
            content={
                "candidate_count": len(result.candidates),
                "scanned_path_count": result.scanned_path_count,
                "ranking": [
                    {
                        "end_entity_id": candidate.end_entity_id,
                        "relation_type": candidate.relation_type,
                        "ranking_score": candidate.ranking_score,
                        "ranking_metadata": candidate.ranking_metadata,
                        "path_count": len(candidate.path_ids),
                        "supporting_claim_count": len(candidate.supporting_claim_ids),
                        "evidence_reference_count": candidate.evidence_reference_count,
                    }
                    for candidate in result.candidates
                ],
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="candidate_hypothesis_pack",
            media_type="application/json",
            content=_proposal_artifact_payload(proposal_records),
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="artifact_write",
            message="Writing mechanism artifacts and staged hypotheses.",
            progress_percent=0.9,
            completed_steps=3,
            total_steps=4,
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "completed",
                "last_mechanism_candidates_key": "mechanism_candidates",
                "last_mechanism_score_report_key": "mechanism_score_report",
                "last_candidate_hypothesis_pack_key": "candidate_hypothesis_pack",
                "mechanism_candidate_count": len(result.candidates),
                "proposal_count": len(proposal_records),
                "proposal_counts": {
                    "pending_review": len(proposal_records),
                    "promoted": 0,
                    "rejected": 0,
                },
                "scanned_reasoning_path_count": result.scanned_path_count,
            },
        )
        updated_run = run_registry.set_run_status(
            space_id=space_id,
            run_id=run.id,
            status="completed",
        )
        final_run = run if updated_run is None else updated_run
        store_primary_result_artifact(
            artifact_store=artifact_store,
            space_id=space_id,
            run_id=run.id,
            artifact_key="mechanism_discovery_response",
            content={
                "run": serialize_run_record(run=final_run),
                "candidates": [
                    serialize_mechanism_candidate(candidate=candidate)
                    for candidate in result.candidates
                ],
                "candidate_count": len(result.candidates),
                "proposal_count": len(proposal_records),
                "scanned_path_count": result.scanned_path_count,
            },
            status_value="completed",
            result_keys=(
                "mechanism_candidates",
                "mechanism_score_report",
                "candidate_hypothesis_pack",
            ),
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="completed",
            message="Mechanism discovery run completed.",
            progress_percent=1.0,
            completed_steps=4,
            total_steps=4,
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.mechanism_candidates_ranked",
            message=f"Ranked {len(result.candidates)} mechanism candidate(s).",
            payload={
                "candidate_count": len(result.candidates),
                "scanned_path_count": result.scanned_path_count,
                "proposal_count": len(proposal_records),
            },
            progress_percent=1.0,
        )
        return MechanismDiscoveryRunExecutionResult(
            run=final_run,
            candidates=result.candidates,
            proposal_records=proposal_records,
            scanned_path_count=result.scanned_path_count,
        )
    except GraphServiceClientError:
        if run is not None:
            _mark_failed_run(
                space_id=space_id,
                run=run,
                error_message="Graph API unavailable during mechanism discovery.",
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        raise
    except Exception as exc:
        if run is not None:
            _mark_failed_run(
                space_id=space_id,
                run=run,
                error_message=str(exc),
                run_registry=run_registry,
                artifact_store=artifact_store,
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Mechanism discovery run failed: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()


__all__ = [
    "HarnessMechanismDiscoveryRequest",
    "MechanismCandidateRecord",
    "MechanismDiscoveryRunExecutionResult",
    "MechanismDiscoveryResult",
    "build_mechanism_discovery_run_input_payload",
    "execute_mechanism_discovery_run",
    "execute_mechanism_discovery",
    "queue_mechanism_discovery_run",
]
