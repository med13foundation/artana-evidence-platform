"""Candidate screening for evidence-selection source-search records."""

from __future__ import annotations

import re
from uuid import UUID

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    DirectSourceSearchStore,
)
from artana_evidence_api.document_store import (
    HarnessDocumentStore,
)
from artana_evidence_api.evidence_selection_candidates import (
    MIN_SELECTION_SCORE,
    EvidenceSelectionCandidateDecision,
    EvidenceSelectionCandidateSearch,
    EvidenceSelectionDecisionDeferralReason,
    EvidenceSelectionDecisionRelevance,
    EvidenceSelectionDecisionState,
    EvidenceSelectionScreeningResult,
    record_dedup_key,
    record_hash,
    relevance_label_for_selected_score,
    score_from_decision,
)
from artana_evidence_api.source_adapters import source_adapter
from artana_evidence_api.source_document_selection_identity import (
    source_document_dedup_key,
    source_document_record_hash,
)
from artana_evidence_api.types.common import JSONObject

_WORD_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]{2,}", re.IGNORECASE)
_GOAL_TERM_SCORE_WEIGHT = 2.0
_TRUSTED_SOURCE_SCORE_BONUS = 1.0
_REVIEW_ARTICLE_SCORE_BONUS = 0.5
_EXCLUSION_TERM_SCORE_PENALTY = 4.0
_STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "against",
        "between",
        "find",
        "from",
        "linking",
        "records",
        "research",
        "result",
        "results",
        "source",
        "sources",
        "that",
        "the",
        "this",
        "with",
    },
)


def screen_candidate_searches(  # noqa: PLR0913
    *,
    space_id: UUID,
    goal: str,
    instructions: str | None,
    inclusion_criteria: tuple[str, ...],
    exclusion_criteria: tuple[str, ...],
    candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...],
    max_records_per_search: int,
    direct_source_search_store: DirectSourceSearchStore,
    document_store: HarnessDocumentStore,
) -> EvidenceSelectionScreeningResult:
    """Screen saved source-search records into selected/skipped/deferred groups."""

    goal_terms = _terms(
        " ".join(
            (
                goal,
                instructions or "",
                " ".join(inclusion_criteria),
            ),
        ),
    )
    exclusion_terms = _terms(" ".join(exclusion_criteria))
    selected: list[EvidenceSelectionCandidateDecision] = []
    skipped: list[EvidenceSelectionCandidateDecision] = []
    deferred: list[EvidenceSelectionCandidateDecision] = []
    errors: list[str] = []
    documents = document_store.list_documents(space_id=space_id)
    existing_document_keys = {
        key for key in (source_document_dedup_key(document) for document in documents) if key
    }
    existing_record_hashes = {
        source_record_hash
        for source_record_hash in (
            source_document_record_hash(document) for document in documents
        )
        if source_record_hash is not None
    }
    for candidate_search in candidate_searches:
        source_search = direct_source_search_store.get(
            space_id=space_id,
            source_key=candidate_search.source_key,
            search_id=candidate_search.search_id,
        )
        if source_search is None:
            errors.append(
                f"Source search {candidate_search.source_key}/{candidate_search.search_id} was not found.",
            )
            deferred.append(
                EvidenceSelectionCandidateDecision(
                    source_key=candidate_search.source_key,
                    source_family="unknown",
                    search_id=str(candidate_search.search_id),
                    decision=EvidenceSelectionDecisionState.DEFERRED,
                    relevance_label=EvidenceSelectionDecisionRelevance.DEFERRED,
                    reason="Saved source search was not found for this space/source.",
                    deferral_reason=(
                        EvidenceSelectionDecisionDeferralReason.MISSING_SOURCE_SEARCH
                    ),
                ),
            )
            continue
        ranked = sorted(
            (
                _decision_for_record(
                    source_search=source_search,
                    record_index=index,
                    record=record,
                    goal_terms=goal_terms,
                    exclusion_terms=exclusion_terms,
                    existing_document_keys=existing_document_keys,
                    existing_record_hashes=existing_record_hashes,
                )
                for index, record in enumerate(source_search.records)
            ),
            key=lambda decision: (
                -score_from_decision(decision),
                (
                    decision.record_index if decision.record_index is not None else 0
                ),
            ),
        )
        search_limit = (
            candidate_search.max_records
            if candidate_search.max_records is not None
            else max_records_per_search
        )
        selected_for_search = 0
        for decision in ranked:
            if (
                decision.decision is EvidenceSelectionDecisionState.SELECTED
                and _decision_is_duplicate(
                    decision=decision,
                    existing_document_keys=existing_document_keys,
                    existing_record_hashes=existing_record_hashes,
                )
            ):
                skipped.append(
                    decision.with_decision(
                        decision=EvidenceSelectionDecisionState.SKIPPED,
                        relevance_label=(
                            EvidenceSelectionDecisionRelevance.CONTEXT_ONLY
                        ),
                        reason=(
                            "This source record was already selected or captured "
                            "in the research space."
                        ),
                    ),
                )
                continue
            if (
                decision.decision is EvidenceSelectionDecisionState.SELECTED
                and selected_for_search < search_limit
            ):
                selected.append(decision)
                selected_for_search += 1
                _mark_decision_seen(
                    decision=decision,
                    existing_document_keys=existing_document_keys,
                    existing_record_hashes=existing_record_hashes,
                )
            elif decision.decision is EvidenceSelectionDecisionState.SELECTED:
                deferred.append(
                    decision.with_decision(
                        decision=EvidenceSelectionDecisionState.DEFERRED,
                        reason="Per-search selection budget reached.",
                        deferral_reason=(
                            EvidenceSelectionDecisionDeferralReason.PER_SEARCH_BUDGET
                        ),
                    ),
                )
            else:
                skipped.append(decision)
    return EvidenceSelectionScreeningResult(
        selected_records=tuple(selected),
        skipped_records=tuple(skipped),
        deferred_records=tuple(deferred),
        errors=tuple(errors),
    )


