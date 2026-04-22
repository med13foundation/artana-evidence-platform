"""
Statement status value object for Statements of Understanding.

Defines the maturity state for hypotheses before promotion to mechanisms.
"""

from enum import Enum


class StatementStatus(str, Enum):
    """Lifecycle status for a Statement of Understanding."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    WELL_SUPPORTED = "well_supported"


__all__ = ["StatementStatus"]
