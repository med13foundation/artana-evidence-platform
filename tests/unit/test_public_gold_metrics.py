from __future__ import annotations

import pytest

from scripts.validation.public_gold.metrics import (
    RelationKey,
    assert_complete_inventory,
    calculate_set_metrics,
)


def _relation(identifier: str) -> RelationKey:
    return RelationKey("doc", "Association", "NOVEL", identifier, "D1")


def test_metrics_are_calculated_from_exact_categorical_keys() -> None:
    metrics = calculate_set_metrics(
        frozenset({_relation("G1"), _relation("G2")}),
        frozenset({_relation("G1"), _relation("G3")}),
    )

    assert metrics.true_positive == 1
    assert metrics.false_positive == 1
    assert metrics.false_negative == 1
    assert metrics.precision.value == 0.5
    assert metrics.recall.value == 0.5


def test_complete_inventory_rejects_missing_documents() -> None:
    with pytest.raises(ValueError, match=r"missing=\['doc-2'\]"):
        assert_complete_inventory(
            frozenset({"doc-1", "doc-2"}),
            frozenset({"doc-1"}),
        )
