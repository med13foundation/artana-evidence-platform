"""Research-bootstrap candidate proposal and payload helpers."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.claim_fingerprint import compute_claim_fingerprint
from artana_evidence_api.graph_client import GraphServiceClientError
from artana_evidence_api.low_signal_labels import filtered_low_signal_label_reason
from artana_evidence_api.objective_label_filters import (
    filtered_taxonomic_spillover_reason,
    filtered_underanchored_fragment_reason,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
)
from artana_evidence_api.ranking import rank_candidate_claim
from artana_evidence_api.types.common import json_int, json_object_or_empty

if TYPE_CHECKING:
    from artana_evidence_api.agent_contracts import GraphConnectionContract
    from artana_evidence_api.graph_client import GraphTransportBundle
    from artana_evidence_api.graph_snapshot import HarnessGraphSnapshotRecord
    from artana_evidence_api.proposal_store import HarnessProposalStore
    from artana_evidence_api.types.common import JSONObject
    from artana_evidence_api.types.graph_contracts import (
        HypothesisResponse,
        KernelGraphDocumentResponse,
        KernelRelationClaimResponse,
    )

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
    return json_object_or_empty(counts)


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
        "linked_proposal_count": json_int(
            source_inventory.get("linked_proposal_count", 0),
        ),
        "bootstrap_generated_proposal_count": json_int(
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




__all__ = [
    "_build_candidate_claim_proposals",
    "_build_pending_questions",
    "_candidate_pool_embedding_refresh_limit",
    "_collect_candidate_claims",
    "_combine_candidate_proposal_entries",
    "_graph_snapshot_payload",
    "_graph_summary_payload",
    "_load_candidate_entity_display_labels",
    "_load_staged_candidate_claim_proposals",
    "_normalized_unique_strings",
    "_proposal_artifact_payload",
    "_research_brief_payload",
    "_snapshot_claim_ids",
    "_snapshot_relation_ids",
    "_source_inventory_payload",
]
