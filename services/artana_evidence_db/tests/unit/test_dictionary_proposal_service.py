"""Regression tests for dictionary proposal service governance boundaries."""

from __future__ import annotations

from typing import cast

import pytest
from artana_evidence_db.dictionary_proposal_service import DictionaryProposalService
from artana_evidence_db.kernel_dictionary_models import DictionaryProposalModel
from artana_evidence_db.semantic_ports import DictionaryPort
from sqlalchemy.orm import Session
from sqlalchemy.sql import Select


@pytest.mark.parametrize(
    ("method_name", "kwargs"),
    [
        (
            "approve_proposal",
            {
                "reviewed_by": "manual:reviewer",
                "decision_reason": "Approved.",
            },
        ),
        (
            "reject_proposal",
            {
                "reviewed_by": "manual:reviewer",
                "decision_reason": "Rejected.",
            },
        ),
        (
            "request_changes",
            {
                "reviewed_by": "manual:reviewer",
                "decision_reason": "Needs changes.",
            },
        ),
        (
            "merge_proposal",
            {
                "reviewed_by": "manual:reviewer",
                "target_id": "TARGET",
                "decision_reason": "Merged.",
            },
        ),
    ],
)
def test_review_actions_load_proposal_for_update(
    method_name: str,
    kwargs: dict[str, str],
) -> None:
    service = _ReviewLockProbe()

    with pytest.raises(ValueError, match="stop after lock probe"):
        getattr(service, method_name)("proposal-id", **kwargs)

    assert service.for_update is True


def test_get_model_for_update_uses_row_locking_statement() -> None:
    session = _LockingSessionProbe()
    service = DictionaryProposalService(
        session=cast("Session", session),
        dictionary_service=cast("DictionaryPort", object()),
    )

    with pytest.raises(ValueError, match="not found"):
        service._get_model("proposal-id", for_update=True)

    assert session.statement is not None
    assert session.statement._for_update_arg is not None


def test_relation_constraint_proposals_have_unique_open_triple_index() -> None:
    indexes = {index.name: index for index in DictionaryProposalModel.__table__.indexes}
    index = indexes.get(
        "uq_dictionary_proposals_open_relation_constraint_triple",
    )

    assert index is not None
    assert index.unique is True
    assert [column.name for column in index.columns] == [
        "source_type",
        "relation_type",
        "target_type",
    ]
    assert index.dialect_options["postgresql"]["where"] is not None
    assert index.dialect_options["sqlite"]["where"] is not None


class _ReviewLockProbe(DictionaryProposalService):
    def __init__(self) -> None:
        self.for_update: bool | None = None

    def _get_model(
        self,
        proposal_id: str,
        *,
        for_update: bool = False,
    ) -> DictionaryProposalModel:
        del proposal_id
        self.for_update = for_update
        raise ValueError("stop after lock probe")


class _ScalarResultProbe:
    def one_or_none(self) -> None:
        return None


class _LockingSessionProbe:
    def __init__(self) -> None:
        self.statement: Select[tuple[DictionaryProposalModel]] | None = None

    def get(self, model_type: type[object], model_id: str) -> None:
        del model_type, model_id
        raise AssertionError("locked proposal loads should not use Session.get")

    def scalars(
        self,
        statement: Select[tuple[DictionaryProposalModel]],
    ) -> _ScalarResultProbe:
        self.statement = statement
        return _ScalarResultProbe()
