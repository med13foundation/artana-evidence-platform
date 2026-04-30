"""Constants shared by queued-run helper modules."""

from __future__ import annotations

import logging

LOGGER = logging.getLogger("artana_evidence_api.queued_run")
_WORKER_HEARTBEAT_PATH = "logs/artana-evidence-api-worker-heartbeat.json"
_WORKER_MAX_AGE_SECONDS = 120.0
_ACTIVE_RUN_STATUSES = frozenset({"queued", "running"})
_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "paused"})
_TEST_WORKER_ID = "queue-wait-test-worker"
_PRIMARY_RESULT_WORKSPACE_KEY = "primary_result_key"
_RESULT_KEYS_WORKSPACE_KEY = "result_keys"
_RESPOND_ASYNC_PREFER_TOKEN = "respond-async"

__all__ = [
    "LOGGER",
    "_ACTIVE_RUN_STATUSES",
    "_PRIMARY_RESULT_WORKSPACE_KEY",
    "_RESPOND_ASYNC_PREFER_TOKEN",
    "_RESULT_KEYS_WORKSPACE_KEY",
    "_TERMINAL_RUN_STATUSES",
    "_TEST_WORKER_ID",
    "_WORKER_HEARTBEAT_PATH",
    "_WORKER_MAX_AGE_SECONDS",
]
