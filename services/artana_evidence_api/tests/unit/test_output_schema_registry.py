"""Regression tests for LiteLLM structured-output schema conversion."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

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
from artana_evidence_api.variant_extraction_contracts import LLMExtractionContract
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
        ("LLMExtractionContract", LLMExtractionContract),
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


def test_variant_llm_schema_has_no_dynamic_object_maps() -> None:
    """OpenAI structured outputs reject arbitrary dict fields in strict schemas."""
    result = type_to_response_format_param(LLMExtractionContract)
    schema = result["json_schema"]["schema"]

    dynamic_paths = _dynamic_additional_properties_paths(schema)

    assert dynamic_paths == []


def _dynamic_additional_properties_paths(node: object, path: str = "$") -> list[str]:
    mapping = _mapping_node(node)
    if mapping is not None:
        dynamic_paths: list[str] = []
        additional_properties = mapping.get("additionalProperties")
        if additional_properties not in (None, False):
            dynamic_paths.append(path)
        for key, value in mapping.items():
            dynamic_paths.extend(
                _dynamic_additional_properties_paths(value, f"{path}.{key}"),
            )
        return dynamic_paths
    if isinstance(node, list):
        dynamic_paths = []
        for index, item in enumerate(node):
            dynamic_paths.extend(
                _dynamic_additional_properties_paths(item, f"{path}[{index}]"),
            )
        return dynamic_paths
    return []


def _mapping_node(node: object) -> Mapping[str, object] | None:
    if not isinstance(node, Mapping):
        return None
    return cast("Mapping[str, object]", node)
