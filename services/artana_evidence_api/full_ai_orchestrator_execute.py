"""Compatibility facade for the full-AI orchestrator execute entrypoint."""

from __future__ import annotations

from artana_evidence_api.full_ai_orchestrator.execute import (
    _ResearchInitExecutor,
    execute_full_ai_orchestrator_run,
    execute_research_init_run,
)

__all__ = [
    "_ResearchInitExecutor",
    "execute_full_ai_orchestrator_run",
    "execute_research_init_run",
]
