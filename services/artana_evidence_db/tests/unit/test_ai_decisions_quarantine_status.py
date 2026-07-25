"""The AI-decisions route must report a refused write as 409, not 500.

`/v1/spaces/{id}/ai-decisions` reaches `relation_claim_service.create_claim`,
whose quarantine check raises `AIPersistenceQuarantineError`. That is a
`RuntimeError`, so it slipped past the route's `ValueError` handler and surfaced
as an unhandled 500.

The write itself was always refused -- data was never at risk -- but a 500 says
"this service is broken" where the truth is "this write is deliberately
quarantined", and a client cannot distinguish the two. See #185.
"""

from __future__ import annotations

import inspect

import pytest
from artana_evidence_db.routers.claim_routes.write_quarantine import (
    raise_ai_persistence_violation,
)
from artana_evidence_db.validation.ai_persistence_quarantine import (
    AIPersistenceQuarantineError,
    AIPersistenceQuarantineViolation,
)
from fastapi import HTTPException, status


def test_the_quarantine_error_is_not_a_value_error() -> None:
    """Pins the reason it escaped.

    Had it been a `ValueError`, the route's existing handler would have caught
    it and returned 400. It is a `RuntimeError`, so nothing caught it. If that
    ever changes, the handler added for #185 may become redundant -- but the
    handler is correct either way, and this records why it exists.
    """

    assert issubclass(AIPersistenceQuarantineError, RuntimeError)
    assert not issubclass(AIPersistenceQuarantineError, ValueError)


def test_the_shared_envelope_is_a_409() -> None:
    """Every route that refuses an agent-authored write reports the same shape."""

    violation = AIPersistenceQuarantineViolation()

    with pytest.raises(HTTPException) as caught:
        raise_ai_persistence_violation(violation)

    assert caught.value.status_code == status.HTTP_409_CONFLICT
    assert caught.value.detail == violation.as_detail()
    assert caught.value.detail["persistability"] == "NON_PERSISTABLE"


def test_the_ai_decisions_route_handles_the_quarantine() -> None:
    """Guards against the handler being dropped in a later edit.

    Source-level rather than behavioural because exercising the real path needs
    a live database and a full AI-full-mode fixture; this at least fails loudly
    if the except clause disappears.
    """

    from artana_evidence_db.routers import ai_full_mode

    source = inspect.getsource(ai_full_mode.submit_ai_decision)

    assert "AIPersistenceQuarantineError" in source, (
        "the quarantine error must be handled, or it surfaces as a 500"
    )
    assert "raise_ai_persistence_violation" in source, (
        "use the shared 409 envelope rather than a local HTTPException"
    )


def test_the_quarantine_handler_rolls_back() -> None:
    """A refused write must not leave a partial transaction committed.

    The sibling `AIDecisionPolicyRejectedError` branch commits on purpose -- it
    records the rejection -- so the two must not be confused.
    """

    from artana_evidence_db.routers import ai_full_mode

    source = inspect.getsource(ai_full_mode.submit_ai_decision)
    quarantine_branch = source.split("except AIPersistenceQuarantineError")[1]
    next_branch = quarantine_branch.split("except ")[0]

    assert "session.rollback()" in next_branch
    assert "session.commit()" not in next_branch
