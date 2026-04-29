"""Candidate contracts and helpers for evidence-selection runs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from artana_evidence_api.types.common import JSONObject, JSONValue

HIGH_PRIORITY_SCORE_THRESHOLD = 5.0
MIN_SELECTION_SCORE = 4.0


class EvidenceSelectionDecisionState(StrEnum):
    """Typed candidate decision states used before artifact serialization."""

    SELECTED = "selected"
    SKIPPED = "skipped"
    DEFERRED = "deferred"


class EvidenceSelectionDecisionRelevance(StrEnum):
    """Typed qualitative relevance labels used by candidate decisions."""

    STRONG_FIT = "strong_fit"
    PLAUSIBLE_FIT = "plausible_fit"
    CONTEXT_ONLY = "context_only"
    OFF_OBJECTIVE = "off_objective"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    DEFERRED = "deferred"


class EvidenceSelectionDecisionDeferralReason(StrEnum):
    """Typed reasons for records that are deferred instead of selected."""

    MISSING_SOURCE_SEARCH = "missing_source_search"
    PER_SEARCH_BUDGET = "per_search_budget"
    RUN_HANDOFF_BUDGET = "run_handoff_budget"
    SHADOW_MODE = "shadow_mode"


@dataclass(frozen=True, slots=True)
class EvidenceSelectionCandidateSearch:
    """One durable source-search run the harness may screen."""

    source_key: str
    search_id: UUID
    max_records: int | None = None


@dataclass(frozen=True, slots=True)
class EvidenceSelectionCandidateDecision:
    """Typed in-memory candidate decision before JSON artifact serialization."""

    source_key: str
    source_family: str
    search_id: str
    decision: EvidenceSelectionDecisionState
    relevance_label: EvidenceSelectionDecisionRelevance
    reason: str
    record_index: int | None = None
    record_hash: str | None = None
    title: str | None = None
    score: float = 0.0
    matched_terms: tuple[str, ...] = ()
    excluded_terms: tuple[str, ...] = ()
    caveats: tuple[str, ...] = ()
    candidate_context: JSONObject | None = None
    original_relevance_label: EvidenceSelectionDecisionRelevance | None = None
    deferral_reason: EvidenceSelectionDecisionDeferralReason | None = None
    shadow_decision: EvidenceSelectionDecisionState | None = None
    would_have_been_selected: bool = False

    def with_decision(
        self,
        *,
        decision: EvidenceSelectionDecisionState,
        relevance_label: EvidenceSelectionDecisionRelevance | None = None,
        reason: str,
        deferral_reason: EvidenceSelectionDecisionDeferralReason | None = None,
        shadow_decision: EvidenceSelectionDecisionState | None = None,
        would_have_been_selected: bool = False,
    ) -> EvidenceSelectionCandidateDecision:
        """Return this candidate decision with a new lifecycle state."""

        next_relevance_label = (
            relevance_label if relevance_label is not None else self.relevance_label
        )
        original_relevance_label = (
            self.relevance_label
            if decision is not EvidenceSelectionDecisionState.SELECTED
            and self.decision is EvidenceSelectionDecisionState.SELECTED
            else self.original_relevance_label
        )
        return EvidenceSelectionCandidateDecision(
            source_key=self.source_key,
            source_family=self.source_family,
            search_id=self.search_id,
            decision=decision,
            relevance_label=next_relevance_label,
            reason=reason,
            record_index=self.record_index,
            record_hash=self.record_hash,
            title=self.title,
            score=self.score,
            matched_terms=self.matched_terms,
            excluded_terms=self.excluded_terms,
            caveats=self.caveats,
            candidate_context=self.candidate_context,
            original_relevance_label=original_relevance_label,
            deferral_reason=deferral_reason,
            shadow_decision=shadow_decision,
            would_have_been_selected=would_have_been_selected,
        )

    def to_artifact_payload(self) -> JSONObject:
        """Serialize this decision at the artifact/API boundary."""

        payload: JSONObject = {
            "source_key": self.source_key,
            "source_family": self.source_family,
            "search_id": self.search_id,
            "decision": self.decision.value,
            "relevance_label": self.relevance_label.value,
            "reason": self.reason,
            "score": self.score,
            "matched_terms": list(self.matched_terms),
            "excluded_terms": list(self.excluded_terms),
            "caveats": list(self.caveats),
        }
        if self.record_index is not None:
            payload["record_index"] = self.record_index
        if self.record_hash is not None:
            payload["record_hash"] = self.record_hash
        if self.title is not None:
            payload["title"] = self.title
        if self.candidate_context is not None:
            payload["candidate_context"] = self.candidate_context
        if self.original_relevance_label is not None:
            payload["original_relevance_label"] = self.original_relevance_label.value
        if self.deferral_reason is not None:
            payload["deferral_reason"] = self.deferral_reason.value
        if self.shadow_decision is not None:
            payload["shadow_decision"] = self.shadow_decision.value
        if self.would_have_been_selected:
            payload["would_have_been_selected"] = self.would_have_been_selected
        return payload


@dataclass(frozen=True, slots=True)
class EvidenceSelectionScreeningResult:
    """Candidate-screening output grouped by downstream action."""

    selected_records: tuple[EvidenceSelectionCandidateDecision, ...]
    skipped_records: tuple[EvidenceSelectionCandidateDecision, ...]
    deferred_records: tuple[EvidenceSelectionCandidateDecision, ...]
    errors: tuple[str, ...]


def record_dedup_key(
    *,
    source_key: str,
    search_id: UUID | str,
    record_index: int,
) -> str:
    """Return the durable deduplication key for one source-search record."""

    return f"{source_key}:{search_id}:{record_index}"


def score_from_decision(decision: JSONObject | EvidenceSelectionCandidateDecision) -> float:
    """Return a numeric selection score from one serialized decision."""

    if isinstance(decision, EvidenceSelectionCandidateDecision):
        return decision.score
    score = decision.get("score")
    if isinstance(score, int | float) and not isinstance(score, bool):
        return float(score)
    return 0.0


def record_hash(record: JSONObject) -> str:
    """Return a stable hash for one source record."""

    return hashlib.sha256(record_text(record).encode("utf-8")).hexdigest()


def record_text(record: JSONObject) -> str:
    """Return a stable JSON text representation for one source record."""

    return json.dumps(record, ensure_ascii=False, sort_keys=True)


def required_decision_string(decision: JSONObject, key: str) -> str:
    """Return a required string field from a serialized candidate decision."""

    value = decision.get(key)
    if not isinstance(value, str) or value.strip() == "":
        msg = f"Evidence-selection decision is missing string field '{key}'."
        raise ValueError(msg)
    return value.strip()


def required_decision_int(decision: JSONObject, key: str) -> int:
    """Return a required integer field from a serialized candidate decision."""

    value: JSONValue | None = decision.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    msg = f"Evidence-selection decision is missing integer field '{key}'."
    raise ValueError(msg)


def relevance_label_for_selected_score(score: float) -> EvidenceSelectionDecisionRelevance:
    """Return the qualitative label for a selected record score."""

    if score >= HIGH_PRIORITY_SCORE_THRESHOLD:
        return EvidenceSelectionDecisionRelevance.STRONG_FIT
    return EvidenceSelectionDecisionRelevance.PLAUSIBLE_FIT


__all__ = [
    "EvidenceSelectionCandidateSearch",
    "EvidenceSelectionCandidateDecision",
    "EvidenceSelectionDecisionDeferralReason",
    "EvidenceSelectionDecisionRelevance",
    "EvidenceSelectionDecisionState",
    "EvidenceSelectionScreeningResult",
    "HIGH_PRIORITY_SCORE_THRESHOLD",
    "MIN_SELECTION_SCORE",
    "record_dedup_key",
    "record_hash",
    "record_text",
    "relevance_label_for_selected_score",
    "required_decision_int",
    "required_decision_string",
    "score_from_decision",
]