def apply_handoff_budget(
    selected_records: list[EvidenceSelectionCandidateDecision],
    *,
    max_handoffs: int,
) -> tuple[
    list[EvidenceSelectionCandidateDecision],
    list[EvidenceSelectionCandidateDecision],
]:
    """Split selected records into kept and deferred records by handoff budget."""

    ranked = sorted(
        selected_records,
        key=_candidate_decision_sort_key,
    )
    if len(ranked) <= max_handoffs:
        return ranked, []
    overflow = ranked[max_handoffs:]
    deferred = [
        record.with_decision(
            decision=EvidenceSelectionDecisionState.DEFERRED,
            reason="Run handoff budget reached before this record.",
            deferral_reason=EvidenceSelectionDecisionDeferralReason.RUN_HANDOFF_BUDGET,
        )
        for record in overflow
    ]
    return ranked[:max_handoffs], deferred


def _candidate_decision_sort_key(
    decision: EvidenceSelectionCandidateDecision,
) -> tuple[float, str, str, tuple[bool, int], str]:
    return (
        -score_from_decision(decision),
        decision.source_key,
        decision.search_id,
        (decision.record_index is None, decision.record_index or 0),
        decision.record_hash or "",
    )


def defer_selected_for_shadow_mode(
    selected_records: list[EvidenceSelectionCandidateDecision],
) -> list[EvidenceSelectionCandidateDecision]:
    """Record shadow-mode selections as typed deferred recommendations."""

    return [
        record.with_decision(
            decision=EvidenceSelectionDecisionState.DEFERRED,
            reason=(
                "Shadow mode records the recommendation without creating a "
                "source handoff."
            ),
            deferral_reason=EvidenceSelectionDecisionDeferralReason.SHADOW_MODE,
            shadow_decision=EvidenceSelectionDecisionState.SELECTED,
            would_have_been_selected=True,
        )
        for record in selected_records
    ]


def _decision_is_duplicate(
    *,
    decision: EvidenceSelectionCandidateDecision,
    existing_document_keys: set[str],
    existing_record_hashes: set[str],
) -> bool:
    source_record_hash = decision.record_hash
    if source_record_hash is not None and source_record_hash in existing_record_hashes:
        return True
    dedup_key = _decision_dedup_key(decision)
    return dedup_key is not None and dedup_key in existing_document_keys


def _mark_decision_seen(
    *,
    decision: EvidenceSelectionCandidateDecision,
    existing_document_keys: set[str],
    existing_record_hashes: set[str],
) -> None:
    if decision.record_hash is not None:
        existing_record_hashes.add(decision.record_hash)
    dedup_key = _decision_dedup_key(decision)
    if dedup_key is not None:
        existing_document_keys.add(dedup_key)


