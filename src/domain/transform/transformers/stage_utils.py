"""
Utility helpers for adapting stage artefacts into reporting structures.
"""

from __future__ import annotations

from collections.abc import Iterable

from .stage_models import StageData, ValidationSummary


def stage_to_dict(stage_result: object) -> StageData:
    """Convert a stage output into a serializable dictionary."""
    if hasattr(stage_result, "as_dict"):
        dictionary = stage_result.as_dict()
        if isinstance(dictionary, dict):
            return dict(dictionary)
    if isinstance(stage_result, dict):
        return dict(stage_result)
    if hasattr(stage_result, "__dict__"):
        return dict(stage_result.__dict__)
    return {}


def stage_errors(stage_result: object) -> list[str]:
    """Extract error messages from a stage output."""
    if hasattr(stage_result, "errors"):
        errors = stage_result.errors
        if isinstance(errors, list):
            return errors
    if isinstance(stage_result, dict):
        errors = stage_result.get("errors", [])
        if isinstance(errors, list):
            return errors
    return []


def _count_list_values(values: Iterable[object]) -> int:
    return sum(len(value) for value in values if isinstance(value, list))


def safe_total_records(stage: object) -> int:
    """Safely count records contained within a stage artefact."""
    if hasattr(stage, "total_records"):
        try:
            return int(stage.total_records())
        except Exception:  # pragma: no cover - defensive
            return 0
    if isinstance(stage, dict):
        return _count_list_values(stage.values())
    return 0


def safe_relationship_count(stage: object) -> int:
    """Safely count relationships contained within a stage artefact."""
    if hasattr(stage, "relationship_count"):
        try:
            return int(stage.relationship_count())
        except Exception:  # pragma: no cover - defensive
            return 0
    if isinstance(stage, dict):
        return _count_list_values(stage.values())
    return 0


def safe_validation_failures(validation: object | None) -> int:
    """Safely retrieve the total validation failures."""
    if validation is None:
        return 0
    if isinstance(validation, ValidationSummary):
        return validation.failed
    if hasattr(validation, "failed"):
        try:
            return int(validation.failed)
        except Exception:  # pragma: no cover - defensive
            return 0
    if isinstance(validation, dict):
        failed = validation.get("failed", 0)
        try:
            return int(failed)
        except (TypeError, ValueError):
            return 0
    return 0


__all__ = [
    "safe_relationship_count",
    "safe_total_records",
    "safe_validation_failures",
    "stage_errors",
    "stage_to_dict",
]
