"""Structured outcome metadata for research-init brief generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from artana_evidence_api.types.common import JSONObject

ResearchInitBriefOutcomeStatus = Literal["completed", "skipped"]
ResearchInitBriefSkipReason = Literal[
    "generation_failed",
    "render_failed",
    "storage_failed",
]
ResearchInitBriefLlmStatus = Literal[
    "not_attempted",
    "completed",
    "fallback_deterministic",
    "failed",
]


@dataclass(frozen=True, slots=True)
class ResearchInitBriefOutcome:
    """Structured result for the final research brief step."""

    status: ResearchInitBriefOutcomeStatus
    reason: ResearchInitBriefSkipReason | None
    error: str | None
    llm_status: ResearchInitBriefLlmStatus
    markdown: str | None = None
    llm_error: str | None = None

    @classmethod
    def completed(
        cls,
        *,
        markdown: str,
        llm_status: ResearchInitBriefLlmStatus,
        llm_error: str | None = None,
    ) -> ResearchInitBriefOutcome:
        return cls(
            status="completed",
            reason=None,
            error=None,
            llm_status=llm_status,
            markdown=markdown,
            llm_error=llm_error,
        )

    @classmethod
    def skipped(
        cls,
        *,
        reason: ResearchInitBriefSkipReason,
        error: str,
        llm_status: ResearchInitBriefLlmStatus,
        markdown: str | None = None,
        llm_error: str | None = None,
    ) -> ResearchInitBriefOutcome:
        return cls(
            status="skipped",
            reason=reason,
            error=error,
            llm_status=llm_status,
            markdown=markdown,
            llm_error=llm_error,
        )

    def to_metadata(self) -> JSONObject:
        markdown_present = (
            isinstance(self.markdown, str) and self.markdown.strip() != ""
        )
        return {
            "status": self.status,
            "reason": self.reason,
            "error": self.error,
            "llm_status": self.llm_status,
            "llm_error": self.llm_error,
            "brief_markdown_present": markdown_present,
            "markdown_length": len(self.markdown) if self.markdown is not None else 0,
        }

    def to_error_message(self) -> str | None:
        if self.status != "skipped":
            return None
        if self.error is None or self.error.strip() == "":
            return f"Research brief generation skipped: {self.reason}"
        return f"Research brief generation skipped: {self.reason}: {self.error}"


__all__ = [
    "ResearchInitBriefLlmStatus",
    "ResearchInitBriefOutcome",
    "ResearchInitBriefOutcomeStatus",
    "ResearchInitBriefSkipReason",
]
