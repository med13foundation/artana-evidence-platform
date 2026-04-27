"""Durable handoffs from direct source-search captures to document extraction."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol, cast
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from artana_evidence_api.direct_source_search import (
    DirectSourceSearchRecord,
    DirectSourceSearchStore,
)
from artana_evidence_api.document_extraction import sha256_hex
from artana_evidence_api.document_store import (
    HarnessDocumentRecord,
    HarnessDocumentStore,
)
from artana_evidence_api.models import SourceSearchHandoffModel
from artana_evidence_api.run_registry import HarnessRunRegistry
from artana_evidence_api.source_policies import (
    source_record_policies,
    source_record_policy,
)
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    SourceResultCapture,
    source_result_capture_metadata,
)
from artana_evidence_api.sqlalchemy_unit_of_work import (
    commit_or_flush,
    in_unit_of_work,
    session_unit_of_work,
)
from artana_evidence_api.types.common import (
    JSONObject,
    JSONValue,
    json_object_or_empty,
)
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

SourceSearchHandoffStatus = Literal["pending", "completed", "failed"]
SourceSearchHandoffTargetKind = Literal["source_document"]

_DURABLE_RUN_BACKED_SOURCE_KEYS = frozenset(
    policy.source_key
    for policy in source_record_policies()
    if policy.direct_search_supported and policy.handoff_target_kind == "source_document"
)
_MAX_CLIENT_METADATA_BYTES = 16 * 1024
_LOGGER = logging.getLogger(__name__)


class SourceSearchHandoffRequest(BaseModel):
    """Request to hand one captured source-search record downstream."""

    model_config = ConfigDict(strict=True)

    target_kind: Literal["source_document"] = Field(
        default="source_document",
        description="Downstream target to create from the selected source record.",
    )
    record_index: int | None = Field(
        default=None,
        ge=0,
        description="Zero-based record index from the captured source-search response.",
    )
    external_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description="Provider identifier for the selected record when known.",
    )
    record_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[a-f0-9]{64}$",
        description="SHA-256 hash of the canonical selected source record JSON.",
    )
    idempotency_key: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description="Client-supplied idempotency key for safe retries.",
    )
    extract_now: bool = Field(
        default=False,
        description="When true, run the existing document extraction route after handoff.",
    )
    metadata: JSONObject = Field(
        default_factory=dict,
        description="Optional client metadata to attach to the handoff document.",
    )

    @field_validator("external_id", "idempotency_key", "record_hash")
    @classmethod
    def _normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = " ".join(value.split())
        return normalized or None

    @field_validator("metadata")
    @classmethod
    def _validate_metadata_size(cls, value: JSONObject) -> JSONObject:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if len(encoded) > _MAX_CLIENT_METADATA_BYTES:
            message = "metadata must be 16 KB or smaller"
            raise ValueError(message)
        return value


class SourceSearchHandoffResponse(BaseModel):
    """Response for a durable source-search handoff."""

    model_config = ConfigDict(strict=True)

    id: UUID
    space_id: UUID
    source_key: str
    search_id: UUID
    status: SourceSearchHandoffStatus
    target_kind: SourceSearchHandoffTargetKind
    idempotency_key: str
    selected_record_index: int
    selected_external_id: str | None = None
    target_document_id: UUID | None = None
    target_run_id: UUID | None = None
    source_capture: SourceResultCapture | None = None
    handoff_payload: JSONObject
    extraction: JSONObject | None = None
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class SourceSearchHandoffRecord:
    """One persisted source-search handoff row."""

    id: str
    space_id: str
    source_key: str
    search_id: str
    status: SourceSearchHandoffStatus
    target_kind: SourceSearchHandoffTargetKind
    idempotency_key: str
    request_hash: str
    created_by: str
    record_selector_payload: JSONObject
    search_snapshot_payload: JSONObject
    source_capture_snapshot: JSONObject
    handoff_payload: JSONObject
    target_run_id: str | None
    target_document_id: str | None
    error_message: str | None
    completed_at: datetime | None


class SourceSearchHandoffConflictError(RuntimeError):
    """Raised when the same idempotency key is reused for different input."""


class SourceSearchHandoffNotFoundError(RuntimeError):
    """Raised when the requested source search cannot be found."""


class SourceSearchHandoffUnsupportedError(RuntimeError):
    """Raised when a source is not yet backed by durable source-search runs."""


class SourceSearchHandoffSelectionError(ValueError):
    """Raised when the request does not identify one source record."""


class SourceSearchHandoffStore(Protocol):
    """Storage contract for durable source-search handoffs."""

    def find(
        self,
        *,
        space_id: UUID,
        source_key: str,
        search_id: UUID,
        target_kind: SourceSearchHandoffTargetKind,
        idempotency_key: str,
    ) -> SourceSearchHandoffRecord | None:
        """Return an existing handoff for one idempotent operation."""
        ...

    def save(self, record: SourceSearchHandoffRecord) -> SourceSearchHandoffRecord:
        """Persist one handoff record."""
        ...

    def update(self, record: SourceSearchHandoffRecord) -> SourceSearchHandoffRecord:
        """Update one existing handoff record."""
        ...


class InMemorySourceSearchHandoffStore:
    """Small handoff store for focused route tests."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str, str, str, str], SourceSearchHandoffRecord] = {}

    @staticmethod
    def _key(
        record: SourceSearchHandoffRecord,
    ) -> tuple[str, str, str, str, str]:
        return (
            record.space_id,
            record.source_key,
            record.search_id,
            record.target_kind,
            record.idempotency_key,
        )

    def find(
        self,
        *,
        space_id: UUID,
        source_key: str,
        search_id: UUID,
        target_kind: SourceSearchHandoffTargetKind,
        idempotency_key: str,
    ) -> SourceSearchHandoffRecord | None:
        return self._records.get(
            (str(space_id), source_key, str(search_id), target_kind, idempotency_key),
        )

    def save(self, record: SourceSearchHandoffRecord) -> SourceSearchHandoffRecord:
        key = self._key(record)
        existing = self._records.get(key)
        if existing is not None:
            if existing.request_hash != record.request_hash:
                message = (
                    "Idempotency key was already used for a different handoff request."
                )
                raise SourceSearchHandoffConflictError(message)
            return existing
        self._records[key] = record
        return record

    def update(self, record: SourceSearchHandoffRecord) -> SourceSearchHandoffRecord:
        self._records[self._key(record)] = record
        return record


