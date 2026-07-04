"""Live-agent preflight contracts for relation feasibility audits."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class ModelHealthSnapshotLike(Protocol):
    """Runtime model-health fields needed by the live-agent audit."""

    status: str
    model_id: str | None
    capability: str | None
    timeout_seconds: float | None
    detail: str


@dataclass(frozen=True, slots=True)
class LiveAgentPreflightSnapshot:
    """Serializable snapshot of model readiness for live relation extraction."""

    status: str
    model_id: str | None
    capability: str | None
    timeout_seconds: float | None
    detail: str


class LiveAgentPreflightError(RuntimeError):
    """Raised when strict live-agent evaluation cannot run safely."""

    def __init__(self, snapshot: LiveAgentPreflightSnapshot) -> None:
        self.snapshot = snapshot
        super().__init__(_format_preflight_error(snapshot))


def ensure_live_agent_ready(
    *,
    health_probe: Callable[[], ModelHealthSnapshotLike] | None = None,
) -> LiveAgentPreflightSnapshot:
    """Fail unless the configured evidence-extraction model is reachable."""

    health = health_probe() if health_probe is not None else _run_default_health_probe()
    snapshot = LiveAgentPreflightSnapshot(
        status=health.status,
        model_id=health.model_id,
        capability=health.capability,
        timeout_seconds=health.timeout_seconds,
        detail=health.detail,
    )
    if snapshot.status != "healthy":
        raise LiveAgentPreflightError(snapshot)
    return snapshot


def _run_default_health_probe() -> ModelHealthSnapshotLike:
    from artana_evidence_api.runtime import get_artana_model_health

    return get_artana_model_health(refresh=True)


def _format_preflight_error(snapshot: LiveAgentPreflightSnapshot) -> str:
    model_fragment = (
        f" model={snapshot.model_id}." if snapshot.model_id is not None else ""
    )
    capability_fragment = (
        f" capability={snapshot.capability}."
        if snapshot.capability is not None
        else ""
    )
    return (
        "Live agent preflight failed: "
        f"status={snapshot.status}."
        f"{model_fragment}"
        f"{capability_fragment}"
        f" detail={snapshot.detail} "
        "Configure OPENAI_API_KEY or ARTANA_OPENAI_API_KEY and ensure the "
        "configured ARTANA_AI_EVIDENCE_EXTRACTION_MODEL is runnable before "
        "strict agent evaluation."
    )


__all__ = [
    "LiveAgentPreflightError",
    "LiveAgentPreflightSnapshot",
    "ensure_live_agent_ready",
]
