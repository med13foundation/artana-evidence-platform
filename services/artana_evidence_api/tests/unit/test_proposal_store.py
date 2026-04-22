"""Unit tests for in-memory proposal-store edge cases."""

from __future__ import annotations

from threading import Barrier, Thread
from uuid import UUID, uuid4

import pytest
from artana_evidence_api.proposal_store import (
    HarnessProposalDraft,
    HarnessProposalRecord,
    HarnessProposalStore,
)


def _create_candidate_claim_proposal(
    *,
    proposal_store: HarnessProposalStore,
    space_id: UUID,
    run_id: UUID,
) -> str:
    return proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key=f"doc:{uuid4()}",
                document_id=None,
                title="MED13 regulates transcription",
                summary="Synthetic proposal for concurrency testing.",
                confidence=0.82,
                ranking_score=0.91,
                reasoning_path={"source": "unit-test"},
                evidence_bundle=[],
                payload={
                    "proposed_subject": str(uuid4()),
                    "proposed_object": str(uuid4()),
                    "proposed_claim_type": "REGULATES",
                },
                metadata={"source": "unit-test"},
            ),
        ),
    )[0].id


def test_decide_proposal_allows_only_one_concurrent_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposal_store = HarnessProposalStore()
    space_id = uuid4()
    run_id = uuid4()
    proposal_id = _create_candidate_claim_proposal(
        proposal_store=proposal_store,
        space_id=space_id,
        run_id=run_id,
    )
    get_proposal = proposal_store.get_proposal
    barrier = Barrier(2)
    decided_statuses: list[str] = []
    errors: list[str] = []

    def _coordinated_get_proposal(
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
    ) -> HarnessProposalRecord | None:
        proposal = get_proposal(space_id=space_id, proposal_id=proposal_id)
        barrier.wait(timeout=5)
        return proposal

    monkeypatch.setattr(proposal_store, "get_proposal", _coordinated_get_proposal)

    def _decide(status: str) -> None:
        try:
            decision = proposal_store.decide_proposal(
                space_id=space_id,
                proposal_id=proposal_id,
                status=status,
                decision_reason=f"{status} from thread",
                metadata={"decision": status},
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
            return
        if decision is None:
            errors.append("Proposal disappeared during decision.")
            return
        decided_statuses.append(decision.status)

    first_thread = Thread(target=_decide, args=("promoted",))
    second_thread = Thread(target=_decide, args=("rejected",))
    first_thread.start()
    second_thread.start()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert not second_thread.is_alive()
    assert len(decided_statuses) == 1
    assert len(errors) == 1
    assert "already decided" in errors[0]
    final_record = get_proposal(space_id=space_id, proposal_id=proposal_id)
    assert final_record is not None
    assert final_record.status == decided_statuses[0]


def test_in_memory_harness_proposal_store_normalizes_oversized_titles() -> None:
    proposal_store = HarnessProposalStore()
    space_id = str(uuid4())
    run_id = str(uuid4())
    oversized_title = (
        "Extracted claim: "
        + ("MED13-associated transcriptional regulator " * 4)
        + "CAUSES "
        + ("neurodevelopmental disorder with variable expressivity " * 4)
    )

    created = proposal_store.create_proposals(
        space_id=space_id,
        run_id=run_id,
        proposals=(
            HarnessProposalDraft(
                proposal_type="candidate_claim",
                source_kind="document_extraction",
                source_key="doc-1:0",
                title=oversized_title,
                summary="Oversized extracted claim title should be normalized.",
                confidence=0.74,
                ranking_score=0.74,
                reasoning_path={"document_id": "doc-1"},
                evidence_bundle=[{"source_type": "paper", "locator": "doc-1"}],
                payload={"proposed_claim_type": "CAUSES"},
                metadata={"source_type": "pubmed"},
            ),
        ),
    )

    assert len(created) == 1
    assert len(created[0].title) == 256
    assert created[0].title.endswith("...")
