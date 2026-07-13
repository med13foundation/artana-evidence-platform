"""Deterministic lifecycle policy for categorical semantic assessments."""

from __future__ import annotations

from uuid import UUID

from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection.ranking.contracts import (
    DeterministicRankingWeight,
    RankingCategoricalInput,
)
from artana_evidence_api.evidence_selection.semantic.contracts import (
    EvidenceSelectionSemanticCandidateAssessment,
)
from artana_evidence_api.evidence_selection.semantic.evidence import (
    SemanticEvidenceOption,
)
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateDecision,
    EvidenceSelectionCandidateSearch,
    EvidenceSelectionDecisionDeferralReason,
    EvidenceSelectionDecisionRelevance,
    EvidenceSelectionDecisionState,
    record_dedup_key,
    record_hash,
)
from artana_evidence_api.source_adapters import source_adapter
from artana_evidence_api.source_document_selection_identity import (
    source_document_dedup_key,
    source_document_record_hash,
)
from artana_evidence_api.types.common import JSONObject

_DIRECT_SELECTION_SCORE = 6.0
_SUPPORTING_SELECTION_SCORE = 4.5
_SEMANTIC_RANKING_POLICY_ID = "evidence_selection_semantic_ranking"
_SEMANTIC_RANKING_POLICY_VERSION = "v1"
_SEMANTIC_RANKING_MAPPING_VERSION = "v1"


def decision_from_semantic_assessment(
    *,
    source_key: str,
    search_id: str,
    record_index: int,
    record: JSONObject,
    assessment: EvidenceSelectionSemanticCandidateAssessment,
    agent_run_id: str,
    evidence_options: tuple[SemanticEvidenceOption, ...],
) -> EvidenceSelectionCandidateDecision:
    """Map categories to lifecycle state and deterministic ranking weight."""

    if assessment.decision == "select":
        decision = EvidenceSelectionDecisionState.SELECTED
        relevance = (
            EvidenceSelectionDecisionRelevance.STRONG_FIT
            if assessment.objective_match == "direct"
            else EvidenceSelectionDecisionRelevance.PLAUSIBLE_FIT
        )
        operational_weight = (
            _DIRECT_SELECTION_SCORE
            if assessment.objective_match == "direct"
            else _SUPPORTING_SELECTION_SCORE
        )
        deferral_reason = None
    elif assessment.decision == "reject":
        decision = EvidenceSelectionDecisionState.SKIPPED
        relevance = (
            EvidenceSelectionDecisionRelevance.CONTEXT_ONLY
            if assessment.objective_match == "context_only"
            else EvidenceSelectionDecisionRelevance.OFF_OBJECTIVE
        )
        operational_weight = 0.0
        deferral_reason = None
    else:
        decision = EvidenceSelectionDecisionState.DEFERRED
        relevance = EvidenceSelectionDecisionRelevance.NEEDS_HUMAN_REVIEW
        operational_weight = 0.0
        deferral_reason = EvidenceSelectionDecisionDeferralReason.SEMANTIC_REVIEW
    return EvidenceSelectionCandidateDecision(
        source_key=source_key,
        source_family=source_family(source_key),
        search_id=search_id,
        decision=decision,
        relevance_label=relevance,
        reason=assessment.explanation,
        record_index=record_index,
        record_hash=record_hash(record),
        title=record_title(
            source_key=source_key,
            record=record,
            index=record_index,
        ),
        operational_ranking=_semantic_operational_ranking(
            assessment=assessment,
            value=operational_weight,
        ),
        caveats=_assessment_caveats(
            assessment=assessment,
            evidence_options=evidence_options,
        ),
        candidate_context=candidate_context(source_key=source_key, record=record),
        deferral_reason=deferral_reason,
        semantic_agent_run_id=agent_run_id,
    )


def agent_failure_decision(
    *,
    source_key: str,
    search_id: str,
    record_index: int,
    record: JSONObject,
) -> EvidenceSelectionCandidateDecision:
    """Create a typed deferred record for an invalid agent batch."""

    return EvidenceSelectionCandidateDecision(
        source_key=source_key,
        source_family=source_family(source_key),
        search_id=search_id,
        decision=EvidenceSelectionDecisionState.DEFERRED,
        relevance_label=EvidenceSelectionDecisionRelevance.DEFERRED,
        reason="Semantic agent did not produce a complete valid assessment.",
        record_index=record_index,
        record_hash=record_hash(record),
        title=record_title(
            source_key=source_key,
            record=record,
            index=record_index,
        ),
        candidate_context=candidate_context(source_key=source_key, record=record),
        deferral_reason=EvidenceSelectionDecisionDeferralReason.SEMANTIC_AGENT_FAILURE,
    )


def missing_search_decision(
    candidate_search: EvidenceSelectionCandidateSearch,
) -> EvidenceSelectionCandidateDecision:
    """Create a typed deferred placeholder for a missing saved search."""

    return EvidenceSelectionCandidateDecision(
        source_key=candidate_search.source_key,
        source_family="unknown",
        search_id=str(candidate_search.search_id),
        decision=EvidenceSelectionDecisionState.DEFERRED,
        relevance_label=EvidenceSelectionDecisionRelevance.DEFERRED,
        reason="Saved source search was not found for this space/source.",
        deferral_reason=EvidenceSelectionDecisionDeferralReason.MISSING_SOURCE_SEARCH,
    )


