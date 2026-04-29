"""Review/proposal staging for selected evidence-selection candidates."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.direct_source_search import DirectSourceSearchStore
from artana_evidence_api.evidence_selection_candidates import (
    HIGH_PRIORITY_SCORE_THRESHOLD,
    EvidenceSelectionCandidateDecision,
    record_dedup_key,
    score_from_decision,
)
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.review_item_store import (
    HarnessReviewItemDraft,
    HarnessReviewItemRecord,
    HarnessReviewItemStore,
)
from artana_evidence_api.source_adapters import (
    EvidenceSourceAdapter,
    require_source_adapter,
)
from artana_evidence_api.source_search_handoff import SourceSearchHandoffResponse
from artana_evidence_api.types.common import JSONObject


def stage_selected_records_for_review(
    *,
    space_id: UUID,
    run_id: str,
    selected_records: tuple[EvidenceSelectionCandidateDecision, ...],
    handoffs: tuple[SourceSearchHandoffResponse, ...],
    search_store: DirectSourceSearchStore,
    proposal_store: HarnessProposalStore,
    review_item_store: HarnessReviewItemStore,
) -> tuple[list[HarnessProposalRecord], list[HarnessReviewItemRecord], list[str]]:
    """Stage selected source records as review-gated proposals and review items."""

    handoff_by_record = _handoffs_by_source_record(handoffs)
    proposal_drafts: list[HarnessProposalDraft] = []
    review_item_drafts: list[HarnessReviewItemDraft] = []
    errors: list[str] = []
    for decision in selected_records:
        if decision.record_index is None:
            errors.append(
                "Cannot stage review output for selected record without record_index.",
            )
            continue
        source_key = decision.source_key
        search_id = UUID(decision.search_id)
        record_index = decision.record_index
        source_search = search_store.get(
            space_id=space_id,
            source_key=source_key,
            search_id=search_id,
        )
        if source_search is None:
            errors.append(
                f"Cannot stage review output for missing source search {source_key}/{search_id}.",
            )
            continue
        try:
            record = source_search.records[record_index]
        except IndexError:
            errors.append(
                f"Cannot stage review output for {source_key}/{search_id} record {record_index}.",
            )
            continue
        handoff = handoff_by_record.get(
            record_dedup_key(
                source_key=source_key,
                search_id=search_id,
                record_index=record_index,
            ),
        )
        document_id = str(handoff.target_document_id) if handoff is not None else None
        review_item_drafts.append(
            _review_item_draft_for_decision(
                decision=decision,
                record=record,
                document_id=document_id,
            ),
        )
        proposal_draft = _proposal_draft_for_decision(
            decision=decision,
            record=record,
            document_id=document_id,
        )
        if proposal_draft is not None:
            proposal_drafts.append(proposal_draft)
    proposals = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=tuple(proposal_drafts),
    )
    review_items = review_item_store.create_review_items(
        space_id=space_id,
        run_id=run_id,
        review_items=tuple(review_item_drafts),
    )
    return proposals, review_items, errors


def _handoffs_by_source_record(
    handoffs: tuple[SourceSearchHandoffResponse, ...],
) -> dict[str, SourceSearchHandoffResponse]:
    indexed: dict[str, SourceSearchHandoffResponse] = {}
    for handoff in handoffs:
        indexed[
            record_dedup_key(
                source_key=handoff.source_key,
                search_id=handoff.search_id,
                record_index=handoff.selected_record_index,
            )
        ] = handoff
    return indexed


def _proposal_draft_for_decision(
    *,
    decision: EvidenceSelectionCandidateDecision,
    record: JSONObject,
    document_id: str | None,
) -> HarnessProposalDraft | None:
    source_key = decision.source_key
    adapter = require_source_adapter(source_key)
    title = decision.title or f"{source_key} record"
    score = score_from_decision(decision)
    metadata = _review_metadata(decision=decision, record=record, adapter=adapter)
    payload = decision.to_artifact_payload()
    return HarnessProposalDraft(
        proposal_type=adapter.proposal_type,
        source_kind="direct_source_search",
        source_key=source_key,
        document_id=document_id,
        title=f"Review candidate: {title}",
        summary=adapter.proposal_summary(decision.reason),
        confidence=min(max(score / 10.0, 0.1), 0.95),
        ranking_score=score,
        reasoning_path={
            "selection_reason": decision.reason,
            "matched_terms": list(decision.matched_terms),
            "caveats": list(decision.caveats),
            "source_specific_limitations": list(adapter.limitations),
        },
        evidence_bundle=[metadata],
        payload={
            "selected_record": record,
            "selection": payload,
            "normalized_extraction": metadata["normalized_extraction"],
            "review_gate": "pending_human_review",
        },
        metadata=metadata,
        claim_fingerprint=f"evidence-selection:{decision.record_hash}",
    )


def _review_item_draft_for_decision(
    *,
    decision: EvidenceSelectionCandidateDecision,
    record: JSONObject,
    document_id: str | None,
) -> HarnessReviewItemDraft:
    source_key = decision.source_key
    source_family = decision.source_family
    adapter = require_source_adapter(source_key)
    title = decision.title or f"{source_key} record"
    score = score_from_decision(decision)
    metadata = _review_metadata(decision=decision, record=record, adapter=adapter)
    payload = decision.to_artifact_payload()
    return HarnessReviewItemDraft(
        review_type=adapter.review_type,
        source_family=source_family,
        source_kind="direct_source_search",
        source_key=source_key,
        document_id=document_id,
        title=f"Review selected source record: {title}",
        summary=adapter.review_item_summary(decision.reason),
        priority="high" if score >= HIGH_PRIORITY_SCORE_THRESHOLD else "medium",
        confidence=min(max(score / 10.0, 0.1), 0.95),
        ranking_score=score,
        evidence_bundle=[metadata],
        payload={
            "selected_record": record,
            "selection": payload,
            "normalized_extraction": metadata["normalized_extraction"],
            "review_gate": "pending_human_review",
        },
        metadata=metadata,
        review_fingerprint=f"evidence-selection-review:{decision.record_hash}",
    )


def _review_metadata(
    *,
    decision: EvidenceSelectionCandidateDecision,
    record: JSONObject,
    adapter: EvidenceSourceAdapter,
) -> JSONObject:
    source_capture = record.get("source_capture")
    return {
        "source_search_id": decision.search_id,
        "source_key": decision.source_key,
        "source_family": decision.source_family,
        "selected_record_index": decision.record_index,
        "selected_record_hash": decision.record_hash,
        "selection_reason": decision.reason,
        "relevance_label": decision.relevance_label.value,
        "selection_score": decision.score,
        "matched_terms": list(decision.matched_terms),
        "excluded_terms": list(decision.excluded_terms),
        "caveats": list(decision.caveats),
        "normalized_extraction": adapter.normalized_extraction_payload(record),
        "source_capture": source_capture if isinstance(source_capture, dict) else None,
    }


__all__ = ["stage_selected_records_for_review"]
