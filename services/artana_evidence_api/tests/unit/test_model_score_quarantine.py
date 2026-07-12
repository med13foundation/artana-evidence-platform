"""Regression tests for model-authored score quarantine at production boundaries."""

from __future__ import annotations

from copy import deepcopy

import pytest
from artana_evidence_api import research_init_helpers
from artana_evidence_api.agent_contracts import (
    LEGACY_EVIDENCE_RELEVANCE_COMPATIBILITY_VALUE,
    ModelEvidenceCitation,
    OnboardingAssistantModelOutput,
)
from artana_evidence_api.graph_connection_runtime import (
    _GraphConnectionExecutionContract,
)
from artana_evidence_api.graph_search_runtime import _GraphSearchExecutionContract
from artana_evidence_api.pubmed_relevance import PubMedRelevanceModelOutput
from artana_evidence_api.variant_extraction_contracts import LLMExtractionContract
from pydantic import ValidationError


def _citation_payload() -> dict[str, object]:
    return {
        "source_type": "paper",
        "locator": "pubmed:12345",
        "excerpt": "The abstract directly discusses the requested mechanism.",
    }


def _onboarding_payload() -> dict[str, object]:
    return {
        "rationale": "The supplied objective is specific enough to begin.",
        "evidence": [_citation_payload()],
        "message_type": "plan_ready",
        "title": "Research plan ready",
        "summary": "Begin a focused literature review.",
        "sections": [],
        "questions": [],
        "suggested_actions": [],
        "artifacts": [],
        "state_patch": {
            "thread_status": "review_needed",
            "onboarding_status": "plan_ready",
            "objective": "Review MED13 mechanisms.",
            "seed_terms": ["MED13"],
            "explored_questions": ["Which mechanisms are documented?"],
            "pending_questions": [],
            "current_hypotheses": [],
        },
        "warnings": [],
    }


def test_model_evidence_citation_rejects_relevance_and_converts_explicitly() -> None:
    payload = _citation_payload()
    payload["relevance"] = 0.99

    with pytest.raises(ValidationError, match="relevance"):
        ModelEvidenceCitation.model_validate(payload)

    legacy = ModelEvidenceCitation.model_validate(
        _citation_payload(),
    ).to_legacy_evidence_item()
    assert legacy.relevance == LEGACY_EVIDENCE_RELEVANCE_COMPATIBILITY_VALUE


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            PubMedRelevanceModelOutput,
            {
                "rationale": "Directly relevant.",
                "evidence": [_citation_payload()],
                "relevance": "relevant",
                "source_type": "pubmed",
                "query": "MED13 mechanism",
            },
        ),
        (OnboardingAssistantModelOutput, _onboarding_payload()),
    ],
)
def test_model_outputs_reject_injected_confidence(
    schema: type[PubMedRelevanceModelOutput | OnboardingAssistantModelOutput],
    payload: dict[str, object],
) -> None:
    tainted = deepcopy(payload)
    tainted["confidence_score"] = 0.99

    with pytest.raises(ValidationError, match="confidence_score"):
        schema.model_validate(tainted)


def test_onboarding_derives_legacy_fields_after_strict_validation() -> None:
    tainted = _onboarding_payload()
    state_patch = tainted["state_patch"]
    assert isinstance(state_patch, dict)
    state_patch["pending_question_count"] = 1_000_000

    with pytest.raises(ValidationError, match="pending_question_count"):
        OnboardingAssistantModelOutput.model_validate(tainted)

    model_output = OnboardingAssistantModelOutput.model_validate(_onboarding_payload())
    public_contract = model_output.to_assistant_contract(agent_run_id="run-1")

    assert public_contract.confidence_score == 0.0
    assert public_contract.state_patch.pending_question_count == len(
        public_contract.state_patch.pending_questions,
    )
    assert (
        public_contract.evidence[0].relevance
        == LEGACY_EVIDENCE_RELEVANCE_COMPATIBILITY_VALUE
    )


@pytest.mark.parametrize(
    ("schema", "payload"),
    [
        (
            _GraphConnectionExecutionContract,
            {"rationale": "Supported.", "evidence": [_citation_payload()]},
        ),
        (
            _GraphSearchExecutionContract,
            {"rationale": "Supported.", "evidence": [_citation_payload()]},
        ),
        (
            LLMExtractionContract,
            {
                "rationale": "Extracted from the cited span.",
                "evidence": [_citation_payload()],
                "decision": "generated",
                "source_type": "paper",
                "document_id": "document-1",
            },
        ),
    ],
)
def test_registered_execution_schemas_reject_evidence_relevance(
    schema: type[
        _GraphConnectionExecutionContract
        | _GraphSearchExecutionContract
        | LLMExtractionContract
    ],
    payload: dict[str, object],
) -> None:
    tainted = deepcopy(payload)
    evidence = tainted["evidence"]
    assert isinstance(evidence, list)
    citation = evidence[0]
    assert isinstance(citation, dict)
    citation["relevance"] = 0.99

    with pytest.raises(ValidationError, match="relevance"):
        schema.model_validate(tainted)


def test_graph_search_execution_schema_rejects_agent_total_results() -> None:
    with pytest.raises(ValidationError, match="total_results"):
        _GraphSearchExecutionContract.model_validate({"total_results": 1_000_000})


@pytest.mark.asyncio
async def test_pubmed_ingestion_order_ignores_llm_confidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    higher_priority = research_init_helpers._PubMedCandidate(
        title="Higher deterministic priority",
        text="MED13 mechanism evidence.",
        queries=["MED13 mechanism"],
        pmid="high",
    )
    lower_priority = research_init_helpers._PubMedCandidate(
        title="Lower deterministic priority",
        text="MED13 context.",
        queries=["MED13"],
        pmid="low",
    )

    def _heuristic_review(
        candidate: research_init_helpers._PubMedCandidate,
        *,
        objective: str,
        seed_terms: list[str],
    ) -> research_init_helpers._PubMedCandidateReview:
        del objective, seed_terms
        is_high_priority = candidate.pmid == "high"
        return research_init_helpers._PubMedCandidateReview(
            method="heuristic",
            label="relevant",
            confidence=0.9 if is_high_priority else 0.5,
            rationale="deterministic heuristic review",
            signal_count=4 if is_high_priority else 1,
            focus_signal_count=3 if is_high_priority else 0,
            query_specificity=8 if is_high_priority else 2,
        )

    async def _llm_review(
        candidate: research_init_helpers._PubMedCandidate,
        *,
        objective: str,
    ) -> research_init_helpers._PubMedCandidateReview:
        del objective
        return research_init_helpers._PubMedCandidateReview(
            method="llm",
            label="relevant",
            confidence=0.0 if candidate.pmid == "high" else 1.0,
            rationale="categorically relevant",
        )

    monkeypatch.setattr(
        research_init_helpers,
        "_review_candidate_with_heuristics",
        _heuristic_review,
    )
    monkeypatch.setattr(
        research_init_helpers,
        "_review_candidate_with_llm",
        _llm_review,
    )

    selected = await research_init_helpers._select_candidates_for_ingestion(
        [lower_priority, higher_priority],
        objective="Review MED13 mechanisms.",
        seed_terms=["MED13"],
        errors=[],
    )

    assert [candidate.pmid for candidate, _review in selected] == ["high", "low"]
    assert all(review.method == "llm" for _candidate, review in selected)
