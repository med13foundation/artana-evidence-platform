"""Errors raised by deterministic kernel-entity resolution paths."""

from __future__ import annotations


class KernelEntityError(Exception):
    """Base error for kernel entity operations."""


class KernelEntityConflictError(KernelEntityError):
    """Raised when deterministic entity matching finds conflicting rows."""


class KernelEntityValidationError(KernelEntityError, ValueError):
    """Raised when an entity request violates deterministic validation rules."""


__all__ = [
    "KernelEntityConflictError",
    "KernelEntityError",
    "KernelEntityValidationError",
]
