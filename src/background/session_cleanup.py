"""Background loop for session cleanup and maintenance."""

from __future__ import annotations

import asyncio
import logging
import os

from src.application.curation.repositories.audit_repository import (
    SqlAlchemyAuditRepository,
)
from src.application.services.audit_service import AuditTrailService
from src.database.session import SessionLocal, set_session_rls_context
from src.infrastructure.dependency_injection.container import container

logger = logging.getLogger(__name__)

_DEFAULT_AUDIT_RETENTION_DAYS = 365 * 6
_DEFAULT_AUDIT_RETENTION_BATCH_SIZE = 1000


def _read_positive_int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        logger.warning(
            "Invalid %s value %r; falling back to %d",
            name,
            raw_value,
            default,
        )
        return default
    if parsed < 1:
        logger.warning(
            "Invalid %s value %r; must be >=1. Falling back to %d",
            name,
            raw_value,
            default,
        )
        return default
    return parsed


AUDIT_LOG_RETENTION_ENABLED = (
    os.getenv("ARTANA_AUDIT_LOG_RETENTION_ENABLED", "1") == "1"
)
AUDIT_LOG_RETENTION_DAYS = _read_positive_int_env(
    "ARTANA_AUDIT_LOG_RETENTION_DAYS",
    _DEFAULT_AUDIT_RETENTION_DAYS,
)
AUDIT_LOG_RETENTION_BATCH_SIZE = _read_positive_int_env(
    "ARTANA_AUDIT_LOG_RETENTION_BATCH_SIZE",
    _DEFAULT_AUDIT_RETENTION_BATCH_SIZE,
)


async def run_session_cleanup_loop(interval_seconds: int) -> None:
    """
    Continuously clean up expired sessions at the provided interval.

    This background task:
    1. Revokes sessions that have expired (marks them as EXPIRED)
    2. Deletes old expired/revoked sessions (older than 30 days)

    Args:
        interval_seconds: How often to run cleanup (in seconds)
    """
    audit_service = AuditTrailService(SqlAlchemyAuditRepository())
    while True:
        try:
            auth_service = await container.get_authentication_service()

            # First, revoke sessions that have expired but are still marked ACTIVE
            revoked_count = await auth_service.revoke_expired_sessions()
            if revoked_count > 0:
                logger.info(
                    "Session cleanup: Revoked %d expired sessions",
                    revoked_count,
                )

            # Then, clean up old expired/revoked sessions (older than 30 days)
            cleaned_count = await auth_service.cleanup_expired_sessions()
            if cleaned_count > 0:
                logger.info(
                    "Session cleanup: Deleted %d old expired sessions",
                    cleaned_count,
                )
            if AUDIT_LOG_RETENTION_ENABLED:
                audit_session = SessionLocal()
                set_session_rls_context(audit_session, bypass_rls=True)
                try:
                    deleted_audit_rows = audit_service.cleanup_old_logs(
                        audit_session,
                        retention_days=AUDIT_LOG_RETENTION_DAYS,
                        batch_size=AUDIT_LOG_RETENTION_BATCH_SIZE,
                    )
                    if deleted_audit_rows > 0:
                        logger.info(
                            "Session cleanup: Deleted %d old audit log rows",
                            deleted_audit_rows,
                        )
                except Exception:  # pragma: no cover - defensive logging
                    logger.exception("Session cleanup: Audit retention cleanup failed")
                finally:
                    audit_session.close()
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            logger.info("Session cleanup loop cancelled")
            break
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Session cleanup loop failed")
        await asyncio.sleep(interval_seconds)
