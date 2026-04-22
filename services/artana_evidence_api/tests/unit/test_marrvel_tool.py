"""Tests for MARRVEL tool registration in the graph-harness tool catalog."""

from __future__ import annotations

import pytest
from artana_evidence_api.tool_catalog import (
    RunMarrvelSearchToolArgs,
    get_graph_harness_tool_spec,
    list_graph_harness_tool_specs,
    visible_tool_names_for_harness,
)
from pydantic import ValidationError


def test_marrvel_tool_spec_registered() -> None:
    spec = get_graph_harness_tool_spec("run_marrvel_search")
    assert spec is not None
    assert spec.display_name == "MARRVEL Search"
    assert spec.input_model is RunMarrvelSearchToolArgs
    assert spec.side_effect is True
    assert spec.risk_level == "medium"


def test_marrvel_tool_visible_in_expected_harnesses() -> None:
    expected_harnesses = (
        "research-init",
        "research-bootstrap",
        "graph-chat",
        "continuous-learning",
        "supervisor",
    )
    for harness_id in expected_harnesses:
        tool_names = visible_tool_names_for_harness(harness_id)
        assert (
            "run_marrvel_search" in tool_names
        ), f"run_marrvel_search not visible in harness {harness_id!r}"


def test_marrvel_tool_not_visible_in_unrelated_harnesses() -> None:
    unrelated = ("claim-curation", "mechanism-discovery")
    for harness_id in unrelated:
        visible = visible_tool_names_for_harness(harness_id)
        assert (
            "run_marrvel_search" not in visible
        ), f"run_marrvel_search should NOT be visible in harness {harness_id!r}"


def test_marrvel_tool_in_full_catalog() -> None:
    all_specs = list_graph_harness_tool_specs()
    names = [spec.name for spec in all_specs]
    assert "run_marrvel_search" in names


def test_marrvel_tool_args_validates_gene_symbol() -> None:
    args = RunMarrvelSearchToolArgs(gene_symbol="BRCA1")
    assert args.gene_symbol == "BRCA1"
    assert args.panels is None
    assert args.taxon_id == 9606


def test_marrvel_tool_args_validates_panels() -> None:
    args = RunMarrvelSearchToolArgs(
        gene_symbol="TP53",
        panels=["omim", "clinvar"],
    )
    assert args.panels == ["omim", "clinvar"]


def test_marrvel_tool_args_rejects_empty_gene_symbol() -> None:
    with pytest.raises(ValidationError):
        RunMarrvelSearchToolArgs(gene_symbol="")


def test_marrvel_tool_function_registered() -> None:
    from artana_evidence_api.tool_registry import _REGISTERED_FUNCTIONS

    assert "run_marrvel_search" in _REGISTERED_FUNCTIONS
    assert callable(_REGISTERED_FUNCTIONS["run_marrvel_search"])
