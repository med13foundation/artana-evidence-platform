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
#: Terminal status for a parked proposal adjudicated as the same fact.
#:
#: Not "rejected": nobody judged the observation unsupported.  A reviewer said
#: it names a claim the space already holds, and the record keeps its own
#: provenance and points at what it duplicates.  Outside migration 024's active
#: unique index, so it can keep its fingerprint.
DUPLICATE_STATUS = "duplicate"
#: What a reviewer can say about a parked proposal's identity.
DUPLICATE_RESOLUTION = "duplicate"
DISTINCT_RESOLUTION = "distinct"
IDENTITY_RESOLUTIONS = frozenset({DUPLICATE_RESOLUTION, DISTINCT_RESOLUTION})
_DECISION_STATUSES = frozenset({"promoted", "rejected"})
_ACTIVE_STATUSES = ("pending_review", "promoted")


def undecidable_proposal_message(*, proposal_id: object, status: str) -> str:
    """Return an accurate reason one proposal cannot be decided right now.

    A parked proposal used to report "is already decided with status
    'identity_pending'", which is false in the way that matters: nobody decided
    anything, and there is no decision for a reviewer to look up.  Both cases
    are still a 409 -- they conflict with the record's current state -- but a
    reviewer reading the message needs to be able to tell them apart, and the
    parked one now has somewhere to go.
    """
    if status == IDENTITY_PENDING_STATUS:
        return (
            f"Proposal '{proposal_id}' is parked awaiting identity adjudication "
            "and cannot be promoted or rejected until that is settled. It is a "
            "second independent observation whose identity has not been resolved "
            "against the existing one (ART-DATA-001). Adjudicate it first through "
            "the review-queue action endpoint: 'resolve_as_duplicate' if the two "
            "are the same fact, or 'release_as_distinct' if they are different "
            "facts, which returns it to pending_review to be decided normally."
        )
    return f"Proposal '{proposal_id}' is already decided with status '{status}'"


def unadjudicable_proposal_message(*, proposal_id: object, status: str) -> str:
    """Return why one proposal's identity cannot be adjudicated right now."""

    return (
        f"Proposal '{proposal_id}' has status '{status}', not "
        f"'{IDENTITY_PENDING_STATUS}', so there is no parked identity to "
        "adjudicate."
    )


def missing_duplicate_counterpart_message(*, proposal_id: object) -> str:
    """Return why "same fact" cannot be recorded without a counterpart."""

    return (
        f"Proposal '{proposal_id}' cannot be resolved as a duplicate because no "
        "active proposal in this space still holds its claim fingerprint. There "
        "is nothing left for it to duplicate, so recording one would invent a "
        "reference. Release it as distinct and decide it on its own merits."
    )


def require_fingerprint_for_bulk_reject(claim_fingerprint: str | None) -> str:
    """Return one usable fingerprint, or refuse to run a bulk rejection.

    ``reject_pending_duplicates`` rejects every pending proposal in a space that
    matches one fingerprint.  Handed no fingerprint, both implementations
    matched every proposal that *has* no fingerprint: the in-memory store
    because ``None == None``, and the durable store because SQLAlchemy renders
    ``column == None`` as ``IS NULL`` rather than as a never-true comparison.
    The two agreed, on the wrong answer -- a single call would have rejected
    every fingerprint-less pending proposal in the space, each with a reason
    saying it duplicated something.

    No caller passes None today; the signature says ``str``.  That is why this
    refuses rather than returning 0: a caller that reached here has lost track
    of what it is deduplicating, and quietly doing nothing would hide it just as
    effectively as quietly doing everything.
    """

    if not isinstance(claim_fingerprint, str) or claim_fingerprint.strip() == "":
        raise ValueError(missing_fingerprint_bulk_reject_message())
    return claim_fingerprint


def missing_fingerprint_bulk_reject_message() -> str:
    """Return why a bulk duplicate rejection cannot run without a fingerprint."""

    return (
        "reject_pending_duplicates requires a non-empty claim_fingerprint. "
        "Without one the query matches every pending proposal that has no "
        "fingerprint, which is a bulk rejection of unrelated evidence rather "
        "than a deduplication."
    )


