"""Service-local approval and intent storage for harness runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID  # noqa: TC003

from artana_evidence_api.types.common import JSONObject  # noqa: TC001

_MAX_APPROVAL_TITLE_LENGTH = 256
_TITLE_ELLIPSIS = "..."


@dataclass(frozen=True, slots=True)
class HarnessApprovalAction:
    """One proposed action in a run intent plan."""

    approval_key: str
    title: str
    risk_level: str
    target_type: str
    target_id: str | None
    requires_approval: bool
    metadata: JSONObject


@dataclass(frozen=True, slots=True)
class HarnessRunIntentRecord:
    """Intent plan stored for one harness run."""

    space_id: str
    run_id: str
    summary: str
    proposed_actions: tuple[HarnessApprovalAction, ...]
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class HarnessApprovalRecord:
    """Approval decision record for one gated run action."""

    space_id: str
    run_id: str
    approval_key: str
    title: str
    risk_level: str
    target_type: str
    target_id: str | None
    status: str
    decision_reason: str | None
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


class HarnessApprovalStore:
    """Store run intent plans and approval decisions."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._intents: dict[tuple[str, str], HarnessRunIntentRecord] = {}
        self._approvals: dict[tuple[str, str], dict[str, HarnessApprovalRecord]] = {}

    def upsert_intent(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        summary: str,
        proposed_actions: tuple[HarnessApprovalAction, ...],
        metadata: JSONObject,
    ) -> HarnessRunIntentRecord:
        """Create or replace the intent plan for one run."""
        normalized_space_id = str(space_id)
        normalized_run_id = str(run_id)
        now = datetime.now(UTC)
        normalized_actions = tuple(
            normalize_approval_action(action) for action in proposed_actions
        )
        intent = HarnessRunIntentRecord(
            space_id=normalized_space_id,
            run_id=normalized_run_id,
            summary=summary,
            proposed_actions=normalized_actions,
            metadata=metadata,
            created_at=now,
            updated_at=now,
        )
        approval_records: dict[str, HarnessApprovalRecord] = {}
        for action in normalized_actions:
            if not action.requires_approval:
                continue
            approval_records[action.approval_key] = HarnessApprovalRecord(
                space_id=normalized_space_id,
                run_id=normalized_run_id,
                approval_key=action.approval_key,
                title=action.title,
                risk_level=action.risk_level,
                target_type=action.target_type,
                target_id=action.target_id,
                status="pending",
                decision_reason=None,
                metadata=action.metadata,
                created_at=now,
                updated_at=now,
            )
        with self._lock:
            self._intents[(normalized_space_id, normalized_run_id)] = intent
            self._approvals[(normalized_space_id, normalized_run_id)] = approval_records
        return intent

    def get_intent(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> HarnessRunIntentRecord | None:
        """Return the stored intent plan for one run."""
        key = (str(space_id), str(run_id))
        with self._lock:
            return self._intents.get(key)

    def list_approvals(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
    ) -> list[HarnessApprovalRecord]:
        """Return approvals for one run."""
        key = (str(space_id), str(run_id))
        with self._lock:
            approvals = self._approvals.get(key, {})
            return list(approvals.values())

    def list_space_approvals(
        self,
        *,
        space_id: UUID | str,
        status: str | None = None,
        run_id: UUID | str | None = None,
    ) -> list[HarnessApprovalRecord]:
        """Return approvals across one space, optionally filtered."""
        normalized_space_id = str(space_id)
        normalized_status = status.strip() if isinstance(status, str) else None
        normalized_run_id = str(run_id) if run_id is not None else None
        with self._lock:
            approvals = [
                approval
                for (approval_space_id, approval_run_id), records in self._approvals.items()
                if approval_space_id == normalized_space_id
                and (
                    normalized_run_id is None or approval_run_id == normalized_run_id
                )
                for approval in records.values()
            ]
        filtered = [
            approval
            for approval in approvals
            if normalized_status is None or approval.status == normalized_status
        ]
        return sorted(filtered, key=lambda approval: approval.updated_at, reverse=True)

    def decide_approval(
        self,
        *,
        space_id: UUID | str,
        run_id: UUID | str,
        approval_key: str,
        status: str,
        decision_reason: str | None,
    ) -> HarnessApprovalRecord | None:
        """Set the decision for one approval record."""
        normalized_status = status.strip().lower()
        if normalized_status not in {"approved", "rejected"}:
            msg = f"Unsupported approval status '{status}'"
            raise ValueError(msg)
        normalized_reason = (
            decision_reason.strip() if isinstance(decision_reason, str) else None
        )
        key = (str(space_id), str(run_id))
        with self._lock:
            approvals = self._approvals.get(key, {})
            existing = approvals.get(approval_key)
            if existing is None:
                return None
            if existing.status != "pending":
                msg = (
                    f"Approval '{approval_key}' is already decided with status "
                    f"'{existing.status}'"
                )
                raise ValueError(msg)
            updated = HarnessApprovalRecord(
                space_id=existing.space_id,
                run_id=existing.run_id,
                approval_key=existing.approval_key,
                title=existing.title,
                risk_level=existing.risk_level,
                target_type=existing.target_type,
                target_id=existing.target_id,
                status=normalized_status,
                decision_reason=normalized_reason,
                metadata=existing.metadata,
                created_at=existing.created_at,
                updated_at=datetime.now(UTC),
            )
            approvals[approval_key] = updated
            return updated


def normalize_approval_title(title: str) -> str:
    """Return an approval title safe for persistence and display."""
    normalized = " ".join(title.split())
    if normalized == "":
        normalized = "Untitled approval"
    if len(normalized) <= _MAX_APPROVAL_TITLE_LENGTH:
        return normalized
    max_prefix_length = _MAX_APPROVAL_TITLE_LENGTH - len(_TITLE_ELLIPSIS)
    truncated = normalized[:max_prefix_length].rstrip()
    if truncated == "":
        return _TITLE_ELLIPSIS[:_MAX_APPROVAL_TITLE_LENGTH]
    return f"{truncated}{_TITLE_ELLIPSIS}"


def normalize_approval_action(action: HarnessApprovalAction) -> HarnessApprovalAction:
    """Return an approval action with a persistence-safe title."""
    return HarnessApprovalAction(
        approval_key=action.approval_key,
        title=normalize_approval_title(action.title),
        risk_level=action.risk_level,
        target_type=action.target_type,
        target_id=action.target_id,
        requires_approval=action.requires_approval,
        metadata=action.metadata,
    )


__all__ = [
    "HarnessApprovalAction",
    "HarnessApprovalRecord",
    "HarnessApprovalStore",
    "HarnessRunIntentRecord",
    "normalize_approval_action",
    "normalize_approval_title",
]
