"""Validity and persistability are different questions.

`_has_evidence` answers "is this claim well-formed enough to plan around" and is
deliberately permissive -- one non-empty string satisfies it. That was also, in
error, the bar for reporting PERSISTABLE, so a claim whose only evidence was
`evidence_summary="x"` was advertised as writable to the graph.

Tightening `_has_evidence` itself is the obvious fix and it is wrong: it gates
`valid=False, severity="blocking"`, so raising that bar turned well-formed
claims into blocking failures and broke five workflow-governance tests. The
split below is what those tests forced.

See ART-VAL-006 / #201.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from artana_evidence_db.graph_api_schemas.kernel_relation_schemas import (
    KernelRelationTripleValidationRequest,
)
from artana_evidence_db.validation.claim_evidence_binding import (
    has_bound_evidence,
    has_evidence,
)


def _request(**fields: object) -> KernelRelationTripleValidationRequest:
    return KernelRelationTripleValidationRequest(
        source_entity_id=uuid4(),
        target_entity_id=uuid4(),
        relation_type="ACTIVATES",
        **fields,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"evidence_summary": "x"},
        {"evidence_sentence": "A activates B."},
        {"evidence_summary": "x", "evidence_sentence": "A activates B."},
    ],
)
def test_free_text_is_valid_but_not_persistable(fields: dict[str, object]) -> None:
    """Free text describes evidence; it does not bind the claim to a source."""

    request = _request(**fields)

    assert has_evidence(request) is True  # noqa: SLF001
    assert has_bound_evidence(request) is False  # noqa: SLF001


@pytest.mark.parametrize(
    "fields",
    [
        {"source_document_id": uuid4()},
        {"source_document_ref": "PMID:12345"},
    ],
)
def test_an_identified_source_is_persistable(fields: dict[str, object]) -> None:
    request = _request(**fields)

    assert has_bound_evidence(request) is True  # noqa: SLF001


def test_a_blank_source_reference_does_not_bind() -> None:
    """Whitespace is not a source; it must not buy persistability."""

    request = _request(source_document_ref="   ")

    assert has_bound_evidence(request) is False  # noqa: SLF001


def test_nothing_attached_is_not_even_valid() -> None:
    """The permissive gate still has a floor."""

    request = _request()

    assert has_evidence(request) is False  # noqa: SLF001
    assert has_bound_evidence(request) is False  # noqa: SLF001


def test_bound_evidence_is_strictly_stronger_than_evidence() -> None:
    """Whatever binds must also count as evidence, or the gates contradict.

    Pins the ordering rather than the two predicates separately: a request that
    is persistable but not valid would be incoherent, and no future edit to
    either predicate should be able to produce one.
    """

    candidates = [
        _request(evidence_summary="x"),
        _request(evidence_sentence="A activates B."),
        _request(source_document_ref="PMID:12345"),
        _request(source_document_id=uuid4()),
        _request(source_document_ref="   "),
        _request(),
    ]

    for request in candidates:
        bound = has_bound_evidence(request)
        present = has_evidence(request)
        assert not (bound and not present), (
            "a request cannot be persistable while failing the validity gate"
        )
