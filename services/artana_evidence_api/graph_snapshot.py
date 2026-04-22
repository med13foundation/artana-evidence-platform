"""Service-local graph snapshot storage for graph-harness workflows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from uuid import UUID, uuid4  # noqa: TC003

from artana_evidence_api.types.common import JSONObject  # noqa: TC001


def _normalized_string_list(values: list[str]) -> list[str]:
    normalized_values: list[str] = []
    seen_values: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized == "" or normalized in seen_values:
            continue
        normalized_values.append(normalized)
        seen_values.add(normalized)
    return normalized_values


@dataclass(frozen=True, slots=True)
class HarnessGraphSnapshotRecord:
    """One run-scoped graph-context snapshot persisted by the harness layer."""

    id: str
    space_id: str
    source_run_id: str
    claim_ids: list[str]
    relation_ids: list[str]
    graph_document_hash: str
    summary: JSONObject
    metadata: JSONObject
    created_at: datetime
    updated_at: datetime


class HarnessGraphSnapshotStore:
    """Store and retrieve graph-context snapshots for harness runs."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._records: dict[str, HarnessGraphSnapshotRecord] = {}
        self._snapshot_ids_by_space: dict[str, list[str]] = {}

    def create_snapshot(  # noqa: PLR0913
        self,
        *,
        space_id: UUID | str,
        source_run_id: UUID | str,
        claim_ids: list[str],
        relation_ids: list[str],
        graph_document_hash: str,
        summary: JSONObject,
        metadata: JSONObject | None = None,
    ) -> HarnessGraphSnapshotRecord:
        """Persist one new run-scoped graph-context snapshot."""
        now = datetime.now(UTC)
        record = HarnessGraphSnapshotRecord(
            id=str(uuid4()),
            space_id=str(space_id),
            source_run_id=str(source_run_id),
            claim_ids=_normalized_string_list(claim_ids),
            relation_ids=_normalized_string_list(relation_ids),
            graph_document_hash=graph_document_hash.strip(),
            summary=summary,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._records[record.id] = record
            self._snapshot_ids_by_space.setdefault(record.space_id, []).append(
                record.id,
            )
        return record

    def get_snapshot(
        self,
        *,
        space_id: UUID | str,
        snapshot_id: UUID | str,
    ) -> HarnessGraphSnapshotRecord | None:
        """Return one snapshot when it belongs to the supplied space."""
        with self._lock:
            record = self._records.get(str(snapshot_id))
        if record is None or record.space_id != str(space_id):
            return None
        return record

    def list_snapshots(
        self,
        *,
        space_id: UUID | str,
        limit: int = 20,
    ) -> list[HarnessGraphSnapshotRecord]:
        """Return the most recent graph snapshots for one space."""
        normalized_space_id = str(space_id)
        with self._lock:
            snapshot_ids = tuple(
                self._snapshot_ids_by_space.get(normalized_space_id, []),
            )
            records = [self._records[snapshot_id] for snapshot_id in snapshot_ids]
        ordered = sorted(records, key=lambda record: record.created_at, reverse=True)
        return ordered[: max(limit, 0)]

    def count_snapshots(self, *, space_id: UUID | str) -> int:
        """Return how many graph snapshots belong to one research space."""
        normalized_space_id = str(space_id)
        with self._lock:
            return len(self._snapshot_ids_by_space.get(normalized_space_id, []))


__all__ = [
    "HarnessGraphSnapshotRecord",
    "HarnessGraphSnapshotStore",
]
