"""
Security audit trail helper.

Provides a thin service wrapper around the audit repository so high-risk routes can
emit append-only audit events without duplicating serialization code.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import TYPE_CHECKING, Literal

from src.models.database.audit import AuditLog

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from collections.abc import Mapping
    from uuid import UUID

    from sqlalchemy.orm import Session

    from src.application.curation.repositories.audit_repository import (
        AuditLogQuery,
        AuditRepository,
    )
    from src.type_definitions.common import AuditContext, JSONValue


class AuditTrailService:
    """Append-only audit logger for sensitive mutations."""

    def __init__(self, repository: AuditRepository) -> None:
        self._repository = repository

    @dataclass(slots=True)
    class QueryResult:
        """Paginated audit log results."""

        logs: list[AuditLog]
        total: int
        page: int
        per_page: int

    def record_action(  # noqa: PLR0913 - audit records require many fields
        self,
        db: Session,
        *,
        action: str,
        target: tuple[str, str],
        actor_id: UUID | str | None,
        details: Mapping[str, JSONValue] | None = None,
        context: AuditContext | None = None,
        success: bool | None = True,
    ) -> AuditLog:
        """
        Persist an audit record describing the action that was taken.

        Args:
            db: SQLAlchemy session to use for persistence
            action: Machine-readable action name (e.g. curation.submit)
            target: Tuple of (entity_type, entity_id) describing the affected record
            actor_id: User responsible for the change
            details: Optional structured metadata that will be JSON encoded
            context: Optional request metadata captured for audit logging
            success: Whether the action succeeded (None if unknown)
        """
        entity_type, entity_id = target
        normalized_actor = str(actor_id) if actor_id else None
        audit_details: dict[str, JSONValue] = {}
        if details:
            audit_details.update(details)

        resolved_context: AuditContext = context if context is not None else {}
        request_metadata: dict[str, JSONValue] = {}
        if "method" in resolved_context:
            request_metadata["method"] = resolved_context["method"]
        if "path" in resolved_context:
            request_metadata["path"] = resolved_context["path"]
        if "request_id" in resolved_context:
            request_metadata["request_id"] = resolved_context["request_id"]
        if request_metadata:
            audit_details["request"] = request_metadata

        serialized_details = (
            json.dumps(audit_details, separators=(",", ":"), sort_keys=True)
            if audit_details
            else None
        )
        log = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user=normalized_actor,
            request_id=resolved_context.get("request_id"),
            ip_address=resolved_context.get("ip_address"),
            user_agent=resolved_context.get("user_agent"),
            success=success,
            details=serialized_details,
        )
        return self._repository.record(db, log)

    def query_logs(
        self,
        db: Session,
        *,
        query: AuditLogQuery,
        page: int = 1,
        per_page: int = 50,
    ) -> QueryResult:
        """List audit logs with filtering and pagination."""
        effective_page = max(page, 1)
        effective_per_page = max(min(per_page, 500), 1)
        offset = (effective_page - 1) * effective_per_page
        logs = self._repository.list_logs(
            db,
            query=query,
            offset=offset,
            limit=effective_per_page,
        )
        total = self._repository.count_logs(db, query=query)
        return self.QueryResult(
            logs=logs,
            total=total,
            page=effective_page,
            per_page=effective_per_page,
        )

    def export_logs(
        self,
        db: Session,
        *,
        query: AuditLogQuery,
        export_format: Literal["json", "csv"] = "json",
        limit: int = 10_000,
    ) -> str:
        """Export filtered logs in JSON or CSV format."""
        logs = self._repository.list_logs(
            db,
            query=query,
            offset=0,
            limit=max(limit, 1),
        )
        serialized_logs = [self.serialize_log(log) for log in logs]
        if export_format == "json":
            return json.dumps(serialized_logs, separators=(",", ":"), default=str)
        return self._to_csv(serialized_logs)

    def cleanup_old_logs(
        self,
        db: Session,
        *,
        retention_days: int,
        batch_size: int = 1000,
    ) -> int:
        """Delete logs older than the configured retention period."""
        if retention_days < 1:
            message = "retention_days must be at least 1"
            raise ValueError(message)
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)
        effective_batch_size = max(batch_size, 1)
        deleted_total = 0
        while True:
            deleted = self._repository.delete_older_than(
                db,
                cutoff=cutoff,
                limit=effective_batch_size,
            )
            deleted_total += deleted
            if deleted < effective_batch_size:
                break
        return deleted_total

    @staticmethod
    def serialize_log(log: AuditLog) -> dict[str, JSONValue]:
        """Convert an audit log row into an API-safe object."""
        parsed_details: JSONValue | None = None
        if log.details:
            try:
                parsed = json.loads(log.details)
                if isinstance(parsed, dict | list):
                    parsed_details = parsed
                else:
                    parsed_details = log.details
            except json.JSONDecodeError:
                parsed_details = log.details
        return {
            "id": log.id,
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "user": log.user,
            "request_id": log.request_id,
            "ip_address": log.ip_address,
            "user_agent": log.user_agent,
            "success": log.success,
            "details": parsed_details,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }

    @staticmethod
    def _to_csv(logs: list[dict[str, JSONValue]]) -> str:
        output = StringIO()
        field_names = [
            "id",
            "created_at",
            "action",
            "entity_type",
            "entity_id",
            "user",
            "request_id",
            "ip_address",
            "user_agent",
            "success",
            "details",
        ]
        writer = csv.DictWriter(output, fieldnames=field_names)
        writer.writeheader()
        for log in logs:
            row = dict(log)
            details_value = row.get("details")
            if isinstance(details_value, dict | list):
                row["details"] = json.dumps(
                    details_value,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            writer.writerow(row)
        return output.getvalue()


__all__ = ["AuditTrailService"]
