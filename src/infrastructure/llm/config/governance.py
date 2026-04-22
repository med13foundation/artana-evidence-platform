"""
Governance configuration for AI agents.

Provides runtime governance settings including tool allowlists,
PII scrubbing, usage limits, and shadow evaluation.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class UsageLimits:
    """
    Usage limits for AI agent operations.

    Controls resource consumption to prevent runaway costs
    and ensure predictable execution.
    """

    total_cost_usd: float | None = None
    max_turns: int | None = None
    max_tokens: int | None = None

    @classmethod
    def default(cls) -> UsageLimits:
        """Create default usage limits."""
        return cls(
            total_cost_usd=1.0,
            max_turns=10,
            max_tokens=8192,
        )

    @classmethod
    def research(cls) -> UsageLimits:
        """Create higher limits for research/exploration tasks."""
        return cls(
            total_cost_usd=5.0,
            max_turns=25,
            max_tokens=16384,
        )

    @classmethod
    def from_environment(cls) -> UsageLimits:
        """Create usage limits from environment variables."""
        cost_raw = os.getenv("ARTANA_USAGE_COST_LIMIT")
        turns_raw = os.getenv("ARTANA_USAGE_MAX_TURNS")
        tokens_raw = os.getenv("ARTANA_USAGE_MAX_TOKENS")

        return cls(
            total_cost_usd=float(cost_raw) if cost_raw else 1.0,
            max_turns=int(turns_raw) if turns_raw else 10,
            max_tokens=int(tokens_raw) if tokens_raw else 8192,
        )


def _get_default_judge_model() -> str:
    """Get the default judge model from registry."""
    # Import here to avoid circular imports
    from src.domain.agents.models import ModelCapability
    from src.infrastructure.llm.config.model_registry import get_model_registry

    try:
        registry = get_model_registry()
        return registry.get_default_model(ModelCapability.JUDGE).model_id
    except (ValueError, KeyError):
        # Fallback if registry not available or no judge model configured
        return "openai:gpt-4o-mini"


@dataclass(frozen=True)
class ShadowEvalConfig:
    """
    Shadow evaluation (LLM-as-Judge) configuration.

    Runs quality checks on live traffic asynchronously
    for monitoring and improvement.
    """

    enabled: bool = False
    sink: str = "database"  # "database", "file", "both"
    sample_rate: float = 0.1  # 10% of requests
    judge_model: str = ""  # Empty string means use registry default

    def __post_init__(self) -> None:
        """Set default judge model from registry if not specified."""
        if not self.judge_model:
            # Use object.__setattr__ because dataclass is frozen
            object.__setattr__(self, "judge_model", _get_default_judge_model())

    @classmethod
    def from_environment(cls) -> ShadowEvalConfig:
        """Create shadow eval config from environment variables."""
        enabled = os.getenv("ARTANA_SHADOW_EVAL_ENABLED", "0") == "1"
        sink = os.getenv("ARTANA_SHADOW_EVAL_SINK", "database")
        sample_rate_raw = os.getenv("ARTANA_SHADOW_EVAL_SAMPLE_RATE", "0.1")
        judge_model = os.getenv("ARTANA_SHADOW_EVAL_JUDGE_MODEL", "")

        # If no env var, use registry default
        if not judge_model:
            judge_model = _get_default_judge_model()

        return cls(
            enabled=enabled,
            sink=sink,
            sample_rate=float(sample_rate_raw),
            judge_model=judge_model,
        )


@dataclass(frozen=True)
class GovernanceConfig:
    """
    Governance configuration for AI agent operations.

    Controls security and compliance settings for agent execution
    including tool gating, PII handling, cost limits, and quality monitoring.
    """

    tool_allowlist: frozenset[str] = field(default_factory=frozenset)
    pii_scrub_enabled: bool = False
    pii_strong_mode: bool = False
    total_cost_usd_limit: float | None = None
    confidence_threshold: float = 0.85
    hitl_threshold: float = 0.5
    require_evidence: bool = True
    usage_limits: UsageLimits = field(default_factory=UsageLimits.default)
    shadow_eval: ShadowEvalConfig = field(default_factory=ShadowEvalConfig)

    @classmethod
    def from_environment(cls) -> GovernanceConfig:
        """
        Create governance config from environment variables.

        Environment variables:
        - ARTANA_GOVERNANCE_TOOL_ALLOWLIST: Comma-separated tool IDs
        - ARTANA_GOVERNANCE_PII_SCRUB: Enable PII scrubbing (1/0)
        - ARTANA_GOVERNANCE_PII_STRONG: Enable strong PII mode (1/0)
        - ARTANA_GOVERNANCE_COST_LIMIT: Max cost in USD
        - ARTANA_GOVERNANCE_CONFIDENCE_THRESHOLD: Min confidence for auto-approval
        - ARTANA_GOVERNANCE_HITL_THRESHOLD: Min confidence before HITL escalation
        - ARTANA_GOVERNANCE_REQUIRE_EVIDENCE: Require evidence for auto-approval (1/0)
        """
        allowlist_raw = os.getenv("ARTANA_GOVERNANCE_TOOL_ALLOWLIST", "")
        allowlist = frozenset(
            tool.strip() for tool in allowlist_raw.split(",") if tool.strip()
        )

        pii_scrub = os.getenv("ARTANA_GOVERNANCE_PII_SCRUB", "0") == "1"
        pii_strong = os.getenv("ARTANA_GOVERNANCE_PII_STRONG", "0") == "1"

        cost_limit_raw = os.getenv("ARTANA_GOVERNANCE_COST_LIMIT")
        cost_limit = float(cost_limit_raw) if cost_limit_raw else None

        threshold_raw = os.getenv("ARTANA_GOVERNANCE_CONFIDENCE_THRESHOLD", "0.85")
        threshold = float(threshold_raw)

        hitl_raw = os.getenv("ARTANA_GOVERNANCE_HITL_THRESHOLD", "0.5")
        hitl_threshold = float(hitl_raw)

        require_evidence = os.getenv("ARTANA_GOVERNANCE_REQUIRE_EVIDENCE", "1") == "1"

        return cls(
            tool_allowlist=allowlist,
            pii_scrub_enabled=pii_scrub,
            pii_strong_mode=pii_strong,
            total_cost_usd_limit=cost_limit,
            confidence_threshold=threshold,
            hitl_threshold=hitl_threshold,
            require_evidence=require_evidence,
            usage_limits=UsageLimits.from_environment(),
            shadow_eval=ShadowEvalConfig.from_environment(),
        )

    def is_tool_allowed(self, tool_id: str) -> bool:
        """
        Check if a tool is allowed by the governance policy.

        If no allowlist is configured, all tools are allowed.
        """
        if not self.tool_allowlist:
            return True
        return tool_id in self.tool_allowlist

    def should_auto_approve(
        self,
        confidence: float,
        *,
        has_evidence: bool,
    ) -> bool:
        """
        Check if a decision should be auto-approved based on governance rules.

        Args:
            confidence: The confidence score (0.0-1.0)
            has_evidence: Whether the decision includes evidence

        Returns:
            True if the decision can be auto-approved
        """
        if confidence < self.confidence_threshold:
            return False
        return not (self.require_evidence and not has_evidence)

    def needs_human_review(self, confidence: float) -> bool:
        """
        Check if a decision needs human review based on HITL threshold.

        Args:
            confidence: The confidence score (0.0-1.0)

        Returns:
            True if the decision needs human review
        """
        return confidence < self.hitl_threshold
