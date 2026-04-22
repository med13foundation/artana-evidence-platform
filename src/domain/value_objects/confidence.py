from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from typing import TYPE_CHECKING, Unpack

if TYPE_CHECKING:
    from src.type_definitions.confidence import ConfidenceExtras


class EvidenceLevel(str, Enum):
    """Evidence confidence level enumeration."""

    DEFINITIVE = "definitive"
    STRONG = "strong"
    MODERATE = "moderate"
    SUPPORTING = "supporting"
    WEAK = "weak"
    DISPROVEN = "disproven"


@dataclass(frozen=True)
class Confidence:
    score: float
    level: EvidenceLevel
    sample_size: int | None = None
    p_value: float | None = None
    study_count: int | None = None
    peer_reviewed: bool = False
    replicated: bool = False

    def __post_init__(self) -> None:
        if not (0.0 <= self.score <= 1.0):
            message = "score must be between 0.0 and 1.0"
            raise ValueError(message)
        if self.sample_size is not None and self.sample_size < 1:
            message = "sample_size must be positive"
            raise ValueError(message)
        if self.p_value is not None and not (0.0 <= self.p_value <= 1.0):
            message = "p_value must be between 0.0 and 1.0"
            raise ValueError(message)
        if self.study_count is not None and self.study_count < 0:
            message = "study_count cannot be negative"
            raise ValueError(message)

    @classmethod
    def from_score(cls, score: float, **kwargs: Unpack[ConfidenceExtras]) -> Confidence:
        level = cls._infer_level(score)
        return cls(score=score, level=level, **kwargs)

    @staticmethod
    def _infer_level(score: float) -> EvidenceLevel:
        definitive_threshold = 0.9
        strong_threshold = 0.8
        moderate_threshold = 0.6
        supporting_threshold = 0.4
        weak_threshold = 0.2
        if score >= definitive_threshold:
            return EvidenceLevel.DEFINITIVE
        if score >= strong_threshold:
            return EvidenceLevel.STRONG
        if score >= moderate_threshold:
            return EvidenceLevel.MODERATE
        if score >= supporting_threshold:
            return EvidenceLevel.SUPPORTING
        if score >= weak_threshold:
            return EvidenceLevel.WEAK
        return EvidenceLevel.DISPROVEN

    def update_level(self, level: EvidenceLevel) -> Confidence:
        return replace(self, level=level)

    def is_significant(self) -> bool:
        significant_threshold = 0.6
        return self.score >= significant_threshold and self.level in {
            EvidenceLevel.DEFINITIVE,
            EvidenceLevel.STRONG,
            EvidenceLevel.MODERATE,
        }

    def requires_validation(self) -> bool:
        min_confidence = 0.7
        return self.score < min_confidence or not self.peer_reviewed

    @property
    def quality_description(self) -> str:
        strong_threshold = 0.8
        moderate_threshold = 0.6
        supporting_threshold = 0.4
        if self.score >= strong_threshold:
            return f"Strong evidence ({self.score:.2f})"
        if self.score >= moderate_threshold:
            return f"Moderate evidence ({self.score:.2f})"
        if self.score >= supporting_threshold:
            return f"Supporting evidence ({self.score:.2f})"
        return f"Weak evidence ({self.score:.2f})"

    def __str__(self) -> str:
        return f"{self.level.value} ({self.score:.2f})"


__all__ = ["Confidence", "EvidenceLevel"]
