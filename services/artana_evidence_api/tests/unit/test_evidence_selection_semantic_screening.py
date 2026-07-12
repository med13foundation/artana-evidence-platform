"""Adversarial tests for agent-first semantic candidate screening."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.direct_source_search import (
    InMemoryDirectSourceSearchStore,
    PubMedSourceSearchResponse,
)
from artana_evidence_api.document_store import HarnessDocumentStore
from artana_evidence_api.evidence_selection.diagnostics.agent_evaluation import (
    evaluate_semantic_selection_agent,
)
from artana_evidence_api.evidence_selection.diagnostics.fixture import (
    load_semantic_diagnostic_fixture,
)
from artana_evidence_api.evidence_selection_candidates import (
    EvidenceSelectionCandidateSearch,
)
from artana_evidence_api.evidence_selection_semantic_contracts import (
    EvidenceSelectionSemanticBatchContract,
    EvidenceSelectionSemanticCandidateAssessment,
)
from artana_evidence_api.evidence_selection_semantic_model import (
    EvidenceSelectionSemanticContext,
)
from artana_evidence_api.evidence_selection_semantic_screening import (
    AgentEvidenceSelectionCandidateScreener,
    EvidenceSelectionScreeningContext,
)
from artana_evidence_api.pubmed_discovery import AdvancedQueryParameters
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)
from pydantic import ValidationError

_FIXTURE_PATH = Path(
    "scripts/validation/evidence_selection/fixtures/"
    "semantic_relevance_failure_corpus_v1.json",
)
_BASELINE_REPORT_PATH = Path(
    "docs/validation/reports/2026-07-11-pr-semantic-pr1-failure-corpus-baseline.json",
)


class _FakeSemanticRunner:
    def __init__(
        self,
        contract: EvidenceSelectionSemanticBatchContract | None = None,
        error: Exception | None = None,
    ) -> None:
        self.contract = contract
        self.error = error
        self.contexts: list[EvidenceSelectionSemanticContext] = []

    async def assess(
        self,
        *,
        context: EvidenceSelectionSemanticContext,
    ) -> EvidenceSelectionSemanticBatchContract:
        self.contexts.append(context)
        if self.error is not None:
            raise self.error
        assert self.contract is not None
        return self.contract

    def model_id(self) -> str | None:
        return "test:semantic-model"


class _ExpectedLabelSemanticRunner:
    def __init__(self) -> None:
        fixture = load_semantic_diagnostic_fixture(_FIXTURE_PATH)
        self._expected_by_title = {
            record.title: record.expected_label
            for case in fixture.cases
            for record in case.records
        }

    async def assess(
        self,
        *,
        context: EvidenceSelectionSemanticContext,
    ) -> EvidenceSelectionSemanticBatchContract:
        assessments = []
        for index, record in enumerate(context.records):
            title = str(record["title"])
            expected = self._expected_by_title[title]
            assessments.append(
                _assessment(
                    index=index,
                    decision=expected,
                    objective="direct" if expected == "select" else "off_objective",
                    evidence_span=title,
                ),
            )
        return _contract(*assessments)

    def model_id(self) -> str | None:
        return "test:expected-label-runner"


class _PartialBatchSemanticRunner:
    async def assess(
        self,
        *,
        context: EvidenceSelectionSemanticContext,
    ) -> EvidenceSelectionSemanticBatchContract:
        if 2 in context.record_indices:
            raise RuntimeError("second batch failed")
        return _contract(
            *(
                _assessment(
                    index=index,
                    decision="select" if index == 0 else "reject",
                    objective="direct" if index == 0 else "off_objective",
                    evidence_span=str(record["title"]),
                )
                for index, record in zip(
                    context.record_indices,
                    context.records,
                    strict=True,
                )
            ),
        )

    def model_id(self) -> str | None:
        return "test:partial-batch-runner"


def _assessment(
    *,
    index: int,
    decision: str,
    objective: str,
    evidence_span: str,
) -> EvidenceSelectionSemanticCandidateAssessment:
    payload = {
        "record_index": index,
        "decision": decision,
        "objective_match": objective,
        "entity_variant_match": "match",
        "population_match": "match",
        "intervention_match": "not_required",
        "outcome_match": "match",
        "study_type_match": "match",
        "inclusion_assessment": "met",
        "exclusion_assessment": "not_triggered",
        "explanation": f"Categorical semantic decision for record {index}.",
        "evidence_spans": [evidence_span],
    }
    if decision == "reject":
        payload["objective_match"] = "off_objective"
        payload["entity_variant_match"] = "no_match"
    if decision == "review":
        payload["objective_match"] = "uncertain"
        payload["inclusion_assessment"] = "uncertain"
    return EvidenceSelectionSemanticCandidateAssessment.model_validate(payload)


def _contract(
    *assessments: EvidenceSelectionSemanticCandidateAssessment,
) -> EvidenceSelectionSemanticBatchContract:
    return EvidenceSelectionSemanticBatchContract(
        schema_version="evidence_selection_semantic_agent.v1",
        agent_run_id="test-agent-run",
        reasoning_summary="Each record was compared with every selection criterion.",
        assessments=assessments,
    )


@pytest.mark.asyncio
async def test_agent_screening_maps_categories_to_deterministic_actions() -> None:
    context = _screening_context()
    runner = _FakeSemanticRunner(
        _contract(
            _assessment(
                index=0,
                decision="select",
                objective="direct",
                evidence_span="EGFR T790M response",
            ),
            _assessment(
                index=1,
                decision="reject",
                objective="off_objective",
                evidence_span="KRAS colorectal review",
            ),
            _assessment(
                index=2,
                decision="review",
                objective="uncertain",
                evidence_span="EGFR commentary",
            ),
        ),
    )

    result = await AgentEvidenceSelectionCandidateScreener(
        model_runner=runner,
    ).screen(context=context)

    assert len(result.selected_records) == 1
    assert result.selected_records[0].score == 6.0
    assert result.selected_records[0].reason.startswith("Categorical semantic")
    assert result.selected_records[0].semantic_agent_run_id == "test-agent-run"
    assert "semantic_entity_variant=match" in result.selected_records[0].caveats
    assert len(result.skipped_records) == 1
    assert result.skipped_records[0].score == 0.0
    assert len(result.deferred_records) == 1
    assert result.deferred_records[0].deferral_reason == "semantic_review"
    assert result.errors == ()
    assert runner.contexts[0].exclusion_criteria == (
        "Exclude review articles without primary patient evidence",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "contract",
    [
        _contract(
            _assessment(
                index=0,
                decision="select",
                objective="direct",
                evidence_span="invented span",
            ),
        ),
        _contract(
            _assessment(
                index=0,
                decision="select",
                objective="direct",
                evidence_span="title",
            ),
            _assessment(
                index=1,
                decision="reject",
                objective="off_objective",
                evidence_span="KRAS colorectal review",
            ),
            _assessment(
                index=2,
                decision="review",
                objective="uncertain",
                evidence_span="EGFR commentary",
            ),
        ),
        _contract(
            _assessment(
                index=0,
                decision="select",
                objective="direct",
                evidence_span="EGFR T790M response",
            ),
            _assessment(
                index=1,
                decision="reject",
                objective="off_objective",
                evidence_span="KRAS colorectal review",
            ),
        ),
    ],
)
async def test_invalid_agent_batch_defers_every_record_without_fallback(
    contract: EvidenceSelectionSemanticBatchContract,
) -> None:
    result = await AgentEvidenceSelectionCandidateScreener(
        model_runner=_FakeSemanticRunner(contract),
    ).screen(context=_screening_context())

    assert result.selected_records == ()
    assert result.skipped_records == ()
    assert len(result.deferred_records) == 3
    assert {decision.deferral_reason for decision in result.deferred_records} == {
        "semantic_agent_failure"
    }
    assert len(result.errors) == 1
    assert "failed closed" in result.errors[0]


@pytest.mark.asyncio
async def test_agent_exception_defers_every_record_without_leaking_error_text() -> None:
    result = await AgentEvidenceSelectionCandidateScreener(
        model_runner=_FakeSemanticRunner(
            error=RuntimeError("secret provider payload"),
        ),
    ).screen(context=_screening_context())

    assert result.selected_records == ()
    assert len(result.deferred_records) == 3
    assert "secret provider payload" not in result.errors[0]
    assert "RuntimeError" in result.errors[0]


@pytest.mark.asyncio
async def test_agent_batch_failure_defers_only_failed_batch(monkeypatch) -> None:
    monkeypatch.setattr(
        "artana_evidence_api.evidence_selection_semantic_screening."
        "_MAX_AGENT_BATCH_RECORDS",
        2,
    )

    result = await AgentEvidenceSelectionCandidateScreener(
        model_runner=_PartialBatchSemanticRunner(),
    ).screen(context=_screening_context())

    assert [decision.record_index for decision in result.selected_records] == [0]
    assert [decision.record_index for decision in result.skipped_records] == [1]
    assert [decision.record_index for decision in result.deferred_records] == [2]
    assert result.deferred_records[0].deferral_reason == "semantic_agent_failure"
    assert len(result.errors) == 1


def test_semantic_contract_forbids_numeric_agent_scores() -> None:
    payload = _assessment(
        index=0,
        decision="select",
        objective="direct",
        evidence_span="EGFR T790M response",
    ).model_dump(mode="json")
    payload["confidence_score"] = 0.99

    with pytest.raises(ValidationError, match="confidence_score"):
        EvidenceSelectionSemanticCandidateAssessment.model_validate(payload)


def test_semantic_contract_rejects_contradictory_select() -> None:
    payload = _assessment(
        index=0,
        decision="select",
        objective="direct",
        evidence_span="EGFR T790M response",
    ).model_dump(mode="json")
    payload["study_type_match"] = "no_match"

    with pytest.raises(ValidationError, match="select requires"):
        EvidenceSelectionSemanticCandidateAssessment.model_validate(payload)


def test_semantic_contract_rejects_unexplained_rejection() -> None:
    payload = _assessment(
        index=0,
        decision="select",
        objective="direct",
        evidence_span="EGFR T790M response",
    ).model_dump(mode="json")
    payload["decision"] = "reject"

    with pytest.raises(ValidationError, match="explicit negative"):
        EvidenceSelectionSemanticCandidateAssessment.model_validate(payload)


@pytest.mark.asyncio
async def test_agent_evaluation_applies_deterministic_quality_and_canary_gates() -> (
    None
):
    fixture = load_semantic_diagnostic_fixture(_FIXTURE_PATH)

    evaluation = await evaluate_semantic_selection_agent(
        fixture_path=_FIXTURE_PATH,
        fixture=fixture,
        runner=_ExpectedLabelSemanticRunner(),
        evaluated_commit="1" * 40,
        generated_at=datetime(2026, 7, 12, tzinfo=UTC),
        baseline_report_path=_BASELINE_REPORT_PATH,
        baseline_precision=0.2381,
        baseline_end_to_end_recall=0.3846,
        minimum_precision=0.8,
        minimum_end_to_end_recall=0.8,
    )

    assert evaluation.score.micro.precision == 1.0
    assert evaluation.score.micro.end_to_end_recall == 1.0
    assert evaluation.deterministic_fallback_count == 0
    assert evaluation.canary_passed is True
    assert evaluation.quality_gate_passed is True


@pytest.mark.asyncio
async def test_agent_evaluation_counts_invalid_agent_without_fallback() -> None:
    fixture = load_semantic_diagnostic_fixture(_FIXTURE_PATH)

    evaluation = await evaluate_semantic_selection_agent(
        fixture_path=_FIXTURE_PATH,
        fixture=fixture,
        runner=_FakeSemanticRunner(error=RuntimeError("provider failure")),
        evaluated_commit="1" * 40,
        generated_at=datetime(2026, 7, 12, tzinfo=UTC),
        baseline_report_path=_BASELINE_REPORT_PATH,
        baseline_precision=0.2381,
        baseline_end_to_end_recall=0.3846,
        minimum_precision=0.8,
        minimum_end_to_end_recall=0.8,
    )

    assert evaluation.score.micro.invalid_agent_count == 30
    assert evaluation.deterministic_fallback_count == 0
    assert evaluation.quality_gate_passed is False


def _screening_context() -> EvidenceSelectionScreeningContext:
    space_id = uuid4()
    owner_id = uuid4()
    search_id = uuid4()
    store = InMemoryDirectSourceSearchStore()
    store.save(
        _pubmed_search(
            space_id=space_id,
            owner_id=owner_id,
            search_id=search_id,
        ),
        created_by=owner_id,
    )
    return EvidenceSelectionScreeningContext(
        space_id=space_id,
        goal="Find primary evidence of EGFR T790M treatment response",
        instructions="Prefer direct patient evidence.",
        inclusion_criteria=("EGFR T790M and treatment response",),
        exclusion_criteria=(
            "Exclude review articles without primary patient evidence",
        ),
        population_context="Patients with EGFR T790M-positive cancer",
        evidence_types=("primary clinical study",),
        priority_outcomes=("treatment response",),
        candidate_searches=(
            EvidenceSelectionCandidateSearch(
                source_key="pubmed",
                search_id=search_id,
                max_records=3,
            ),
        ),
        max_records_per_search=3,
        direct_source_search_store=store,
        document_store=HarnessDocumentStore(),
    )


def _pubmed_search(
    *,
    space_id: UUID,
    owner_id: UUID,
    search_id: UUID,
) -> PubMedSourceSearchResponse:
    now = datetime.now(UTC)
    records = [
        {
            "pmid": "1",
            "title": "EGFR T790M response in treated patients",
            "abstract": "EGFR T790M response was observed after targeted treatment.",
        },
        {
            "pmid": "2",
            "title": "KRAS colorectal review",
            "abstract": "A narrative review of KRAS colorectal cancer biology.",
        },
        {
            "pmid": "3",
            "title": "EGFR commentary",
            "abstract": "EGFR commentary with no stated variant or patient outcome.",
        },
    ]
    capture = source_result_capture_metadata(
        source_key="pubmed",
        capture_stage=SourceCaptureStage.SEARCH_RESULT,
        capture_method="direct_source_search",
        locator=f"pubmed:search:{search_id}",
        retrieved_at=now,
        search_id=str(search_id),
        query="EGFR T790M treatment response",
        query_payload={"search_term": "EGFR T790M treatment response"},
        result_count=len(records),
        provenance={"provider": "semantic_screening_test"},
    )
    return PubMedSourceSearchResponse(
        id=search_id,
        space_id=space_id,
        owner_id=owner_id,
        query="EGFR T790M treatment response",
        query_preview="EGFR T790M treatment response",
        parameters=AdvancedQueryParameters(
            search_term="EGFR T790M treatment response",
            max_results=len(records),
        ),
        total_results=len(records),
        record_count=len(records),
        records=records,
        created_at=now,
        updated_at=now,
        completed_at=now,
        source_capture=SourceResultCapture.model_validate(capture),
    )
