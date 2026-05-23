"""Runtime logic for patient-context evidence queries."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from artana_evidence_api.proposal_store import (
    HarnessProposalRecord,
    HarnessProposalStore,
)
from artana_evidence_api.study_outcomes import (
    HarnessStudyOutcomeStore,
    StudyOutcomeRecord,
    StudyOutcomeResponse,
)
from artana_evidence_api.trial_matching import TrialMatchingQuery, match_clinical_trials
from artana_evidence_api.trial_matching.matching import TrialMatchingGatewayProtocol

from .contracts import (
    PatientContext,
    PatientQueryRunRequest,
    PatientQueryRunResponse,
    PatientRelevantClaimResponse,
)

_NORMALIZE_PATTERN = re.compile(r"[^a-z0-9]+")
_NEGATIVE_MARKER_VALUES = frozenset(
    {
        "negative",
        "neg",
        "absent",
        "not detected",
        "none",
        "no",
    },
)
_DIAGNOSIS_SYNONYMS = {
    "gbm": ("gbm", "glioblastoma"),
}
_TREATMENT_SYNONYMS = {
    "tmz": ("tmz", "temozolomide"),
}
_GRADE_WEIGHTS = {
    "high": 0.16,
    "moderate": 0.1,
    "limited": 0.04,
    "provisional": 0.02,
}


@dataclass(frozen=True, slots=True)
class _ContextTerm:
    display: str
    normalized_values: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _PatientContextIndex:
    positive_terms: tuple[_ContextTerm, ...]
    exclusion_terms: tuple[str, ...]
    has_specific_context: bool


async def create_patient_query_run_async(
    *,
    space_id: UUID,
    request: PatientQueryRunRequest,
    proposal_store: HarnessProposalStore,
    study_outcome_store: HarnessStudyOutcomeStore,
    clinicaltrials_gateway: TrialMatchingGatewayProtocol,
) -> PatientQueryRunResponse:
    """Async wrapper used by FastAPI route handlers."""

    context_index = _context_index(request.patient_context)
    trial_response = await match_clinical_trials(
        space_id=space_id,
        query=_trial_matching_query(request),
        gateway=clinicaltrials_gateway,
    )
    claim_matches = _claim_matches(
        space_id=space_id,
        request=request,
        proposal_store=proposal_store,
        context_index=context_index,
    )
    outcome_matches = _study_outcome_matches(
        space_id=space_id,
        request=request,
        study_outcome_store=study_outcome_store,
        context_index=context_index,
    )
    return PatientQueryRunResponse(
        id=uuid4(),
        space_id=space_id,
        status="completed",
        query=request.query,
        patient_context=request.patient_context,
        claim_matches=claim_matches,
        study_outcomes=outcome_matches,
        trial_matches=trial_response.trial_matches,
        generated_at=datetime.now(UTC),
    )


def _claim_matches(
    *,
    space_id: UUID,
    request: PatientQueryRunRequest,
    proposal_store: HarnessProposalStore,
    context_index: _PatientContextIndex,
) -> list[PatientRelevantClaimResponse]:
    candidates: list[tuple[float, PatientRelevantClaimResponse]] = []
    for proposal in proposal_store.list_proposals(
        space_id=space_id,
        status="promoted",
    ):
        match = _proposal_match(
            proposal=proposal,
            context_index=context_index,
        )
        if match is None:
            continue
        score, matched_terms = match
        response = PatientRelevantClaimResponse(
            proposal_id=proposal.id,
            title=proposal.title,
            summary=proposal.summary,
            source_key=proposal.source_key,
            evidence_grade=proposal.evidence_grade,
            confidence=proposal.confidence,
            ranking_score=proposal.ranking_score,
            relevance_score=score,
            matched_terms=matched_terms,
            payload=proposal.payload,
            metadata=proposal.metadata,
            evidence_bundle=proposal.evidence_bundle,
        )
        candidates.append((score, response))
    candidates.sort(key=lambda item: (item[0], item[1].ranking_score), reverse=True)
    return [response for _, response in candidates[: request.max_claims]]


def _study_outcome_matches(
    *,
    space_id: UUID,
    request: PatientQueryRunRequest,
    study_outcome_store: HarnessStudyOutcomeStore,
    context_index: _PatientContextIndex,
) -> list[StudyOutcomeResponse]:
    candidates: list[tuple[int, StudyOutcomeRecord]] = []
    for outcome in study_outcome_store.list_outcomes(
        space_id=space_id,
        offset=0,
        limit=1_000,
    ):
        match_count = _record_match_count(
            text=_outcome_text(outcome),
            context_index=context_index,
        )
        if match_count == 0 and context_index.has_specific_context:
            continue
        if _has_excluded_term(_outcome_text(outcome), context_index.exclusion_terms):
            continue
        candidates.append((match_count, outcome))
    candidates.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
    return [
        StudyOutcomeResponse.from_record(outcome)
        for _, outcome in candidates[: request.max_outcomes]
    ]


def _proposal_match(
    *,
    proposal: HarnessProposalRecord,
    context_index: _PatientContextIndex,
) -> tuple[float, list[str]] | None:
    text = _proposal_text(proposal)
    if _has_excluded_term(text, context_index.exclusion_terms):
        return None
    matched_terms = _matched_terms(text=text, context_index=context_index)
    if context_index.has_specific_context and not matched_terms:
        return None
    grade_weight = _GRADE_WEIGHTS.get((proposal.evidence_grade or "").casefold(), 0.0)
    score = min(
        1.0,
        round(
            0.25
            + min(0.45, len(matched_terms) * 0.15)
            + min(0.24, proposal.ranking_score * 0.24)
            + grade_weight,
            3,
        ),
    )
    return score, matched_terms


def _context_index(context: PatientContext) -> _PatientContextIndex:
    positive_terms: list[_ContextTerm] = []
    exclusion_terms: list[str] = []
    for marker, value in context.molecular_markers.items():
        marker_display = " ".join(marker.split())
        value_display = " ".join(value.split())
        if _is_negative_marker_value(value_display):
            exclusion_terms.append(_normalize_text(marker_display))
            continue
        display = f"{marker_display} {value_display}"
        positive_terms.append(
            _ContextTerm(
                display=display,
                normalized_values=(_normalize_text(display),),
            ),
        )
    for treatment in context.prior_treatments:
        display = " ".join(treatment.split())
        synonyms = _TREATMENT_SYNONYMS.get(display.casefold(), ())
        positive_terms.append(
            _ContextTerm(
                display=display,
                normalized_values=tuple(
                    dict.fromkeys(
                        _normalize_text(value) for value in (display, *synonyms)
                    ),
                ),
            ),
        )
    if context.diagnosis:
        diagnosis_values = _DIAGNOSIS_SYNONYMS.get(
            context.diagnosis.casefold(),
            (context.diagnosis,),
        )
        positive_terms.append(
            _ContextTerm(
                display=context.diagnosis,
                normalized_values=tuple(
                    dict.fromkeys(_normalize_text(value) for value in diagnosis_values),
                ),
            ),
        )
    return _PatientContextIndex(
        positive_terms=tuple(positive_terms),
        exclusion_terms=tuple(dict.fromkeys(exclusion_terms)),
        has_specific_context=bool(context.molecular_markers or context.prior_treatments),
    )


def _trial_matching_query(request: PatientQueryRunRequest) -> TrialMatchingQuery:
    context = request.patient_context
    location = context.location
    molecular_markers = tuple(
        f"{marker} {value}"
        for marker, value in context.molecular_markers.items()
        if not _is_negative_marker_value(value)
    )
    return TrialMatchingQuery(
        condition=context.diagnosis or request.query,
        age=context.age,
        country=location.country if location is not None else None,
        within_miles=location.within_miles if location is not None else None,
        reference_city=location.city if location is not None else None,
        reference_latitude=location.latitude if location is not None else None,
        reference_longitude=location.longitude if location is not None else None,
        molecular_markers=molecular_markers,
        prior_treatments=tuple(context.prior_treatments),
        max_results=request.max_trials,
    )


def _matched_terms(
    *,
    text: str,
    context_index: _PatientContextIndex,
) -> list[str]:
    matched = [
        term.display
        for term in context_index.positive_terms
        if any(value and value in text for value in term.normalized_values)
    ]
    return list(dict.fromkeys(matched))


def _record_match_count(
    *,
    text: str,
    context_index: _PatientContextIndex,
) -> int:
    return len(_matched_terms(text=text, context_index=context_index))


def _has_excluded_term(text: str, exclusion_terms: tuple[str, ...]) -> bool:
    return any(term and term in text for term in exclusion_terms)


def _proposal_text(proposal: HarnessProposalRecord) -> str:
    return _normalize_text(
        " ".join(
            (
                proposal.title,
                proposal.summary,
                _object_text(proposal.payload),
                _object_text(proposal.metadata),
                _object_text(proposal.evidence_bundle),
            ),
        ),
    )


def _outcome_text(outcome: StudyOutcomeRecord) -> str:
    return _normalize_text(
        " ".join(
            (
                outcome.intervention,
                outcome.comparator or "",
                outcome.outcome_metric,
                outcome.population,
                outcome.source_quote,
                _object_text(outcome.metadata),
            ),
        ),
    )


def _object_text(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool | int | float):
        return str(value)
    if isinstance(value, Mapping):
        return " ".join(
            f"{_object_text(key)} {_object_text(item)}"
            for key, item in value.items()
        )
    if isinstance(value, Sequence):
        return " ".join(_object_text(item) for item in value)
    return ""


def _normalize_text(value: str) -> str:
    return _NORMALIZE_PATTERN.sub(" ", value.casefold()).strip()


def _is_negative_marker_value(value: str) -> bool:
    return _normalize_text(value) in _NEGATIVE_MARKER_VALUES


__all__ = [
    "create_patient_query_run_async",
]