class SqlAlchemySourceSearchHandoffStore:
    """Persist source-search handoffs in the Evidence API database."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Group handoff writes under one explicit SQLAlchemy transaction."""

        with session_unit_of_work(self._session):
            yield

    def _finish_write(self, model: SourceSearchHandoffModel) -> SourceSearchHandoffRecord:
        commit_or_flush(self._session)
        self._session.refresh(model)
        return _handoff_record_from_model(model)

    def find(
        self,
        *,
        space_id: UUID,
        source_key: str,
        search_id: UUID,
        target_kind: SourceSearchHandoffTargetKind,
        idempotency_key: str,
    ) -> SourceSearchHandoffRecord | None:
        stmt = select(SourceSearchHandoffModel).where(
            SourceSearchHandoffModel.space_id == str(space_id),
            SourceSearchHandoffModel.source_key == source_key,
            SourceSearchHandoffModel.search_id == str(search_id),
            SourceSearchHandoffModel.target_kind == target_kind,
            SourceSearchHandoffModel.idempotency_key == idempotency_key,
        )
        model = self._session.execute(stmt).scalar_one_or_none()
        if model is None:
            return None
        return _handoff_record_from_model(model)

    def save(self, record: SourceSearchHandoffRecord) -> SourceSearchHandoffRecord:
        model = SourceSearchHandoffModel(
            id=record.id,
            space_id=record.space_id,
            source_key=record.source_key,
            search_id=record.search_id,
            target_kind=record.target_kind,
            idempotency_key=record.idempotency_key,
            request_hash=record.request_hash,
            status=record.status,
            created_by=record.created_by,
            record_selector_payload=record.record_selector_payload,
            search_snapshot_payload=record.search_snapshot_payload,
            source_capture_snapshot=record.source_capture_snapshot,
            handoff_payload=record.handoff_payload,
            target_run_id=record.target_run_id,
            target_document_id=record.target_document_id,
            error_message=record.error_message,
            completed_at=record.completed_at,
        )
        existing = self.find(
            space_id=UUID(record.space_id),
            source_key=record.source_key,
            search_id=UUID(record.search_id),
            target_kind=record.target_kind,
            idempotency_key=record.idempotency_key,
        )
        if existing is not None:
            if existing.request_hash != record.request_hash:
                message = (
                    "Idempotency key was already used for a different handoff "
                    "request."
                )
                raise SourceSearchHandoffConflictError(message)
            return existing

        try:
            if in_unit_of_work(self._session):
                self._session.add(model)
                self._session.flush()
                self._session.refresh(model)
                return _handoff_record_from_model(model)
            self._session.add(model)
            return self._finish_write(model)
        except IntegrityError as exc:
            if in_unit_of_work(self._session):
                raise
            self._session.rollback()
            existing = self.find(
                space_id=UUID(record.space_id),
                source_key=record.source_key,
                search_id=UUID(record.search_id),
                target_kind=record.target_kind,
                idempotency_key=record.idempotency_key,
            )
            if existing is None:
                raise
            if existing.request_hash != record.request_hash:
                message = (
                    "Idempotency key was already used for a different handoff "
                    "request."
                )
                raise SourceSearchHandoffConflictError(message) from exc
            return existing

    def update(self, record: SourceSearchHandoffRecord) -> SourceSearchHandoffRecord:
        model = self._session.get(SourceSearchHandoffModel, record.id)
        if model is None:
            return self.save(record)
        model.status = record.status
        model.request_hash = record.request_hash
        model.record_selector_payload = record.record_selector_payload
        model.search_snapshot_payload = record.search_snapshot_payload
        model.source_capture_snapshot = record.source_capture_snapshot
        model.handoff_payload = record.handoff_payload
        model.target_run_id = record.target_run_id
        model.target_document_id = record.target_document_id
        model.error_message = record.error_message
        model.completed_at = record.completed_at
        return self._finish_write(model)


