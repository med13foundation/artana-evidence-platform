"""Contracts for the Mediator variant-registry build script."""

from __future__ import annotations

import pytest

from scripts import build_mediator_variant_registry


def test_node_by_gene_applies_default_and_overrides() -> None:
    assert build_mediator_variant_registry._node_by_gene(
        genes=("MED23", "MED25"),
        default_node="cardiac-septal",
        node_map_values=["MED25=secondary-node"],
    ) == {
        "MED23": "cardiac-septal",
        "MED25": "secondary-node",
    }


def test_node_by_gene_rejects_malformed_overrides() -> None:
    with pytest.raises(SystemExit, match="expected GENE=NODE"):
        build_mediator_variant_registry._node_by_gene(
            genes=("MED23",),
            default_node="",
            node_map_values=["MED23"],
        )
