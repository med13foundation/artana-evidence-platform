"""Unit tests for PubMed execution helpers used by research-init."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.research_init_helpers import (
    _PubMedCandidate,
    _PubMedCandidateReview,
)
from artana_evidence_api.research_init_models import (
    ResearchInitPubMedResultRecord,
    _PubMedQueryExecutionResult,
)
from artana_evidence_api.research_init_pubmed_execution import (
    pubmed_document_source_capture,
    run_pubmed_query_executions,
)


@pytest.mark.asyncio
async def test_run_pubmed_query_executions_preserves_order_with_bounded_concurrency() -> (
    None
):
    current_concurrency = 0
    max_concurrency = 0

    def _query_builder(
        objective: str,
        seed_terms: list[str],
    ) -> Sequence[Mapping[str, str | None]]:
        assert objective == "Investigate MED13."
        assert seed_terms == ["MED13"]
        return (
            {"search_term": "slow-query", "gene_symbol": None},
            {"search_term": "fast-query", "gene_symbol": None},
            {"search_term": "third-query", "gene_symbol": None},
        )

    async def _query_runner(
        *,
        query_params: Mapping[str, str | None],
        owner_id: UUID,
    ) -> _PubMedQueryExecutionResult:
        del owner_id
        nonlocal current_concurrency, max_concurrency
        current_concurrency += 1
        max_concurrency = max(max_concurrency, current_concurrency)
        query = query_params.get("search_term", "") or ""
        try:
            await asyncio.sleep(0.04 if query == "slow-query" else 0.01)
            return _PubMedQueryExecutionResult(
                query_result=ResearchInitPubMedResultRecord(
                    query=query,
                    total_found=len(query),
                    abstracts_ingested=0,
                ),
                candidates=(),
                errors=(),
            )
        finally:
            current_concurrency -= 1

    results = await run_pubmed_query_executions(
        objective="Investigate MED13.",
        seed_terms=["MED13"],
        query_builder=_query_builder,
        query_runner=_query_runner,
        owner_id=uuid4(),
        concurrency_limit=2,
    )

    assert max_concurrency == 2
    assert [result.query_result.query for result in results if result.query_result] == [
        "slow-query",
        "fast-query",
        "third-query",
    ]


def test_pubmed_document_source_capture_includes_review_and_query_metadata() -> None:
    candidate = _PubMedCandidate(
        title="MED13 coordinates mediator programs",
        text="MED13 regulates mediator complex activity.",
        queries=["MED13 mediator", "MED13 neurodevelopment"],
        pmid="12345",
        doi="10.1000/test",
        pmc_id="PMC123",
        journal="Example Journal",
    )
    review = _PubMedCandidateReview(
        method="heuristic",
        label="relevant",
        confidence=0.91,
        rationale="Focused on MED13.",
    )

    capture = pubmed_document_source_capture(
        candidate=candidate,
        review=review,
        sha256="abcdef1234567890",
        ingestion_run_id="run-1",
    )

    assert capture["source_key"] == "pubmed"
    assert capture["capture_stage"] == "source_document"
    assert capture["capture_method"] == "research_plan"
    assert capture["locator"] == "pubmed:12345"
    assert capture["external_id"] == "12345"
    assert capture["citation"] == "MED13 coordinates mediator programs. Example Journal"
    assert capture["run_id"] == "run-1"
    assert capture["query"] == "MED13 mediator, MED13 neurodevelopment"
    assert capture["query_payload"] == {
        "queries": ["MED13 mediator", "MED13 neurodevelopment"],
        "pmid": "12345",
        "doi": "10.1000/test",
        "pmc_id": "PMC123",
    }
    assert capture["provenance"] == {
        "source": "research-init-pubmed",
        "review_method": "heuristic",
        "review_label": "relevant",
        "review_confidence": 0.91,
        "sha256": "abcdef1234567890",
    }
