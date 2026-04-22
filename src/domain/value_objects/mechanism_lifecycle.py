from enum import Enum


class MechanismLifecycleState(str, Enum):
    """Lifecycle state for canonical mechanisms."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    CANONICAL = "canonical"
    DEPRECATED = "deprecated"


__all__ = ["MechanismLifecycleState"]
