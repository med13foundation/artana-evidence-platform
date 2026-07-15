"""Apply governed relation-type decisions to extraction candidates."""

from __future__ import annotations

from dataclasses import replace

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    normalize_relation_type_label,
)
from artana_evidence_api.document_extraction_support.claim_frames import (
    replace_claim_frame_projection,
)
from artana_evidence_api.relation_type_resolver import (
    RelationTypeAction,
    RelationTypeDecision,
)


def apply_relation_resolution_decisions(
    *,
    candidates: list[ExtractedRelationCandidate],
    decisions: dict[str, RelationTypeDecision],
) -> list[ExtractedRelationCandidate]:
    """Return candidates whose raw relation types are governed for use."""

    resolved_candidates: list[ExtractedRelationCandidate] = []
    for candidate in candidates:
        key = normalize_relation_type_label(candidate.relation_type)
        decision = decisions.get(key)
        if decision is None:
            resolved_candidates.append(candidate)
            continue
        if decision.action in {
            RelationTypeAction.MAP_TO_EXISTING,
            RelationTypeAction.TYPO_CORRECTION,
        }:
            resolved_candidates.append(
                replace(
                    candidate,
                    relation_type=decision.canonical_type,
                    claim_frame=replace_claim_frame_projection(
                        candidate.claim_frame,
                        predicate=decision.canonical_type,
                    ),
                ),
            )
    return resolved_candidates


__all__ = ["apply_relation_resolution_decisions"]
