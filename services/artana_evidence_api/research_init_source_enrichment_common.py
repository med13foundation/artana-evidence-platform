"""Shared helpers for research-init structured source enrichment."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    attach_source_capture_metadata,
    compact_provenance,
    source_result_capture_metadata,
)
from artana_evidence_api.types.common import JSONObject

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.proposal_store import HarnessProposalDraft
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

logger = logging.getLogger(__name__)

_SYSTEM_OWNER_ID = UUID("00000000-0000-0000-0000-000000000000")

# Gene symbols are short uppercase alphanumeric tokens, optionally with hyphens.
_GENE_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9\-]{1,9}$")

# Free-text gene-mention pattern: token of 2-10 chars starting with an uppercase
# letter, followed by uppercase/digit/hyphen, surrounded by word boundaries.
# Used to extract gene-like mentions from PubMed titles/abstracts.
_GENE_MENTION_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}(?:-[A-Z0-9]+)?)\b")

# Common false positives — short uppercase tokens that are not genes.
_GENE_MENTION_STOPWORDS = frozenset(
    {
        "DNA",
        "RNA",
        "MRNA",
        "PCR",
        "ATP",
        "GTP",
        "ADP",
        "GDP",
        "NADH",
        "NADPH",
        "FAD",
        "USA",
        "UK",
        "EU",
        "WHO",
        "FDA",
        "NIH",
        "NCBI",
        "PMID",
        "DOI",
        "OMIM",
        "MIM",
        "ID",
        "II",
        "III",
        "IV",
        "VI",
        "ICU",
        "MRI",
        "CT",
        "EEG",
        "ECG",
        "BMI",
        "AND",
        "OR",
        "NOT",
        "GWAS",
        "QTL",
        "SNP",
        "ORF",
        "PDB",
        "BLAST",
        "BMC",
        "PNAS",
        "PLOS",
        "PMC",
        "ELSEVIER",
        "SPRINGER",
    },
)


def extract_gene_mentions_from_text(text: str, *, max_count: int = 30) -> list[str]:
    """Extract likely gene symbol mentions from a free-text passage.

    Used to seed structured-source enrichment with entities discovered in
    PubMed titles and abstracts before full extraction has run.  Returns
    deduplicated, ordered list bounded by ``max_count``.
    """
    if not text:
        return []
    seen: set[str] = set()
    mentions: list[str] = []
    for match in _GENE_MENTION_RE.finditer(text):
        token = match.group(1)
        if token in _GENE_MENTION_STOPWORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        mentions.append(token)
        if len(mentions) >= max_count:
            break
    return mentions


# Maximum number of terms to query per source during init to bound latency.
_MAX_TERMS_PER_SOURCE = 5
_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE = 0.5


def _bootstrap_proposal_metadata(
    *,
    source: str,
    extra: JSONObject | None = None,
) -> JSONObject:
    """Return metadata for structured proposals awaiting qualitative review."""
    return {
        "source": source,
        "bootstrap_claim_path": "structured_source_bootstrap_draft",
        "claim_generation_mode": "deterministic_structured_draft_unreviewed",
        "requires_qualitative_review": True,
        "direct_graph_promotion_allowed": False,
        **(extra or {}),
    }


@dataclass(frozen=True)
class SourceEnrichmentResult:
    """Result of running one structured source enrichment."""

    source_key: str
    documents_created: list[HarnessDocumentRecord] = field(default_factory=list)
    proposals_created: list[HarnessProposalDraft] = field(default_factory=list)
    records_processed: int = 0
    errors: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Helpers — gene symbol extraction
# ---------------------------------------------------------------------------


def _extract_likely_gene_symbols(seed_terms: list[str]) -> list[str]:
    """Filter seed terms for likely gene symbols.

    Gene symbols are uppercase, 2-10 characters, alphanumeric with optional
    hyphens (e.g. BRCA1, TP53, HLA-A).  Returns a deduplicated list preserving
    insertion order.
    """
    seen: set[str] = set()
    symbols: list[str] = []
    for term in seed_terms:
        candidate = term.strip().upper()
        if (
            candidate
            and _GENE_SYMBOL_RE.match(candidate)
            and candidate not in _GENE_MENTION_STOPWORDS
            and candidate not in seen
        ):
            seen.add(candidate)
            symbols.append(candidate)
    return symbols


# ---------------------------------------------------------------------------
# Helpers — document creation with dedup
# ---------------------------------------------------------------------------


def _create_enrichment_document(
    *,
    space_id: UUID,
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
    title: str,
    source_type: str,
    text_content: str,
    metadata: JSONObject,
) -> HarnessDocumentRecord | None:
    """Create or resolve a harness document for enrichment results.

    Returns the existing document when the content hash already exists in the space
    so downstream proposals can still point at a resolvable source document.
    """
    content_bytes = text_content.encode("utf-8")
    sha256 = hashlib.sha256(content_bytes).hexdigest()

    existing = document_store.find_document_by_sha256(
        space_id=space_id,
        sha256=sha256,
    )
    if existing is not None:
        logger.debug(
            "Reusing duplicate enrichment document (sha256=%s, source=%s)",
            sha256[:12],
            source_type,
        )
        return existing

    ingestion_run = run_registry.create_run(
        space_id=space_id,
        harness_id=f"research-init-{source_type}",
        title=title,
        input_payload={
            "source": f"research-init-{source_type}",
            "title": title,
        },
        graph_service_status=parent_run.graph_service_status,
        graph_service_version=parent_run.graph_service_version,
    )
    artifact_store.seed_for_run(run=ingestion_run)
    run_registry.set_run_status(
        space_id=space_id,
        run_id=ingestion_run.id,
        status="completed",
    )
    document_metadata = _enrichment_document_metadata_with_capture(
        source_type=source_type,
        metadata=metadata,
        sha256=sha256,
        ingestion_run_id=ingestion_run.id,
        parent_run_id=parent_run.id,
    )

    return document_store.create_document(
        space_id=space_id,
        created_by=_SYSTEM_OWNER_ID,
        title=title[:256],
        source_type=source_type,
        filename=None,
        media_type="text/plain",
        sha256=sha256,
        byte_size=len(content_bytes),
        page_count=None,
        text_content=text_content,
        raw_storage_key=None,
        enriched_storage_key=None,
        ingestion_run_id=ingestion_run.id,
        last_enrichment_run_id=None,
        enrichment_status="skipped",
        extraction_status="not_started",
        metadata=document_metadata,
    )


def _enrichment_document_metadata_with_capture(
    *,
    source_type: str,
    metadata: JSONObject,
    sha256: str,
    ingestion_run_id: str,
    parent_run_id: str,
) -> JSONObject:
    """Attach normalized source-capture metadata to enrichment documents."""

    query = _metadata_first_text(metadata, ("gene_symbol", "query_term"))
    result_count = _metadata_first_count(
        metadata,
        (
            "record_count",
            "variant_count",
            "prediction_count",
            "trial_count",
            "gene_count",
            "panel_count",
        ),
    )
    source_capture = source_result_capture_metadata(
        source_key=source_type,
        capture_stage=SourceCaptureStage.SOURCE_DOCUMENT,
        capture_method="research_plan",
        locator=f"{source_type}:document:{sha256[:16]}",
        external_id=query,
        run_id=ingestion_run_id,
        query=query,
        result_count=result_count,
        provenance=compact_provenance(
            source=metadata.get("source"),
            parent_run_id=parent_run_id,
            sha256=sha256,
        ),
    )
    return attach_source_capture_metadata(
        metadata=metadata,
        source_capture=source_capture,
    )


def _metadata_first_text(metadata: JSONObject, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _metadata_first_count(metadata: JSONObject, keys: tuple[str, ...]) -> int | None:
    for key in keys:
        value = metadata.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None




__all__ = [
    "SourceEnrichmentResult",
    "_MAX_TERMS_PER_SOURCE",
    "_SYSTEM_OWNER_ID",
    "_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE",
    "_bootstrap_proposal_metadata",
    "_create_enrichment_document",
    "_extract_likely_gene_symbols",
    "extract_gene_mentions_from_text",
    "logger",
]
