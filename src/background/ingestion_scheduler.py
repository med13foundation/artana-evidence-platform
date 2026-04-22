"""Background loop for ingestion scheduling."""

from __future__ import annotations

import asyncio
import logging

from src.infrastructure.factories.ingestion_scheduler_factory import (
    ingestion_scheduling_service_context,
)

logger = logging.getLogger(__name__)


async def run_ingestion_scheduler_loop(interval_seconds: int) -> None:
    """Continuously execute due ingestion jobs at the provided interval."""
    while True:
        try:
            with ingestion_scheduling_service_context() as service:
                await service.run_due_jobs()
        except asyncio.CancelledError:  # pragma: no cover - cancellation path
            break
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Ingestion scheduler loop failed")
        await asyncio.sleep(interval_seconds)
