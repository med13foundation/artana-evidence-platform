"""Service-local review-item storage contracts for harness review workflows."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4

from artana_evidence_api.types.common import JSONObject  # noqa: TC001

_PENDING_REVIEW_STATUS = "pending_review"
_DECISION_STATUSES = frozenset({"resolved", "dismissed"})
_PRIORITY_VALUES = frozenset({"low", "medium", "high"})
_MAX_REVIEW_ITEM_TITLE_LENGTH = 256
_TITLE_ELLIPSIS = "..."


@dataclass(frozen=True, slots=True)
class HarnessReviewItemDraft:
    """One review item ready to be persisted by the harness layer."""

    review_type: str
    source_family: str
    source_kind: str
    source_key: str
    title: str
    summary: str
    priority: str
    confidence: float
    ranking_score: float
    evidence_bundle: list[JSONObject]
    payload: JSONObject
    metadata: JSONObject
    document_id: str | None = None
    review_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class HarnessReviewItemRecord:
    """One persisted review item in the harness review store."""

    id: str
    space_id: str
    run_id: str
    review_type: str
    source_family: str
    source_kind: str
    source_key: str
    document_id: str | None
    title: str
    summary: str
    priority: str
    status: str
    confidence: float
    ranking_score: float
    evidence_bundle: list[JSONObject]
    payload: JSONObject
    metadata: JSONObject
    decision_reason: str | None
    decided_at: datetime | None
    linked_proposal_id: str | None
    linked_approval_key: str | None
    created_at: datetime
    updated_at: datetime
    review_fingerprint: str | None = None


class HarnessReviewItemStore:
    """Store and retrieve review-only items for the harness layer."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._review_items: dict[str, HarnessReviewItemRecord] = {}
        self._review_item_ids_by_space: dict[str, list[str]] = {}

    @staticmethod
    def normalize_review_item_title(title: str) -> str:
        """Return a review-item title that is safe for persistence and display."""
        normalized = " ".join(title.split())
        if normalized == "":
            normalized = "Untitled review item"
        if len(normalized) <= _MAX_REVIEW_ITEM_TITLE_LENGTH:
            return normalized
        max_prefix_length = _MAX_REVIEW_ITEM_TITLE_LENGTH - len(_TITLE_ELLIPSIS)
        truncated = normalized[:max_prefix_length].rstrip()
        if truncated == "":
            return _TITLE_ELLIPSIS[:_MAX_REVIEW_ITEM_TITLE_LENGTH]
        return f"{truncated}{_TITLE_ELLIPSIS}"

    @staticmethod
    def normalize_priority(priority: str) -> str:
        """Return one supported priority label."""
        normalized = priority.strip().lower()
        if normalized not in _PRIORITY_VALUES:
            msg = f"Unsupported review item priority '{priority}'"
            raise ValueError(msg)
        return normalized

    @staticmethod
    def normalize_source_family(
        source_family: str,
        *,
        source_kind: str,
    ) -> str:
        """Return one normalized source family label."""
        normalized = source_family.strip().lower()
        if normalized != "":
            return normalized
        fallback = source_kind.strip().lower()
        if fallback != "":
            return fallback
        msg = "Review items require a non-empty source_family or source_kind"
        raise ValueError(msg)

    @classmethod
    def normalize_review_item_draft(
        cls,
        review_item: HarnessReviewItemDraft,
    ) -> HarnessReviewItemDraft:
        """Return a normalized draft with persistence-safe fields."""
        return replace(
            review_item,
            source_family=cls.normalize_source_family(
                review_item.source_family,
                source_kind=review_item.source_kind,
            ),
            title=cls.normalize_review_item_title(review_item.title),
            priority=cls.normalize_priority(review_item.priority),
        )

    def _existing_review_item(
        self,
        *,
        space_id: str,
        draft: HarnessReviewItemDraft,
    ) -> HarnessReviewItemRecord | None:
        for review_item_id in self._review_item_ids_by_space.get(space_id, []):
            existing = self._review_items.get(review_item_id)
            if existing is None:
                continue
            if (
                draft.review_fingerprint is not None
                and existing.review_fingerprint == draft.review_fingerprint
            ):
                return existing
            if (
                existing.review_type == draft.review_type
                and existing.source_key == draft.source_key
            ):
                return existing
        return None

    def create_review_items(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        review_items: tuple[HarnessReviewItemDraft, ...],
    ) -> list[HarnessReviewItemRecord]:
        """Persist a batch of review items for one run."""
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        created_records: list[HarnessReviewItemRecord] = []
        now = datetime.now(UTC)
        with self._lock:
            for review_item in review_items:
                normalized_item = self.normalize_review_item_draft(review_item)
                if (
                    self._existing_review_item(
                        space_id=normalized_space_id,
                        draft=normalized_item,
                    )
                    is not None
                ):
                    continue
                record = HarnessReviewItemRecord(
                    id=str(uuid4()),
                    space_id=normalized_space_id,
                    run_id=normalized_run_id,
                    review_type=normalized_item.review_type,
                    source_family=normalized_item.source_family,
                    source_kind=normalized_item.source_kind,
                    source_key=normalized_item.source_key,
                    document_id=normalized_item.document_id,
                    title=normalized_item.title,
                    summary=normalized_item.summary,
                    priority=normalized_item.priority,
                    status=_PENDING_REVIEW_STATUS,
                    confidence=normalized_item.confidence,
                    ranking_score=normalized_item.ranking_score,
                    evidence_bundle=list(normalized_item.evidence_bundle),
                    payload=normalized_item.payload,
                    metadata=normalized_item.metadata,
                    decision_reason=None,
                    decided_at=None,
                    linked_proposal_id=None,
                    linked_approval_key=None,
                    created_at=now,
                    updated_at=now,
                    review_fingerprint=normalized_item.review_fingerprint,
                )
                self._review_items[record.id] = record
                self._review_item_ids_by_space.setdefault(
                    normalized_space_id, []
                ).append(
                    record.id,
                )
                created_records.append(record)
        return sorted(
            created_records,
            key=lambda record: (-record.ranking_score, record.created_at),
        )

    def list_review_items(
        self,
        *,
        space_id: UUID | str,
        status: str | None = None,
        review_type: str | None = None,
        source_family: str | None = None,
        run_id: UUID | str | None = None,
        document_id: UUID | str | None = None,
    ) -> list[HarnessReviewItemRecord]:
        """List review items for one space ordered by ranking."""
        normalized_space_id = str(space_id)
        normalized_status = status.strip() if isinstance(status, str) else None
        normalized_type = review_type.strip() if isinstance(review_type, str) else None
        normalized_source_family = (
            source_family.strip().lower() if isinstance(source_family, str) else None
        )
        normalized_run_id = str(run_id) if run_id is not None else None
        normalized_document_id = str(document_id) if document_id is not None else None
        with self._lock:
            review_items = [
                self._review_items[review_item_id]
                for review_item_id in self._review_item_ids_by_space.get(
                    normalized_space_id,
                    [],
                )
            ]
        filtered = [
            review_item
            for review_item in review_items
            if (
                (normalized_status is None or review_item.status == normalized_status)
                and (
                    normalized_type is None
                    or review_item.review_type == normalized_type
                )
                and (
                    normalized_source_family is None
                    or review_item.source_family == normalized_source_family
                )
                and (
                    normalized_run_id is None or review_item.run_id == normalized_run_id
                )
                and (
                    normalized_document_id is None
                    or review_item.document_id == normalized_document_id
                )
            )
        ]
        return sorted(
            filtered,
            key=lambda review_item: (
                -review_item.ranking_score,
                review_item.updated_at,
            ),
        )

    def count_review_items(
        self,
        *,
        space_id: UUID | str,
    ) -> int:
        """Return how many review items belong to one research space."""
        normalized_space_id = str(space_id)
        with self._lock:
            return len(self._review_item_ids_by_space.get(normalized_space_id, []))

    def get_review_item(
        self,
        *,
        space_id: UUID | str,
        review_item_id: UUID | str,
    ) -> HarnessReviewItemRecord | None:
        """Return one review item from the store."""
        with self._lock:
            review_item = self._review_items.get(str(review_item_id))
        if review_item is None or review_item.space_id != str(space_id):
            return None
        return review_item

    def decide_review_item(
        self,
        *,
        space_id: UUID | str,
        review_item_id: UUID | str,
        status: str,
        decision_reason: str | None,
        metadata: JSONObject | None = None,
        linked_proposal_id: str | None = None,
        linked_approval_key: str | None = None,
    ) -> HarnessReviewItemRecord | None:
        """Resolve or dismiss one review item."""
        normalized_status = status.strip().lower()
        if normalized_status not in _DECISION_STATUSES:
            msg = f"Unsupported review item status '{status}'"
            raise ValueError(msg)
        with self._lock:
            review_item = self._review_items.get(str(review_item_id))
            if review_item is None or review_item.space_id != str(space_id):
                return None
            if review_item.status != _PENDING_REVIEW_STATUS:
                msg = (
                    f"Review item '{review_item_id}' is already decided with status "
                    f"'{review_item.status}'"
                )
                raise ValueError(msg)
            decision_timestamp = datetime.now(UTC)
            updated = HarnessReviewItemRecord(
                id=review_item.id,
                space_id=review_item.space_id,
                run_id=review_item.run_id,
                review_type=review_item.review_type,
                source_family=review_item.source_family,
                source_kind=review_item.source_kind,
                source_key=review_item.source_key,
                document_id=review_item.document_id,
                title=review_item.title,
                summary=review_item.summary,
                priority=review_item.priority,
                status=normalized_status,
                confidence=review_item.confidence,
                ranking_score=review_item.ranking_score,
                evidence_bundle=review_item.evidence_bundle,
                payload=review_item.payload,
                metadata={**review_item.metadata, **(metadata or {})},
                decision_reason=(
                    decision_reason.strip()
                    if isinstance(decision_reason, str)
                    and decision_reason.strip() != ""
                    else None
                ),
                decided_at=decision_timestamp,
                linked_proposal_id=(
                    linked_proposal_id.strip()
                    if isinstance(linked_proposal_id, str)
                    and linked_proposal_id.strip() != ""
                    else review_item.linked_proposal_id
                ),
                linked_approval_key=(
                    linked_approval_key.strip()
                    if isinstance(linked_approval_key, str)
                    and linked_approval_key.strip() != ""
                    else review_item.linked_approval_key
                ),
                created_at=review_item.created_at,
                updated_at=decision_timestamp,
                review_fingerprint=review_item.review_fingerprint,
            )
            self._review_items[review_item.id] = updated
            return updated


__all__ = [
    "HarnessReviewItemDraft",
    "HarnessReviewItemRecord",
    "HarnessReviewItemStore",
]
