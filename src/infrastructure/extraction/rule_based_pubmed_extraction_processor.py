"""Rule-based extraction processor for PubMed title/abstract text."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol

from src.application.services.ports.extraction_processor_port import (
    ExtractionOutcome,
    ExtractionProcessorPort,
    ExtractionProcessorResult,
    ExtractionTextPayload,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from src.domain.entities.extraction_queue_item import ExtractionQueueItem
    from src.domain.entities.publication import Publication
    from src.type_definitions.common import (
        ExtractionFact,
        ExtractionFactType,
        JSONObject,
    )


_HPO_ID_PATTERN = re.compile(r"\bHP:\d{7}\b")
_CDNA_VARIANT_PATTERN = re.compile(r"\bc\.\d+[ACGT]>[ACGT]\b", re.IGNORECASE)
_PROTEIN_VARIANT_3_PATTERN = re.compile(r"\bp\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}\b")
_PROTEIN_VARIANT_1_PATTERN = re.compile(r"\bp\.[A-Z]\d+[A-Z]\b")


class RuleBasedPubMedExtractionProcessor(ExtractionProcessorPort):
    """Extracts simple gene, variant, and phenotype facts from titles/abstracts."""

    def __init__(self, *, gene_symbols: Iterable[str] | None = None) -> None:
        symbols = gene_symbols or ("MED13",)
        self._gene_symbols = {symbol.strip().upper() for symbol in symbols if symbol}

    def extract_publication(
        self,
        *,
        queue_item: ExtractionQueueItem,
        publication: Publication | None,
        text_payload: ExtractionTextPayload | None = None,
    ) -> ExtractionProcessorResult:
        if publication is None and text_payload is None:
            return ExtractionProcessorResult(
                status="failed",
                facts=[],
                metadata={},
                processor_name="rule_based_pubmed_v1",
                text_source="title_abstract",
                error_message="publication_not_found",
            )

        if text_payload is not None:
            text = text_payload.text
            text_source = text_payload.text_source
            document_reference = text_payload.document_reference
        else:
            if publication is None:
                return ExtractionProcessorResult(
                    status="failed",
                    facts=[],
                    metadata={},
                    processor_name="rule_based_pubmed_v1",
                    text_source="title_abstract",
                    error_message="publication_not_found",
                )
            text = _build_text(publication)
            text_source = "title_abstract"
            document_reference = None
        if not text:
            return ExtractionProcessorResult(
                status="skipped",
                facts=[],
                metadata={
                    "reason": "empty_text",
                    "queue_item_id": str(queue_item.id),
                },
                processor_name="rule_based_pubmed_v1",
                text_source=text_source,
                document_reference=document_reference,
            )

        facts: list[ExtractionFact] = []
        seen: set[tuple[ExtractionFactType, str, str | None]] = set()

        def add_fact(
            fact_type: ExtractionFactType,
            value: str,
            *,
            normalized_id: str | None = None,
            source: str | None = None,
            attributes: JSONObject | None = None,
        ) -> None:
            key = (fact_type, value, normalized_id)
            if key in seen:
                return
            seen.add(key)
            fact: ExtractionFact = {
                "fact_type": fact_type,
                "value": value,
            }
            if normalized_id:
                fact["normalized_id"] = normalized_id
            if source:
                fact["source"] = source
            if attributes:
                fact["attributes"] = attributes
            facts.append(fact)

        _extract_gene_mentions(text, self._gene_symbols, add_fact, source=text_source)
        _extract_variants(text, add_fact, source=text_source)
        _extract_hpo_ids(text, add_fact, source=text_source)

        status: ExtractionOutcome = "completed" if facts else "skipped"
        metadata: JSONObject = {
            "queue_item_id": str(queue_item.id),
            "fact_count": len(facts),
        }
        return ExtractionProcessorResult(
            status=status,
            facts=facts,
            metadata=metadata,
            processor_name="rule_based_pubmed_v1",
            processor_version="1.0",
            text_source=text_source,
            document_reference=document_reference,
        )


def _build_text(publication: Publication) -> str:
    parts = [publication.title, publication.abstract or ""]
    return " ".join(part.strip() for part in parts if part and part.strip())


class _AddFact(Protocol):
    def __call__(
        self,
        fact_type: ExtractionFactType,
        value: str,
        *,
        normalized_id: str | None = None,
        source: str | None = None,
        attributes: JSONObject | None = None,
    ) -> None: ...


def _extract_gene_mentions(
    text: str,
    symbols: set[str],
    add_fact: _AddFact,
    *,
    source: str,
) -> None:
    if not symbols:
        return
    for symbol in symbols:
        pattern = re.compile(rf"\b{re.escape(symbol)}\b", re.IGNORECASE)
        if pattern.search(text):
            add_fact(
                "gene",
                symbol,
                normalized_id=symbol,
                source=source,
            )


def _extract_variants(text: str, add_fact: _AddFact, *, source: str) -> None:
    for match in _CDNA_VARIANT_PATTERN.findall(text):
        add_fact(
            "variant",
            match,
            source=source,
            attributes={"pattern": "hgvs_c"},
        )
    for match in _PROTEIN_VARIANT_3_PATTERN.findall(text):
        add_fact(
            "variant",
            match,
            source=source,
            attributes={"pattern": "hgvs_p3"},
        )
    for match in _PROTEIN_VARIANT_1_PATTERN.findall(text):
        add_fact(
            "variant",
            match,
            source=source,
            attributes={"pattern": "hgvs_p1"},
        )


def _extract_hpo_ids(text: str, add_fact: _AddFact, *, source: str) -> None:
    for match in _HPO_ID_PATTERN.findall(text):
        add_fact(
            "phenotype",
            match,
            normalized_id=match,
            source=source,
        )


__all__ = ["RuleBasedPubMedExtractionProcessor"]
