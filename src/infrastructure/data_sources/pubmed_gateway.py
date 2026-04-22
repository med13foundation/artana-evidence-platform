"""Infrastructure gateway for PubMed data sources."""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.domain.entities.data_source_configs import PubMedQueryConfig  # noqa: TCH001
from src.domain.entities.source_sync_state import CheckpointKind
from src.domain.services.pubmed_ingestion import (
    PubMedGateway,
    PubMedGatewayFetchResult,
    PubMedQueryValidationResult,
)
from src.infrastructure.ingest.pubmed_ingestor import PubMedIngestor
from src.type_definitions.common import JSONObject, JSONValue, RawRecord  # noqa: TCH001

if TYPE_CHECKING:
    from src.domain.agents.contracts.pubmed_relevance import PubMedRelevanceContract
    from src.domain.agents.ports.pubmed_relevance_port import PubMedRelevancePort

logger = logging.getLogger(__name__)
_QUERY_TOKEN_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
_QUERY_STOPWORDS = frozenset(
    {
        "and",
        "or",
        "not",
        "title",
        "abstract",
        "all",
        "fields",
        "mesh",
        "terms",
        "pmid",
        "sb",
    },
)
_MAX_DERIVED_RESCUE_TERMS = 8
_MIN_RESCUE_TERM_LENGTH = 2
_UPPERCASE_RESCUE_TOKEN_MIN_LENGTH = 4


@dataclass(frozen=True)
class _RelevanceFilterOutcome:
    records: list[RawRecord]
    filtered_out_pubmed_ids: list[str]
    semantic_filtering_enabled: bool
    pre_rescue_filtered_out_pubmed_ids: list[str]
    full_text_entity_rescue_enabled: bool
    full_text_entity_rescue_terms: list[str]
    full_text_rescue_attempted_pubmed_ids: list[str]
    full_text_rescued_pubmed_ids: list[str]


@dataclass(frozen=True)
class _FullTextRescueOutcome:
    rescued_records: list[RawRecord]
    attempted_pubmed_ids: list[str]
    rescued_pubmed_ids: list[str]
    rescue_terms: list[str]
    enabled: bool


