"""Regression tests for LiteLLM structured-output schema conversion."""

from __future__ import annotations

import pytest
from artana_evidence_api.agent_contracts import (
    GraphConnectionContract,
    GraphSearchContract,
    OnboardingAssistantContract,
)
from artana_evidence_api.document_extraction import (
    build_llm_extraction_output_schema,
    build_proposal_review_output_schema,
)
from artana_evidence_api.graph_connection_runtime import (
    _GraphConnectionExecutionContract,
)
from artana_evidence_api.marrvel_enrichment import _MarrvelGeneInferenceResult
from artana_evidence_api.pubmed_relevance import PubMedRelevanceContract
from artana_evidence_api.relation_type_resolver import (
    EntityDecision,
    RelationTypeDecision,
)
from artana_evidence_api.runtime_support import (
    build_model_health_probe_output_schema,
)
from litellm.llms.base_llm.base_utils import type_to_response_format_param
from pydantic import BaseModel


@pytest.mark.parametrize(
    ("schema_name", "schema_class"),
    [
        ("GraphConnectionContract", GraphConnectionContract),
        (
            "_GraphConnectionExecutionContract",
            _GraphConnectionExecutionContract,
        ),
        ("GraphSearchContract", GraphSearchContract),
        ("OnboardingAssistantContract", OnboardingAssistantContract),
        ("PubMedRelevanceContract", PubMedRelevanceContract),
        ("RelationTypeDecision", RelationTypeDecision),
        ("EntityDecision", EntityDecision),
        ("_MarrvelGeneInferenceResult", _MarrvelGeneInferenceResult),
        (
            "LLMExtractionResult",
            build_llm_extraction_output_schema(max_relations=10),
        ),
        ("ProposalReviewResult", build_proposal_review_output_schema()),
        ("ModelHealthProbeOutput", build_model_health_probe_output_schema()),
    ],
)
def test_output_schemas_pass_litellm_strict_conversion(
    schema_name: str,
    schema_class: type[BaseModel],
) -> None:
    result = type_to_response_format_param(schema_class)

    assert result is not None, schema_name
    assert result["type"] == "json_schema", schema_name
    assert result["json_schema"]["strict"] is True, schema_name