def _decision_dedup_key(decision: EvidenceSelectionCandidateDecision) -> str | None:
    if decision.record_index is not None:
        return record_dedup_key(
            source_key=decision.source_key,
            search_id=decision.search_id,
            record_index=decision.record_index,
        )
    return None


def _decision_for_record(
    *,
    source_search: DirectSourceSearchRecord,
    record_index: int,
    record: JSONObject,
    goal_terms: frozenset[str],
    exclusion_terms: frozenset[str],
    existing_document_keys: set[str],
    existing_record_hashes: set[str],
) -> EvidenceSelectionCandidateDecision:
    record_text = _record_search_text(record)
    record_terms = _terms(record_text)
    matched_terms = sorted(goal_terms & record_terms)
    excluded_terms = sorted(exclusion_terms & record_terms)
    source_record_hash = record_hash(record)
    dedup_key = record_dedup_key(
        source_key=source_search.source_key,
        search_id=source_search.id,
        record_index=record_index,
    )
    title = _record_title(record, fallback=f"{source_search.source_key} record {record_index}")
    score = _relevance_score(
        matched_terms=matched_terms,
        excluded_terms=excluded_terms,
        source_key=source_search.source_key,
        record_text=record_text,
    )
    adapter = source_adapter(source_search.source_key)
    caveats = _record_caveats(
        source_key=source_search.source_key,
        record_text=record_text,
        matched_terms=matched_terms,
        excluded_terms=excluded_terms,
    )
    candidate_context = (
        adapter.build_candidate_context(record).to_json() if adapter is not None else None
    )
    source_family = adapter.source_family if adapter is not None else "unknown"
    if dedup_key in existing_document_keys or source_record_hash in existing_record_hashes:
        return _candidate_decision(
            source_search=source_search,
            record_index=record_index,
            source_record_hash=source_record_hash,
            title=title,
            score=score,
            matched_terms=matched_terms,
            excluded_terms=excluded_terms,
            caveats=caveats,
            source_family=source_family,
            candidate_context=candidate_context,
            decision=EvidenceSelectionDecisionState.SKIPPED,
            relevance_label=EvidenceSelectionDecisionRelevance.CONTEXT_ONLY,
            original_relevance_label=(
                relevance_label_for_selected_score(score)
                if matched_terms and not excluded_terms and score >= MIN_SELECTION_SCORE
                else None
            ),
            reason=(
                "This source record was already selected or captured in the "
                "research space."
            ),
        )
    if excluded_terms:
        return _candidate_decision(
            source_search=source_search,
            record_index=record_index,
            source_record_hash=source_record_hash,
            title=title,
            score=score,
            matched_terms=matched_terms,
            excluded_terms=excluded_terms,
            caveats=caveats,
            source_family=source_family,
            candidate_context=candidate_context,
            decision=EvidenceSelectionDecisionState.SKIPPED,
            relevance_label=EvidenceSelectionDecisionRelevance.OFF_OBJECTIVE,
            reason="Record matched exclusion criteria.",
        )
    if not matched_terms:
        return _candidate_decision(
            source_search=source_search,
            record_index=record_index,
            source_record_hash=source_record_hash,
            title=title,
            score=score,
            matched_terms=matched_terms,
            excluded_terms=excluded_terms,
            caveats=caveats,
            source_family=source_family,
            candidate_context=candidate_context,
            decision=EvidenceSelectionDecisionState.SKIPPED,
            relevance_label=EvidenceSelectionDecisionRelevance.OFF_OBJECTIVE,
            reason="Record did not match the research goal or inclusion criteria.",
        )
    if score < MIN_SELECTION_SCORE:
        return _candidate_decision(
            source_search=source_search,
            record_index=record_index,
            source_record_hash=source_record_hash,
            title=title,
            score=score,
            matched_terms=matched_terms,
            excluded_terms=excluded_terms,
            caveats=caveats,
            source_family=source_family,
            candidate_context=candidate_context,
            decision=EvidenceSelectionDecisionState.SKIPPED,
            relevance_label=EvidenceSelectionDecisionRelevance.NEEDS_HUMAN_REVIEW,
            reason="Record had only weak goal overlap and needs a stronger topic match.",
        )
    return _candidate_decision(
        source_search=source_search,
        record_index=record_index,
        source_record_hash=source_record_hash,
        title=title,
        score=score,
        matched_terms=matched_terms,
        excluded_terms=excluded_terms,
        caveats=caveats,
        source_family=source_family,
        candidate_context=candidate_context,
        decision=EvidenceSelectionDecisionState.SELECTED,
        relevance_label=relevance_label_for_selected_score(score),
        reason=_selection_reason(
            matched_terms=matched_terms,
            source_key=source_search.source_key,
        ),
    )


