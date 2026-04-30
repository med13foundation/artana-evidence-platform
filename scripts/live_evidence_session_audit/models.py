"""Configuration models for live evidence session audits."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class LogCommandConfig:
    command: str
    name: str


@dataclass(frozen=True, slots=True)
class LiveEvidenceSessionAuditConfig:
    base_url: str
    auth_headers: dict[str, str]
    output_dir: Path
    label: str | None
    space_ids: tuple[str, ...]
    objective: str
    seed_terms: tuple[str, ...]
    research_init_title: str
    research_init_max_depth: int
    research_init_max_hypotheses: int
    sources: dict[str, bool] | None
    bootstrap_objective: str
    bootstrap_title: str
    bootstrap_seed_entity_ids: tuple[str, ...]
    bootstrap_source_type: str
    bootstrap_max_depth: int
    bootstrap_max_hypotheses: int
    repeat_count: int
    promote_first_proposal: bool
    promotion_reason: str
    require_graph_activity: bool
    poll_timeout_seconds: float
    poll_interval_seconds: float
    graph_settle_seconds: float
    log_commands: tuple[LogCommandConfig, ...]
    log_error_patterns: tuple[str, ...]
    log_ignore_patterns: tuple[str, ...]
    fail_on_log_match: bool


__all__ = ["LiveEvidenceSessionAuditConfig", "LogCommandConfig"]
