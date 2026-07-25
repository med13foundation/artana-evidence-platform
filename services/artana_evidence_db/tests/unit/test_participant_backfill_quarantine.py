"""A backfill is a write, so the quarantine binds it too.

`claim-participants/backfill` walked every claim in a space and created
participant rows for each, with no authorship check -- so it wrote graph rows
for agent-authored claims that every other write boundary refuses.

The skip is counted rather than silent: a quarantine that quietly drops work
looks identical to a quarantine that never fired. See #186.
"""

from __future__ import annotations

import inspect

from artana_evidence_db.claim_metrics import get_metric_counters_snapshot
from artana_evidence_db.validation.ai_persistence_quarantine import (
    GraphAIPersistenceQuarantinePolicy,
)


class _Claim:
    """Minimal stand-in carrying only what the quarantine inspects."""

    def __init__(
        self,
        *,
        agent_run_id: str | None = None,
        metadata_payload: dict[str, object] | None = None,
    ) -> None:
        self.agent_run_id = agent_run_id
        self.metadata_payload = metadata_payload or {}


def test_an_agent_run_id_makes_a_claim_agent_authored() -> None:
    """The rule the backfill now honours, stated directly.

    Any non-empty `agent_run_id` is sufficient. This is why the pre-existing
    backfill fixture tripped the guard: it seeded a claim labelled
    `graph-service-backfill-test`, which is agent-authored under this rule even
    though it was only ever meant as a test label.
    """

    policy = GraphAIPersistenceQuarantinePolicy()

    assert policy.violation_for_claim(_Claim(agent_run_id="agent:run-1")) is not None
    assert policy.violation_for_claim(_Claim()) is None


def test_a_manual_claim_is_not_quarantined() -> None:
    """The backfill must still do its job for human-authored claims."""

    policy = GraphAIPersistenceQuarantinePolicy()
    manual = _Claim(metadata_payload={"origin": "curator_import"})

    assert policy.violation_for_claim(manual) is None


def test_both_backfill_write_paths_consult_the_quarantine() -> None:
    """Per-space and global backfill must agree; one guarded path is not enough.

    Source-level because exercising both against real data needs a live
    database, but it fails loudly if either guard is dropped.
    """

    from artana_evidence_db import claim_participant_backfill_service as service

    for method in (
        service.KernelClaimParticipantBackfillService.backfill_for_space,
        service.KernelClaimParticipantBackfillService.backfill_globally,
    ):
        source = inspect.getsource(method)
        assert "violation_for_claim" in source, (
            f"{method.__name__} writes participants without an authorship check"
        )
        assert "quarantined_claims" in source, (
            f"{method.__name__} must count what it skips, not skip silently"
        )


def test_the_skip_is_observable() -> None:
    """A silent quarantine is indistinguishable from one that never fired."""

    assert "claim_participants_backfill_quarantined_total" in (
        get_metric_counters_snapshot()
    )
