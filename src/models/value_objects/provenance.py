"""
Compatibility wrapper for provenance value objects.

Canonical business definitions live in `src.domain.value_objects.provenance`.
This module remains to avoid breaking older imports under `src.models.*`.
"""

from src.domain.value_objects.provenance import DataSource, Provenance

__all__ = ["DataSource", "Provenance"]
