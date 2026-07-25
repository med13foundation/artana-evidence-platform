"""Distinct-document counting, and one implementation for both write paths.

`source_count` is rendered to users as "sources", and it counted evidence
*rows*: three spans quoted from one paper read as three sources.  It now counts
distinct documents (§5.6).

Separately, two implementations of the recompute had drifted.  The dictionary
relation-type merge path wrote three of the six derived fields and skipped the
eligibility filter, so a merged relation kept pre-merge `support_confidence`,
`refute_confidence`, and `distinct_source_family_count` -- values that are
query-filterable and API-exposed.  Both paths now delegate to one function.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass

import pytest
from artana_evidence_db.relation_aggregate_recompute import distinct_document_count


@dataclass
class _Evidence:
    source_document_id: str | None


def test_repeated_quotes_from_one_document_count_once() -> None:
    """The defect: three spans from one paper are one source, not three."""

    evidences = [_Evidence("doc-a"), _Evidence("doc-a"), _Evidence("doc-a")]

    assert distinct_document_count(evidences) == 1


def test_separate_documents_each_count() -> None:
    evidences = [_Evidence("doc-a"), _Evidence("doc-b"), _Evidence("doc-c")]

    assert distinct_document_count(evidences) == 3


def test_mixed_repeats_and_distinct_documents() -> None:
    evidences = [
        _Evidence("doc-a"),
        _Evidence("doc-a"),
        _Evidence("doc-b"),
    ]

    assert distinct_document_count(evidences) == 2


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_unattributed_evidence_is_not_collapsed(missing: str | None) -> None:
    """Absent provenance could be one document or several.

    Collapsing them would understate the count and quietly assert an identity
    the data does not support.  Missing is not equal (invariant 8).
    """

    evidences = [_Evidence(missing), _Evidence(missing), _Evidence("doc-a")]

    assert distinct_document_count(evidences) == 3


def test_no_evidence_counts_zero() -> None:
    assert distinct_document_count([]) == 0


def test_both_write_paths_share_one_implementation() -> None:
    """The divergence is what let a merge leave three fields stale."""

    from artana_evidence_db._dictionary_repository_constraints_merge_mixin import (
        GraphDictionaryRepositoryConstraintsMergeMixin,
    )
    from artana_evidence_db._relation_curation_mixin import (
        _KernelRelationCurationMixin,
    )

    merge_body = inspect.getsource(
        GraphDictionaryRepositoryConstraintsMergeMixin._recompute_relation_aggregate,  # noqa: SLF001
    )
    curation_body = inspect.getsource(
        _KernelRelationCurationMixin._recompute_relation_aggregate,  # noqa: SLF001
    )

    for body in (merge_body, curation_body):
        assert "recompute_relation_aggregate(self._session" in body
        assert "len(evidences)" not in body, (
            "source_count must not be recomputed from evidence-row count"
        )


def test_the_shared_recompute_writes_every_derived_field() -> None:
    """A partial write is what produced stale confidence after a merge."""

    from artana_evidence_db import relation_aggregate_recompute

    body = inspect.getsource(relation_aggregate_recompute.recompute_relation_aggregate)
    reset = inspect.getsource(relation_aggregate_recompute._reset)  # noqa: SLF001

    for field in (
        "aggregate_confidence",
        "source_count",
        "highest_evidence_tier",
        "support_confidence",
        "refute_confidence",
        "distinct_source_family_count",
    ):
        assert f"relation_model.{field}" in body, field
        assert f"relation_model.{field}" in reset, f"{field} missing from empty path"