def existing_document_identities(
    *,
    space_id: UUID,
    document_store: HarnessDocumentStore,
) -> tuple[set[str], set[str]]:
    """Return the durable keys and hashes already present in one space."""

    documents = document_store.list_documents(space_id=space_id)
    keys = {
        key
        for key in (source_document_dedup_key(document) for document in documents)
        if key
    }
    hashes = {
        value
        for value in (source_document_record_hash(document) for document in documents)
        if value is not None
    }
    return keys, hashes


def decision_is_duplicate(
    *,
    decision: EvidenceSelectionCandidateDecision,
    existing_keys: set[str],
    existing_hashes: set[str],
) -> bool:
    """Return whether a selected candidate has already been observed."""

    if decision.record_hash is not None and decision.record_hash in existing_hashes:
        return True
    key = _decision_key(decision)
    return key is not None and key in existing_keys


def mark_decision_seen(
    *,
    decision: EvidenceSelectionCandidateDecision,
    existing_keys: set[str],
    existing_hashes: set[str],
) -> None:
    """Add a selected candidate to this run's deterministic duplicate state."""

    if decision.record_hash is not None:
        existing_hashes.add(decision.record_hash)
    key = _decision_key(decision)
    if key is not None:
        existing_keys.add(key)


def semantic_rank_key(
    decision: EvidenceSelectionCandidateDecision,
) -> tuple[float, int]:
    """Rank only from deterministic weights derived from categories."""

    operational_ranking = decision.operational_ranking
    value = operational_ranking.value if operational_ranking is not None else 0.0
    return (-value, decision.record_index or 0)


def _semantic_operational_ranking(
    *,
    assessment: EvidenceSelectionSemanticCandidateAssessment,
    value: float,
) -> DeterministicRankingWeight:
    categorical_values = {
        "decision": assessment.decision,
        "entity_variant_match": assessment.entity_variant_match,
        "exclusion_assessment": assessment.exclusion_assessment,
        "inclusion_assessment": assessment.inclusion_assessment,
        "intervention_match": assessment.intervention_match,
        "objective_match": assessment.objective_match,
        "outcome_match": assessment.outcome_match,
        "population_match": assessment.population_match,
        "study_type_match": assessment.study_type_match,
    }
    blocking_categories = tuple(
        f"{field}={category}"
        for field, category in categorical_values.items()
        if category
        in {
            "ambiguous",
            "context_only",
            "no_match",
            "not_met",
            "off_objective",
            "triggered",
            "uncertain",
        }
    )
    vetoes = (
        ("exclusion_triggered",)
        if assessment.exclusion_assessment == "triggered"
        else ()
    )
    return DeterministicRankingWeight(
        value=value,
        policy_id=_SEMANTIC_RANKING_POLICY_ID,
        policy_version=_SEMANTIC_RANKING_POLICY_VERSION,
        mapping_version=_SEMANTIC_RANKING_MAPPING_VERSION,
        categorical_inputs=tuple(
            RankingCategoricalInput(field=field, value=category)
            for field, category in categorical_values.items()
        ),
        caps=(),
        vetoes=vetoes,
        blocking_categories=blocking_categories,
    )


def source_family(source_key: str) -> str:
    adapter = source_adapter(source_key)
    return adapter.source_family if adapter is not None else "unknown"


def candidate_context(*, source_key: str, record: JSONObject) -> JSONObject | None:
    adapter = source_adapter(source_key)
    return (
        adapter.build_candidate_context(record).to_json()
        if adapter is not None
        else None
    )


def record_title(*, source_key: str, record: JSONObject, index: int) -> str:
    for key in (
        "title",
        "brief_title",
        "official_title",
        "name",
        "gene_symbol",
        "label",
        "accession",
        "uniprot_id",
    ):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return f"{source_key} record {index}"


def _assessment_caveats(
    *,
    assessment: EvidenceSelectionSemanticCandidateAssessment,
    evidence_options: tuple[SemanticEvidenceOption, ...],
) -> tuple[str, ...]:
    findings = {
        "entity_variant": assessment.entity_variant_match,
        "population": assessment.population_match,
        "intervention": assessment.intervention_match,
        "outcome": assessment.outcome_match,
        "study_type": assessment.study_type_match,
        "inclusion": assessment.inclusion_assessment,
        "exclusion": assessment.exclusion_assessment,
    }
    return (
        *(f"semantic_{name}={value}" for name, value in findings.items()),
        *(
            f'evidence_reference="{option.reference}" '
            f'source_path="{option.source_path}" span="{option.text}"'
            for option in evidence_options
        ),
    )


def _decision_key(decision: EvidenceSelectionCandidateDecision) -> str | None:
    if decision.record_index is None:
        return None
    return record_dedup_key(
        source_key=decision.source_key,
        search_id=decision.search_id,
        record_index=decision.record_index,
    )


__all__ = [
    "agent_failure_decision",
    "decision_from_semantic_assessment",
    "decision_is_duplicate",
    "existing_document_identities",
    "mark_decision_seen",
    "missing_search_decision",
    "semantic_rank_key",
]
