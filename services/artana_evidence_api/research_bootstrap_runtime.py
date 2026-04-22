"""Research-bootstrap runtime for graph-harness workflows."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID  # noqa: TC003

from artana_evidence_api.agent_contracts import (
    EvidenceItem,
    GraphConnectionContract,
    ProposedRelation,
)
from artana_evidence_api.claim_curation_workflow import (
    ClaimCurationNoEligibleProposalsError,
    execute_claim_curation_run_for_proposals,
)
from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.graph_connection_runtime import (
    HarnessGraphConnectionRequest,
    HarnessGraphConnectionResult,
)
from artana_evidence_api.low_signal_labels import filtered_low_signal_label_reason
from artana_evidence_api.objective_label_filters import (
    filtered_taxonomic_spillover_reason,
    filtered_underanchored_fragment_reason,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
)
from artana_evidence_api.queued_run_support import store_primary_result_artifact
from artana_evidence_api.ranking import rank_candidate_claim
from artana_evidence_api.research_question_policy import (
    should_allow_directional_follow_up,
)
from artana_evidence_api.response_serialization import (
    serialize_graph_snapshot_record,
    serialize_research_state_record,
    serialize_run_record,
)
from artana_evidence_api.tool_runtime import (
    run_capture_graph_snapshot,
    run_list_graph_claims,
    run_list_graph_hypotheses,
)
from artana_evidence_api.transparency import (
    append_skill_activity,
    ensure_run_transparency_seed,
)
from artana_evidence_api.types.graph_contracts import (
    HypothesisListResponse,
    KernelEntityEmbeddingRefreshRequest,
    KernelEntityEmbeddingStatusListResponse,
    KernelGraphDocumentCounts,
    KernelGraphDocumentMeta,
    KernelGraphDocumentResponse,
    KernelRelationClaimListResponse,
    KernelRelationSuggestionListResponse,
    KernelRelationSuggestionRequest,
)
from fastapi import HTTPException, status

from src.domain.agents.contracts.fact_assessment import (
    GroundingLevel,
    MappingStatus,
    SpeculationLevel,
    build_fact_assessment_from_confidence,
)

if TYPE_CHECKING:
    from artana_evidence_api.approval_store import HarnessApprovalStore
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.composition import GraphHarnessKernelRuntime
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.graph_connection_runtime import (
        HarnessGraphConnectionRunner,
    )
    from artana_evidence_api.graph_snapshot import (
        HarnessGraphSnapshotRecord,
        HarnessGraphSnapshotStore,
    )
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.research_state import (
        HarnessResearchStateRecord,
        HarnessResearchStateStore,
    )
    from artana_evidence_api.run_registry import (
        HarnessRunRecord,
        HarnessRunRegistry,
    )
    from artana_evidence_api.schedule_store import HarnessScheduleStore
    from artana_evidence_api.types.common import JSONObject
    from artana_evidence_api.types.graph_contracts import (
        HypothesisResponse,
        KernelRelationClaimResponse,
    )

_TOTAL_PROGRESS_STEPS = 4
_BLANK_SEED_ENTITY_IDS_ERROR = "seed_entity_ids cannot contain blank values"
_INVALID_SEED_ENTITY_IDS_ERROR = "seed_entity_ids must contain valid UUID values"
_GRAPH_CONNECTION_TIMEOUT_SECONDS = 45.0
_CANDIDATE_POOL_EMBEDDING_REFRESH_MIN_LIMIT = 50
_CANDIDATE_POOL_EMBEDDING_REFRESH_MAX_LIMIT = 200
_TOP_STAGED_PROPOSAL_CONTEXT_LIMIT = 5
_PAIR_LABEL_COUNT = 2
_FOLLOW_UP_ANCHOR_PATTERN = re.compile(
    r"\b([A-Za-z][A-Za-z0-9-]*(?:\s+[A-Za-z][A-Za-z0-9-]*){0,3}\s+"
    r"(?:syndrome|disease|disorder|condition|gene|protein|biomarker|"
    r"pathway|complex|receptor|mutation|variant))\b",
    re.IGNORECASE,
)
_CLINICAL_FOCUS_TERMS = frozenset(
    {
        "clinical",
        "cohort",
        "condition",
        "disease",
        "disorder",
        "management",
        "patient",
        "phenotype",
        "rare disease",
        "syndrome",
        "treatment",
    },
)
_CLINICAL_DIRECTION_OPTIONS = (
    "treatment or repurposing leads",
    "disease mechanisms and pathways",
    "phenotypes, natural history, or case reports",
    "related genes, pathways, and overlapping conditions",
)
_SOURCE_BRANDED_ANCHOR_PREFIXES = frozenset(
    {
        "alphafold",
        "clinvar",
        "clinicaltrials",
        "drugbank",
        "hgnc",
        "marrvel",
        "mgi",
        "mondo",
        "pubmed",
        "uniprot",
        "zfin",
    },
)
_BIOLOGY_DIRECTION_OPTIONS = (
    "direct functional evidence",
    "mechanisms and pathways",
    "perturbation or model-system evidence",
    "related genes, proteins, biomarkers, or pathways",
)


@dataclass(frozen=True, slots=True)
class ResearchBootstrapExecutionResult:
    """One completed research-bootstrap execution result."""

    run: HarnessRunRecord
    graph_snapshot: HarnessGraphSnapshotRecord
    research_state: HarnessResearchStateRecord
    research_brief: JSONObject
    graph_summary: JSONObject
    source_inventory: JSONObject
    proposal_records: list[HarnessProposalRecord]
    pending_questions: list[str]
    errors: list[str]
    claim_curation: ResearchBootstrapClaimCurationSummary | None = None


@dataclass(frozen=True, slots=True)
class ResearchBootstrapClaimCurationSummary:
    """One optional governed claim-curation follow-up for bootstrap proposals."""

    status: str
    run_id: str | None
    proposal_ids: tuple[str, ...]
    proposal_count: int
    blocked_proposal_count: int
    pending_approval_count: int
    reason: str | None = None


def _embedding_readiness_payload(
    *,
    status_response: KernelEntityEmbeddingStatusListResponse,
) -> JSONObject:
    ready_count = 0
    pending_count = 0
    failed_count = 0
    stale_count = 0
    skipped_source_ids: list[str] = []
    for status_row in status_response.statuses:
        normalized_state = status_row.state.strip().lower()
        if normalized_state == "ready":
            ready_count += 1
            continue
        skipped_source_ids.append(str(status_row.entity_id))
        if normalized_state == "failed":
            failed_count += 1
        elif normalized_state == "stale":
            stale_count += 1
        else:
            pending_count += 1
    return {
        "statuses": [
            status_row.model_dump(mode="json")
            for status_row in status_response.statuses
        ],
        "embedding_ready_seed_count": ready_count,
        "embedding_pending_seed_count": pending_count,
        "embedding_failed_seed_count": failed_count,
        "embedding_stale_seed_count": stale_count,
        "skipped_relation_suggestion_source_ids": skipped_source_ids,
    }


def _claim_curation_summary_payload(
    summary: ResearchBootstrapClaimCurationSummary,
) -> JSONObject:
    return {
        "status": summary.status,
        "run_id": summary.run_id,
        "proposal_ids": list(summary.proposal_ids),
        "proposal_count": summary.proposal_count,
        "blocked_proposal_count": summary.blocked_proposal_count,
        "pending_approval_count": summary.pending_approval_count,
        "reason": summary.reason,
    }


def _select_bootstrap_claim_curation_proposals(
    *,
    proposals: list[HarnessProposalRecord],
    limit: int,
) -> list[HarnessProposalRecord]:
    bounded_limit = max(limit, 1)
    selected = [
        proposal
        for proposal in proposals
        if proposal.proposal_type == "candidate_claim"
        and proposal.status == "pending_review"
    ]
    return selected[:bounded_limit]


def _maybe_start_bootstrap_claim_curation(  # noqa: PLR0913
    *,
    space_id: UUID,
    proposals: list[HarnessProposalRecord],
    proposal_limit: int,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    proposal_store: HarnessProposalStore,
    approval_store: HarnessApprovalStore | None,
    graph_api_gateway_factory: Callable[[], GraphTransportBundle] | None,
    runtime: GraphHarnessKernelRuntime,
) -> tuple[ResearchBootstrapClaimCurationSummary | None, list[str]]:
    if approval_store is None or graph_api_gateway_factory is None:
        return None, []

    curatable_proposals = _select_bootstrap_claim_curation_proposals(
        proposals=proposals,
        limit=proposal_limit,
    )
    if not curatable_proposals:
        return None, []

    try:
        execution = execute_claim_curation_run_for_proposals(
            space_id=space_id,
            proposals=curatable_proposals,
            title="Claim Curation Harness",
            run_registry=run_registry,
            artifact_store=artifact_store,
            proposal_store=proposal_store,
            approval_store=approval_store,
            graph_api_gateway=graph_api_gateway_factory(),
            runtime=runtime,
        )
    except ClaimCurationNoEligibleProposalsError as exc:
        summary = ResearchBootstrapClaimCurationSummary(
            status="skipped",
            run_id=None,
            proposal_ids=tuple(proposal.id for proposal in curatable_proposals),
            proposal_count=len(curatable_proposals),
            blocked_proposal_count=len(curatable_proposals),
            pending_approval_count=0,
            reason=str(exc),
        )
        return summary, [f"claim_curation:{exc}"]
    except Exception as exc:  # noqa: BLE001
        summary = ResearchBootstrapClaimCurationSummary(
            status="failed",
            run_id=None,
            proposal_ids=tuple(proposal.id for proposal in curatable_proposals),
            proposal_count=len(curatable_proposals),
            blocked_proposal_count=0,
            pending_approval_count=0,
            reason=f"Failed to initialize claim curation: {exc}",
        )
        return summary, [f"claim_curation:Failed to initialize claim curation: {exc}"]

    return (
        ResearchBootstrapClaimCurationSummary(
            status=execution.run.status,
            run_id=execution.run.id,
            proposal_ids=tuple(proposal.id for proposal in curatable_proposals),
            proposal_count=execution.proposal_count,
            blocked_proposal_count=execution.blocked_proposal_count,
            pending_approval_count=execution.pending_approval_count,
            reason=None,
        ),
        [],
    )


def _empty_graph_document(
    *,
    seed_entity_ids: list[str],
    depth: int,
    top_k: int,
) -> KernelGraphDocumentResponse:
    """Build a starter/seeded empty graph document without calling graph tools."""
    return KernelGraphDocumentResponse(
        nodes=[],
        edges=[],
        meta=KernelGraphDocumentMeta(
            mode="seeded" if seed_entity_ids else "starter",
            seed_entity_ids=[
                UUID(seed_entity_id) for seed_entity_id in seed_entity_ids
            ],
            requested_depth=depth,
            requested_top_k=top_k,
            pre_cap_entity_node_count=0,
            pre_cap_canonical_edge_count=0,
            truncated_entity_nodes=False,
            truncated_canonical_edges=False,
            included_claims=True,
            included_evidence=True,
            max_claims=max(25, top_k * 2),
            evidence_limit_per_claim=3,
            counts=KernelGraphDocumentCounts(
                entity_nodes=0,
                claim_nodes=0,
                evidence_nodes=0,
                canonical_edges=0,
                claim_participant_edges=0,
                claim_evidence_edges=0,
            ),
        ),
    )


def _empty_claim_list(*, limit: int) -> KernelRelationClaimListResponse:
    """Return an empty claim-list response for degraded graph bootstrap paths."""
    return KernelRelationClaimListResponse(
        claims=[],
        total=0,
        offset=0,
        limit=limit,
    )


def _empty_hypothesis_list(*, limit: int) -> HypothesisListResponse:
    """Return an empty hypothesis-list response for degraded graph bootstrap paths."""
    return HypothesisListResponse(
        hypotheses=[],
        total=0,
        offset=0,
        limit=limit,
    )


def build_research_bootstrap_run_input_payload(  # noqa: PLR0913
    *,
    objective: str | None,
    seed_entity_ids: list[str],
    source_type: str,
    relation_types: list[str] | None,
    max_depth: int,
    max_hypotheses: int,
    model_id: str | None,
    parent_run_id: str | None = None,
) -> JSONObject:
    """Build the canonical queued-run payload for research bootstrap."""
    return {
        "objective": objective,
        "seed_entity_ids": normalize_bootstrap_seed_entity_ids(seed_entity_ids),
        "source_type": source_type,
        "relation_types": list(relation_types or []),
        "max_depth": max_depth,
        "max_hypotheses": max_hypotheses,
        "model_id": model_id,
        "parent_run_id": parent_run_id,
    }


def queue_research_bootstrap_run(  # noqa: PLR0913
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
    graph_service_status: str,
    graph_service_version: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run_id: str | None = None,
) -> HarnessRunRecord:
    """Create a queued research-bootstrap run without executing it yet."""
    run = run_registry.create_run(
        space_id=space_id,
        harness_id="research-bootstrap",
        title=title,
        input_payload=build_research_bootstrap_run_input_payload(
            objective=objective,
            seed_entity_ids=seed_entity_ids,
            source_type=source_type,
            relation_types=relation_types,
            max_depth=max_depth,
            max_hypotheses=max_hypotheses,
            model_id=model_id,
            parent_run_id=parent_run_id,
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
            "objective": objective,
            "seed_entity_ids": normalize_bootstrap_seed_entity_ids(seed_entity_ids),
        },
    )
    return run


def normalize_bootstrap_seed_entity_ids(seed_entity_ids: list[str] | None) -> list[str]:
    """Return normalized seed entity identifiers for bootstrap runs."""
    if seed_entity_ids is None:
        return []
    normalized_ids: list[str] = []
    seen_ids: set[str] = set()
    for value in seed_entity_ids:
        normalized = value.strip()
        if normalized == "":
            raise ValueError(_BLANK_SEED_ENTITY_IDS_ERROR)
        try:
            UUID(normalized)
        except ValueError as exc:
            raise ValueError(_INVALID_SEED_ENTITY_IDS_ERROR) from exc
        if normalized in seen_ids:
            continue
        normalized_ids.append(normalized)
        seen_ids.add(normalized)
    return normalized_ids


def _serialize_hypothesis_text(hypothesis: HypothesisResponse) -> str:
    if isinstance(hypothesis.claim_text, str) and hypothesis.claim_text.strip() != "":
        return hypothesis.claim_text.strip()
    source_label = hypothesis.source_label or "Unknown source"
    target_label = hypothesis.target_label or "Unknown target"
    return f"{source_label} {hypothesis.relation_type} {target_label}"


def _normalized_unique_strings(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized == "" or normalized in seen_values:
            continue
        normalized_values.append(normalized)
        seen_values.add(normalized)
    return normalized_values


def _candidate_pool_embedding_refresh_limit(
    *,
    seed_entity_ids: list[str],
    linked_proposals: list[HarnessProposalRecord],
) -> int:
    """Return a bounded refresh limit for bootstrap candidate-pool hydration."""
    candidate_hint = max(len(seed_entity_ids), len(linked_proposals))
    return max(
        _CANDIDATE_POOL_EMBEDDING_REFRESH_MIN_LIMIT,
        min(candidate_hint, _CANDIDATE_POOL_EMBEDDING_REFRESH_MAX_LIMIT),
    )


def _normalize_follow_up_anchor(candidate: str) -> str:
    parts = candidate.split()
    if len(parts) <= _PAIR_LABEL_COUNT:
        return candidate.strip()
    return " ".join(parts[-_PAIR_LABEL_COUNT:]).strip()


def _follow_up_anchor_tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token for token in re.findall(r"[A-Za-z0-9-]+", value.casefold()) if token != ""
    )


def _is_source_branded_anchor(candidate: str) -> bool:
    tokens = _follow_up_anchor_tokens(candidate)
    if not tokens:
        return False
    return tokens[0] in _SOURCE_BRANDED_ANCHOR_PREFIXES


def _follow_up_anchor_score(
    *,
    candidate: str,
    objective_tokens: frozenset[str],
    occurrence_index: int,
) -> tuple[int, int, int, int, int]:
    tokens = _follow_up_anchor_tokens(candidate)
    overlap = len({token for token in tokens if token in objective_tokens})
    return (
        0 if _is_source_branded_anchor(candidate) else 1,
        overlap,
        1 if any(character.isdigit() for character in candidate) else 0,
        len(tokens),
        -occurrence_index,
    )


def _should_skip_follow_up_question(
    *,
    objective: str | None,
    subject: str,
    relation_type: str,
    target: str,
) -> bool:
    if (
        relation_type == "EXPRESSED_IN"
        and filtered_taxonomic_spillover_reason(label=target, objective=objective)
        is not None
    ):
        return True
    return (
        filtered_low_signal_label_reason(subject) is not None
        or filtered_underanchored_fragment_reason(
            label=subject,
            objective=objective,
        )
        is not None
        or filtered_low_signal_label_reason(target) is not None
        or filtered_underanchored_fragment_reason(
            label=target,
            objective=objective,
        )
        is not None
    )


def _join_direction_labels(labels: tuple[str, ...]) -> str:
    if len(labels) == 0:
        return ""
    if len(labels) == 1:
        return labels[0]
    if len(labels) == _PAIR_LABEL_COUNT:
        return f"{labels[0]} or {labels[1]}"
    return f"{', '.join(labels[:-1])}, or {labels[-1]}"


def _question_context_texts(
    *,
    objective: str | None,
    proposals: list[HarnessProposalRecord],
) -> list[str]:
    texts: list[str] = []
    if isinstance(objective, str) and objective.strip() != "":
        texts.append(objective.strip())
    for proposal in proposals[:8]:
        proposed_subject_label = proposal.payload.get(
            "proposed_subject_label",
            proposal.metadata.get("subject_label"),
        )
        proposed_object_label = proposal.payload.get(
            "proposed_object_label",
            proposal.metadata.get("object_label"),
        )
        texts.extend(
            value.strip()
            for value in (
                proposal.title,
                proposal.summary,
                proposed_subject_label,
                proposed_object_label,
                proposal.payload.get("proposed_subject"),
                proposal.payload.get("proposed_object"),
            )
            if (
                isinstance(value, str)
                and value.strip() != ""
                and filtered_low_signal_label_reason(value.strip()) is None
                and filtered_underanchored_fragment_reason(
                    label=value.strip(),
                    objective=objective,
                )
                is None
            )
        )
    return texts


def _infer_follow_up_anchor(
    *,
    objective: str | None,
    proposals: list[HarnessProposalRecord],
) -> str:
    objective_tokens = frozenset(
        _follow_up_anchor_tokens(objective)
        if isinstance(objective, str) and objective.strip() != ""
        else ()
    )
    ranked_candidates: list[tuple[tuple[int, int, int, int, int], str]] = []
    seen_candidates: set[str] = set()
    occurrence_index = 0
    for text in _question_context_texts(objective=objective, proposals=proposals):
        matches = [
            _normalize_follow_up_anchor(match.group(1).strip())
            for match in _FOLLOW_UP_ANCHOR_PATTERN.finditer(text)
        ]
        for candidate in matches:
            normalized_candidate = candidate.casefold()
            if normalized_candidate in seen_candidates:
                continue
            seen_candidates.add(normalized_candidate)
            if filtered_low_signal_label_reason(candidate) is not None:
                continue
            if (
                filtered_underanchored_fragment_reason(
                    label=candidate,
                    objective=objective,
                )
                is not None
            ):
                continue
            ranked_candidates.append(
                (
                    _follow_up_anchor_score(
                        candidate=candidate,
                        objective_tokens=objective_tokens,
                        occurrence_index=occurrence_index,
                    ),
                    candidate,
                ),
            )
            occurrence_index += 1
    if ranked_candidates:
        return max(ranked_candidates, key=lambda item: item[0])[1]
    if isinstance(objective, str) and objective.strip() != "":
        return objective.strip()
    if proposals:
        first_subject = proposals[0].payload.get("proposed_subject")
        if (
            isinstance(first_subject, str)
            and first_subject.strip() != ""
            and filtered_low_signal_label_reason(first_subject.strip()) is None
            and filtered_underanchored_fragment_reason(
                label=first_subject.strip(),
                objective=objective,
            )
            is None
        ):
            return first_subject.strip()
    return ""


def _is_clinical_follow_up(
    *,
    objective: str | None,
    proposals: list[HarnessProposalRecord],
) -> bool:
    combined_text = " ".join(
        text.casefold()
        for text in _question_context_texts(objective=objective, proposals=proposals)
    )
    return any(term in combined_text for term in _CLINICAL_FOCUS_TERMS)


def _build_directional_follow_up_question(
    *,
    objective: str | None,
    proposals: list[HarnessProposalRecord],
) -> str | None:
    anchor = _infer_follow_up_anchor(objective=objective, proposals=proposals)
    directions = (
        _CLINICAL_DIRECTION_OPTIONS
        if _is_clinical_follow_up(objective=objective, proposals=proposals)
        else _BIOLOGY_DIRECTION_OPTIONS
    )
    direction_text = _join_direction_labels(directions)
    if direction_text == "":
        return None
    lead = "I finished the initial research pass"
    if anchor != "":
        lead += f" for {anchor}"
    if proposals:
        lead += " and already pulled in starting evidence."
    else:
        lead += "."
    return f"{lead} Which direction should I deepen next: {direction_text}?"


def _collect_candidate_claims(
    outcomes: list[GraphConnectionContract],
    *,
    max_candidates: int,
    soft_fallback_seed_ids: set[str],
    timeout_seed_ids: set[str],
) -> tuple[list[JSONObject], list[str], list[str]]:
    candidates: list[JSONObject] = []
    errors: list[str] = []
    fallback_seed_ids: list[str] = []
    for outcome in outcomes:
        if outcome.decision == "fallback" and not outcome.proposed_relations:
            if outcome.seed_entity_id not in timeout_seed_ids:
                fallback_seed_ids.append(outcome.seed_entity_id)
            if outcome.seed_entity_id not in soft_fallback_seed_ids:
                errors.append(
                    f"seed:{outcome.seed_entity_id}:no_generated_relations:{outcome.decision}",
                )
        elif outcome.decision != "generated" and not outcome.proposed_relations:
            errors.append(
                f"seed:{outcome.seed_entity_id}:no_generated_relations:{outcome.decision}",
            )
        for relation in outcome.proposed_relations:
            if len(candidates) >= max_candidates:
                break
            candidates.append(
                {
                    "seed_entity_id": outcome.seed_entity_id,
                    "source_entity_id": relation.source_id,
                    "relation_type": relation.relation_type,
                    "target_entity_id": relation.target_id,
                    "confidence": relation.confidence,
                    "evidence_summary": relation.evidence_summary,
                    "reasoning": relation.reasoning,
                    "agent_run_id": outcome.agent_run_id,
                    "source_type": outcome.source_type,
                },
            )
    return candidates, errors, _normalized_unique_strings(fallback_seed_ids)


def _proposal_identity_key(record: HarnessProposalRecord) -> str:
    fingerprint = (
        record.claim_fingerprint.strip()
        if isinstance(record.claim_fingerprint, str)
        else ""
    )
    if fingerprint != "":
        return f"fingerprint:{fingerprint}"
    return f"source_key:{record.source_key}"


def _dedupe_proposal_records(
    proposals: list[HarnessProposalRecord],
) -> list[HarnessProposalRecord]:
    deduped: list[HarnessProposalRecord] = []
    seen_keys: set[str] = set()
    for proposal in proposals:
        identity_key = _proposal_identity_key(proposal)
        if identity_key in seen_keys:
            continue
        seen_keys.add(identity_key)
        deduped.append(proposal)
    return deduped


def _candidate_source_for_generated_proposal(record: HarnessProposalRecord) -> str:
    if record.source_kind == "research_bootstrap":
        return "graph_connection"
    return record.source_kind


def _load_staged_candidate_claim_proposals(
    *,
    space_id: UUID,
    proposal_store: HarnessProposalStore,
    preferred_run_id: str | None,
) -> tuple[list[HarnessProposalRecord], JSONObject]:
    preferred_records: list[HarnessProposalRecord] = []
    if isinstance(preferred_run_id, str) and preferred_run_id.strip() != "":
        preferred_records = proposal_store.list_proposals(
            space_id=space_id,
            status="pending_review",
            proposal_type="candidate_claim",
            run_id=preferred_run_id,
        )
    selection_strategy = (
        "current_parent_run" if preferred_records else "space_pending_review"
    )
    matching_records = preferred_records or proposal_store.list_proposals(
        space_id=space_id,
        status="pending_review",
        proposal_type="candidate_claim",
    )
    linked_records = _dedupe_proposal_records(matching_records)
    return linked_records, {
        "selection_strategy": selection_strategy,
        "preferred_run_id": preferred_run_id,
        "total_matching_staged_proposals": len(matching_records),
        "linked_proposal_count": len(linked_records),
        "top_linked_proposals": [
            {"proposal_id": proposal.id, "title": proposal.title}
            for proposal in linked_records[:_TOP_STAGED_PROPOSAL_CONTEXT_LIMIT]
        ],
    }


def _combine_candidate_proposal_entries(
    *,
    linked_proposals: list[HarnessProposalRecord],
    generated_proposals: list[HarnessProposalRecord],
) -> list[tuple[str, HarnessProposalRecord]]:
    entries: list[tuple[str, HarnessProposalRecord]] = []
    seen_keys: set[str] = set()

    def _append_entries(
        proposals: list[HarnessProposalRecord],
        *,
        staged: bool,
    ) -> None:
        for proposal in proposals:
            identity_key = _proposal_identity_key(proposal)
            if identity_key in seen_keys:
                continue
            seen_keys.add(identity_key)
            entries.append(
                (
                    (
                        "staged_proposal"
                        if staged
                        else _candidate_source_for_generated_proposal(proposal)
                    ),
                    proposal,
                ),
            )

    _append_entries(linked_proposals, staged=True)
    _append_entries(generated_proposals, staged=False)
    return entries


def _candidate_source_counts(
    proposal_entries: list[tuple[str, HarnessProposalRecord]],
) -> JSONObject:
    counts: dict[str, int] = {}
    for candidate_source, _proposal in proposal_entries:
        counts[candidate_source] = counts.get(candidate_source, 0) + 1
    return counts


def _load_candidate_entity_display_labels(
    *,
    space_id: UUID,
    graph_api_gateway: GraphTransportBundle,
    outcomes: list[GraphConnectionContract],
) -> dict[str, str]:
    if not hasattr(graph_api_gateway, "list_entities"):
        return {}
    entity_ids = sorted(
        {
            entity_id.strip()
            for outcome in outcomes
            for relation in outcome.proposed_relations
            for entity_id in (relation.source_id, relation.target_id)
            if entity_id.strip() != ""
        },
    )
    if not entity_ids:
        return {}
    try:
        response = graph_api_gateway.list_entities(
            space_id=space_id,
            ids=entity_ids,
            limit=max(len(entity_ids), 1),
        )
    except GraphServiceClientError:
        return {}
    labels: dict[str, str] = {}
    for entity in response.entities:
        entity_id = str(entity.id)
        display_label = (
            entity.display_label.strip()
            if isinstance(entity.display_label, str)
            and entity.display_label.strip() != ""
            else entity_id
        )
        labels[entity_id] = display_label
    return labels


def _resolve_candidate_entity_label(
    entity_id: str,
    entity_display_labels: Mapping[str, str],
) -> str:
    display_label = entity_display_labels.get(entity_id)
    if isinstance(display_label, str) and display_label.strip() != "":
        return display_label.strip()
    return entity_id


def _build_candidate_claim_proposals(
    outcomes: list[GraphConnectionContract],
    *,
    max_candidates: int,
    entity_display_labels: Mapping[str, str] | None = None,
) -> tuple[HarnessProposalDraft, ...]:
    proposals: list[HarnessProposalDraft] = []
    normalized_entity_display_labels = entity_display_labels or {}
    for outcome in outcomes:
        for relation in outcome.proposed_relations:
            if len(proposals) >= max_candidates:
                break
            source_label = _resolve_candidate_entity_label(
                relation.source_id,
                normalized_entity_display_labels,
            )
            target_label = _resolve_candidate_entity_label(
                relation.target_id,
                normalized_entity_display_labels,
            )
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
                    "source_type": "bootstrap_relation",
                    "locator": (
                        f"{relation.source_id}:{relation.relation_type}:"
                        f"{relation.target_id}"
                    ),
                    "excerpt": relation.evidence_summary,
                    "relevance": relation.confidence,
                },
            )
            proposals.append(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="research_bootstrap",
                    source_key=(
                        f"{outcome.seed_entity_id}:{relation.source_id}:"
                        f"{relation.relation_type}:{relation.target_id}"
                    ),
                    title=(
                        f"Candidate claim: {source_label} "
                        f"{relation.relation_type} {target_label}"
                    ),
                    summary=relation.evidence_summary,
                    confidence=relation.confidence,
                    ranking_score=ranking.score,
                    reasoning_path={
                        "seed_entity_id": outcome.seed_entity_id,
                        "source_entity_id": relation.source_id,
                        "source_entity_label": source_label,
                        "relation_type": relation.relation_type,
                        "target_entity_id": relation.target_id,
                        "target_entity_label": target_label,
                        "reasoning": relation.reasoning,
                        "agent_run_id": outcome.agent_run_id,
                    },
                    evidence_bundle=evidence_bundle,
                    payload={
                        "proposed_claim_type": relation.relation_type,
                        "proposed_subject": relation.source_id,
                        "proposed_subject_label": source_label,
                        "proposed_object": relation.target_id,
                        "proposed_object_label": target_label,
                        "evidence_tier": relation.evidence_tier,
                        "supporting_document_count": relation.supporting_document_count,
                        "supporting_provenance_ids": relation.supporting_provenance_ids,
                    },
                    metadata={
                        "seed_entity_id": outcome.seed_entity_id,
                        "agent_run_id": outcome.agent_run_id,
                        "source_type": outcome.source_type,
                        "subject_label": source_label,
                        "object_label": target_label,
                        **ranking.metadata,
                    },
                    claim_fingerprint=compute_claim_fingerprint(
                        source_label,
                        relation.relation_type,
                        target_label,
                    ),
                ),
            )
    return tuple(proposals)


def _proposal_artifact_payload(
    proposal_entries: list[tuple[str, HarnessProposalRecord]],
) -> JSONObject:
    linked_proposal_count = sum(
        1
        for candidate_source, _proposal in proposal_entries
        if candidate_source == "staged_proposal"
    )
    return {
        "proposal_count": len(proposal_entries),
        "linked_proposal_count": linked_proposal_count,
        "bootstrap_generated_proposal_count": (
            len(proposal_entries) - linked_proposal_count
        ),
        "candidate_source_counts": _candidate_source_counts(proposal_entries),
        "proposal_ids": [proposal.id for _source, proposal in proposal_entries],
        "proposals": [
            {
                "id": proposal.id,
                "proposal_id": proposal.id,
                "run_id": proposal.run_id,
                "proposal_type": proposal.proposal_type,
                "source_kind": proposal.source_kind,
                "candidate_source": candidate_source,
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
            for candidate_source, proposal in proposal_entries
        ],
    }


def _graph_summary_payload(  # noqa: PLR0913
    *,
    objective: str | None,
    seed_entity_ids: list[str],
    graph_document: KernelGraphDocumentResponse,
    claims: list[KernelRelationClaimResponse],
    current_hypotheses: list[str],
) -> JSONObject:
    counts = graph_document.meta.counts.model_dump(mode="json")
    return {
        "objective": objective,
        "mode": graph_document.meta.mode,
        "seed_entity_ids": seed_entity_ids,
        "graph_document_counts": counts,
        "graph_node_count": len(graph_document.nodes),
        "graph_edge_count": len(graph_document.edges),
        "claim_count": len(claims),
        "hypothesis_count": len(current_hypotheses),
        "hypotheses": current_hypotheses[:10],
        "sample_labels": [node.label for node in graph_document.nodes[:10]],
    }


def _graph_snapshot_payload(
    *,
    snapshot: HarnessGraphSnapshotRecord,
    graph_summary: JSONObject,
) -> JSONObject:
    return {
        "snapshot_id": snapshot.id,
        "space_id": snapshot.space_id,
        "source_run_id": snapshot.source_run_id,
        "claim_ids": list(snapshot.claim_ids),
        "relation_ids": list(snapshot.relation_ids),
        "graph_document_hash": snapshot.graph_document_hash,
        "summary": graph_summary,
        "metadata": snapshot.metadata,
        "created_at": snapshot.created_at.isoformat(),
        "updated_at": snapshot.updated_at.isoformat(),
    }


def _build_pending_questions(
    *,
    objective: str | None,
    proposals: list[HarnessProposalRecord],
    max_questions: int,
    allow_directional_question: bool,
) -> list[str]:
    questions: list[str] = []
    if allow_directional_question:
        directional_question = _build_directional_follow_up_question(
            objective=objective,
            proposals=proposals,
        )
        if directional_question is not None:
            questions.append(directional_question)
    if not questions and allow_directional_question:
        questions.append("Which seed entities should be expanded next?")
    return _normalized_unique_strings(questions)[:max_questions]


def _source_inventory_payload(
    *,
    claims: list[KernelRelationClaimResponse],
    current_hypotheses: list[str],
    outcomes: list[GraphConnectionContract],
    proposal_entries: list[tuple[str, HarnessProposalRecord]],
    graph_connection_timeout_seed_ids: list[str],
    graph_connection_fallback_seed_ids: list[str],
) -> JSONObject:
    agent_run_ids = _normalized_unique_strings(
        [
            outcome.agent_run_id
            for outcome in outcomes
            if isinstance(outcome.agent_run_id, str)
        ],
    )
    source_types = _normalized_unique_strings(
        [claim.source_type for claim in claims]
        + [outcome.source_type for outcome in outcomes],
    )
    supporting_document_count = sum(
        relation.supporting_document_count
        for outcome in outcomes
        for relation in outcome.proposed_relations
    )
    linked_proposal_count = sum(
        1
        for candidate_source, _proposal in proposal_entries
        if candidate_source == "staged_proposal"
    )
    bootstrap_generated_proposal_count = len(proposal_entries) - linked_proposal_count
    return {
        "graph_claim_count": len(claims),
        "current_hypothesis_count": len(current_hypotheses),
        "source_types": source_types,
        "agent_run_ids": agent_run_ids,
        "supporting_document_count": supporting_document_count,
        "proposal_count": len(proposal_entries),
        "linked_proposal_count": linked_proposal_count,
        "bootstrap_generated_proposal_count": bootstrap_generated_proposal_count,
        "candidate_source_counts": _candidate_source_counts(proposal_entries),
        "graph_connection_timeout_count": len(graph_connection_timeout_seed_ids),
        "graph_connection_timeout_seed_ids": graph_connection_timeout_seed_ids,
        "graph_connection_fallback_seed_ids": graph_connection_fallback_seed_ids,
    }


def _research_brief_payload(  # noqa: PLR0913
    *,
    objective: str | None,
    graph_summary: JSONObject,
    proposal_entries: list[tuple[str, HarnessProposalRecord]],
    pending_questions: list[str],
    source_inventory: JSONObject,
) -> JSONObject:
    return {
        "objective": objective,
        "graph_summary": graph_summary,
        "source_inventory": source_inventory,
        "proposal_count": len(proposal_entries),
        "linked_proposal_count": int(
            source_inventory.get("linked_proposal_count", 0),
        ),
        "bootstrap_generated_proposal_count": int(
            source_inventory.get("bootstrap_generated_proposal_count", 0),
        ),
        "top_candidate_claims": [
            {
                "proposal_id": proposal.id,
                "candidate_source": candidate_source,
                "title": proposal.title,
                "summary": proposal.summary,
                "ranking_score": proposal.ranking_score,
            }
            for candidate_source, proposal in proposal_entries[:5]
        ],
        "pending_questions": pending_questions,
    }


def _graph_connection_timeout_contract(
    *,
    request: HarnessGraphConnectionRequest,
    source_type: str,
) -> GraphConnectionContract:
    return GraphConnectionContract(
        decision="fallback",
        confidence_score=0.0,
        rationale=("Graph connection timed out before relation discovery completed."),
        evidence=[
            EvidenceItem(
                source_type="note",
                locator=f"graph-connection-timeout:{request.seed_entity_id}",
                excerpt=(
                    "Graph connection timed out after "
                    f"{int(_GRAPH_CONNECTION_TIMEOUT_SECONDS)} seconds."
                ),
                relevance=0.2,
            ),
        ],
        source_type=source_type,
        research_space_id=request.research_space_id,
        seed_entity_id=request.seed_entity_id,
        proposed_relations=[],
        rejected_candidates=[],
        shadow_mode=request.shadow_mode,
        agent_run_id=None,
    )


def _graph_suggestion_label_map(
    *,
    graph_api_gateway: GraphTransportBundle,
    space_id: UUID,
    entity_ids: list[str],
) -> dict[str, str]:
    if not entity_ids:
        return {}
    try:
        entities = graph_api_gateway.list_entities(
            space_id=space_id,
            ids=entity_ids,
            limit=max(len(entity_ids), 50),
        )
    except GraphServiceClientError:
        return {}
    return {
        str(entity.id): (
            entity.display_label.strip()
            if isinstance(entity.display_label, str) and entity.display_label.strip()
            else str(entity.id)
        )
        for entity in entities.entities
    }


def _build_graph_connection_result_from_suggestions(
    *,
    request: HarnessGraphConnectionRequest,
    suggestion_response: KernelRelationSuggestionListResponse,
    label_map: dict[str, str],
) -> HarnessGraphConnectionResult:
    seed_entity_id = request.seed_entity_id
    seed_label = label_map.get(seed_entity_id, seed_entity_id)
    if suggestion_response.suggestions:
        proposed_relations = [
            ProposedRelation(
                source_id=str(suggestion.source_entity_id),
                relation_type=suggestion.relation_type,
                target_id=str(suggestion.target_entity_id),
                assessment=build_fact_assessment_from_confidence(
                    confidence=float(suggestion.final_score),
                    confidence_rationale=(
                        "Deterministic bootstrap suggestion from current graph structure."
                    ),
                    grounding_level=GroundingLevel.GRAPH_INFERENCE,
                    mapping_status=MappingStatus.NOT_APPLICABLE,
                    speculation_level=SpeculationLevel.NOT_APPLICABLE,
                ),
                evidence_summary=(
                    f"Graph bootstrap suggests {seed_label} "
                    f"{suggestion.relation_type} "
                    f"{label_map.get(str(suggestion.target_entity_id), str(suggestion.target_entity_id))}."
                ),
                supporting_provenance_ids=[],
                supporting_document_count=0,
                reasoning=(
                    "Deterministic bootstrap relation candidate derived from graph "
                    "structure, neighborhood overlap, and dictionary relation fit."
                ),
            )
            for suggestion in suggestion_response.suggestions
        ]
        contract = GraphConnectionContract(
            decision="generated",
            confidence_score=max(
                relation.confidence for relation in proposed_relations
            ),
            rationale=(
                "Generated graph-connection candidates from deterministic relation "
                "suggestions."
            ),
            evidence=[
                EvidenceItem(
                    source_type="note",
                    locator=f"graph-suggestions:{seed_entity_id}",
                    excerpt=(
                        "Graph service returned "
                        f"{len(proposed_relations)} deterministic relation suggestion(s)."
                    ),
                    relevance=0.6,
                ),
            ],
            source_type=request.source_type or "pubmed",
            research_space_id=request.research_space_id,
            seed_entity_id=seed_entity_id,
            proposed_relations=proposed_relations,
            rejected_candidates=[],
            shadow_mode=request.shadow_mode,
            agent_run_id=None,
        )
        return HarnessGraphConnectionResult(
            contract=contract,
            agent_run_id=None,
            active_skill_names=(),
        )

    matching_skip = next(
        (
            skipped
            for skipped in suggestion_response.skipped_sources
            if str(skipped.entity_id) == seed_entity_id
        ),
        None,
    )
    if matching_skip is not None:
        if matching_skip.reason == "constraint_config_missing":
            rationale = (
                "Graph relation suggestions were skipped because no active "
                "dictionary constraints are configured for this seed entity type."
            )
            excerpt = (
                f"Skipped relation suggestions for {seed_label}: "
                "constraint_config_missing."
            )
        else:
            rationale = (
                "Graph relation suggestions were skipped because the source entity "
                f"embedding is {matching_skip.state}."
            )
            excerpt = (
                f"Skipped relation suggestions for {seed_label}: "
                f"{matching_skip.reason} ({matching_skip.state})."
            )
    else:
        rationale = "Graph relation suggestions returned no safe candidates."
        excerpt = (
            f"No deterministic relation suggestions were returned for {seed_label}."
        )
    contract = GraphConnectionContract(
        decision="fallback",
        confidence_score=0.0,
        rationale=rationale,
        evidence=[
            EvidenceItem(
                source_type="note",
                locator=f"graph-suggestions:{seed_entity_id}",
                excerpt=excerpt,
                relevance=0.2,
            ),
        ],
        source_type=request.source_type or "pubmed",
        research_space_id=request.research_space_id,
        seed_entity_id=seed_entity_id,
        proposed_relations=[],
        rejected_candidates=[],
        shadow_mode=request.shadow_mode,
        agent_run_id=None,
    )
    return HarnessGraphConnectionResult(
        contract=contract,
        agent_run_id=None,
        active_skill_names=(),
    )


def _run_bootstrap_graph_suggestions(
    *,
    graph_api_gateway: GraphTransportBundle,
    space_id: UUID,
    request: HarnessGraphConnectionRequest,
    relation_types: list[str] | None,
    max_candidates: int,
) -> HarnessGraphConnectionResult | None:
    if not hasattr(graph_api_gateway, "suggest_relations"):
        return None
    normalized_relation_types = relation_types if relation_types else None
    try:
        suggestion_response = graph_api_gateway.suggest_relations(
            space_id=space_id,
            request=KernelRelationSuggestionRequest(
                source_entity_ids=[UUID(request.seed_entity_id)],
                limit_per_source=max(1, min(max_candidates, 10)),
                min_score=0.7,
                allowed_relation_types=normalized_relation_types,
                target_entity_types=None,
                exclude_existing_relations=True,
                require_all_ready=False,
            ),
        )
    except GraphServiceClientError:
        return None
    related_entity_ids = _normalized_unique_strings(
        [
            request.seed_entity_id,
            *[
                str(suggestion.target_entity_id)
                for suggestion in suggestion_response.suggestions
            ],
        ],
    )
    label_map = (
        _graph_suggestion_label_map(
            graph_api_gateway=graph_api_gateway,
            space_id=space_id,
            entity_ids=related_entity_ids,
        )
        if hasattr(graph_api_gateway, "list_entities")
        else {}
    )
    return _build_graph_connection_result_from_suggestions(
        request=request,
        suggestion_response=suggestion_response,
        label_map=label_map,
    )


def _snapshot_claim_ids(
    *,
    graph_document: KernelGraphDocumentResponse,
    claims: list[KernelRelationClaimResponse],
    current_hypotheses: list[HypothesisResponse],
) -> list[str]:
    candidate_ids = [
        node.resource_id for node in graph_document.nodes if node.kind == "CLAIM"
    ]
    candidate_ids.extend(str(claim.id) for claim in claims)
    candidate_ids.extend(str(hypothesis.claim_id) for hypothesis in current_hypotheses)
    return _normalized_unique_strings(candidate_ids)


def _snapshot_relation_ids(graph_document: KernelGraphDocumentResponse) -> list[str]:
    candidate_ids = [
        edge.resource_id
        for edge in graph_document.edges
        if edge.kind == "CANONICAL_RELATION" and isinstance(edge.resource_id, str)
    ]
    return _normalized_unique_strings(candidate_ids)


def _graph_document_hash(graph_document: KernelGraphDocumentResponse) -> str:
    payload = graph_document.model_dump(mode="json")
    encoded_payload = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded_payload).hexdigest()


def _mark_failed_run(
    *,
    space_id: UUID,
    run: HarnessRunRecord,
    error_message: str,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
) -> None:
    run_registry.set_run_status(space_id=space_id, run_id=run.id, status="failed")
    run_registry.set_progress(
        space_id=space_id,
        run_id=run.id,
        phase="failed",
        message=error_message,
        progress_percent=0.0,
        completed_steps=0,
        total_steps=_TOTAL_PROGRESS_STEPS,
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
        artifact_key="research_bootstrap_error",
        media_type="application/json",
        content={"error": error_message},
    )


async def execute_research_bootstrap_run(  # noqa: PLR0912, PLR0913, PLR0915
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
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    graph_api_gateway: GraphTransportBundle,
    graph_connection_runner: HarnessGraphConnectionRunner,
    proposal_store: HarnessProposalStore,
    research_state_store: HarnessResearchStateStore,
    graph_snapshot_store: HarnessGraphSnapshotStore,
    schedule_store: HarnessScheduleStore,
    runtime: GraphHarnessKernelRuntime,
    marrvel_enabled: bool = True,  # noqa: ARG001
    approval_store: HarnessApprovalStore | None = None,
    claim_curation_graph_api_gateway_factory: (
        Callable[[], GraphTransportBundle] | None
    ) = None,
    auto_queue_claim_curation: bool = False,
    claim_curation_proposal_limit: int = 5,
    existing_run: HarnessRunRecord | None = None,
    parent_run_id: str | None = None,
) -> ResearchBootstrapExecutionResult:
    """Bootstrap one research space into a durable harness memory state."""
    run: HarnessRunRecord | None = None
    pre_candidate_errors: list[str] = []
    pre_candidate_diagnostics: list[str] = []
    normalized_seed_entity_ids = normalize_bootstrap_seed_entity_ids(seed_entity_ids)

    try:
        graph_health = graph_api_gateway.get_health()
        if existing_run is None:
            run = queue_research_bootstrap_run(
                space_id=space_id,
                title=title,
                objective=objective,
                seed_entity_ids=normalized_seed_entity_ids,
                source_type=source_type,
                relation_types=relation_types,
                max_depth=max_depth,
                max_hypotheses=max_hypotheses,
                model_id=model_id,
                parent_run_id=parent_run_id,
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
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "running",
                "objective": objective,
                "seed_entity_ids": normalized_seed_entity_ids,
            },
        )
        linked_proposal_records, staged_proposal_context = (
            _load_staged_candidate_claim_proposals(
                space_id=space_id,
                proposal_store=proposal_store,
                preferred_run_id=parent_run_id,
            )
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="staged_proposal_context",
            media_type="application/json",
            content=staged_proposal_context,
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "last_staged_proposal_context_key": "staged_proposal_context",
            },
        )
        if normalized_seed_entity_ids:
            try:
                refresh_summary = graph_api_gateway.refresh_entity_embeddings(
                    space_id=space_id,
                    request=KernelEntityEmbeddingRefreshRequest(
                        entity_ids=None,
                        limit=_candidate_pool_embedding_refresh_limit(
                            seed_entity_ids=normalized_seed_entity_ids,
                            linked_proposals=linked_proposal_records,
                        ),
                    ),
                )
            except GraphServiceClientError as exc:
                pre_candidate_diagnostics.append(
                    "Failed to refresh bootstrap candidate embeddings: "
                    f"{exc.detail or str(exc)}",
                )
            else:
                artifact_store.patch_workspace(
                    space_id=space_id,
                    run_id=run.id,
                    patch={
                        "candidate_pool_embedding_refresh_summary": (
                            refresh_summary.model_dump(mode="json")
                        ),
                    },
                )
        try:
            embedding_statuses = graph_api_gateway.list_entity_embedding_status(
                space_id=space_id,
                entity_ids=normalized_seed_entity_ids,
            )
        except GraphServiceClientError as exc:
            pre_candidate_diagnostics.append(
                f"Failed to load seed embedding readiness: {exc.detail or str(exc)}",
            )
        else:
            embedding_readiness = _embedding_readiness_payload(
                status_response=embedding_statuses,
            )
            artifact_store.put_artifact(
                space_id=space_id,
                run_id=run.id,
                artifact_key="embedding_readiness",
                media_type="application/json",
                content=embedding_readiness,
            )
            artifact_store.patch_workspace(
                space_id=space_id,
                run_id=run.id,
                patch={
                    "last_embedding_readiness_key": "embedding_readiness",
                    "embedding_ready_seed_count": embedding_readiness[
                        "embedding_ready_seed_count"
                    ],
                    "embedding_pending_seed_count": embedding_readiness[
                        "embedding_pending_seed_count"
                    ],
                    "embedding_failed_seed_count": embedding_readiness[
                        "embedding_failed_seed_count"
                    ],
                    "embedding_stale_seed_count": embedding_readiness[
                        "embedding_stale_seed_count"
                    ],
                    "skipped_relation_suggestion_source_ids": embedding_readiness[
                        "skipped_relation_suggestion_source_ids"
                    ],
                },
            )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="graph_snapshot",
            message="Capturing graph context snapshot.",
            progress_percent=0.25,
            completed_steps=1,
            total_steps=_TOTAL_PROGRESS_STEPS,
        )
        graph_context_errors: list[str] = []
        graph_context_diagnostics: list[str] = []
        graph_snapshot_step_top_k = max(25, max_hypotheses)
        claim_list_limit = max(50, max_hypotheses * 5)
        hypothesis_list_limit = max(25, max_hypotheses)
        if not normalized_seed_entity_ids:
            graph_document = _empty_graph_document(
                seed_entity_ids=[],
                depth=max_depth,
                top_k=graph_snapshot_step_top_k,
            )
            claim_list = _empty_claim_list(limit=claim_list_limit)
            hypothesis_list = _empty_hypothesis_list(limit=hypothesis_list_limit)
            graph_context_diagnostics.append(
                "Skipped graph context capture because no bootstrap seed entities were available.",
            )
        else:
            try:
                graph_snapshot_payload = run_capture_graph_snapshot(
                    runtime=runtime,
                    run=run,
                    space_id=str(space_id),
                    seed_entity_ids=normalized_seed_entity_ids,
                    depth=max_depth,
                    top_k=graph_snapshot_step_top_k,
                    step_key="bootstrap.graph_snapshot_capture",
                )
                graph_document = KernelGraphDocumentResponse.model_validate_json(
                    json.dumps(
                        graph_snapshot_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    ),
                )
                claim_list = run_list_graph_claims(
                    runtime=runtime,
                    run=run,
                    space_id=str(space_id),
                    claim_status=None,
                    limit=claim_list_limit,
                    step_key="bootstrap.graph_claims",
                )
                hypothesis_list = run_list_graph_hypotheses(
                    runtime=runtime,
                    run=run,
                    space_id=str(space_id),
                    limit=hypothesis_list_limit,
                    step_key="bootstrap.graph_hypotheses",
                )
            except Exception as exc:
                if not linked_proposal_records:
                    raise
                graph_document = _empty_graph_document(
                    seed_entity_ids=normalized_seed_entity_ids,
                    depth=max_depth,
                    top_k=graph_snapshot_step_top_k,
                )
                claim_list = _empty_claim_list(limit=claim_list_limit)
                hypothesis_list = _empty_hypothesis_list(limit=hypothesis_list_limit)
                graph_context_errors.append(
                    "Graph context capture failed; continuing with staged proposals: "
                    f"{exc}",
                )
        current_hypotheses = [
            _serialize_hypothesis_text(hypothesis)
            for hypothesis in hypothesis_list.hypotheses[:10]
        ]
        graph_summary = _graph_summary_payload(
            objective=objective,
            seed_entity_ids=normalized_seed_entity_ids,
            graph_document=graph_document,
            claims=claim_list.claims,
            current_hypotheses=current_hypotheses,
        )
        graph_snapshot = graph_snapshot_store.create_snapshot(
            space_id=space_id,
            source_run_id=run.id,
            claim_ids=_snapshot_claim_ids(
                graph_document=graph_document,
                claims=claim_list.claims,
                current_hypotheses=hypothesis_list.hypotheses,
            ),
            relation_ids=_snapshot_relation_ids(graph_document),
            graph_document_hash=_graph_document_hash(graph_document),
            summary=graph_summary,
            metadata={
                "mode": graph_document.meta.mode,
                "seed_entity_ids": normalized_seed_entity_ids,
            },
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_context_snapshot",
            media_type="application/json",
            content=_graph_snapshot_payload(
                snapshot=graph_snapshot,
                graph_summary=graph_summary,
            ),
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="graph_summary",
            media_type="application/json",
            content=graph_summary,
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.graph_snapshot_captured",
            message=(
                "Captured graph context snapshot."
                if not graph_context_errors
                else "Captured degraded graph context snapshot."
            ),
            payload={
                "snapshot_id": graph_snapshot.id,
                "graph_context_errors": list(graph_context_errors),
                "graph_context_diagnostics": list(graph_context_diagnostics),
            },
            progress_percent=0.25,
        )

        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="candidate_claims",
            message="Generating initial candidate claims from bootstrap seeds.",
            progress_percent=0.55,
            completed_steps=2,
            total_steps=_TOTAL_PROGRESS_STEPS,
            metadata={"snapshot_id": graph_snapshot.id},
        )
        outcome_results = []
        graph_connection_timeout_seed_ids: list[str] = []
        for seed_entity_id in normalized_seed_entity_ids:
            request = HarnessGraphConnectionRequest(
                harness_id="research-bootstrap",
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
            )
            deterministic_outcome = _run_bootstrap_graph_suggestions(
                graph_api_gateway=graph_api_gateway,
                space_id=space_id,
                request=request,
                relation_types=relation_types,
                max_candidates=max_hypotheses,
            )
            if deterministic_outcome is not None:
                outcome_results.append(deterministic_outcome)
                continue
            try:
                outcome_result = await asyncio.wait_for(
                    graph_connection_runner.run(request),
                    timeout=_GRAPH_CONNECTION_TIMEOUT_SECONDS,
                )
            except TimeoutError:
                graph_connection_timeout_seed_ids.append(seed_entity_id)
                outcome_results.append(
                    HarnessGraphConnectionResult(
                        contract=_graph_connection_timeout_contract(
                            request=request,
                            source_type=source_type,
                        ),
                        agent_run_id=None,
                        active_skill_names=(),
                    ),
                )
                continue
            append_skill_activity(
                space_id=space_id,
                run_id=run.id,
                skill_names=outcome_result.active_skill_names,
                source_run_id=outcome_result.agent_run_id,
                source_kind="research_bootstrap",
                artifact_store=artifact_store,
                run_registry=run_registry,
                runtime=runtime,
            )
            outcome_results.append(outcome_result)
        outcomes = [result.contract for result in outcome_results]
        candidate_claims, errors, graph_connection_fallback_seed_ids = (
            _collect_candidate_claims(
                outcomes,
                max_candidates=max_hypotheses,
                soft_fallback_seed_ids=(
                    set(normalized_seed_entity_ids)
                    if linked_proposal_records
                    else set()
                )
                | set(graph_connection_timeout_seed_ids),
                timeout_seed_ids=set(graph_connection_timeout_seed_ids),
            )
        )
        errors = [*pre_candidate_errors, *graph_context_errors, *errors]
        candidate_entity_display_labels = _load_candidate_entity_display_labels(
            space_id=space_id,
            graph_api_gateway=graph_api_gateway,
            outcomes=outcomes,
        )
        generated_proposal_records = proposal_store.create_proposals(
            space_id=space_id,
            run_id=run.id,
            proposals=_build_candidate_claim_proposals(
                outcomes,
                max_candidates=max_hypotheses,
                entity_display_labels=candidate_entity_display_labels,
            ),
        )
        proposal_entries = _combine_candidate_proposal_entries(
            linked_proposals=linked_proposal_records,
            generated_proposals=generated_proposal_records,
        )
        proposal_records = [proposal for _source, proposal in proposal_entries]
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="candidate_claim_pack",
            media_type="application/json",
            content=_proposal_artifact_payload(proposal_entries),
        )

        source_inventory = _source_inventory_payload(
            claims=claim_list.claims,
            current_hypotheses=current_hypotheses,
            outcomes=outcomes,
            proposal_entries=proposal_entries,
            graph_connection_timeout_seed_ids=_normalized_unique_strings(
                graph_connection_timeout_seed_ids,
            ),
            graph_connection_fallback_seed_ids=graph_connection_fallback_seed_ids,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="source_inventory",
            media_type="application/json",
            content=source_inventory,
        )
        existing_state = research_state_store.get_state(space_id=space_id)
        allow_directional_question = should_allow_directional_follow_up(
            objective=objective,
            explored_questions=(
                list(existing_state.explored_questions)
                if existing_state is not None
                else []
            ),
            last_graph_snapshot_id=(
                existing_state.last_graph_snapshot_id
                if existing_state is not None
                else None
            ),
        )
        pending_questions = _build_pending_questions(
            objective=objective,
            proposals=proposal_records,
            max_questions=5,
            allow_directional_question=allow_directional_question,
        )
        research_brief = _research_brief_payload(
            objective=objective,
            graph_summary=graph_summary,
            proposal_entries=proposal_entries,
            pending_questions=pending_questions,
            source_inventory=source_inventory,
        )
        artifact_store.put_artifact(
            space_id=space_id,
            run_id=run.id,
            artifact_key="research_brief",
            media_type="application/json",
            content=research_brief,
        )
        claim_curation_summary: ResearchBootstrapClaimCurationSummary | None = None
        if auto_queue_claim_curation:
            claim_curation_summary, claim_curation_errors = (
                _maybe_start_bootstrap_claim_curation(
                    space_id=space_id,
                    proposals=proposal_records,
                    proposal_limit=claim_curation_proposal_limit,
                    run_registry=run_registry,
                    artifact_store=artifact_store,
                    proposal_store=proposal_store,
                    approval_store=approval_store,
                    graph_api_gateway_factory=claim_curation_graph_api_gateway_factory,
                    runtime=runtime,
                )
            )
            errors = [*errors, *claim_curation_errors]

        active_schedules = [
            schedule.id
            for schedule in schedule_store.list_schedules(space_id=space_id)
            if schedule.status == "active"
        ]
        explored_questions = _normalized_unique_strings(
            (
                list(existing_state.explored_questions)
                if existing_state is not None
                else []
            )
            + (
                [objective]
                if isinstance(objective, str) and objective.strip() != ""
                else []
            ),
        )
        research_state = research_state_store.upsert_state(
            space_id=space_id,
            objective=objective,
            current_hypotheses=current_hypotheses,
            explored_questions=explored_questions,
            pending_questions=pending_questions,
            last_graph_snapshot_id=graph_snapshot.id,
            last_learning_cycle_at=(
                existing_state.last_learning_cycle_at
                if existing_state is not None
                else None
            ),
            active_schedules=active_schedules,
            confidence_model={
                "proposal_ranking_model": "candidate_claim_v1",
                "graph_snapshot_model": "graph_document_v1",
                "bootstrap_runtime_model": "research_bootstrap_v1",
            },
            budget_policy=(
                existing_state.budget_policy if existing_state is not None else {}
            ),
            metadata={
                "last_bootstrap_run_id": run.id,
                "proposal_count": len(proposal_records),
                "candidate_claim_count": len(proposal_records),
                "error_count": len(errors),
                "linked_proposal_count": int(
                    source_inventory.get("linked_proposal_count", 0),
                ),
                "bootstrap_generated_proposal_count": int(
                    source_inventory.get("bootstrap_generated_proposal_count", 0),
                ),
                **(
                    {
                        "claim_curation": _claim_curation_summary_payload(
                            claim_curation_summary,
                        ),
                    }
                    if claim_curation_summary is not None
                    else {}
                ),
            },
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.research_state_updated",
            message="Updated structured research state.",
            payload={
                "last_graph_snapshot_id": graph_snapshot.id,
                "pending_question_count": len(pending_questions),
            },
            progress_percent=0.8,
        )
        run_registry.record_event(
            space_id=space_id,
            run_id=run.id,
            event_type="run.proposals_staged",
            message=(
                f"Assembled {len(proposal_records)} bootstrap candidate claim(s)."
            ),
            payload={
                "proposal_count": len(proposal_records),
                "artifact_key": "candidate_claim_pack",
                "linked_proposal_count": int(
                    source_inventory.get("linked_proposal_count", 0),
                ),
                "bootstrap_generated_proposal_count": int(
                    source_inventory.get("bootstrap_generated_proposal_count", 0),
                ),
            },
            progress_percent=0.8,
        )
        artifact_store.patch_workspace(
            space_id=space_id,
            run_id=run.id,
            patch={
                "status": "completed",
                "last_graph_snapshot_id": graph_snapshot.id,
                "last_graph_context_snapshot_key": "graph_context_snapshot",
                "last_graph_summary_key": "graph_summary",
                "last_research_brief_key": "research_brief",
                "last_source_inventory_key": "source_inventory",
                "last_candidate_claim_pack_key": "candidate_claim_pack",
                "linked_proposal_count": int(
                    source_inventory.get("linked_proposal_count", 0),
                ),
                "bootstrap_generated_proposal_count": int(
                    source_inventory.get("bootstrap_generated_proposal_count", 0),
                ),
                "graph_connection_timeout_count": int(
                    source_inventory.get("graph_connection_timeout_count", 0),
                ),
                "graph_connection_timeout_seed_ids": source_inventory.get(
                    "graph_connection_timeout_seed_ids",
                    [],
                ),
                "graph_connection_fallback_seed_ids": source_inventory.get(
                    "graph_connection_fallback_seed_ids",
                    [],
                ),
                "bootstrap_diagnostics": list(pre_candidate_diagnostics),
                "proposal_count": len(proposal_records),
                "proposal_counts": {
                    "pending_review": len(proposal_records),
                    "promoted": 0,
                    "rejected": 0,
                },
                "pending_question_count": len(pending_questions),
                **(
                    {
                        "claim_curation": _claim_curation_summary_payload(
                            claim_curation_summary,
                        ),
                        "claim_curation_run_id": claim_curation_summary.run_id,
                        "claim_curation_status": claim_curation_summary.status,
                        "claim_curation_pending_approval_count": (
                            claim_curation_summary.pending_approval_count
                        ),
                    }
                    if claim_curation_summary is not None
                    else {}
                ),
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
            artifact_key="research_bootstrap_response",
            content={
                "run": serialize_run_record(run=final_run),
                "graph_snapshot": serialize_graph_snapshot_record(
                    snapshot=graph_snapshot,
                    graph_summary=graph_summary,
                ),
                "research_state": serialize_research_state_record(
                    research_state=research_state,
                ),
                "research_brief": research_brief,
                "graph_summary": graph_summary,
                "source_inventory": source_inventory,
                "proposal_count": len(proposal_records),
                "pending_questions": list(pending_questions),
                "bootstrap_diagnostics": list(pre_candidate_diagnostics),
                "errors": list(errors),
                "claim_curation": (
                    _claim_curation_summary_payload(claim_curation_summary)
                    if claim_curation_summary is not None
                    else None
                ),
            },
            status_value="completed",
            result_keys=(
                "graph_context_snapshot",
                "graph_summary",
                "research_brief",
                "source_inventory",
                "candidate_claim_pack",
            ),
        )
        run_registry.set_progress(
            space_id=space_id,
            run_id=run.id,
            phase="completed",
            message="Research bootstrap completed.",
            progress_percent=1.0,
            completed_steps=_TOTAL_PROGRESS_STEPS,
            total_steps=_TOTAL_PROGRESS_STEPS,
            metadata={
                "snapshot_id": graph_snapshot.id,
                "proposal_count": len(proposal_records),
                "research_state_space_id": research_state.space_id,
            },
        )
        return ResearchBootstrapExecutionResult(
            run=final_run,
            graph_snapshot=graph_snapshot,
            research_state=research_state,
            research_brief=research_brief,
            graph_summary=graph_summary,
            source_inventory=source_inventory,
            proposal_records=proposal_records,
            pending_questions=pending_questions,
            errors=errors,
            claim_curation=claim_curation_summary,
        )
    except GraphServiceClientError:
        if run is not None:
            _mark_failed_run(
                space_id=space_id,
                run=run,
                error_message="Graph API unavailable during research bootstrap.",
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
            detail=f"Research bootstrap run failed: {exc}",
        ) from exc
    finally:
        graph_api_gateway.close()


__all__ = [
    "ResearchBootstrapExecutionResult",
    "build_research_bootstrap_run_input_payload",
    "execute_research_bootstrap_run",
    "normalize_bootstrap_seed_entity_ids",
    "queue_research_bootstrap_run",
]