def build_identity_adjudication(
    *,
    resolution: str,
    duplicate_of_proposal_id: str | None,
    released_claim_fingerprint: str | None,
    reason: str | None,
    decided_by: ReviewActor | None,
    decided_at: datetime,
) -> JSONObject:
    """Return the system-authored record of one identity adjudication.

    Kept in its own field rather than in ``metadata``, which callers populate
    freely -- a caller must not be able to supply data that reads back as
    adjudication history (the same reason migration 027 gave an approval its own
    superseded-decision column).  It also has to survive the later promote or
    reject of a released proposal, which overwrites decision_reason,
    decided_at and decided_by.
    """

    return {
        "resolution": resolution,
        "duplicate_of_proposal_id": duplicate_of_proposal_id,
        "released_claim_fingerprint": released_claim_fingerprint,
        "reason": reason.strip()
        if isinstance(reason, str) and reason.strip() != ""
        else None,
        "decided_by_user_id": decided_by.user_id if decided_by is not None else None,
        "decided_by_email": decided_by.email if decided_by is not None else None,
        "decided_at": decided_at.isoformat(),
    }


def clean_decision_reason(reason: str | None) -> str | None:
    """Return one written reason, or None when nothing usable was written."""

    if isinstance(reason, str) and reason.strip() != "":
        return reason.strip()
    return None


def normalize_identity_resolution(resolution: str) -> str:
    """Return one supported identity resolution, or raise."""

    normalized = resolution.strip().lower()
    if normalized not in IDENTITY_RESOLUTIONS:
        msg = (
            f"Unsupported identity resolution '{resolution}'. Supported values: "
            f"{', '.join(sorted(IDENTITY_RESOLUTIONS))}"
        )
        raise ValueError(msg)
    return normalized


def is_undecidable_proposal_error(exc: ValueError) -> bool:
    """Return whether one store error means "conflicts with the current state".

    The routers map store ValueErrors onto status codes by inspecting the text,
    so the parked wording has to be recognized here or a parked proposal would
    start reporting 400 instead of 409.
    """
    text = str(exc)
    return (
        "already decided" in text
        or "parked awaiting identity" in text
        or "so there is no parked identity to adjudicate" in text
        or "cannot be resolved as a duplicate" in text
    )
_MAX_PROPOSAL_TITLE_LENGTH = 256
_TITLE_ELLIPSIS = "..."


def _is_same_known_document(
    *,
    existing_document_id: str | None,
    incoming_document_id: str | None,
) -> bool:
    """Return whether two proposals are known to come from one document.

    Unknown provenance is never "the same": when either side has no document,
    the safe reading is that they may be two sources, so they are treated as
    two.
    """

    if existing_document_id is None or incoming_document_id is None:
        return False
    return str(existing_document_id) == str(incoming_document_id)


def _is_same_document_rederivation(
    *,
    existing_document_id: str | None,
    incoming_document_id: str | None,
) -> bool:
    """Return whether a collision with a *stored* proposal is a re-extraction.

    Re-extracting an already-persisted document reproduces its own claims, so
    the incoming copy is the same observation arriving again -- deduplicating it
    loses nothing, and retaining it would add a row on every re-extraction.  A
    collision across two documents is a genuine second source and must be
    retained (ART-DATA-001).

    This reading holds only against a proposal that was already committed.  Two
    drafts of *one* extraction pass that share a document are not one
    observation arriving twice; see ``in_batch_identity_collision_reason``.
    """

    return _is_same_known_document(
        existing_document_id=existing_document_id,
        incoming_document_id=incoming_document_id,
    )


