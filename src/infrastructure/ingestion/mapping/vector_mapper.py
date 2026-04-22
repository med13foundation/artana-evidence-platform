"""
Vector similarity mapper for the ingestion pipeline.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from artana_evidence_db.runtime import (
    create_graph_domain_context_policy,
    resolve_graph_domain_context,
)

from src.infrastructure.ingestion.types import MappedObservation, RawRecord

if TYPE_CHECKING:
    from artana_evidence_db.kernel_domain_models import DictionarySearchResult
    from artana_evidence_db.semantic_ports import DictionaryPort

    from src.domain.services.ingestion import IngestionProgressCallback
    from src.type_definitions.common import JSONObject


def _read_similarity_threshold() -> float:
    raw_value = (
        os.getenv("ARTANA_VECTOR_MAPPER_SIMILARITY_THRESHOLD")
        or os.getenv("VECTOR_MAPPER_SIMILARITY_THRESHOLD")
        or "0.7"
    )
    try:
        parsed = float(raw_value)
    except ValueError:
        return 0.7
    return min(1.0, max(0.0, parsed))


def _read_top_k() -> int:
    raw_value = (
        os.getenv("ARTANA_VECTOR_MAPPER_TOP_K")
        or os.getenv("VECTOR_MAPPER_TOP_K")
        or "5"
    )
    try:
        parsed = int(raw_value)
    except ValueError:
        return 5
    return max(1, parsed)


VECTOR_MAPPER_SIMILARITY_THRESHOLD = _read_similarity_threshold()
VECTOR_MAPPER_TOP_K = _read_top_k()
_COMMON_IGNORED_FIELDS = frozenset(
    {
        "created_at",
        "date",
        "fetched_at",
        "id",
        "identifier",
        "original_source_id",
        "source",
        "source_id",
        "source_record_id",
        "timestamp",
        "type",
        "updated_at",
    },
)
_PUBMED_PUBLICATION_IGNORED_FIELDS = frozenset(
    {
        "abstract",
        "authors",
        "country",
        "doi",
        "fetched_at",
        "issue",
        "journal",
        "keywords",
        "language",
        "medline_date",
        "mesh_terms",
        "pages",
        "pmc_id",
        "pmcid",
        "pmid",
        "publication_date",
        "publication_types",
        "pubmed_id",
        "pubmed_ids",
        "source",
        "title",
        "volume",
    },
)


class VectorMapper:
    """
    Maps raw records to observations using vector dictionary search fallback.
    """

    def __init__(
        self,
        dictionary_repository: DictionaryPort,
        *,
        similarity_threshold: float = VECTOR_MAPPER_SIMILARITY_THRESHOLD,
        top_k: int = VECTOR_MAPPER_TOP_K,
    ) -> None:
        self.dictionary_repo = dictionary_repository
        self.similarity_threshold = min(1.0, max(0.0, similarity_threshold))
        self.top_k = max(1, top_k)
        self._search_cache: dict[
            tuple[str | None, str],
            list[DictionarySearchResult],
        ] = {}
        self._last_run_metrics: JSONObject | None = None

    def map(self, record: RawRecord) -> list[MappedObservation]:
        return self.map_with_progress(record)

    def map_with_progress(
        self,
        record: RawRecord,
        *,
        progress_callback: IngestionProgressCallback | None = None,
    ) -> list[MappedObservation]:
        _ = progress_callback
        observations: list[MappedObservation] = []
        subject_anchor = self._extract_subject_anchor(record)
        observed_at = self._extract_timestamp(record)
        domain_context = self._extract_domain_context(record)
        metrics: dict[str, int] = {
            "searched_field_count": 0,
            "skipped_field_count": 0,
            "cache_hit_count": 0,
            "cache_miss_count": 0,
        }

        for key, value in record.data.items():
            if self._should_skip_field(record, key, value):
                metrics["skipped_field_count"] += 1
                continue

            metrics["searched_field_count"] += 1
            search_results, from_cache = self._search_variables(
                key,
                domain_context=domain_context,
            )
            if from_cache:
                metrics["cache_hit_count"] += 1
            else:
                metrics["cache_miss_count"] += 1
            vector_matches = self._select_vector_matches(search_results)
            if not vector_matches:
                continue

            best_match = max(
                vector_matches,
                key=lambda result: result.similarity_score,
            )
            observations.append(
                MappedObservation(
                    subject_anchor=subject_anchor,
                    variable_id=best_match.entry_id,
                    value=value,
                    unit=None,
                    observed_at=observed_at,
                    provenance={
                        "source_id": record.source_id,
                        "original_key": key,
                        "method": "vector_match",
                        "similarity_score": best_match.similarity_score,
                        "matched_dimension": best_match.dimension,
                        "matched_display_name": best_match.display_name,
                        "match_method": best_match.match_method,
                        "match_metadata": best_match.metadata,
                        "domain_context": best_match.domain_context,
                        "metadata": record.metadata,
                    },
                ),
            )

        self._last_run_metrics = self._build_run_metrics(
            record=record,
            metrics=metrics,
            matched_observations_count=len(observations),
        )
        return observations

    def consume_run_metrics(self) -> JSONObject | None:
        metrics = self._last_run_metrics
        self._last_run_metrics = None
        return metrics

    def _select_vector_matches(
        self,
        search_results: list[DictionarySearchResult],
    ) -> list[DictionarySearchResult]:
        return [
            result
            for result in search_results
            if result.dimension == "variables"
            and result.match_method == "vector"
            and result.similarity_score >= self.similarity_threshold
        ]

    def _search_variables(
        self,
        key: str,
        *,
        domain_context: str | None,
    ) -> tuple[list[DictionarySearchResult], bool]:
        cache_key = (domain_context, self._normalize_field_name(key))
        cached_results = self._search_cache.get(cache_key)
        if cached_results is not None:
            return list(cached_results), True

        search_results = self.dictionary_repo.dictionary_search(
            terms=[key],
            dimensions=["variables"],
            domain_context=domain_context,
            limit=self.top_k,
        )
        cached_copy = list(search_results)
        self._search_cache[cache_key] = cached_copy
        return list(cached_copy), False

    def _should_skip_field(
        self,
        record: RawRecord,
        key: str,
        value: object,
    ) -> bool:
        if value is None or value == "":
            return True
        if isinstance(value, dict | list | tuple | set):
            return True

        normalized_key = self._normalize_field_name(key)
        if normalized_key in _COMMON_IGNORED_FIELDS:
            return True

        record_type = record.metadata.get("type")
        entity_type = record.metadata.get("entity_type")
        return (
            record_type == "pubmed"
            and entity_type == "PUBLICATION"
            and normalized_key in _PUBMED_PUBLICATION_IGNORED_FIELDS
        )

    @staticmethod
    def _normalize_field_name(key: str) -> str:
        return key.strip().casefold().replace("-", "_").replace(" ", "_")

    def _extract_domain_context(self, record: RawRecord) -> str | None:
        raw_source_type = record.metadata.get("type")
        source_type = raw_source_type if isinstance(raw_source_type, str) else None
        return resolve_graph_domain_context(
            domain_context_policy=create_graph_domain_context_policy(),
            metadata=record.metadata,
            source_type=source_type,
            fallback=None,
        )

    def _extract_subject_anchor(self, record: RawRecord) -> JSONObject:
        anchors: JSONObject = {}

        record_type = record.metadata.get("type")
        entity_type = record.metadata.get("entity_type")
        if (
            isinstance(record_type, str)
            and record_type == "pubmed"
            and entity_type == "PUBLICATION"
        ):
            for key in ["pmid", "doi", "title"]:
                if key in record.data and record.data[key] is not None:
                    anchors[key] = record.data[key]
            return anchors

        for key in [
            "mrn",
            "issuer",
            "patient_id",
            "email",
            "hgnc_id",
            "gene_symbol",
            "clinvar_id",
            "variant_id",
            "variation_id",
            "hgvs_notation",
            "hgvs",
            "rsid",
            "display_label",
            "label",
            "mechanism_name",
        ]:
            if key in record.data and record.data[key] is not None:
                anchors[key] = record.data[key]

        for key in ["source_record_id", "external_record_id"]:
            if key in anchors:
                continue
            raw_value = record.metadata.get(key)
            if raw_value is not None and raw_value != "":
                anchors[key] = raw_value

        if not anchors and record.source_id.strip():
            anchors["source_id"] = record.source_id.strip()
        return anchors

    def _extract_timestamp(self, record: RawRecord) -> datetime | None:
        for key in [
            "timestamp",
            "date",
            "created_at",
            "observed_at",
            "publication_date",
        ]:
            if key not in record.data:
                continue
            value = record.data[key]
            if not isinstance(value, str):
                continue
            try:
                dt = datetime.fromisoformat(value)
            except ValueError:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt
        return None

    def _build_run_metrics(
        self,
        *,
        record: RawRecord,
        metrics: dict[str, int],
        matched_observations_count: int,
    ) -> JSONObject:
        searched_field_count = metrics["searched_field_count"]
        skipped_field_count = metrics["skipped_field_count"]
        cache_hit_count = metrics["cache_hit_count"]
        cache_miss_count = metrics["cache_miss_count"]
        summary_message = (
            "Vector search scanned "
            f"{searched_field_count} candidate field"
            f"{'' if searched_field_count == 1 else 's'}, "
            f"skipped {skipped_field_count} low-value field"
            f"{'' if skipped_field_count == 1 else 's'}, "
            f"cache hits {cache_hit_count}, "
            f"cache misses {cache_miss_count}."
        )
        return {
            "record_type": record.metadata.get("type"),
            "entity_type": record.metadata.get("entity_type"),
            "searched_field_count": searched_field_count,
            "skipped_field_count": skipped_field_count,
            "cache_hit_count": cache_hit_count,
            "cache_miss_count": cache_miss_count,
            "matched_observations_count": matched_observations_count,
            "summary_message": summary_message,
        }
