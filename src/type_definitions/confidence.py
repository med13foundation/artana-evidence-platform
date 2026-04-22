"""
Confidence score typed contracts.
"""

from __future__ import annotations

from typing import TypedDict


class ConfidenceExtras(TypedDict, total=False):
    """Optional fields for confidence score calculations."""

    sample_size: int | None
    p_value: float | None
    study_count: int | None
    peer_reviewed: bool
    replicated: bool


class ConfidenceScoreOptions(TypedDict, total=False):
    """Optional parameters for constructing a confidence score."""

    sample_size: int | None
    p_value: float | None
    study_count: int | None
    peer_reviewed: bool
    replicated: bool


__all__ = ["ConfidenceExtras", "ConfidenceScoreOptions"]