def in_batch_identity_collision_reason(
    *,
    claim_fingerprint: str,
    same_document: bool,
) -> str:
    """Return why one draft was parked against an earlier draft in its batch.

    Both cases park (ART-DATA-001), including the same-document one.  A single
    extraction pass emitting two drafts under one fingerprint is not that
    document being read twice: the two drafts carry their own evidence bundles,
    spans and provenance, and the fingerprint is precisely the thing that cannot
    tell them apart.  Dropping the second would delete an observation with no
    row and no log, which is the failure this rule exists to prevent.
    """

    origin = "the same document" if same_document else "a different document"
    return (
        f"Retained by ART-DATA-001: claim fingerprint {claim_fingerprint} is "
        "already claimed by an earlier proposal in this same batch, from "
        f"{origin}. Awaiting identity adjudication; not auto-merged."
    )


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
    #: System-authored trail of how this record's parked identity was settled.
    identity_adjudication: JSONObject | None = None


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

        Two drafts of this same call that collide are both kept, whichever
        document they came from: one extraction pass emitting two claims under
        one fingerprint is ordinary, and the second one's evidence is not the
        first one's.

        See ART-DATA-001.  This mirrors the durable store so the two
        implementations cannot diverge on whether data survives.
        """
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        created_records: list[HarnessProposalRecord] = []
        # Fingerprints this call has already planned as pending_review, which
        # are the ones that take the active-identity slot.  Without this the
        # second draft of one extraction pass looks indistinguishable from a
        # re-extraction of an already-stored document, and gets dropped.
        claimed_in_batch: dict[str, str | None] = {}
        now = datetime.now(UTC)
        with self._lock:
            for proposal in proposals:
                normalized_proposal = self.normalize_proposal_draft(proposal)
                planned = self._plan_one_proposal(
                    space_id=normalized_space_id,
                    normalized_proposal=normalized_proposal,
                    claimed_in_batch=claimed_in_batch,
                )
                if planned is None:
                    continue
                status, decision_reason = planned
                if (
                    status == _PENDING_REVIEW_STATUS
                    and normalized_proposal.claim_fingerprint
                ):
                    claimed_in_batch[normalized_proposal.claim_fingerprint] = (
                        normalized_proposal.document_id
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

    def _plan_one_proposal(
        self,
        *,
        space_id: str,
        normalized_proposal: HarnessProposalDraft,
        claimed_in_batch: dict[str, str | None],
    ) -> tuple[str, str | None] | None:
        """Decide one draft's status, or return None to drop it.

        Dropping is reserved for a single case -- re-extracting a document whose
        claim is already stored -- and it is logged, because a proposal that
        leaves no row must at least leave a trace (ART-DATA-001).
        """

        fingerprint = normalized_proposal.claim_fingerprint
        if not fingerprint:
            return (_PENDING_REVIEW_STATUS, None)
        if fingerprint in claimed_in_batch:
            return (
                IDENTITY_PENDING_STATUS,
                in_batch_identity_collision_reason(
                    claim_fingerprint=fingerprint,
                    same_document=_is_same_known_document(
                        existing_document_id=claimed_in_batch[fingerprint],
                        incoming_document_id=normalized_proposal.document_id,
                    ),
                ),
            )
        existing = self._fingerprint_exists(space_id, fingerprint)
        if existing is None or existing.status not in (
            _PENDING_REVIEW_STATUS,
            "promoted",
        ):
            return (_PENDING_REVIEW_STATUS, None)
        if _is_same_document_rederivation(
            existing_document_id=existing.document_id,
            incoming_document_id=normalized_proposal.document_id,
        ):
            logger.info(
                "Dropping re-derived proposal from the already-stored document "
                "(fingerprint=%s, existing=%s, source_key=%s)",
                fingerprint[:12],
                existing.id,
                normalized_proposal.source_key,
            )
            return None
        logger.info(
            "Retaining cross-document duplicate proposal as %s "
            "(fingerprint=%s, existing=%s status=%s)",
            IDENTITY_PENDING_STATUS,
            fingerprint[:12],
            existing.id,
            existing.status,
        )
        return (
            IDENTITY_PENDING_STATUS,
            (
                "Retained by ART-DATA-001: claim fingerprint "
                f"{fingerprint} already has an active proposal {existing.id} "
                f"with status '{existing.status}' from a different document in "
                "this space. Awaiting identity adjudication; not auto-merged."
            ),
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
                # Survives the decision on purpose: a released proposal was
                # adjudicated by one reviewer and decided by another, and the
                # decision fields only have room for the second.
                identity_adjudication=proposal.identity_adjudication,
                created_at=proposal.created_at,
                updated_at=decision_timestamp,
            )
            self._proposals[proposal.id] = updated
            return updated

    def adjudicate_parked_proposal(
        self,
        *,
        space_id: UUID | str,
        proposal_id: UUID | str,
        resolution: str,
        reason: str | None,
        decided_by: ReviewActor | None,
    ) -> HarnessProposalRecord | None:
        """Settle whether a parked proposal is the same fact as the one it hit.

        ``identity_pending`` used to be terminal: no route reached it, the queue
        offered no action on it, and every recovered second observation went
        somewhere nobody could see.  This is the exit, and it is the reviewer's
        to take -- the system still refuses to guess (ART-DATA-001).

        "duplicate" keeps the record and points it at what it duplicates.
        "distinct" returns it to ``pending_review`` so it can be promoted or
        rejected normally, and clears its claim fingerprint: the reviewer has
        just said that fingerprint groups two different facts, so it does not
        identify this one, and leaving it would collide with the counterpart
        under migration 024's active unique index.
        """

        normalized_resolution = normalize_identity_resolution(resolution)
        with self._lock:
            proposal = self._proposals.get(str(proposal_id))
            if proposal is None or proposal.space_id != str(space_id):
                return None
            if proposal.status != IDENTITY_PENDING_STATUS:
                raise ValueError(
                    unadjudicable_proposal_message(
                        proposal_id=proposal_id,
                        status=proposal.status,
                    ),
                )
            decided_at = datetime.now(UTC)
            if normalized_resolution == DUPLICATE_RESOLUTION:
                counterpart = self._active_fingerprint_counterpart(
                    space_id=proposal.space_id,
                    claim_fingerprint=proposal.claim_fingerprint,
                    exclude_id=proposal.id,
                )
                if counterpart is None:
                    raise ValueError(
                        missing_duplicate_counterpart_message(
                            proposal_id=proposal_id,
                        ),
                    )
                updated = replace(
                    proposal,
                    status=DUPLICATE_STATUS,
                    decision_reason=clean_decision_reason(reason),
                    decided_at=decided_at,
                    decided_by=decided_by,
                    identity_adjudication=build_identity_adjudication(
                        resolution=normalized_resolution,
                        duplicate_of_proposal_id=counterpart.id,
                        released_claim_fingerprint=None,
                        reason=reason,
                        decided_by=decided_by,
                        decided_at=decided_at,
                    ),
                    updated_at=decided_at,
                )
            else:
                updated = replace(
                    proposal,
                    status=_PENDING_REVIEW_STATUS,
                    claim_fingerprint=None,
                    # Undecided again, so the decision fields must not claim
                    # otherwise; who released it lives in the adjudication.
                    decision_reason=None,
                    decided_at=None,
                    decided_by=None,
                    identity_adjudication=build_identity_adjudication(
                        resolution=normalized_resolution,
                        duplicate_of_proposal_id=None,
                        released_claim_fingerprint=proposal.claim_fingerprint,
                        reason=reason,
                        decided_by=decided_by,
                        decided_at=decided_at,
                    ),
                    updated_at=decided_at,
                )
            self._proposals[updated.id] = updated
            return updated

    def _active_fingerprint_counterpart(
        self,
        *,
        space_id: str,
        claim_fingerprint: str | None,
        exclude_id: str,
    ) -> HarnessProposalRecord | None:
        """Return the active proposal a parked one collided with, if it remains."""

        if not claim_fingerprint:
            return None
        for pid in self._proposal_ids_by_space.get(space_id, []):
            candidate = self._proposals.get(pid)
            if (
                candidate is not None
                and candidate.id != exclude_id
                and candidate.claim_fingerprint == claim_fingerprint
                and candidate.status in _ACTIVE_STATUSES
            ):
                return candidate
        return None

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

        Refuses an absent fingerprint (see
        ``missing_fingerprint_bulk_reject_message``).
        """
        require_fingerprint_for_bulk_reject(claim_fingerprint)
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
                    rejected = replace(
                        p,
                        status="rejected",
                        decision_reason=reason,
                        decided_at=now,
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
    "DISTINCT_RESOLUTION",
    "DUPLICATE_RESOLUTION",
    "DUPLICATE_STATUS",
    "IDENTITY_PENDING_STATUS",
    "IDENTITY_RESOLUTIONS",
    "HarnessProposalDraft",
    "HarnessProposalRecord",
    "HarnessProposalStore",
    "build_identity_adjudication",
    "in_batch_identity_collision_reason",
    "is_undecidable_proposal_error",
    "missing_duplicate_counterpart_message",
    "missing_fingerprint_bulk_reject_message",
    "require_fingerprint_for_bulk_reject",
    "normalize_identity_resolution",
    "unadjudicable_proposal_message",
    "undecidable_proposal_message",
]
