"""Background loop for durable queued pipeline orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
from contextlib import suppress

from src.infrastructure.factories.pipeline_orchestration_factory import (
    pipeline_orchestration_service_context,
)

logger = logging.getLogger(__name__)

_ENV_PIPELINE_WORKER_MAX_CONCURRENCY = "ARTANA_PIPELINE_WORKER_MAX_CONCURRENCY"
_ENV_PIPELINE_WORKER_POLL_INTERVAL_SECONDS = (
    "ARTANA_PIPELINE_WORKER_POLL_INTERVAL_SECONDS"
)
_ENV_PIPELINE_WORKER_HEARTBEAT_INTERVAL_SECONDS = (
    "ARTANA_PIPELINE_WORKER_HEARTBEAT_INTERVAL_SECONDS"
)
_DEFAULT_STAGING_MAX_CONCURRENCY = 1
_DEFAULT_NON_STAGING_MAX_CONCURRENCY = 2
_DEFAULT_PIPELINE_WORKER_POLL_INTERVAL_SECONDS = 5
_DEFAULT_PIPELINE_WORKER_HEARTBEAT_INTERVAL_SECONDS = 15


def _read_positive_int_env(env_name: str, *, default_value: int) -> int:
    raw_value = os.getenv(env_name)
    if raw_value is None or not raw_value.strip():
        return default_value
    try:
        parsed = int(raw_value.strip())
    except ValueError:
        logger.warning(
            "Invalid integer override in %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    if parsed <= 0:
        logger.warning(
            "Non-positive integer override in %s=%r; using default %d",
            env_name,
            raw_value,
            default_value,
        )
        return default_value
    return parsed


def _default_worker_concurrency() -> int:
    environment = os.getenv("ARTANA_ENV", "development").strip().lower()
    if environment == "staging":
        return _DEFAULT_STAGING_MAX_CONCURRENCY
    return _DEFAULT_NON_STAGING_MAX_CONCURRENCY


async def _heartbeat_claimed_job(
    *,
    job_id: str,
    worker_id: str,
    heartbeat_interval_seconds: int,
) -> None:
    while True:
        try:
            await asyncio.sleep(heartbeat_interval_seconds)
            async with pipeline_orchestration_service_context() as service:
                from uuid import UUID

                service.heartbeat_claimed_run(
                    job_id=UUID(job_id),
                    worker_id=worker_id,
                )
        except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
            break
        except Exception:  # noqa: BLE001 - defensive heartbeat guard
            logger.warning(
                "Pipeline worker heartbeat failed for job_id=%s worker_id=%s",
                job_id,
                worker_id,
                exc_info=True,
            )


async def _run_pipeline_worker_slot(
    *,
    worker_id: str,
    poll_interval_seconds: int,
    heartbeat_interval_seconds: int,
) -> None:
    while True:
        heartbeat_task: asyncio.Task[None] | None = None
        claimed_job = None
        try:
            async with pipeline_orchestration_service_context() as service:
                claimed_job = service.claim_next_queued_run(worker_id=worker_id)
            if claimed_job is None:
                await asyncio.sleep(poll_interval_seconds)
                continue

            heartbeat_task = asyncio.create_task(
                _heartbeat_claimed_job(
                    job_id=str(claimed_job.id),
                    worker_id=worker_id,
                    heartbeat_interval_seconds=heartbeat_interval_seconds,
                ),
                name=f"pipeline-worker-heartbeat:{worker_id}",
            )
            async with pipeline_orchestration_service_context() as service:
                await service.execute_claimed_run(
                    claimed_job=claimed_job,
                    worker_id=worker_id,
                )
        except asyncio.CancelledError:  # pragma: no cover - cooperative shutdown
            break
        except Exception:  # pragma: no cover - defensive logging
            logger.exception(
                "Pipeline worker slot failed for worker_id=%s",
                worker_id,
            )
            await asyncio.sleep(poll_interval_seconds)
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task


async def run_pipeline_worker_loop() -> None:
    """Run durable pipeline-worker slots until the task is cancelled."""
    worker_concurrency = _read_positive_int_env(
        _ENV_PIPELINE_WORKER_MAX_CONCURRENCY,
        default_value=_default_worker_concurrency(),
    )
    poll_interval_seconds = _read_positive_int_env(
        _ENV_PIPELINE_WORKER_POLL_INTERVAL_SECONDS,
        default_value=_DEFAULT_PIPELINE_WORKER_POLL_INTERVAL_SECONDS,
    )
    heartbeat_interval_seconds = _read_positive_int_env(
        _ENV_PIPELINE_WORKER_HEARTBEAT_INTERVAL_SECONDS,
        default_value=_DEFAULT_PIPELINE_WORKER_HEARTBEAT_INTERVAL_SECONDS,
    )
    host_token = socket.gethostname() or "worker"
    tasks = [
        asyncio.create_task(
            _run_pipeline_worker_slot(
                worker_id=f"{host_token}:pipeline:{slot_index}",
                poll_interval_seconds=poll_interval_seconds,
                heartbeat_interval_seconds=heartbeat_interval_seconds,
            ),
            name=f"pipeline-worker-slot:{slot_index}",
        )
        for slot_index in range(worker_concurrency)
    ]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
