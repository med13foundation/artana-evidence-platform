"""Handoff creation for selected evidence-selection candidates."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.direct_source_search import DirectSourceSearchStore
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateDecision,
)
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.source_search_handoff import (
    SourceSearchHandoffConflictError,
    SourceSearchHandoffNotFoundError,
    SourceSearchHandoffRequest,
    SourceSearchHandoffResponse,
    SourceSearchHandoffSelectionError,
    SourceSearchHandoffService,
    SourceSearchHandoffStore,
    SourceSearchHandoffUnsupportedError,
)


def create_selected_handoffs(
    *,
    space_id: UUID,
    created_by: UUID | str,
    selected_records: tuple[EvidenceSelectionCandidateDecision, ...],
    search_store: DirectSourceSearchStore,
    handoff_store: SourceSearchHandoffStore | None,
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
) -> tuple[list[SourceSearchHandoffResponse], list[str]]:
    """Create guarded handoffs for selected source-search records."""

    if handoff_store is None:
        return [], ["Handoff store is unavailable."]
    service = SourceSearchHandoffService(
        search_store=search_store,
        handoff_store=handoff_store,
        document_store=document_store,
        run_registry=run_registry,
    )
    handoffs: list[SourceSearchHandoffResponse] = []
    errors: list[str] = []
    for decision in selected_records:
        if decision.record_index is None or decision.record_hash is None:
            errors.append(
                "Cannot create source handoff for a selected record without "
                "record_index and record_hash.",
            )
            continue
        source_key = decision.source_key
        search_id = UUID(decision.search_id)
        try:
            handoff = service.create_handoff(
                space_id=space_id,
                source_key=source_key,
                search_id=search_id,
                created_by=created_by,
                request=SourceSearchHandoffRequest(
                    record_index=decision.record_index,
                    idempotency_key=(
                        "evidence-selection:"
                        f"{source_key}:{search_id}:{decision.record_index}"
                    ),
                    metadata={
                        "selected_by": "evidence-selection",
                        "selected_record_hash": decision.record_hash,
                    },
                ),
            )
        except (
            SourceSearchHandoffConflictError,
            SourceSearchHandoffNotFoundError,
            SourceSearchHandoffSelectionError,
            SourceSearchHandoffUnsupportedError,
            ValueError,
        ) as exc:
            errors.append(
                "Failed to hand off "
                f"{source_key}/{search_id} record {decision.record_index}: {exc}",
            )
            continue
        handoffs.append(handoff)
    return handoffs, errors


__all__ = ["create_selected_handoffs"]