def _candidate_decision(
    *,
    source_search: DirectSourceSearchRecord,
    record_index: int,
    source_record_hash: str,
    title: str,
    score: float,
    matched_terms: list[str],
    excluded_terms: list[str],
    caveats: list[str],
    source_family: str,
    candidate_context: JSONObject | None,
    decision: EvidenceSelectionDecisionState,
    relevance_label: EvidenceSelectionDecisionRelevance,
    reason: str,
    original_relevance_label: EvidenceSelectionDecisionRelevance | None = None,
) -> EvidenceSelectionCandidateDecision:
    return EvidenceSelectionCandidateDecision(
        source_key=source_search.source_key,
        source_family=source_family,
        search_id=str(source_search.id),
        decision=decision,
        relevance_label=relevance_label,
        reason=reason,
        record_index=record_index,
        record_hash=source_record_hash,
        title=title,
        score=score,
        matched_terms=tuple(matched_terms),
        excluded_terms=tuple(excluded_terms),
        caveats=tuple(caveats),
        candidate_context=candidate_context,
        original_relevance_label=original_relevance_label,
    )

def _selection_reason(*, matched_terms: list[str], source_key: str) -> str:
    preview = ", ".join(matched_terms[:5])
    if preview:
        return f"Record matches the goal/instructions through: {preview}."
    return f"Record from {source_key} matched the evidence-selection policy."


def _record_caveats(
    *,
    source_key: str,
    record_text: str,
    matched_terms: list[str],
    excluded_terms: list[str],
) -> list[str]:
    caveats: list[str] = []
    adapter = source_adapter(source_key)
    limitations = adapter.limitations if adapter is not None else ()
    caveats.extend(limitations)
    lowered = record_text.lower()
    if "association" in lowered and "caus" not in lowered:
        caveats.append("Association language should not be treated as causal proof.")
    if "conflict" in lowered or "contradict" in lowered:
        caveats.append("Record contains possible conflict or contradiction language.")
    if not matched_terms:
        caveats.append("No direct goal term match was found.")
    if excluded_terms:
        caveats.append("Record matched explicit exclusion criteria.")
    return caveats


def _relevance_score(
    *,
    matched_terms: list[str],
    excluded_terms: list[str],
    source_key: str,
    record_text: str,
) -> float:
    score = float(len(matched_terms)) * _GOAL_TERM_SCORE_WEIGHT
    if source_key in {"pubmed", "clinvar", "clinical_trials"}:
        score += _TRUSTED_SOURCE_SCORE_BONUS
    if "review" in record_text.lower():
        score += _REVIEW_ARTICLE_SCORE_BONUS
    score -= float(len(excluded_terms)) * _EXCLUSION_TERM_SCORE_PENALTY
    return max(score, 0.0)


def _terms(text: str) -> frozenset[str]:
    return frozenset(
        token.casefold()
        for token in _WORD_PATTERN.findall(text)
        if token.casefold() not in _STOP_WORDS
    )


def _record_search_text(record: JSONObject) -> str:
    values: list[str] = []

    def collect(value: object) -> None:
        if isinstance(value, str):
            values.append(value)
            return
        if isinstance(value, int | float) and not isinstance(value, bool):
            values.append(str(value))
            return
        if isinstance(value, dict):
            for nested_value in value.values():
                collect(nested_value)
            return
        if isinstance(value, list | tuple):
            for nested_value in value:
                collect(nested_value)

    collect(record)
    return " ".join(values)


def _record_title(record: JSONObject, *, fallback: str) -> str:
    for key in ("title", "brief_title", "official_title", "name", "gene_symbol"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


__all__ = [
    "apply_handoff_budget",
    "defer_selected_for_shadow_mode",
    "screen_candidate_searches",
]
