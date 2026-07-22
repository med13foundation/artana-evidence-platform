"""Durable exactly-once attempt reservation and acknowledgement state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.validation.public_gold.staged_event.context_experiment.source_first.custody import (
    CustodyPersistenceError,
    write_json_atomic,
    write_json_exclusive,
)


class AttemptStateError(RuntimeError):
    """A provider creation attempt cannot be safely started or acknowledged."""


def reserve_attempt(
    path: Path,
    *,
    stage: str,
    provider_input: str,
    preregistration_sha256: str,
) -> None:
    try:
        write_json_exclusive(
            path,
            {
                "state": "CREATION_RESERVED",
                "stage": stage,
                "provider_input_sha256": hashlib.sha256(
                    provider_input.encode()
                ).hexdigest(),
                "preregistration_sha256": preregistration_sha256,
                "provider_creation_limit": 1,
                "provider_retries": 0,
            },
        )
    except CustodyPersistenceError as exc:
        raise AttemptStateError(
            f"{stage} creation is already reserved and cannot be repeated"
        ) from exc


def acknowledge_attempt(path: Path, *, response_id: str) -> None:
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or loaded.get("state") != "CREATION_RESERVED":
        raise AttemptStateError("provider attempt reservation is invalid")
    write_json_atomic(
        path,
        {**loaded, "state": "ACKNOWLEDGED", "response_id": response_id},
    )


__all__ = ["AttemptStateError", "acknowledge_attempt", "reserve_attempt"]