class PubMedSourceGateway(PubMedGateway):
    """Adapter that executes PubMed queries per data source configuration."""

    def __init__(
        self,
        ingestor: PubMedIngestor | None = None,
        *,
        relevance_agent: PubMedRelevancePort | None = None,
        relevance_model_id: str | None = None,
        full_text_rescue_timeout_seconds: int = 20,
    ) -> None:
        self._ingestor = ingestor or PubMedIngestor()
        self._relevance_agent = relevance_agent
        self._relevance_model_id = relevance_model_id
        self._full_text_rescue_timeout_seconds = max(
            int(full_text_rescue_timeout_seconds),
            1,
        )

    async def fetch_records(self, config: PubMedQueryConfig) -> list[RawRecord]:
        """Fetch PubMed records using per-source query parameters."""
        params: dict[str, JSONValue] = {
            "query": config.query,
            "publication_types": config.publication_types,
            "mindate": config.date_from,
            "maxdate": config.date_to,
            "publication_date_from": config.date_from,
            "max_results": config.max_results,
            "open_access_only": config.open_access_only,
        }
        if isinstance(config.pinned_pubmed_id, str) and config.pinned_pubmed_id.strip():
            params["pinned_pubmed_id"] = config.pinned_pubmed_id.strip()

        raw_records = await self._ingestor.fetch_data(**params)
        outcome = await self._apply_relevance_threshold(
            raw_records,
            config=config,
        )
        return outcome.records

    async def validate_query(
        self,
        config: PubMedQueryConfig,
    ) -> PubMedQueryValidationResult:
        """Validate a PubMed query against ESearch before running ingestion."""
        return await self._ingestor.validate_query(
            config.query,
            publication_types=config.publication_types,
            mindate=config.date_from,
            maxdate=config.date_to,
            publication_date_from=config.date_from,
            open_access_only=config.open_access_only,
        )

    async def fetch_records_incremental(
        self,
        config: PubMedQueryConfig,
        *,
        checkpoint: JSONObject | None = None,
    ) -> PubMedGatewayFetchResult:
        """Fetch PubMed records with cursor-aware checkpoint semantics."""
        retstart = self._extract_retstart(checkpoint)
        params: dict[str, JSONValue] = {
            "query": config.query,
            "publication_types": config.publication_types,
            "mindate": config.date_from,
            "maxdate": config.date_to,
            "publication_date_from": config.date_from,
            "max_results": config.max_results,
            "retstart": retstart,
            "open_access_only": config.open_access_only,
        }
        if isinstance(config.pinned_pubmed_id, str) and config.pinned_pubmed_id.strip():
            params["pinned_pubmed_id"] = config.pinned_pubmed_id.strip()

        if hasattr(self._ingestor, "fetch_page"):
            page = await self._ingestor.fetch_page(**params)
            next_retstart = page.next_retstart if page.has_more else 0
            raw_records = list(page.records)
            fetched_records = len(raw_records)
            total_count = page.total_count
            page_size = page.retmax
            has_more = page.has_more
            returned_count = page.returned_count
        else:
            raw_records = await self._ingestor.fetch_data(**params)
            fetched_records = len(raw_records)
            total_count = fetched_records
            page_size = max(config.max_results, 1)
            next_retstart = retstart + fetched_records if fetched_records else 0
            has_more = False
            returned_count = fetched_records

        # Protect checkpoint progression when upstream search returned IDs but the
        # fetch/parser path yielded zero records. Advancing the cursor in this case
        # can permanently skip a page.
        preserve_cursor_for_empty_page = returned_count > 0 and fetched_records == 0
        if preserve_cursor_for_empty_page:
            logger.warning(
                (
                    "PubMed incremental fetch returned IDs but yielded zero records; "
                    "preserving cursor to avoid page loss"
                ),
                extra={
                    "query": config.query,
                    "retstart": retstart,
                    "returned_count": returned_count,
                    "fetched_records": fetched_records,
                    "total_count": total_count,
                },
            )
            next_retstart = retstart
            has_more = True

        outcome = await self._apply_relevance_threshold(
            raw_records,
            config=config,
        )
        checkpoint_after: JSONObject = {
            "provider": "pubmed",
            "cursor_type": "retstart",
            "retstart": next_retstart,
            "retmax": page_size,
            "total_count": total_count,
            "returned_count": returned_count,
            "has_more": has_more,
            "cycle_completed": not has_more,
            "relevance_threshold": config.relevance_threshold,
            "open_access_only": config.open_access_only,
            "semantic_relevance_filtering": outcome.semantic_filtering_enabled,
            "filtered_out_count": len(outcome.filtered_out_pubmed_ids),
            "filtered_out_pubmed_ids": outcome.filtered_out_pubmed_ids,
            "pre_rescue_filtered_out_count": len(
                outcome.pre_rescue_filtered_out_pubmed_ids,
            ),
            "pre_rescue_filtered_out_pubmed_ids": (
                outcome.pre_rescue_filtered_out_pubmed_ids
            ),
            "full_text_entity_rescue_enabled": (
                outcome.full_text_entity_rescue_enabled
            ),
            "full_text_entity_rescue_terms": outcome.full_text_entity_rescue_terms,
            "full_text_rescue_attempted_count": len(
                outcome.full_text_rescue_attempted_pubmed_ids,
            ),
            "full_text_rescue_attempted_pubmed_ids": (
                outcome.full_text_rescue_attempted_pubmed_ids
            ),
            "full_text_rescued_count": len(outcome.full_text_rescued_pubmed_ids),
            "full_text_rescued_pubmed_ids": outcome.full_text_rescued_pubmed_ids,
            "cursor_preserved_due_to_empty_page": preserve_cursor_for_empty_page,
        }
        return PubMedGatewayFetchResult(
            records=outcome.records,
            fetched_records=fetched_records,
            checkpoint_after=checkpoint_after,
            checkpoint_kind=CheckpointKind.CURSOR,
        )

    @staticmethod
    def _extract_retstart(checkpoint: JSONObject | None) -> int:
        """Resolve provider cursor from checkpoint payload."""
        if checkpoint is None:
            return 0
        provider = checkpoint.get("provider")
        if isinstance(provider, str) and provider.lower() != "pubmed":
            return 0
        retstart_raw = checkpoint.get("retstart")
        if isinstance(retstart_raw, int) and retstart_raw >= 0:
            return retstart_raw
        if isinstance(retstart_raw, float):
            candidate = int(retstart_raw)
            return max(candidate, 0)
        if isinstance(retstart_raw, str) and retstart_raw.isdigit():
            return int(retstart_raw)
        return 0

    async def _apply_relevance_threshold(
        self,
        records: list[RawRecord],
        *,
        config: PubMedQueryConfig,
    ) -> _RelevanceFilterOutcome:
        threshold = config.relevance_threshold
        if self._relevance_agent is not None and threshold > 0:
            return await self._apply_semantic_relevance_threshold(
                records=records,
                threshold=threshold,
                config=config,
            )

        if threshold <= 0:
            return _RelevanceFilterOutcome(
                records=records,
                filtered_out_pubmed_ids=[],
                semantic_filtering_enabled=False,
                pre_rescue_filtered_out_pubmed_ids=[],
                full_text_entity_rescue_enabled=config.full_text_entity_rescue_enabled,
                full_text_entity_rescue_terms=[],
                full_text_rescue_attempted_pubmed_ids=[],
                full_text_rescued_pubmed_ids=[],
            )

        kept_records: list[RawRecord] = []
        filtered_records: list[RawRecord] = []
        filtered_out_pubmed_ids: list[str] = []
        for record in records:
            relevance = record.get("med13_relevance")
            score = None
            if isinstance(relevance, dict):
                score_value = relevance.get("score")
                if isinstance(score_value, int | float):
                    score = int(score_value)
            if score is None or score >= threshold:
                kept_records.append(record)
            else:
                filtered_records.append(record)
                pubmed_id = self._extract_pubmed_id(record)
                if pubmed_id is not None:
                    filtered_out_pubmed_ids.append(pubmed_id)
        pre_rescue_filtered_out_pubmed_ids = list(filtered_out_pubmed_ids)
        rescue_outcome = await self._run_full_text_entity_rescue_lane(
            filtered_records=filtered_records,
            config=config,
        )
        rescued_record_ids = {id(record) for record in rescue_outcome.rescued_records}
        kept_record_ids = {id(record) for record in kept_records}
        filtered_out_after_rescue = [
            pubmed_id
            for pubmed_id in pre_rescue_filtered_out_pubmed_ids
            if pubmed_id not in set(rescue_outcome.rescued_pubmed_ids)
        ]
        final_records = [
            record
            for record in records
            if id(record) in kept_record_ids or id(record) in rescued_record_ids
        ]

        if final_records:
            return _RelevanceFilterOutcome(
                records=final_records,
                filtered_out_pubmed_ids=filtered_out_after_rescue,
                semantic_filtering_enabled=False,
                pre_rescue_filtered_out_pubmed_ids=pre_rescue_filtered_out_pubmed_ids,
                full_text_entity_rescue_enabled=rescue_outcome.enabled,
                full_text_entity_rescue_terms=rescue_outcome.rescue_terms,
                full_text_rescue_attempted_pubmed_ids=(
                    rescue_outcome.attempted_pubmed_ids
                ),
                full_text_rescued_pubmed_ids=rescue_outcome.rescued_pubmed_ids,
            )
        logger.warning(
            (
                "PubMed relevance threshold removed all fetched records; "
                "falling back to unfiltered records"
            ),
            extra={
                "threshold": threshold,
                "raw_record_count": len(records),
                "filtered_out_pubmed_ids": pre_rescue_filtered_out_pubmed_ids,
                "full_text_rescue_attempted_pubmed_ids": (
                    rescue_outcome.attempted_pubmed_ids
                ),
                "full_text_rescued_pubmed_ids": rescue_outcome.rescued_pubmed_ids,
            },
        )
        return _RelevanceFilterOutcome(
            records=records,
            filtered_out_pubmed_ids=[],
            semantic_filtering_enabled=False,
            pre_rescue_filtered_out_pubmed_ids=pre_rescue_filtered_out_pubmed_ids,
            full_text_entity_rescue_enabled=rescue_outcome.enabled,
            full_text_entity_rescue_terms=rescue_outcome.rescue_terms,
            full_text_rescue_attempted_pubmed_ids=(rescue_outcome.attempted_pubmed_ids),
            full_text_rescued_pubmed_ids=rescue_outcome.rescued_pubmed_ids,
        )

    async def _apply_semantic_relevance_threshold(
        self,
        *,
        records: list[RawRecord],
        threshold: int,
        config: PubMedQueryConfig,
    ) -> _RelevanceFilterOutcome:
        classification_tasks = [
            self._classify_record_relevance(record=record, config=config)
            for record in records
        ]
        classification_results = await asyncio.gather(
            *classification_tasks,
            return_exceptions=True,
        )

        filtered_records: list[RawRecord] = []
        filtered_out_records: list[RawRecord] = []
        filtered_out_pubmed_ids: list[str] = []
        classification_errors = 0
        classification_error_pubmed_ids: list[str] = []

        for index, record in enumerate(records):
            outcome = classification_results[index]
            if isinstance(outcome, BaseException):
                classification_errors += 1
                pubmed_id = self._extract_pubmed_id(record)
                if pubmed_id is not None:
                    classification_error_pubmed_ids.append(pubmed_id)
                self._set_semantic_relevance_metadata(
                    record=record,
                    label="unclassified",
                    confidence=0.0,
                    rationale=f"classification_failed:{type(outcome).__name__}",
                    agent_run_id=None,
                )
                filtered_records.append(record)
                continue

            label = outcome.relevance
            confidence = max(0.0, min(1.0, float(outcome.confidence_score)))
            score = self._semantic_relevance_score(label=label, confidence=confidence)
            self._set_semantic_relevance_metadata(
                record=record,
                label=label,
                confidence=confidence,
                rationale=outcome.rationale,
                agent_run_id=outcome.agent_run_id,
            )
            if score >= threshold:
                filtered_records.append(record)
                continue

            filtered_out_records.append(record)
            pubmed_id = self._extract_pubmed_id(record)
            if pubmed_id is not None:
                filtered_out_pubmed_ids.append(pubmed_id)

        pre_rescue_filtered_out_pubmed_ids = list(filtered_out_pubmed_ids)
        rescue_outcome = await self._run_full_text_entity_rescue_lane(
            filtered_records=filtered_out_records,
            config=config,
        )
        rescued_record_ids = {id(record) for record in rescue_outcome.rescued_records}
        kept_record_ids = {id(record) for record in filtered_records}
        filtered_out_after_rescue = [
            pubmed_id
            for pubmed_id in pre_rescue_filtered_out_pubmed_ids
            if pubmed_id not in set(rescue_outcome.rescued_pubmed_ids)
        ]
        final_records = [
            record
            for record in records
            if id(record) in kept_record_ids or id(record) in rescued_record_ids
        ]

        if final_records:
            logger.info(
                "PubMed semantic relevance filtering completed",
                extra={
                    "threshold": threshold,
                    "raw_record_count": len(records),
                    "kept_count": len(final_records),
                    "pre_rescue_filtered_out_count": len(
                        pre_rescue_filtered_out_pubmed_ids,
                    ),
                    "filtered_out_count": len(filtered_out_after_rescue),
                    "classification_errors": classification_errors,
                    "classification_error_pubmed_ids": classification_error_pubmed_ids,
                    "full_text_rescue_attempted_count": len(
                        rescue_outcome.attempted_pubmed_ids,
                    ),
                    "full_text_rescued_count": len(rescue_outcome.rescued_pubmed_ids),
                },
            )
            return _RelevanceFilterOutcome(
                records=final_records,
                filtered_out_pubmed_ids=filtered_out_after_rescue,
                semantic_filtering_enabled=True,
                pre_rescue_filtered_out_pubmed_ids=pre_rescue_filtered_out_pubmed_ids,
                full_text_entity_rescue_enabled=rescue_outcome.enabled,
                full_text_entity_rescue_terms=rescue_outcome.rescue_terms,
                full_text_rescue_attempted_pubmed_ids=(
                    rescue_outcome.attempted_pubmed_ids
                ),
                full_text_rescued_pubmed_ids=rescue_outcome.rescued_pubmed_ids,
            )

        logger.warning(
            (
                "PubMed semantic relevance filtering removed all fetched records; "
                "falling back to unfiltered records"
            ),
            extra={
                "threshold": threshold,
                "raw_record_count": len(records),
                "filtered_out_pubmed_ids": pre_rescue_filtered_out_pubmed_ids,
                "classification_errors": classification_errors,
                "classification_error_pubmed_ids": classification_error_pubmed_ids,
                "full_text_rescue_attempted_pubmed_ids": (
                    rescue_outcome.attempted_pubmed_ids
                ),
                "full_text_rescued_pubmed_ids": rescue_outcome.rescued_pubmed_ids,
            },
        )
        return _RelevanceFilterOutcome(
            records=records,
            filtered_out_pubmed_ids=[],
            semantic_filtering_enabled=True,
            pre_rescue_filtered_out_pubmed_ids=pre_rescue_filtered_out_pubmed_ids,
            full_text_entity_rescue_enabled=rescue_outcome.enabled,
            full_text_entity_rescue_terms=rescue_outcome.rescue_terms,
            full_text_rescue_attempted_pubmed_ids=(rescue_outcome.attempted_pubmed_ids),
            full_text_rescued_pubmed_ids=rescue_outcome.rescued_pubmed_ids,
        )

    async def _classify_record_relevance(
        self,
        *,
        record: RawRecord,
        config: PubMedQueryConfig,
    ) -> PubMedRelevanceContract:
        if self._relevance_agent is None:
            msg = "Semantic relevance classifier is not configured."
            raise RuntimeError(msg)
        title_raw = record.get("title")
        abstract_raw = record.get("abstract")
        title = title_raw.strip() if isinstance(title_raw, str) else ""
        abstract = abstract_raw.strip() if isinstance(abstract_raw, str) else ""
        if not title and not abstract:
            msg = "Record has neither title nor abstract for semantic relevance."
            raise ValueError(msg)

        from src.domain.agents.contexts.pubmed_relevance_context import (
            PubMedRelevanceContext,
        )

        context = PubMedRelevanceContext(
            source_type="pubmed",
            query=config.query,
            title=title or None,
            abstract=abstract or None,
            domain_context=config.domain_context,
            pubmed_id=self._extract_pubmed_id(record),
        )
        return await self._relevance_agent.classify(
            context,
            model_id=self._relevance_model_id,
        )

    @staticmethod
    def _semantic_relevance_score(*, label: str, confidence: float) -> int:
        if label != "relevant":
            return 0
        normalized_confidence = max(0.0, min(1.0, confidence))
        return int(round(normalized_confidence * 10.0))

    @staticmethod
    def _set_semantic_relevance_metadata(
        *,
        record: RawRecord,
        label: str,
        confidence: float,
        rationale: str,
        agent_run_id: str | None,
    ) -> None:
        record["semantic_relevance"] = {
            "label": label,
            "confidence": confidence,
            "rationale": rationale,
            "agent_run_id": agent_run_id,
        }

    @staticmethod
    def _extract_pubmed_id(record: RawRecord) -> str | None:
        for key in ("pmid", "pubmed_id"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, int):
                return str(value)
        return None

    async def _run_full_text_entity_rescue_lane(
        self,
        *,
        filtered_records: list[RawRecord],
        config: PubMedQueryConfig,
    ) -> _FullTextRescueOutcome:
        if not config.full_text_entity_rescue_enabled:
            return _FullTextRescueOutcome(
                rescued_records=[],
                attempted_pubmed_ids=[],
                rescued_pubmed_ids=[],
                rescue_terms=[],
                enabled=False,
            )
        if not filtered_records:
            return _FullTextRescueOutcome(
                rescued_records=[],
                attempted_pubmed_ids=[],
                rescued_pubmed_ids=[],
                rescue_terms=self._resolve_full_text_entity_rescue_terms(config),
                enabled=True,
            )

        rescue_terms = self._resolve_full_text_entity_rescue_terms(config)
        if not rescue_terms:
            return _FullTextRescueOutcome(
                rescued_records=[],
                attempted_pubmed_ids=[],
                rescued_pubmed_ids=[],
                rescue_terms=[],
                enabled=True,
            )

        rescued_records: list[RawRecord] = []
        attempted_pubmed_ids: list[str] = []
        rescued_pubmed_ids: list[str] = []
        for record in filtered_records:
            pubmed_id = self._extract_pubmed_id(record)
            fetch_result = await self._fetch_open_access_full_text_for_record(record)
            attempted_sources = getattr(fetch_result, "attempted_sources", ())
            if attempted_sources and pubmed_id is not None:
                attempted_pubmed_ids.append(pubmed_id)
            content_text_raw = getattr(fetch_result, "content_text", None)
            content_text = content_text_raw if isinstance(content_text_raw, str) else ""
            matched_terms = self._match_rescue_terms(
                content_text=content_text,
                rescue_terms=rescue_terms,
            )
            if not matched_terms:
                continue
            if pubmed_id is not None:
                rescued_pubmed_ids.append(pubmed_id)
            self._set_full_text_entity_rescue_metadata(
                record=record,
                matched_terms=matched_terms,
                acquisition_method=getattr(
                    fetch_result,
                    "acquisition_method",
                    "skipped",
                ),
                source_url=getattr(fetch_result, "source_url", None),
            )
            rescued_records.append(record)

        if rescued_pubmed_ids:
            logger.info(
                "PubMed full-text rescue lane retained filtered records",
                extra={
                    "rescue_terms": rescue_terms,
                    "attempted_pubmed_ids": attempted_pubmed_ids,
                    "rescued_pubmed_ids": rescued_pubmed_ids,
                },
            )

        return _FullTextRescueOutcome(
            rescued_records=rescued_records,
            attempted_pubmed_ids=attempted_pubmed_ids,
            rescued_pubmed_ids=rescued_pubmed_ids,
            rescue_terms=rescue_terms,
            enabled=True,
        )

    async def _fetch_open_access_full_text_for_record(
        self,
        record: RawRecord,
    ) -> object:
        from src.infrastructure.llm.content_enrichment_full_text import (
            fetch_pubmed_open_access_full_text,
        )

        metadata: JSONObject = {}
        for key in ("pmc_id", "pmid", "pubmed_id", "doi"):
            value = record.get(key)
            if isinstance(value, str) and value.strip():
                metadata[key] = value.strip()
            elif isinstance(value, int):
                metadata[key] = str(value)
        return await asyncio.to_thread(
            fetch_pubmed_open_access_full_text,
            metadata,
            timeout_seconds=self._full_text_rescue_timeout_seconds,
        )

    def _resolve_full_text_entity_rescue_terms(
        self,
        config: PubMedQueryConfig,
    ) -> list[str]:
        configured_terms = config.full_text_entity_rescue_terms or []
        normalized_configured_terms = self._normalize_rescue_terms(configured_terms)
        if normalized_configured_terms:
            return normalized_configured_terms

        query_term_slice = re.split(
            r"\bNOT\b",
            config.query,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        derived_tokens = _QUERY_TOKEN_PATTERN.findall(query_term_slice)
        candidate_terms: list[str] = []
        for token in derived_tokens:
            normalized = token.casefold()
            if normalized in _QUERY_STOPWORDS:
                continue
            if any(character.isdigit() for character in normalized) or (
                token.isupper() and len(token) >= _UPPERCASE_RESCUE_TOKEN_MIN_LENGTH
            ):
                candidate_terms.append(normalized)
        return self._normalize_rescue_terms(candidate_terms)[:_MAX_DERIVED_RESCUE_TERMS]

    @staticmethod
    def _normalize_rescue_terms(terms: list[str]) -> list[str]:
        normalized_terms: list[str] = []
        seen: set[str] = set()
        for raw_term in terms:
            candidate = raw_term.strip().casefold()
            if len(candidate) < _MIN_RESCUE_TERM_LENGTH or candidate in seen:
                continue
            seen.add(candidate)
            normalized_terms.append(candidate)
        return normalized_terms

    @staticmethod
    def _match_rescue_terms(
        *,
        content_text: str,
        rescue_terms: list[str],
    ) -> list[str]:
        if not content_text:
            return []
        content_lower = content_text.casefold()
        matched_terms: list[str] = []
        for rescue_term in rescue_terms:
            if " " in rescue_term or "-" in rescue_term or "_" in rescue_term:
                if rescue_term in content_lower:
                    matched_terms.append(rescue_term)
                continue
            term_pattern = rf"\b{re.escape(rescue_term)}\b"
            if re.search(term_pattern, content_lower):
                matched_terms.append(rescue_term)
        return matched_terms

    @staticmethod
    def _set_full_text_entity_rescue_metadata(
        *,
        record: RawRecord,
        matched_terms: list[str],
        acquisition_method: object,
        source_url: object,
    ) -> None:
        record["full_text_entity_rescue"] = {
            "rescued": True,
            "matched_terms": matched_terms,
            "acquisition_method": (
                str(acquisition_method) if isinstance(acquisition_method, str) else None
            ),
            "source_url": source_url if isinstance(source_url, str) else None,
        }
        semantic_relevance_raw = record.get("semantic_relevance")
        if not isinstance(semantic_relevance_raw, dict):
            return
        semantic_relevance_raw["rescued_by_full_text"] = True
        semantic_relevance_raw["rescue_terms"] = matched_terms
