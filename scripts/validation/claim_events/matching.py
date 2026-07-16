"""Deterministic polynomial-time maximum-weight event matching."""

from __future__ import annotations

from collections.abc import Sequence


def maximum_weight_pairs(
    weights: Sequence[Sequence[int]],
) -> tuple[tuple[int, int], ...]:
    """Return positive-weight one-to-one pairs using the Hungarian algorithm."""

    row_count = len(weights)
    column_count = max((len(row) for row in weights), default=0)
    if any(len(row) != column_count for row in weights):
        raise ValueError("matching weights must form a rectangular matrix")
    if row_count == 0 or column_count == 0:
        return ()
    size = max(row_count, column_count)
    maximum = max(max(row, default=0) for row in weights)
    costs = [
        [
            maximum
            - (weights[row][column] if row < row_count and column < column_count else 0)
            for column in range(size)
        ]
        for row in range(size)
    ]
    assignment = _minimum_cost_assignment(costs)
    return tuple(
        (row, column)
        for row, column in enumerate(assignment[:row_count])
        if column < column_count and weights[row][column] > 0
    )


def _minimum_cost_assignment(  # noqa: PLR0912 - canonical Hungarian loop
    costs: Sequence[Sequence[int]],
) -> tuple[int, ...]:
    size = len(costs)
    row_potential = [0] * (size + 1)
    column_potential = [0] * (size + 1)
    matched_row = [0] * (size + 1)
    predecessor = [0] * (size + 1)
    for row in range(1, size + 1):
        matched_row[0] = row
        minimum = [10**18] * (size + 1)
        used = [False] * (size + 1)
        column = 0
        while True:
            used[column] = True
            active_row = matched_row[column]
            delta = 10**18
            next_column = 0
            for candidate in range(1, size + 1):
                if used[candidate]:
                    continue
                reduced = (
                    costs[active_row - 1][candidate - 1]
                    - row_potential[active_row]
                    - column_potential[candidate]
                )
                if reduced < minimum[candidate]:
                    minimum[candidate] = reduced
                    predecessor[candidate] = column
                if minimum[candidate] < delta:
                    delta = minimum[candidate]
                    next_column = candidate
            for candidate in range(size + 1):
                if used[candidate]:
                    row_potential[matched_row[candidate]] += delta
                    column_potential[candidate] -= delta
                else:
                    minimum[candidate] -= delta
            column = next_column
            if matched_row[column] == 0:
                break
        while True:
            previous = predecessor[column]
            matched_row[column] = matched_row[previous]
            column = previous
            if column == 0:
                break
    assignment = [-1] * size
    for column in range(1, size + 1):
        assignment[matched_row[column] - 1] = column - 1
    return tuple(assignment)


__all__ = ["maximum_weight_pairs"]
