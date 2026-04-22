"""Service-local proposal storage contracts for graph-harness workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from artana_evidence_api.types.common import JSONObject  # noqa: TC001

logger = logging.getLogger(__name__)

_PENDING_REVIEW_STATUS = "pending_review"
_DECISION_STATUSES = frozenset({"promoted", "rejected"})
_MAX_PROPOSAL_TITLE_LENGTH = 256
_TITLE_ELLIPSIS = "..."


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
        return replace(
            proposal,
            title=cls.normalize_proposal_title(proposal.title),
        )

    def create_proposals(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        proposals: tuple[HarnessProposalDraft, ...],
    ) -> list[HarnessProposalRecord]:
        """Persist a batch of proposals for one run.

        Proposals whose ``claim_fingerprint`` matches an existing promoted
        or pending proposal in the same space are silently skipped.
        Proposals matching a *rejected* proposal are allowed through
        (the user explicitly rejected, new evidence may change the decision).
        """
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        created_records: list[HarnessProposalRecord] = []
        now = datetime.now(UTC)
        with self._lock:
            for proposal in proposals:
                normalized_proposal = self.normalize_proposal_draft(proposal)
                # --- fingerprint dedup ---
                if normalized_proposal.claim_fingerprint:
                    existing = self._fingerprint_exists(
                        normalized_space_id,
                        normalized_proposal.claim_fingerprint,
                    )
                    if existing and existing.status in (
                        _PENDING_REVIEW_STATUS,
                        "promoted",
                    ):
                        logger.info(
                            "Skipping duplicate proposal (fingerprint=%s, "
                            "existing=%s status=%s)",
                            normalized_proposal.claim_fingerprint[:12],
                            existing.id,
                            existing.status,
                        )
                        continue

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
                    status=_PENDING_REVIEW_STATUS,
                    confidence=normalized_proposal.confidence,
                    ranking_score=normalized_proposal.ranking_score,
                    reasoning_path=normalized_proposal.reasoning_path,
                    evidence_bundle=list(normalized_proposal.evidence_bundle),
                    payload=normalized_proposal.payload,
                    metadata=normalized_proposal.metadata,
                    claim_fingerprint=normalized_proposal.claim_fingerprint,
                    decision_reason=None,
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
    ) -> list[HarnessProposalRecord]:
        """List proposals for one space ordered by ranking."""
        normalized_space_id = str(space_id)
        normalized_status = status.strip() if isinstance(status, str) else None
        normalized_type = (
            proposal_type.strip() if isinstance(proposal_type, str) else None
        )
        normalized_run_id = str(run_id) if run_id is not None else None
        normalized_document_id = str(document_id) if document_id is not None else None
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

    def decide_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
        status: str,
        decision_reason: str | None,
        metadata: JSONObject | None = None,
    ) -> HarnessProposalRecord | None:
        """Promote or reject one proposal."""
        normalized_status = status.strip().lower()
        if normalized_status not in _DECISION_STATUSES:
            message = f"Unsupported proposal status '{status}'"
            raise ValueError(message)
        with self._lock:
            proposal = self._proposals.get(str(proposal_id))
            if proposal is None or proposal.space_id != str(space_id):
                return None
            if proposal.status != _PENDING_REVIEW_STATUS:
                message = (
                    f"Proposal '{proposal_id}' is already decided with status "
                    f"'{proposal.status}'"
                )
                raise ValueError(message)
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
                decision_reason=(
                    decision_reason.strip()
                    if isinstance(decision_reason, str)
                    and decision_reason.strip() != ""
                    else None
                ),
                decided_at=decision_timestamp,
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
                        decision_reason=reason,
                        decided_at=now,
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
