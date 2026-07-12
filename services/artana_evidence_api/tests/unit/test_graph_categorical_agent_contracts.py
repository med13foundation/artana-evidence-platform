"""Regression tests for categorical graph-agent output boundaries."""

from __future__ import annotations

from copy import deepcopy

import pytest
from artana_evidence_api.runtime.graph_agents.connection import (
    _GraphConnectionExecutionContract,
)
from artana_evidence_api.runtime.graph_agents.search import (
    AgentGraphSearchResult,
    _GraphSearchExecutionContract,
    normalize_graph_search_results,
)
from pydantic import ValidationError


def _fact_assessment() -> dict[str, str]:
    return {
        "support_band": "STRONG",
        "grounding_level": "SPAN",
        "mapping_status": "RESOLVED",
        "speculation_level": "DIRECT",
        "confidence_rationale": "Direct source evidence resolves both endpoints.",
    }


def _search_assessment(
    *,
    support_band: str = "STRONG",
    grounding_level: str = "AGGREGATED",
) -> dict[str, str]:
    return {
        "support_band": support_band,
        "grounding_level": grounding_level,
        "confidence_rationale": "Graph evidence supports this category.",
    }


def _connection_payload() -> dict[str, object]:
    return {
        "rationale": "One source-backed relation was found.",
        "evidence": [
            {
                "source_type": "paper",
                "locator": "pmid:123",
                "excerpt": "The paper directly supports this relation.",
            },
        ],
        "decision": "generated",
        "proposed_relations": [
            {
                "source_id": "entity-1",
                "relation_type": "ASSOCIATED_WITH",
                "target_id": "entity-2",
                "assessment": _fact_assessment(),
                "evidence_summary": "Direct source evidence.",
                "supporting_provenance_ids": ["prov-1"],
                "supporting_document_locators": ["pmid:123", "pmid:123"],
                "reasoning": "The cited source resolves and supports the relation.",
            },
        ],
        "rejected_candidates": [],
    }


@pytest.mark.parametrize(
    ("field", "level"),
    [
        ("confidence_score", "run"),
        ("confidence", "relation"),
        ("supporting_document_count", "relation"),
    ],
)
def test_graph_connection_agent_rejects_numeric_judgments(
    field: str,
    level: str,
) -> None:
    payload = deepcopy(_connection_payload())
    if level == "relation":
        relations = payload["proposed_relations"]
        assert isinstance(relations, list)
        relation = relations[0]
        assert isinstance(relation, dict)
        relation[field] = 0.99
    else:
        payload[field] = 0.99

    with pytest.raises(ValidationError, match=field):
        _GraphConnectionExecutionContract.model_validate(payload)


def test_graph_connection_derives_unique_cited_document_count() -> None:
    contract = _GraphConnectionExecutionContract.model_validate(_connection_payload())

    relation = contract.proposed_relations[0].to_public_relation(
        cited_locators=contract.cited_locators,
    )

    assert relation.confidence == pytest.approx(0.9)
    assert relation.supporting_document_count == 1
    assert relation.supporting_document_locators == ["pmid:123"]


def test_graph_connection_rejects_uncited_document_locator() -> None:
    payload = _connection_payload()
    relations = payload["proposed_relations"]
    assert isinstance(relations, list)
    relation = relations[0]
    assert isinstance(relation, dict)
    relation["supporting_document_locators"] = ["pmid:uncited"]
    contract = _GraphConnectionExecutionContract.model_validate(payload)

    with pytest.raises(ValueError, match="uncited document locators"):
        contract.proposed_relations[0].to_public_relation(
            cited_locators=contract.cited_locators,
        )


def test_graph_connection_agent_bounds_candidate_lists() -> None:
    payload = _connection_payload()
    relations = payload["proposed_relations"]
    assert isinstance(relations, list)
    payload["proposed_relations"] = [deepcopy(relations[0]) for _ in range(101)]

    with pytest.raises(ValidationError, match="proposed_relations"):
        _GraphConnectionExecutionContract.model_validate(payload)


def _search_payload() -> dict[str, object]:
    return {
        "assessment": _search_assessment(),
        "rationale": "Categorical graph results were produced.",
        "evidence": [],
        "decision": "generated",
        "interpreted_intent": "Find supported MED13 entities.",
        "query_plan_summary": "Query relations and observations.",
        "results": [
            {
                "entity_id": "entity-1",
                "entity_type": "GENE",
                "assessment": _search_assessment(),
                "matching_observation_ids": ["observation-1"],
                "matching_relation_ids": ["relation-1"],
                "evidence_chain": [
                    {
                        "relation_id": "relation-1",
                        "assessment": _search_assessment(
                            support_band="SUPPORTED",
                            grounding_level="RELATION",
                        ),
                        "evidence_sentence": "Direct graph relation evidence.",
                    },
                ],
                "explanation": "The graph contains direct support.",
                "support_summary": "One relation and one observation.",
            },
        ],
        "warnings": [],
    }


def _first_search_result_payload() -> dict[str, object]:
    results = _search_payload()["results"]
    assert isinstance(results, list)
    result = results[0]
    assert isinstance(result, dict)
    return deepcopy(result)


@pytest.mark.parametrize(
    ("field", "level"),
    [
        ("confidence_score", "run"),
        ("relevance_score", "result"),
        ("confidence", "evidence"),
    ],
)
def test_graph_search_agent_rejects_numeric_judgments(
    field: str,
    level: str,
) -> None:
    payload = deepcopy(_search_payload())
    if level == "run":
        payload[field] = 0.99
    else:
        results = payload["results"]
        assert isinstance(results, list)
        result = results[0]
        assert isinstance(result, dict)
        if level == "result":
            result[field] = 0.99
        else:
            chain = result["evidence_chain"]
            assert isinstance(chain, list)
            item = chain[0]
            assert isinstance(item, dict)
            item[field] = 0.99

    with pytest.raises(ValidationError, match=field):
        _GraphSearchExecutionContract.model_validate(payload)


def test_graph_search_agent_rejects_runtime_owned_execution_path() -> None:
    payload = _search_payload()
    payload["executed_path"] = "agent_fallback"

    with pytest.raises(ValidationError, match="executed_path"):
        _GraphSearchExecutionContract.model_validate(payload)


def test_graph_search_agent_bounds_result_list() -> None:
    payload = _search_payload()
    results = payload["results"]
    assert isinstance(results, list)
    payload["results"] = [deepcopy(results[0]) for _ in range(201)]

    with pytest.raises(ValidationError, match="results"):
        _GraphSearchExecutionContract.model_validate(payload)


def test_graph_search_ranks_from_categories_and_derives_weights() -> None:
    weaker = AgentGraphSearchResult.model_validate(
        {
            **_first_search_result_payload(),
            "entity_id": "weaker",
            "assessment": _search_assessment(
                support_band="TENTATIVE",
                grounding_level="ENTITY",
            ),
            "evidence_chain": [],
        },
    )
    stronger = AgentGraphSearchResult.model_validate(
        {
            **_first_search_result_payload(),
            "entity_id": "stronger",
        },
    )

    tied = stronger.model_copy(update={"entity_id": "alpha"})
    ranked = normalize_graph_search_results(
        [weaker, stronger, tied, stronger],
        limit=2,
    )

    assert [result.entity_id for result in ranked] == ["alpha", "stronger"]
    assert ranked[0].relevance_score == pytest.approx(0.9)
    assert ranked[0].evidence_chain[0].confidence == pytest.approx(0.7)
    assert ranked[1].relevance_score == pytest.approx(0.9)
    assert weaker.to_public_result().relevance_score == pytest.approx(0.45)
