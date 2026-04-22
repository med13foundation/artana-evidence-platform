"""Runtime bootstrap exports used by application startup."""

from src.infrastructure.dependency_injection.container import container
from src.infrastructure.dependency_injection.dependencies import (
    initialize_legacy_session,
)

__all__ = ["container", "initialize_legacy_session"]
