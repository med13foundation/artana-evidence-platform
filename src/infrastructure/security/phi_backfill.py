"""Batch backfill utility for PHI identifier encryption columns."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, TypeGuard

from src.database.session import set_session_rls_context
from src.infrastructure.queries.graph_security_queries import (
    load_phi_identifier_backfill_batch,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.orm import Session

    from src.infrastructure.security.phi_encryption import PHIEncryptionService

logger = logging.getLogger(__name__)


class _MutablePHIIdentifierRow(Protocol):
    id: int
    identifier_value: str
    identifier_blind_index: str | None
    encryption_key_version: str | None
    blind_index_version: str | None


def _is_mutable_phi_identifier_row(row: object) -> TypeGuard[_MutablePHIIdentifierRow]:
    return (
        isinstance(getattr(row, "id", None), int)
        and isinstance(getattr(row, "identifier_value", None), str)
        and (
            getattr(row, "identifier_blind_index", None) is None
            or isinstance(getattr(row, "identifier_blind_index", None), str)
        )
        and (
            getattr(row, "encryption_key_version", None) is None
            or isinstance(getattr(row, "encryption_key_version", None), str)
        )
        and (
            getattr(row, "blind_index_version", None) is None
            or isinstance(getattr(row, "blind_index_version", None), str)
        )
    )


@dataclass(frozen=True, slots=True)
class PHIBackfillSummary:
    """Summary returned from one PHI identifier backfill run."""

    dry_run: bool
    batches_processed: int
    scanned_rows: int
    updated_rows: int
    skipped_rows: int
    failed_rows: int


@dataclass(frozen=True, slots=True)
class _BatchResult:
    scanned_rows: int
    updated_rows: int
    skipped_rows: int
    failed_rows: int
    last_seen_id: int


class PHIIdentifierBackfillRunner:
    """Encrypt legacy plaintext PHI identifiers in manageable batches."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        encryption_service: PHIEncryptionService,
    ) -> None:
        self._session_factory = session_factory
        self._encryption_service = encryption_service

    def run(
        self,
        *,
        batch_size: int = 1000,
        max_rows: int | None = None,
        dry_run: bool = True,
    ) -> PHIBackfillSummary:
        """Run PHI backfill and return an aggregate summary."""
        if batch_size < 1:
            message = "batch_size must be >= 1"
            raise ValueError(message)
        if max_rows is not None and max_rows < 1:
            message = "max_rows must be >= 1 when provided"
            raise ValueError(message)

        last_seen_id = 0
        batches_processed = 0
        scanned_rows = 0
        updated_rows = 0
        skipped_rows = 0
        failed_rows = 0

        while True:
            effective_limit = self._resolve_effective_limit(
                batch_size=batch_size,
                max_rows=max_rows,
                scanned_rows=scanned_rows,
            )
            if effective_limit is None:
                break
            batch_result = self._process_batch(
                last_seen_id=last_seen_id,
                limit=effective_limit,
                dry_run=dry_run,
            )
            if batch_result is None:
                break

            batches_processed += 1
            scanned_rows += batch_result.scanned_rows
            updated_rows += batch_result.updated_rows
            skipped_rows += batch_result.skipped_rows
            failed_rows += batch_result.failed_rows
            last_seen_id = batch_result.last_seen_id

        return PHIBackfillSummary(
            dry_run=dry_run,
            batches_processed=batches_processed,
            scanned_rows=scanned_rows,
            updated_rows=updated_rows,
            skipped_rows=skipped_rows,
            failed_rows=failed_rows,
        )

    @staticmethod
    def _resolve_effective_limit(
        *,
        batch_size: int,
        max_rows: int | None,
        scanned_rows: int,
    ) -> int | None:
        remaining_rows = None if max_rows is None else max_rows - scanned_rows
        if remaining_rows is not None and remaining_rows <= 0:
            return None
        return (
            min(batch_size, remaining_rows)
            if remaining_rows is not None
            else batch_size
        )

    def _process_batch(
        self,
        *,
        last_seen_id: int,
        limit: int,
        dry_run: bool,
    ) -> _BatchResult | None:
        session = self._session_factory()
        set_session_rls_context(session, bypass_rls=True)
        try:
            batch = self._load_batch(
                session,
                last_seen_id=last_seen_id,
                limit=limit,
            )
            if not batch:
                if dry_run:
                    session.rollback()
                return None

            scanned_rows = 0
            updated_rows = 0
            skipped_rows = 0
            failed_rows = 0
            current_last_seen_id = last_seen_id

            for row in batch:
                scanned_rows += 1
                current_last_seen_id = row.id
                result = self._process_row(row)
                if result == "updated":
                    updated_rows += 1
                elif result == "skipped":
                    skipped_rows += 1
                else:
                    failed_rows += 1

            if dry_run:
                session.rollback()
            else:
                session.commit()

            return _BatchResult(
                scanned_rows=scanned_rows,
                updated_rows=updated_rows,
                skipped_rows=skipped_rows,
                failed_rows=failed_rows,
                last_seen_id=current_last_seen_id,
            )
        finally:
            session.close()

    def _load_batch(
        self,
        session: Session,
        *,
        last_seen_id: int,
        limit: int,
    ) -> list[_MutablePHIIdentifierRow]:
        return [
            row
            for row in load_phi_identifier_backfill_batch(
                session,
                last_seen_id=last_seen_id,
                limit=limit,
            )
            if _is_mutable_phi_identifier_row(row)
        ]

    def _process_row(
        self,
        row: _MutablePHIIdentifierRow,
    ) -> Literal["updated", "skipped", "failed"]:
        original_value = row.identifier_value
        is_encrypted = self._encryption_service.is_encrypted_identifier(original_value)
        needs_encrypt = not is_encrypted
        needs_blind_index = row.identifier_blind_index is None
        needs_versions = (
            row.encryption_key_version is None or row.blind_index_version is None
        )

        if not (needs_encrypt or needs_blind_index or needs_versions):
            return "skipped"

        plaintext_value = original_value
        if is_encrypted:
            try:
                plaintext_value = self._encryption_service.decrypt(original_value)
            except ValueError:
                logger.warning(
                    "Skipping PHI row %s because encrypted payload could not be decrypted",
                    row.id,
                )
                return "failed"

        row.identifier_blind_index = self._encryption_service.blind_index(
            plaintext_value,
        )
        row.encryption_key_version = self._encryption_service.key_version
        row.blind_index_version = self._encryption_service.blind_index_version
        if needs_encrypt:
            row.identifier_value = self._encryption_service.encrypt(plaintext_value)

        return "updated"


__all__ = ["PHIBackfillSummary", "PHIIdentifierBackfillRunner"]
