"""
Repository-specific typed contracts.
"""

from __future__ import annotations

from typing import TypedDict


class GeneStatistics(TypedDict):
    total_genes: int
    genes_with_variants: int
    genes_with_phenotypes: int


class SourceTemplateStatistics(TypedDict):
    total_templates: int
    public_templates: int
    approved_templates: int
    total_usage: int
    average_success_rate: float


class UserDataSourceStatistics(TypedDict):
    total_sources: int
    status_counts: dict[str, int]
    type_counts: dict[str, int]
    average_quality_score: float | None
    sources_with_quality_metrics: int


__all__ = [
    "GeneStatistics",
    "SourceTemplateStatistics",
    "UserDataSourceStatistics",
]
