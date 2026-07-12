"""Agent-first semantic screening with deterministic safety enforcement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

from artana_evidence_api.direct_source_search import DirectSourceSearchStore
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection.semantic.contracts import (
    EvidenceSelectionSemanticCandidateAssessment,
)
from artana_evidence_api.evidence_selection.semantic.decisions import (
    agent_failure_decision,
    decision_from_semantic_assessment,
    decision_is_duplicate,
    existing_document_identities,
    mark_decision_seen,
    missing_search_decision,
    semantic_rank_key,
)
from artana_evidence_api.evidence_selection.semantic.model import (
    ArtanaEvidenceSelectionSemanticModelRunner,
    EvidenceSelectionSemanticContext,
    EvidenceSelectionSemanticModelRunner,
)
from artana_evidence_api.evidence_selection.semantic.validation import (
    assess_validated_semantic_batch,
)
from artana_evidence_api.evidence_selection_candidate_screening import (
    screen_candidate_searches,
)
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateDecision,
    EvidenceSelectionCandidateSearch,
    EvidenceSelectionDecisionDeferralReason,
    EvidenceSelectionDecisionRelevance,
    EvidenceSelectionDecisionState,
    EvidenceSelectionScreeningResult,
)
from artana_evidence_api.types.common import JSONObject

_MAX_AGENT_BATCH_RECORDS = 10
_MAX_AGENT_BATCH_CHARACTERS = 80_000


@dataclass(frozen=True, slots=True)
class EvidenceSelectionScreeningContext:
    """Complete runtime input for one candidate-screening phase."""

    space_id: UUID
    goal: str
    instructions: str | None
    inclusion_criteria: tuple[str, ...]
    exclusion_criteria: tuple[str, ...]
    population_context: str | None
    evidence_types: tuple[str, ...]
    priority_outcomes: tuple[str, ...]
    candidate_searches: tuple[EvidenceSelectionCandidateSearch, ...]
    max_records_per_search: int
    direct_source_search_store: DirectSourceSearchStore
    document_store: HarnessDocumentStore


class EvidenceSelectionCandidateScreener(Protocol):
    """Asynchronous candidate-screening boundary used by the runtime."""

    async def screen(
        self,
        *,
        context: EvidenceSelectionScreeningContext,
    ) -> EvidenceSelectionScreeningResult:
        """Classify all supplied candidate-search records."""
        ...

    def selector_kind(self) -> Literal["agent", "deterministic"]:
        """Return the semantic decision implementation identity."""
        ...


class DeterministicEvidenceSelectionCandidateScreener:
    """Explicit legacy screener for diagnostics and isolated compatibility tests."""

    async def screen(
        self,
        *,
        context: EvidenceSelectionScreeningContext,
    ) -> EvidenceSelectionScreeningResult:
        return screen_candidate_searches(
            space_id=context.space_id,
            goal=context.goal,
            instructions=context.instructions,
            inclusion_criteria=context.inclusion_criteria,
            exclusion_criteria=context.exclusion_criteria,
            candidate_searches=context.candidate_searches,
            max_records_per_search=context.max_records_per_search,
            direct_source_search_store=context.direct_source_search_store,
            document_store=context.document_store,
        )

    def selector_kind(self) -> Literal["deterministic"]:
        return "deterministic"


class AgentEvidenceSelectionCandidateScreener:
    """Use categorical agent judgments and fail closed without semantic fallback."""

    def __init__(
        self,
        *,
        model_runner: EvidenceSelectionSemanticModelRunner | None = None,
    ) -> None:
        self._model_runner = (
            model_runner or ArtanaEvidenceSelectionSemanticModelRunner()
        )

    async def screen(
        self,
        *,
        context: EvidenceSelectionScreeningContext,
    ) -> EvidenceSelectionScreeningResult:
        selected: list[EvidenceSelectionCandidateDecision] = []
        skipped: list[EvidenceSelectionCandidateDecision] = []
        deferred: list[EvidenceSelectionCandidateDecision] = []
        errors: list[str] = []
        existing_keys, existing_hashes = existing_document_identities(
            space_id=context.space_id,
            document_store=context.document_store,
        )

        for candidate_search in context.candidate_searches:
            source_search = context.direct_source_search_store.get(
                space_id=context.space_id,
                source_key=candidate_search.source_key,
                search_id=candidate_search.search_id,
            )
            if source_search is None:
                errors.append(
                    "Source search "
                    f"{candidate_search.source_key}/{candidate_search.search_id} was not found.",
                )
                deferred.append(missing_search_decision(candidate_search))
                continue

            records = tuple(source_search.records)
            assessments: dict[int, EvidenceSelectionSemanticCandidateAssessment] = {}
            agent_run_ids: dict[int, str] = {}
            failed_decisions: list[EvidenceSelectionCandidateDecision] = []
            for record_indices, batch_records in _record_batches(records):
                try:
                    semantic_context = EvidenceSelectionSemanticContext(
                        goal=context.goal,
                        instructions=context.instructions,
                        inclusion_criteria=context.inclusion_criteria,
                        exclusion_criteria=context.exclusion_criteria,
                        population_context=context.population_context,
                        evidence_types=context.evidence_types,
                        priority_outcomes=context.priority_outcomes,
                        source_key=source_search.source_key,
                        search_id=str(source_search.id),
                        records=batch_records,
                        record_indices=record_indices,
                    )
                    validated_batch = await assess_validated_semantic_batch(
                        runner=self._model_runner,
                        context=semantic_context,
                    )
                except Exception as exc:  # noqa: BLE001 - Agent failures fail closed.
                    errors.append(
                        "Semantic agent failed closed for "
                        f"{source_search.source_key}/{source_search.id} "
                        f"records={list(record_indices)} ({type(exc).__name__}).",
                    )
                    failed_decisions.extend(
                        agent_failure_decision(
                            source_key=source_search.source_key,
                            search_id=str(source_search.id),
                            record_index=index,
                            record=record,
                        )
                        for index, record in zip(
                            record_indices,
                            batch_records,
                            strict=True,
                        )
                    )
                    continue
                assessments.update(validated_batch.assessments)
                agent_run_ids.update(
                    dict.fromkeys(
                        record_indices,
                        validated_batch.agent_run_id,
                    ),
                )

            ranked = sorted(
                [
                    *failed_decisions,
                    *(
                        decision_from_semantic_assessment(
                            source_key=source_search.source_key,
                            search_id=str(source_search.id),
                            record=record,
                            assessment=assessments[index],
                            agent_run_id=agent_run_ids[index],
                        )
                        for index, record in enumerate(records)
                        if index in assessments
                    ),
                ],
                key=semantic_rank_key,
            )
            search_limit = (
                candidate_search.max_records
                if candidate_search.max_records is not None
                else context.max_records_per_search
            )
            selected_count = 0
            for decision in ranked:
                if decision.decision is EvidenceSelectionDecisionState.DEFERRED:
                    deferred.append(decision)
                    continue
                if decision.decision is EvidenceSelectionDecisionState.SKIPPED:
                    skipped.append(decision)
                    continue
                if decision_is_duplicate(
                    decision=decision,
                    existing_keys=existing_keys,
                    existing_hashes=existing_hashes,
                ):
                    skipped.append(
                        decision.with_decision(
                            decision=EvidenceSelectionDecisionState.SKIPPED,
                            relevance_label=EvidenceSelectionDecisionRelevance.CONTEXT_ONLY,
                            reason=(
                                "This source record was already selected or captured "
                                "in the research space."
                            ),
                        ),
                    )
                    continue
                if selected_count >= search_limit:
                    deferred.append(
                        decision.with_decision(
                            decision=EvidenceSelectionDecisionState.DEFERRED,
                            reason="Per-search selection budget reached.",
                            deferral_reason=(
                                EvidenceSelectionDecisionDeferralReason.PER_SEARCH_BUDGET
                            ),
                        ),
                    )
                    continue
                selected.append(decision)
                selected_count += 1
                mark_decision_seen(
                    decision=decision,
                    existing_keys=existing_keys,
                    existing_hashes=existing_hashes,
                )

        return EvidenceSelectionScreeningResult(
            selected_records=tuple(selected),
            skipped_records=tuple(skipped),
            deferred_records=tuple(deferred),
            errors=tuple(errors),
        )

    def selector_kind(self) -> Literal["agent"]:
        return "agent"


def _record_batches(
    records: tuple[JSONObject, ...],
) -> tuple[tuple[tuple[int, ...], tuple[JSONObject, ...]], ...]:
    batches: list[tuple[tuple[int, ...], tuple[JSONObject, ...]]] = []
    indices: list[int] = []
    batch_records: list[JSONObject] = []
    character_count = 0
    for index, record in enumerate(records):
        record_character_count = len(str(record))
        if batch_records and (
            len(batch_records) >= _MAX_AGENT_BATCH_RECORDS
            or character_count + record_character_count > _MAX_AGENT_BATCH_CHARACTERS
        ):
            batches.append((tuple(indices), tuple(batch_records)))
            indices = []
            batch_records = []
            character_count = 0
        indices.append(index)
        batch_records.append(record)
        character_count += record_character_count
    if batch_records:
        batches.append((tuple(indices), tuple(batch_records)))
    return tuple(batches)


__all__ = [
    "AgentEvidenceSelectionCandidateScreener",
    "DeterministicEvidenceSelectionCandidateScreener",
    "EvidenceSelectionCandidateScreener",
    "EvidenceSelectionScreeningContext",
]
