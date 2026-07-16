"""Tests for deterministic polynomial-time event matching."""

from scripts.validation.claim_events.matching import maximum_weight_pairs


def test_maximum_weight_pairs_finds_global_optimum() -> None:
    assert maximum_weight_pairs(((10, 9), (9, 0))) == ((0, 1), (1, 0))


def test_maximum_weight_pairs_handles_rectangular_and_zero_edges() -> None:
    assert maximum_weight_pairs(((0, 4, 0),)) == ((0, 1),)
    assert maximum_weight_pairs(((0,), (0,))) == ()


def test_maximum_weight_pairs_handles_production_maximum_without_subset_search() -> None:
    weights = tuple(
        tuple(100 if row == column else 1 for column in range(64))
        for row in range(64)
    )

    assert maximum_weight_pairs(weights) == tuple((index, index) for index in range(64))
