"""Automated promotion and human review are separate facts (D7).

`reviewed_by IS NULL` used to mean both "no human reviewed this" and "a machine
approved this".  The recheck predicate keyed on that NULL, so recording a
reviewer would have silently switched the recheck off and made auto-promotions
permanent -- which is why `materialize_support_claim` discarded the reviewer it
was handed instead of persisting it.

These tests pin the separation: a recorded reviewer must not suppress the
recheck, and an auto-promotion must still be rechecked when evidence changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class _Relation:
    """The fields `_demote_auto_promoted_relation_for_recheck` reads."""

    curation_status: str
    reviewed_by: object | None
    reviewed_at: datetime | None
    auto_promoted: bool


class _Repository:
    """The demotion predicate, isolated from SQLAlchemy."""

    def __init__(self) -> None:
        self.flushed = 0

    def _flush(self) -> None:
        self.flushed += 1

    def demote(self, relation: _Relation) -> None:
        from artana_evidence_db.relation_repository import (
            SqlAlchemyKernelRelationRepository,
        )

        SqlAlchemyKernelRelationRepository._demote_auto_promoted_relation_for_recheck(  # noqa: SLF001
            _SessionShim(self),
            relation,
        )


class _SessionShim:
    """Bind the unbound predicate to a session that only needs `flush`."""

    def __init__(self, repository: _Repository) -> None:
        self._session = _FlushOnly(repository)


class _FlushOnly:
    def __init__(self, repository: _Repository) -> None:
        self._repository = repository

    def flush(self) -> None:
        self._repository._flush()  # noqa: SLF001


def _auto_promoted() -> _Relation:
    return _Relation(
        curation_status="APPROVED",
        reviewed_by=None,
        reviewed_at=datetime.now(UTC),
        auto_promoted=True,
    )


def test_auto_promotion_is_still_rechecked_when_evidence_changes() -> None:
    repository = _Repository()
    relation = _auto_promoted()

    repository.demote(relation)

    assert relation.curation_status == "UNDER_REVIEW"
    assert relation.reviewed_at is None
    assert relation.auto_promoted is False


def test_recording_a_reviewer_does_not_suppress_the_recheck() -> None:
    """The regression this whole ticket exists to avoid.

    Under the old `reviewed_by IS NULL` predicate this relation would have been
    skipped, and the auto-promotion would have become permanent purely because
    a human once resolved a claim that projected into it.
    """

    repository = _Repository()
    relation = _auto_promoted()
    relation.reviewed_by = "11111111-1111-1111-1111-111111111111"

    repository.demote(relation)

    assert relation.curation_status == "UNDER_REVIEW"
    assert relation.auto_promoted is False


def test_a_human_approval_is_never_demoted() -> None:
    repository = _Repository()
    relation = _Relation(
        curation_status="APPROVED",
        reviewed_by="22222222-2222-2222-2222-222222222222",
        reviewed_at=datetime.now(UTC),
        auto_promoted=False,
    )

    repository.demote(relation)

    assert relation.curation_status == "APPROVED"
    assert relation.reviewed_at is not None
    assert repository.flushed == 0


def test_a_draft_relation_is_untouched() -> None:
    repository = _Repository()
    relation = _Relation(
        curation_status="DRAFT",
        reviewed_by=None,
        reviewed_at=None,
        auto_promoted=False,
    )

    repository.demote(relation)

    assert relation.curation_status == "DRAFT"
    assert repository.flushed == 0


def test_the_relations_table_carries_the_explicit_flag() -> None:
    from artana_evidence_db.kernel_relation_models import RelationModel

    columns = RelationModel.__table__.c

    assert "auto_promoted" in columns
    assert columns["auto_promoted"].nullable is False
    assert "reviewed_by" in columns, (
        "the reviewer column must remain: separating the two facts is the point"
    )


def test_materialization_no_longer_discards_the_reviewer() -> None:
    """ART-GOV-002: the acting user must reach the repository."""

    import inspect

    from artana_evidence_db.relation_projection_materialization_service import (
        KernelRelationProjectionMaterializationService,
    )

    body = inspect.getsource(
        KernelRelationProjectionMaterializationService.materialize_support_claim,
    )

    assert "del reviewed_by" not in body
    assert "reviewed_by=reviewed_by" in body
