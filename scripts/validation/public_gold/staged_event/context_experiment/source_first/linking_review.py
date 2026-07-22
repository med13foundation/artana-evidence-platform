"""Typed source-only review contract for one staged linking graph."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from scripts.validation.public_gold.staged_event.contracts import StrictStageModel


class SourceOnlyLinkingReview(StrictStageModel):
    verdict: Literal["SUPPORTED", "CONTRADICTED", "INCOMPLETE", "ABSTAIN"]
    exact_evidence: str = Field(min_length=1, max_length=4000)
    explanation: str = Field(min_length=1, max_length=3000)


__all__ = ["SourceOnlyLinkingReview"]
