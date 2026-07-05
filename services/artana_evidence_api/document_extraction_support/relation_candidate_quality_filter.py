"""Evidence/value filtering for agent-extracted relation candidates."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.document_extraction_contracts import (
    ExtractedRelationCandidate,
)
from artana_evidence_api.document_extraction_relation_taxonomy import (
    canonicalize_extraction_relation_type,
)
from artana_evidence_api.document_extraction_support.evidence_grounding import (
    ground_relation_sentence,
)
from artana_evidence_api.document_extraction_support.evidence_support_verifier import (
    verify_triple_support,
)

RelationCandidateQualityFilterReason = Literal[
    "missing_relation_arguments",
    "support_not_entailed",
    "uncertain_relation_claim",
]

_UNCERTAIN_RELATION_CUE_RE = re.compile(
    r"\b("
    r"hypothesized|may|might|possible|possibly|putative|speculative|"
    r"suggested|suggestive|suggests|tentative|trend|trended|weakly"
    r")\b",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class QualityFilteredRelationCandidate:
    """One candidate removed by evidence/value filtering."""

    candidate_index: int
    candidate: ExtractedRelationCandidate
    reason: RelationCandidateQualityFilterReason


@dataclass(frozen=True, slots=True)
class RelationCandidateQualityFilterResult:
    """Candidate list plus evidence/value filtering telemetry."""

    candidates: tuple[ExtractedRelationCandidate, ...]
    filtered_candidates: tuple[QualityFilteredRelationCandidate, ...]

    @property
    def filtered_count(self) -> int:
        """Return the number of candidates removed by quality filtering."""

        return len(self.filtered_candidates)


def filter_low_value_relation_candidates(
    candidates: tuple[ExtractedRelationCandidate, ...],
) -> RelationCandidateQualityFilterResult:
    """Remove agent candidates that fail evidence/value floors."""

    kept_candidates: list[ExtractedRelationCandidate] = []
    filtered_candidates: list[QualityFilteredRelationCandidate] = []
    for candidate_index, candidate in enumerate(candidates):
        reason = _quality_filter_reason(candidate)
        if reason is None:
            kept_candidates.append(candidate)
            continue
        filtered_candidates.append(
            QualityFilteredRelationCandidate(
                candidate_index=candidate_index,
                candidate=candidate,
                reason=reason,
            ),
        )
    return RelationCandidateQualityFilterResult(
        candidates=tuple(kept_candidates),
        filtered_candidates=tuple(filtered_candidates),
    )


def _quality_filter_reason(
    candidate: ExtractedRelationCandidate,
) -> RelationCandidateQualityFilterReason | None:
    if candidate.relation_governance_status != "canonical":
        return None
    if canonicalize_extraction_relation_type(candidate.relation_type) is None:
        return None
    if _UNCERTAIN_RELATION_CUE_RE.search(candidate.sentence) is not None:
        return "uncertain_relation_claim"

    grounding = ground_relation_sentence(
        source_text=candidate.sentence,
        sentence=candidate.sentence,
        subject=candidate.subject_label,
        object_=candidate.object_label,
    )
    if not (grounding.subject_present and grounding.object_present):
        return "missing_relation_arguments"

    support = verify_triple_support(
        sentence=candidate.sentence,
        subject=candidate.subject_label,
        relation_type=candidate.relation_type,
        object_=candidate.object_label,
    )
    if support.support != "ENTAILS":
        return "support_not_entailed"
    return None


__all__ = [
    "QualityFilteredRelationCandidate",
    "RelationCandidateQualityFilterResult",
    "filter_low_value_relation_candidates",
]