def _handoff_transaction(
    store: SourceSearchHandoffStore,
) -> AbstractContextManager[None]:
    transaction = getattr(store, "transaction", None)
    if callable(transaction):
        return cast("Callable[[], AbstractContextManager[None]]", transaction)()
    return nullcontext()


class SourceSearchHandoffService:
    """Create idempotent downstream handoffs from saved source-search results."""

    def __init__(
        self,
        *,
        search_store: DirectSourceSearchStore,
        handoff_store: SourceSearchHandoffStore,
        document_store: HarnessDocumentStore,
        run_registry: HarnessRunRegistry,
    ) -> None:
        self._search_store = search_store
        self._handoff_store = handoff_store
        self._document_store = document_store
        self._run_registry = run_registry

    def create_handoff(
        self,
        *,
        space_id: UUID,
        source_key: str,
        search_id: UUID,
        created_by: UUID | str,
        request: SourceSearchHandoffRequest,
    ) -> SourceSearchHandoffResponse:
        """Create or replay one source-search handoff."""

        created_by_id = _validated_uuid_string(created_by)
        if source_key not in _DURABLE_RUN_BACKED_SOURCE_KEYS:
            message = (
                f"Source '{source_key}' search results are not yet backed by "
                "durable source_search_runs handoff storage."
            )
            raise SourceSearchHandoffUnsupportedError(message)

        source_search = self._search_store.get(
            space_id=space_id,
            source_key=source_key,
            search_id=search_id,
        )
        if source_search is None:
            message = "Source search was not found for this space and source."
            raise SourceSearchHandoffNotFoundError(message)

        selected = _select_record(
            source_key=source_key,
            records=source_search.records,
            record_index=request.record_index,
            external_id=request.external_id,
            record_hash=request.record_hash,
        )
        target_kind: SourceSearchHandoffTargetKind = "source_document"
        request_hash = _request_hash(request=request, target_kind=target_kind)
        idempotency_key = request.idempotency_key or _default_idempotency_key(
            selected=selected,
            target_kind=target_kind,
        )
        existing = self._handoff_store.find(
            space_id=space_id,
            source_key=source_key,
            search_id=search_id,
            target_kind=target_kind,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                message = (
                    "Idempotency key was already used for a different handoff request."
                )
                raise SourceSearchHandoffConflictError(message)
            if existing.status == "pending" and target_kind == "source_document":
                return self._complete_pending_document_handoff(
                    pending=existing,
                    persist_pending=False,
                    space_id=space_id,
                    source_key=source_key,
                    search_id=search_id,
                    created_by=created_by_id,
                    source_search=source_search,
                    selected=selected,
                )
            return _response_from_record(existing, replayed=True)

        document_id = _deterministic_document_id(
            space_id=space_id,
            source_key=source_key,
            search_id=search_id,
            target_kind=target_kind,
            idempotency_key=idempotency_key,
        )
        pending = _pending_document_record(
            space_id=space_id,
            source_key=source_key,
            search_id=search_id,
            created_by=created_by_id,
            source_search=source_search,
            selected=selected,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            document_id=document_id,
            request_metadata=request.metadata,
        )
        return self._complete_pending_document_handoff(
            pending=pending,
            persist_pending=True,
            space_id=space_id,
            source_key=source_key,
            search_id=search_id,
            created_by=created_by_id,
            source_search=source_search,
            selected=selected,
        )

    def _complete_pending_document_handoff(
        self,
        *,
        pending: SourceSearchHandoffRecord,
        persist_pending: bool,
        space_id: UUID,
        source_key: str,
        search_id: UUID,
        created_by: str,
        source_search: DirectSourceSearchRecord,
        selected: _SelectedSourceRecord,
    ) -> SourceSearchHandoffResponse:
        ingestion_run_id: str | None = None
        try:
            with _handoff_transaction(self._handoff_store):
                if persist_pending:
                    pending = self._handoff_store.save(pending)
                document_id = (
                    UUID(pending.target_document_id)
                    if pending.target_document_id is not None
                    else uuid4()
                )
                existing_document = self._document_store.get_document(
                    space_id=space_id,
                    document_id=document_id,
                )
                if existing_document is not None:
                    raw_capture = existing_document.metadata.get("source_capture")
                    source_capture = SourceResultCapture.model_validate(raw_capture)
                    completed = _completed_record(
                        space_id=space_id,
                        source_key=source_key,
                        search_id=search_id,
                        created_by=created_by,
                        source_search=source_search,
                        selected=selected,
                        idempotency_key=pending.idempotency_key,
                        request_hash=pending.request_hash,
                        run_id=existing_document.ingestion_run_id,
                        document=existing_document,
                        source_capture=source_capture,
                        handoff_id=pending.id,
                    )
                    return _response_from_record(
                        self._handoff_store.update(completed),
                        replayed=True,
                    )
                ingestion_run = self._run_registry.create_run(
                    space_id=space_id,
                    harness_id="source-search-handoff",
                    title=f"Source Handoff: {source_key} search {search_id}",
                    input_payload=_handoff_run_input(
                        source_key=source_key,
                        search_id=search_id,
                        selected=selected,
                        target_kind=pending.target_kind,
                    ),
                    graph_service_status="not_checked",
                    graph_service_version="not_checked",
                )
                ingestion_run_id = ingestion_run.id
                source_capture = _document_capture(
                    source_key=source_key,
                    search_id=search_id,
                    document_id=document_id,
                    run_id=ingestion_run.id,
                    source_search=source_search,
                    selected=selected,
                )
                document = _create_handoff_document(
                    document_store=self._document_store,
                    source_key=source_key,
                    space_id=space_id,
                    created_by=created_by,
                    document_id=document_id,
                    ingestion_run_id=ingestion_run.id,
                    source_search=source_search,
                    selected=selected,
                    source_capture=source_capture,
                    request_metadata=json_object_or_empty(
                        pending.handoff_payload.get("client_metadata"),
                    ),
                )
                self._run_registry.set_run_status(
                    space_id=space_id,
                    run_id=ingestion_run.id,
                    status="completed",
                )
                record = _completed_record(
                    space_id=space_id,
                    source_key=source_key,
                    search_id=search_id,
                    created_by=created_by,
                    source_search=source_search,
                    selected=selected,
                    idempotency_key=pending.idempotency_key,
                    request_hash=pending.request_hash,
                    run_id=ingestion_run.id,
                    document=document,
                    source_capture=source_capture,
                    handoff_id=pending.id,
                )
                return _response_from_record(
                    self._handoff_store.update(record),
                    replayed=False,
                )
        except Exception as exc:
            try:
                with _handoff_transaction(self._handoff_store):
                    failed_run_id = ingestion_run_id
                    if ingestion_run_id is not None:
                        failed_run = self._run_registry.set_run_status(
                            space_id=space_id,
                            run_id=ingestion_run_id,
                            status="failed",
                        )
                        if failed_run is None:
                            failed_run = self._run_registry.create_run(
                                space_id=space_id,
                                harness_id="source-search-handoff",
                                title=(
                                    f"Source Handoff Failed: {source_key} "
                                    f"search {search_id}"
                                ),
                                input_payload=_handoff_run_input(
                                    source_key=source_key,
                                    search_id=search_id,
                                    selected=selected,
                                    target_kind=pending.target_kind,
                                ),
                                graph_service_status="not_checked",
                                graph_service_version="not_checked",
                            )
                            failed_run = self._run_registry.set_run_status(
                                space_id=space_id,
                                run_id=failed_run.id,
                                status="failed",
                            )
                        if failed_run is not None:
                            failed_run_id = failed_run.id
                    latest = self._handoff_store.find(
                        space_id=space_id,
                        source_key=source_key,
                        search_id=search_id,
                        target_kind=pending.target_kind,
                        idempotency_key=pending.idempotency_key,
                    )
                    if latest is None or latest.status == "pending":
                        self._handoff_store.update(
                            _failed_record(
                                pending=latest or pending,
                                run_id=failed_run_id,
                                error_message=str(exc),
                            ),
                        )
            except Exception:
                _LOGGER.exception(
                    "Failed to persist failed source-search handoff '%s'.",
                    pending.id,
                )
            raise


@dataclass(frozen=True, slots=True)
class _SelectedSourceRecord:
    index: int
    record: JSONObject
    external_id: str | None


def _handoff_record_from_model(
    model: SourceSearchHandoffModel,
) -> SourceSearchHandoffRecord:
    return SourceSearchHandoffRecord(
        id=model.id,
        space_id=model.space_id,
        source_key=model.source_key,
        search_id=model.search_id,
        status=cast("SourceSearchHandoffStatus", model.status),
        target_kind=cast("SourceSearchHandoffTargetKind", model.target_kind),
        idempotency_key=model.idempotency_key,
        request_hash=model.request_hash,
        created_by=model.created_by,
        record_selector_payload=json_object_or_empty(model.record_selector_payload),
        search_snapshot_payload=json_object_or_empty(model.search_snapshot_payload),
        source_capture_snapshot=json_object_or_empty(model.source_capture_snapshot),
        handoff_payload=json_object_or_empty(model.handoff_payload),
        target_run_id=model.target_run_id,
        target_document_id=model.target_document_id,
        error_message=model.error_message,
        completed_at=model.completed_at,
    )


def _select_record(  # noqa: PLR0912
    *,
    source_key: str,
    records: list[JSONObject],
    record_index: int | None,
    external_id: str | None,
    record_hash: str | None,
) -> _SelectedSourceRecord:
    if not records:
        message = "Source search has no records to hand off."
        raise SourceSearchHandoffSelectionError(message)
    provided_selectors = sum(
        selector is not None for selector in (record_index, external_id, record_hash)
    )
    if provided_selectors > 1:
        message = "Provide only one of record_index, external_id, or record_hash."
        raise SourceSearchHandoffSelectionError(message)
    if record_index is not None:
        if record_index >= len(records):
            message = "record_index is outside the source-search record list."
            raise SourceSearchHandoffSelectionError(message)
        record = records[record_index]
        return _SelectedSourceRecord(
            index=record_index,
            record=record,
            external_id=_provider_external_id(source_key=source_key, record=record),
        )
    if external_id is not None:
        matches: list[_SelectedSourceRecord] = []
        for index, record in enumerate(records):
            provider_id = _provider_external_id(source_key=source_key, record=record)
            if provider_id == external_id:
                matches.append(
                    _SelectedSourceRecord(
                        index=index,
                        record=record,
                        external_id=provider_id,
                    ),
                )
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            message = (
                "external_id matched more than one source-search record; "
                "select by record_index or record_hash."
            )
            raise SourceSearchHandoffSelectionError(message)
        message = "external_id did not match any source-search record."
        raise SourceSearchHandoffSelectionError(message)
    if record_hash is not None:
        matches = []
        for index, record in enumerate(records):
            if _record_hash(record) == record_hash:
                matches.append(
                    _SelectedSourceRecord(
                        index=index,
                        record=record,
                        external_id=_provider_external_id(
                            source_key=source_key,
                            record=record,
                        ),
                    ),
                )
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            message = (
                "record_hash matched more than one source-search record; "
                "select by record_index."
            )
            raise SourceSearchHandoffSelectionError(message)
        message = "record_hash did not match any source-search record."
        raise SourceSearchHandoffSelectionError(message)
    if len(records) == 1:
        record = records[0]
        return _SelectedSourceRecord(
            index=0,
            record=record,
            external_id=_provider_external_id(source_key=source_key, record=record),
        )
    message = (
        "Select exactly one source-search record with record_index, "
        "external_id, or record_hash."
    )
    raise SourceSearchHandoffSelectionError(message)


def _provider_external_id(*, source_key: str, record: JSONObject) -> str | None:
    policy = source_record_policy(source_key)
    return policy.provider_external_id(record) if policy is not None else None


def _record_supports_variant_aware(
    *,
    source_key: str,
    selected: _SelectedSourceRecord,
) -> bool:
    policy = source_record_policy(source_key)
    return bool(policy and policy.recommends_variant_aware(selected.record))


def _handoff_run_input(
    *,
    source_key: str,
    search_id: UUID,
    selected: _SelectedSourceRecord,
    target_kind: SourceSearchHandoffTargetKind,
) -> JSONObject:
    return {
        "source_key": source_key,
        "search_id": str(search_id),
        "record_index": selected.index,
        "external_id": selected.external_id,
        "target_kind": target_kind,
    }


def _validated_uuid_string(value: UUID | str) -> str:
    try:
        return str(UUID(str(value)))
    except ValueError as exc:
        message = "created_by must be a UUID"
        raise ValueError(message) from exc


def _deterministic_document_id(
    *,
    space_id: UUID,
    source_key: str,
    search_id: UUID,
    target_kind: SourceSearchHandoffTargetKind,
    idempotency_key: str,
) -> UUID:
    return uuid5(
        NAMESPACE_URL,
        ":".join(
            (
                "source-search-handoff",
                str(space_id),
                source_key,
                str(search_id),
                target_kind,
                idempotency_key,
            ),
        ),
    )


def _request_hash(
    *,
    request: SourceSearchHandoffRequest,
    target_kind: SourceSearchHandoffTargetKind,
) -> str:
    payload = {
        **request.model_dump(mode="json", exclude_none=True),
        "resolved_target_kind": target_kind,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8"),
    ).hexdigest()


def _default_idempotency_key(
    *,
    selected: _SelectedSourceRecord,
    target_kind: SourceSearchHandoffTargetKind,
) -> str:
    if selected.external_id is not None:
        return f"{target_kind}:external:{selected.external_id}"
    return f"{target_kind}:record_hash:{_record_hash(selected.record)}"


def _record_hash(record: JSONObject) -> str:
    return hashlib.sha256(
        json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8"),
    ).hexdigest()


def _search_snapshot(source_search: DirectSourceSearchRecord) -> JSONObject:
    return json_object_or_empty(
        source_search.model_dump(
            mode="json",
            exclude={"records"},
        ),
    )


def _record_selector(selected: _SelectedSourceRecord) -> JSONObject:
    payload: JSONObject = {
        "record_index": selected.index,
    }
    if selected.external_id is not None:
        payload["external_id"] = selected.external_id
    return payload


def _document_capture(
    *,
    source_key: str,
    search_id: UUID,
    document_id: UUID,
    run_id: str,
    source_search: DirectSourceSearchRecord,
    selected: _SelectedSourceRecord,
) -> SourceResultCapture:
    metadata = source_result_capture_metadata(
        source_key=source_key,
        capture_stage=SourceCaptureStage.SOURCE_DOCUMENT,
        capture_method="direct_source_handoff",
        locator=f"{source_key}:search:{search_id}:record:{selected.index}",
        external_id=selected.external_id,
        retrieved_at=datetime.now(UTC),
        run_id=run_id,
        search_id=str(search_id),
        document_id=str(document_id),
        query=source_search.query,
        query_payload=source_search.source_capture.query_payload,
        result_count=1,
        provenance={
            **source_search.source_capture.provenance,
            "selected_record_index": selected.index,
        },
    )
    return SourceResultCapture.model_validate(metadata)


def _create_handoff_document(
    *,
    document_store: HarnessDocumentStore,
    source_key: str,
    space_id: UUID,
    created_by: UUID | str,
    document_id: UUID,
    ingestion_run_id: str,
    source_search: DirectSourceSearchRecord,
    selected: _SelectedSourceRecord,
    source_capture: SourceResultCapture,
    request_metadata: JSONObject,
) -> HarnessDocumentRecord:
    text = _source_record_text(
        source_key=source_key,
        source_search=source_search,
        selected=selected,
    )
    encoded = text.encode("utf-8")
    title = _source_record_title(
        source_key=source_key,
        source_search=source_search,
        selected=selected,
    )
    normalized_record = _normalized_source_record(
        source_key=source_key,
        selected=selected,
    )
    metadata: JSONObject = {
        "source_capture": source_capture.to_metadata(),
        "source_family": _source_family(source_key),
        "normalization_profile": f"{source_key}_source_document_v1",
        "source_search_id": str(source_search.id),
        "source_search_handoff": True,
        "selected_record_index": selected.index,
        "selected_record": selected.record,
        "normalized_record": normalized_record,
        "client_metadata": request_metadata,
        "variant_aware_recommended": _record_supports_variant_aware(
            source_key=source_key,
            selected=selected,
        ),
    }
    return document_store.create_document(
        document_id=document_id,
        space_id=space_id,
        created_by=created_by,
        title=title,
        source_type=source_key,
        filename=None,
        media_type="application/json",
        sha256=sha256_hex(encoded),
        byte_size=len(encoded),
        page_count=None,
        text_content=text,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=ingestion_run_id,
        last_enrichment_run_id=None,
        enrichment_status="completed",
        extraction_status="pending",
        metadata=metadata,
    )


def _pending_document_record(
    *,
    space_id: UUID,
    source_key: str,
    search_id: UUID,
    created_by: str,
    source_search: DirectSourceSearchRecord,
    selected: _SelectedSourceRecord,
    idempotency_key: str,
    request_hash: str,
    document_id: UUID,
    request_metadata: JSONObject,
) -> SourceSearchHandoffRecord:
    return SourceSearchHandoffRecord(
        id=str(uuid4()),
        space_id=str(space_id),
        source_key=source_key,
        search_id=str(search_id),
        status="pending",
        target_kind="source_document",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        created_by=created_by,
        record_selector_payload=_record_selector(selected),
        search_snapshot_payload=_search_snapshot(source_search),
        source_capture_snapshot={},
        handoff_payload={
            "selected_record_index": selected.index,
            "selected_record": selected.record,
            "selected_external_id": selected.external_id,
            "target_document_id": str(document_id),
            "document_extraction_status": "pending_handoff",
            "client_metadata": request_metadata,
        },
        target_run_id=None,
        target_document_id=str(document_id),
        error_message=None,
        completed_at=None,
    )


def _source_record_text(
    *,
    source_key: str,
    source_search: DirectSourceSearchRecord,
    selected: _SelectedSourceRecord,
) -> str:
    normalized_record = _normalized_source_record(
        source_key=source_key,
        selected=selected,
    )
    if normalized_record:
        lines = [
            f"# {_source_family(source_key).replace('_', ' ').title()} Source Record",
            "",
            f"Source: {source_key}",
            f"Search ID: {source_search.id}",
            f"Query: {source_search.query}",
            f"Record index: {selected.index}",
        ]
        if selected.external_id is not None:
            lines.append(f"External ID: {selected.external_id}")
        lines.extend(["", "## Normalized Fields"])
        for key, value in normalized_record.items():
            if _is_empty_json_value(value):
                continue
            lines.append(f"- {key}: {_display_json_value(value)}")
        lines.extend(
            [
                "",
                "## Raw Record JSON",
                json.dumps(
                    selected.record,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                ),
            ],
        )
        return "\n".join(lines)
    return json.dumps(
        {
            "source_key": source_key,
            "query": source_search.query,
            "search_id": str(source_search.id),
            "record_index": selected.index,
            "record": selected.record,
        },
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def _source_record_title(
    *,
    source_key: str,
    source_search: DirectSourceSearchRecord,
    selected: _SelectedSourceRecord,
) -> str:
    for key in (
        "title",
        "name",
        "panel_name",
        "gene_symbol",
        "uniprot_id",
        "brief_title",
    ):
        value: JSONValue | None = selected.record.get(key)
        if isinstance(value, str) and value.strip():
            return f"{source_key}: {value.strip()}"
    if selected.external_id is not None:
        return f"{source_key}: {selected.external_id}"
    return f"{source_key}: {source_search.query}"


def _source_family(source_key: str) -> str:
    policy = source_record_policy(source_key)
    return policy.source_family if policy is not None else "document"


def _normalized_source_record(
    *,
    source_key: str,
    selected: _SelectedSourceRecord,
) -> JSONObject:
    policy = source_record_policy(source_key)
    if policy is not None:
        return policy.normalize_record(selected.record)
    return {}


def _display_json_value(value: JSONValue) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, int | float | bool) or value is None:
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _is_empty_json_value(value: JSONValue | None) -> bool:
    if value is None:
        return True
    if value == "":
        return True
    return value == []


def _completed_record(
    *,
    space_id: UUID,
    source_key: str,
    search_id: UUID,
    created_by: UUID | str,
    source_search: DirectSourceSearchRecord,
    selected: _SelectedSourceRecord,
    idempotency_key: str,
    request_hash: str,
    run_id: str,
    document: HarnessDocumentRecord,
    source_capture: SourceResultCapture,
    handoff_id: str | None = None,
) -> SourceSearchHandoffRecord:
    handoff_payload: JSONObject = {
        "selected_record_index": selected.index,
        "selected_record": selected.record,
        "selected_external_id": selected.external_id,
        "target_document_id": document.id,
        "target_run_id": run_id,
        "document_extraction_status": document.extraction_status,
    }
    return SourceSearchHandoffRecord(
        id=str(uuid4()) if handoff_id is None else handoff_id,
        space_id=str(space_id),
        source_key=source_key,
        search_id=str(search_id),
        status="completed",
        target_kind="source_document",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        created_by=str(created_by),
        record_selector_payload=_record_selector(selected),
        search_snapshot_payload=_search_snapshot(source_search),
        source_capture_snapshot=source_capture.to_metadata(),
        handoff_payload=handoff_payload,
        target_run_id=run_id,
        target_document_id=document.id,
        error_message=None,
        completed_at=datetime.now(UTC),
    )


def _failed_record(
    *,
    pending: SourceSearchHandoffRecord,
    run_id: str | None,
    error_message: str,
) -> SourceSearchHandoffRecord:
    handoff_payload: JSONObject = {
        **pending.handoff_payload,
        "document_extraction_status": "failed",
    }
    return SourceSearchHandoffRecord(
        id=pending.id,
        space_id=pending.space_id,
        source_key=pending.source_key,
        search_id=pending.search_id,
        status="failed",
        target_kind=pending.target_kind,
        idempotency_key=pending.idempotency_key,
        request_hash=pending.request_hash,
        created_by=pending.created_by,
        record_selector_payload=pending.record_selector_payload,
        search_snapshot_payload=pending.search_snapshot_payload,
        source_capture_snapshot=pending.source_capture_snapshot,
        handoff_payload=handoff_payload,
        target_run_id=run_id,
        target_document_id=pending.target_document_id,
        error_message=error_message,
        completed_at=datetime.now(UTC),
    )


def _response_from_record(
    record: SourceSearchHandoffRecord,
    *,
    replayed: bool,
) -> SourceSearchHandoffResponse:
    selector = record.record_selector_payload
    record_index = selector.get("record_index")
    if not isinstance(record_index, int):
        message = "Persisted source-search handoff is missing a valid record_index."
        raise TypeError(message)
    selected_external_id = selector.get("external_id")
    source_capture = (
        SourceResultCapture.model_validate(record.source_capture_snapshot)
        if record.source_capture_snapshot
        else None
    )
    return SourceSearchHandoffResponse(
        id=UUID(record.id),
        space_id=UUID(record.space_id),
        source_key=record.source_key,
        search_id=UUID(record.search_id),
        status=record.status,
        target_kind=record.target_kind,
        idempotency_key=record.idempotency_key,
        selected_record_index=record_index,
        selected_external_id=(
            selected_external_id if isinstance(selected_external_id, str) else None
        ),
        target_document_id=(
            UUID(record.target_document_id)
            if record.target_document_id is not None
            else None
        ),
        target_run_id=UUID(record.target_run_id) if record.target_run_id else None,
        source_capture=source_capture,
        handoff_payload=record.handoff_payload,
        replayed=replayed,
    )


__all__ = [
    "InMemorySourceSearchHandoffStore",
    "SourceSearchHandoffConflictError",
    "SourceSearchHandoffNotFoundError",
    "SourceSearchHandoffRequest",
    "SourceSearchHandoffResponse",
    "SourceSearchHandoffSelectionError",
    "SourceSearchHandoffService",
    "SourceSearchHandoffStore",
    "SourceSearchHandoffUnsupportedError",
    "SqlAlchemySourceSearchHandoffStore",
]
