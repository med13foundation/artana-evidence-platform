"""Service-local proposal storage contracts for graph-harness workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from artana_evidence_api.claim_fingerprint import require_storable_fingerprint
from artana_evidence_api.document_extraction_support.proposal_relation_type_guard import (
    normalize_candidate_claim_relation_payload,
)
from artana_evidence_api.types.common import JSONObject  # noqa: TC001
from artana_evidence_api.types.evidence_grade import normalize_evidence_grade
from artana_evidence_api.types.review_actor import ReviewActor
from artana_evidence_api.types.source_provenance import ClaimSourceProvenance

logger = logging.getLogger(__name__)

_PENDING_REVIEW_STATUS = "pending_review"
#: Status for a proposal retained after a claim-fingerprint collision.
#:
#: Deliberately outside the review queue and outside migration 024's active
#: unique index.  A proposal in this state is a second independent observation
#: whose identity has not been adjudicated -- not something a reviewer can act
#: on, and not something to discard.  See ART-DATA-001.
IDENTITY_PENDING_STATUS = "identity_pending"
_DECISION_STATUSES = frozenset({"promoted", "rejected"})


def undecidable_proposal_message(*, proposal_id: object, status: str) -> str:
    """Return an accurate reason one proposal cannot be decided right now.

    A parked proposal used to report "is already decided with status
    'identity_pending'", which is false in the way that matters: nobody decided
    anything, and there is no decision for a reviewer to look up.  Both cases
    are still a 409 -- they conflict with the record's current state -- but a
    reviewer reading the message needs to be able to tell them apart.
    """
    if status == IDENTITY_PENDING_STATUS:
        return (
            f"Proposal '{proposal_id}' is parked awaiting identity adjudication "
            "and cannot be decided. It is a second independent observation whose "
            "identity has not been resolved against the existing one (ART-DATA-001); "
            "no decision has been made about it."
        )
    return f"Proposal '{proposal_id}' is already decided with status '{status}'"


def is_undecidable_proposal_error(exc: ValueError) -> bool:
    """Return whether one store error means "conflicts with the current state".

    The routers map store ValueErrors onto status codes by inspecting the text,
    so the parked wording has to be recognized here or a parked proposal would
    start reporting 400 instead of 409.
    """
    text = str(exc)
    return "already decided" in text or "parked awaiting identity" in text
_MAX_PROPOSAL_TITLE_LENGTH = 256
_TITLE_ELLIPSIS = "..."


def _is_same_document_rederivation(
    *,
    existing_document_id: str | None,
    incoming_document_id: str | None,
) -> bool:
    """Return whether a fingerprint collision is one document seen twice.

    Re-extracting a document reproduces its own claims, so a collision within a
    single document is the same observation arriving again -- deduplicating it
    loses nothing.  A collision across two documents is a genuine second
    source and must be retained (ART-DATA-001).

    Unknown provenance is treated as a distinct source: when either side has no
    document, the safe reading is that evidence might be lost, so the record is
    kept.
    """

    if existing_document_id is None or incoming_document_id is None:
        return False
    return str(existing_document_id) == str(incoming_document_id)


@dataclass(frozen=True, slots=True)
class HarnessProposalDraft:
    """One proposal ready to be persisted by the harness layer."""

    proposal_type: str
    source_kind: str
    source_key: str
    title: str
    summary: str
    confidence: float
    ranking_score: float
    reasoning_path: JSONObject
    evidence_bundle: list[JSONObject]
    payload: JSONObject
    metadata: JSONObject
    document_id: str | None = None
    claim_fingerprint: str | None = None
    evidence_grade: str | None = None
    source_provenance: ClaimSourceProvenance | None = None


@dataclass(frozen=True, slots=True)
class HarnessProposalRecord:
    """One persisted proposal in the harness proposal store."""

    id: str
    space_id: str
    run_id: str
    proposal_type: str
    source_kind: str
    source_key: str
    document_id: str | None
    title: str
    summary: str
    status: str
    confidence: float
    ranking_score: float
    reasoning_path: JSONObject
    evidence_bundle: list[JSONObject]
    payload: JSONObject
    metadata: JSONObject
    decision_reason: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime
    claim_fingerprint: str | None = None
    evidence_grade: str | None = None
    source_provenance: ClaimSourceProvenance | None = None
    decided_by: ReviewActor | None = None


class HarnessProposalStore:
    """Store and retrieve candidate proposals for graph-harness flows."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._proposals: dict[str, HarnessProposalRecord] = {}
        self._proposal_ids_by_space: dict[str, list[str]] = {}

    def _fingerprint_exists(
        self,
        space_id: str,
        fingerprint: str | None,
    ) -> HarnessProposalRecord | None:
        """Return an existing proposal with the same fingerprint, or None."""
        if not fingerprint:
            return None
        for pid in self._proposal_ids_by_space.get(space_id, []):
            p = self._proposals.get(pid)
            if p and p.claim_fingerprint == fingerprint:
                return p
        return None

    @staticmethod
    def normalize_proposal_title(title: str) -> str:
        """Return a proposal title that is safe for persistence and display."""
        normalized = " ".join(title.split())
        if normalized == "":
            normalized = "Untitled proposal"
        if len(normalized) <= _MAX_PROPOSAL_TITLE_LENGTH:
            return normalized
        max_prefix_length = _MAX_PROPOSAL_TITLE_LENGTH - len(_TITLE_ELLIPSIS)
        truncated = normalized[:max_prefix_length].rstrip()
        if truncated == "":
            return _TITLE_ELLIPSIS[:_MAX_PROPOSAL_TITLE_LENGTH]
        return f"{truncated}{_TITLE_ELLIPSIS}"

    @classmethod
    def normalize_proposal_draft(
        cls,
        proposal: HarnessProposalDraft,
    ) -> HarnessProposalDraft:
        """Return a normalized draft with persistence-safe presentation fields."""
        payload = normalize_candidate_claim_relation_payload(
            proposal_type=proposal.proposal_type,
            payload=proposal.payload,
        )
        if (
            proposal.source_provenance is not None
            and proposal.source_provenance.status == "verified"
            and proposal.document_id is None
        ):
            msg = "verified source provenance requires a proposal document_id"
            raise ValueError(msg)
        require_storable_fingerprint(
            proposal.claim_fingerprint,
            field="claim_fingerprint",
        )
        return replace(
            proposal,
            title=cls.normalize_proposal_title(proposal.title),
            payload=payload,
            evidence_grade=normalize_evidence_grade(proposal.evidence_grade),
        )

    def create_proposals(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        proposals: tuple[HarnessProposalDraft, ...],
    ) -> list[HarnessProposalRecord]:
        """Persist a batch of proposals for one run.

        A proposal whose ``claim_fingerprint`` matches an active proposal in the
        same space is retained as ``IDENTITY_PENDING`` rather than dropped: it
        is a second independent observation, and whether it is genuinely the
        same assertion needs an identity model that does not exist yet.  A
        proposal matching a *rejected* one is admitted normally, since the
        rejection was an explicit human decision that new evidence may revisit.

        See ART-DATA-001.  This mirrors the durable store so the two
        implementations cannot diverge on whether data survives.
        """
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        created_records: list[HarnessProposalRecord] = []
        now = datetime.now(UTC)
        with self._lock:
            for proposal in proposals:
                normalized_proposal = self.normalize_proposal_draft(proposal)
                status = _PENDING_REVIEW_STATUS
                decision_reason: str | None = None
                if normalized_proposal.claim_fingerprint:
                    existing = self._fingerprint_exists(
                        normalized_space_id,
                        normalized_proposal.claim_fingerprint,
                    )
                    if existing and existing.status in (
                        _PENDING_REVIEW_STATUS,
                        "promoted",
                    ):
                        if _is_same_document_rederivation(
                            existing_document_id=existing.document_id,
                            incoming_document_id=normalized_proposal.document_id,
                        ):
                            logger.info(
                                "Skipping re-derived proposal from the same "
                                "document (fingerprint=%s, existing=%s)",
                                normalized_proposal.claim_fingerprint[:12],
                                existing.id,
                            )
                            continue
                        status = IDENTITY_PENDING_STATUS
                        decision_reason = (
                            "Retained by ART-DATA-001: claim fingerprint "
                            f"{normalized_proposal.claim_fingerprint} already "
                            f"has an active proposal {existing.id} with status "
                            f"'{existing.status}' from a different document in "
                            "this space. Awaiting identity adjudication; not "
                            "auto-merged."
                        )
                        logger.info(
                            "Retaining cross-document duplicate proposal as %s "
                            "(fingerprint=%s, existing=%s status=%s)",
                            IDENTITY_PENDING_STATUS,
                            normalized_proposal.claim_fingerprint[:12],
                            existing.id,
                            existing.status,
                        )

                record = HarnessProposalRecord(
                    id=str(uuid4()),
                    space_id=normalized_space_id,
                    run_id=normalized_run_id,
                    proposal_type=normalized_proposal.proposal_type,
                    source_kind=normalized_proposal.source_kind,
                    source_key=normalized_proposal.source_key,
                    document_id=normalized_proposal.document_id,
                    title=normalized_proposal.title,
                    summary=normalized_proposal.summary,
                    status=status,
                    confidence=normalized_proposal.confidence,
                    ranking_score=normalized_proposal.ranking_score,
                    reasoning_path=normalized_proposal.reasoning_path,
                    evidence_bundle=list(normalized_proposal.evidence_bundle),
                    payload=normalized_proposal.payload,
                    metadata=normalized_proposal.metadata,
                    claim_fingerprint=normalized_proposal.claim_fingerprint,
                    evidence_grade=normalized_proposal.evidence_grade,
                    source_provenance=normalized_proposal.source_provenance,
                    decision_reason=decision_reason,
                    decided_at=None,
                    created_at=now,
                    updated_at=now,
                )
                self._proposals[record.id] = record
                self._proposal_ids_by_space.setdefault(normalized_space_id, []).append(
                    record.id,
                )
                created_records.append(record)
        return sorted(
            created_records,
            key=lambda record: (-record.ranking_score, record.created_at),
        )

    def list_proposals(
        self,
        *,
        space_id: UUID | str,
        status: str | None = None,
        proposal_type: str | None = None,
        run_id: UUID | str | None = None,
        document_id: UUID | str | None = None,
        evidence_grade: str | None = None,
    ) -> list[HarnessProposalRecord]:
        """List proposals for one space ordered by ranking."""
        normalized_space_id = str(space_id)
        normalized_status = status.strip() if isinstance(status, str) else None
        normalized_type = (
            proposal_type.strip() if isinstance(proposal_type, str) else None
        )
        normalized_run_id = str(run_id) if run_id is not None else None
        normalized_document_id = str(document_id) if document_id is not None else None
        normalized_evidence_grade = normalize_evidence_grade(evidence_grade)
        with self._lock:
            proposals = [
                self._proposals[proposal_id]
                for proposal_id in self._proposal_ids_by_space.get(
                    normalized_space_id,
                    [],
                )
            ]
        filtered = [
            proposal
            for proposal in proposals
            if (
                (normalized_status is None or proposal.status == normalized_status)
                and (
                    normalized_type is None or proposal.proposal_type == normalized_type
                )
                and (normalized_run_id is None or proposal.run_id == normalized_run_id)
                and (
                    normalized_document_id is None
                    or proposal.document_id == normalized_document_id
                )
                and (
                    normalized_evidence_grade is None
                    or proposal.evidence_grade == normalized_evidence_grade
                )
            )
        ]
        return sorted(
            filtered,
            key=lambda proposal: (-proposal.ranking_score, proposal.updated_at),
        )

    def count_proposals(
        self,
        *,
        space_id: UUID | str,
    ) -> int:
        """Return how many proposals belong to one research space."""
        normalized_space_id = str(space_id)
        with self._lock:
            return len(self._proposal_ids_by_space.get(normalized_space_id, []))

    def get_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
    ) -> HarnessProposalRecord | None:
        """Return one proposal from the store."""
        with self._lock:
            proposal = self._proposals.get(str(proposal_id))
        if proposal is None or proposal.space_id != str(space_id):
            return None
        return proposal

    def delete_proposals_for_documents(
        self,
        *,
        space_id: UUID | str,
        document_ids: tuple[UUID | str, ...],
    ) -> int:
        """Delete proposals linked to any supplied document ids."""
        normalized_space_id = str(space_id)
        target_ids = {str(document_id) for document_id in document_ids}
        if not target_ids:
            return 0
        deleted_count = 0
        with self._lock:
            proposal_ids = list(
                self._proposal_ids_by_space.get(normalized_space_id, [])
            )
            retained_ids: list[str] = []
            for proposal_id in proposal_ids:
                proposal = self._proposals.get(proposal_id)
                if proposal is None:
                    continue
                if proposal.document_id in target_ids:
                    del self._proposals[proposal_id]
                    deleted_count += 1
                    continue
                retained_ids.append(proposal_id)
            self._proposal_ids_by_space[normalized_space_id] = retained_ids
        return deleted_count

    def decide_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
        status: str,
        decision_reason: str | None,
        decided_by: ReviewActor | None,
        metadata: JSONObject | None = None,
    ) -> HarnessProposalRecord | None:
        """Promote or reject one proposal.

        ``decided_by`` has no default so that every caller has to say who is
        deciding.  Passing None is allowed -- some decisions really are made by
        the system -- but it has to be said out loud rather than defaulted into.
        """
        normalized_status = status.strip().lower()
        if normalized_status not in _DECISION_STATUSES:
            message = f"Unsupported proposal status '{status}'"
            raise ValueError(message)
        with self._lock:
            proposal = self._proposals.get(str(proposal_id))
            if proposal is None or proposal.space_id != str(space_id):
                return None
            if proposal.status != _PENDING_REVIEW_STATUS:
                raise ValueError(
                    undecidable_proposal_message(
                        proposal_id=proposal_id,
                        status=proposal.status,
                    ),
                )
            decision_timestamp = datetime.now(UTC)
            updated = HarnessProposalRecord(
                id=proposal.id,
                space_id=proposal.space_id,
                run_id=proposal.run_id,
                proposal_type=proposal.proposal_type,
                source_kind=proposal.source_kind,
                source_key=proposal.source_key,
                document_id=proposal.document_id,
                title=proposal.title,
                summary=proposal.summary,
                status=normalized_status,
                confidence=proposal.confidence,
                ranking_score=proposal.ranking_score,
                reasoning_path=proposal.reasoning_path,
                evidence_bundle=proposal.evidence_bundle,
                payload=proposal.payload,
                metadata={**proposal.metadata, **(metadata or {})},
                claim_fingerprint=proposal.claim_fingerprint,
                evidence_grade=proposal.evidence_grade,
                decision_reason=(
                    decision_reason.strip()
                    if isinstance(decision_reason, str)
                    and decision_reason.strip() != ""
                    else None
                ),
                decided_at=decision_timestamp,
                decided_by=decided_by,
                source_provenance=proposal.source_provenance,
                created_at=proposal.created_at,
                updated_at=decision_timestamp,
            )
            self._proposals[proposal.id] = updated
            return updated

    def reject_pending_duplicates(
        self,
        *,
        space_id: UUID | str,
        claim_fingerprint: str,
        exclude_id: UUID | str,
        reason: str,
    ) -> int:
        """Reject all pending_review proposals with the same fingerprint.

        Returns the number of proposals rejected.  Used after promotion to
        clean up duplicate proposals that can never be approved.
        """
        normalized_space_id = str(space_id)
        normalized_exclude_id = str(exclude_id)
        count = 0
        now = datetime.now(UTC)
        with self._lock:
            for pid in self._proposal_ids_by_space.get(normalized_space_id, []):
                p = self._proposals.get(pid)
                if (
                    p
                    and p.id != normalized_exclude_id
                    and p.claim_fingerprint == claim_fingerprint
                    and p.status == _PENDING_REVIEW_STATUS
                ):
                    rejected = HarnessProposalRecord(
                        id=p.id,
                        space_id=p.space_id,
                        run_id=p.run_id,
                        proposal_type=p.proposal_type,
                        source_kind=p.source_kind,
                        source_key=p.source_key,
                        document_id=p.document_id,
                        title=p.title,
                        summary=p.summary,
                        status="rejected",
                        confidence=p.confidence,
                        ranking_score=p.ranking_score,
                        reasoning_path=p.reasoning_path,
                        evidence_bundle=p.evidence_bundle,
                        payload=p.payload,
                        metadata=p.metadata,
                        claim_fingerprint=p.claim_fingerprint,
                        evidence_grade=p.evidence_grade,
                        decision_reason=reason,
                        decided_at=now,
                        source_provenance=p.source_provenance,
                        created_at=p.created_at,
                        updated_at=now,
                    )
                    self._proposals[p.id] = rejected
                    count += 1
        if count:
            logger.info(
                "Auto-rejected %d pending duplicate(s) for fingerprint=%s",
                count,
                claim_fingerprint[:12],
            )
        return count


__all__ = [
    "HarnessProposalDraft",
    "HarnessProposalRecord",
    "HarnessProposalStore",
]
