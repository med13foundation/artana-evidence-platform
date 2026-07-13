"""Test doubles for agent-authorized evidence-selection ranking."""

from __future__ import annotations

from dataclasses import replace
from typing import Literal

from artana_evidence_api.evidence_selection.ranking.contracts import (
    DeterministicRankingWeight,
    RankingCategoricalInput,
)
from artana_evidence_api.evidence_selection.semantic.screening import (
    DeterministicEvidenceSelectionCandidateScreener,
    EvidenceSelectionScreeningContext,
)
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateDecision,
    EvidenceSelectionScreeningResult,
    candidate_ordering_value,
)


class OperationalRankingTestScreener:
    """Attach a governed test policy rank to retrieval-selected fixtures."""

    def __init__(self) -> None:
        self._retrieval_screener = DeterministicEvidenceSelectionCandidateScreener()

    async def screen(
        self,
        *,
        context: EvidenceSelectionScreeningContext,
    ) -> EvidenceSelectionScreeningResult:
        result = await self._retrieval_screener.screen(context=context)
        return EvidenceSelectionScreeningResult(
            selected_records=tuple(
                _with_test_operational_ranking(decision)
                for decision in result.selected_records
            ),
            skipped_records=result.skipped_records,
            deferred_records=result.deferred_records,
            errors=result.errors,
        )

    def selector_kind(self) -> Literal["agent"]:
        return "agent"


def _with_test_operational_ranking(
    decision: EvidenceSelectionCandidateDecision,
) -> EvidenceSelectionCandidateDecision:
    return replace(
        decision,
        operational_ranking=DeterministicRankingWeight(
            value=candidate_ordering_value(decision),
            policy_id="test_agent_semantic_ranking",
            policy_version="v1",
            mapping_version="v1",
            categorical_inputs=(
                RankingCategoricalInput(
                    field="relevance_label",
                    value=decision.relevance_label.value,
                ),
            ),
        ),
        retrieval_ranking=None,
    )


__all__ = ["OperationalRankingTestScreener"]
