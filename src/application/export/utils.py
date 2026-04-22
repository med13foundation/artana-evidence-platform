"""
Shared helpers for bulk export service logic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.type_definitions.common import QueryFilters, clone_query_filters

if TYPE_CHECKING:
    from collections.abc import Callable

    from .export_types import EntityItem

__all__ = [
    "collect_paginated",
    "copy_filters",
    "get_entity_fields",
    "get_evidence_fields",
    "get_gene_fields",
    "get_observation_fields",
    "get_phenotype_fields",
    "get_relation_fields",
    "get_variants_fields",
]

_ENTITY_FIELDS = [
    "id",
    "research_space_id",
    "entity_type",
    "display_label",
    "metadata_payload",
    "created_at",
    "updated_at",
]

_OBSERVATION_FIELDS = [
    "id",
    "research_space_id",
    "subject_id",
    "variable_id",
    "value_numeric",
    "value_text",
    "value_date",
    "value_coded",
    "value_boolean",
    "value_json",
    "unit",
    "observed_at",
    "provenance_id",
    "confidence",
    "created_at",
]

_RELATION_FIELDS = [
    "id",
    "research_space_id",
    "source_id",
    "relation_type",
    "target_id",
    "aggregate_confidence",
    "source_count",
    "highest_evidence_tier",
    "curation_status",
    "provenance_id",
    "reviewed_by",
    "reviewed_at",
    "created_at",
    "updated_at",
]

_GENE_FIELDS = [
    "id",
    "gene_id",
    "symbol",
    "name",
    "description",
    "gene_type",
    "chromosome",
    "start_position",
    "end_position",
    "ensembl_id",
    "ncbi_gene_id",
    "uniprot_id",
    "created_at",
    "updated_at",
]

_VARIANT_FIELDS = [
    "id",
    "variant_id",
    "clinvar_id",
    "chromosome",
    "position",
    "reference_allele",
    "alternate_allele",
    "variant_type",
    "clinical_significance",
    "gene_symbol",
    "hgvs_genomic",
    "hgvs_cdna",
    "hgvs_protein",
    "condition",
    "review_status",
    "allele_frequency",
    "gnomad_af",
    "created_at",
    "updated_at",
]

_PHENOTYPE_FIELDS = [
    "id",
    "identifier.hpo_id",
    "identifier.hpo_term",
    "name",
    "definition",
    "category",
    "parent_hpo_id",
    "is_root_term",
    "frequency_in_med13",
    "severity_score",
    "created_at",
    "updated_at",
]

_EVIDENCE_FIELDS = [
    "id",
    "variant_id",
    "phenotype_id",
    "description",
    "summary",
    "evidence_level",
    "evidence_type",
    "confidence.score",
    "quality_score",
    "sample_size",
    "study_type",
    "statistical_significance",
    "reviewed",
    "review_date",
    "reviewer_notes",
    "created_at",
    "updated_at",
]


def collect_paginated(
    fetch_page: Callable[[int, int], tuple[list[EntityItem], int]],
    chunk_size: int,
) -> list[EntityItem]:
    """Gather all items from a paginated service call."""
    page = 1
    results: list[EntityItem] = []
    batch_size = max(chunk_size, 1)

    while True:
        items, _total = fetch_page(page, batch_size)
        if not items:
            break
        results.extend(items)
        if len(items) < batch_size:
            break
        page += 1

    return results


def copy_filters(filters: QueryFilters | None) -> QueryFilters:
    """Clone query filters to avoid mutating caller state."""
    return clone_query_filters(filters) or {}


def get_entity_fields() -> list[str]:
    return list(_ENTITY_FIELDS)


def get_gene_fields() -> list[str]:
    return list(_GENE_FIELDS)


def get_variants_fields() -> list[str]:
    return list(_VARIANT_FIELDS)


def get_phenotype_fields() -> list[str]:
    return list(_PHENOTYPE_FIELDS)


def get_evidence_fields() -> list[str]:
    return list(_EVIDENCE_FIELDS)


def get_observation_fields() -> list[str]:
    return list(_OBSERVATION_FIELDS)


def get_relation_fields() -> list[str]:
    return list(_RELATION_FIELDS)
