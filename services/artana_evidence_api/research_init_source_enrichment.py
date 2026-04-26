"""Structured source enrichment for research-init.

Queries ClinVar, DrugBank, AlphaFold, MARRVEL, and UniProt gateways using
seed terms extracted from PubMed discovery, creates harness documents from the
results, and tracks progress in source_results.
"""

from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.source_enrichment_bridges import (
    ClinVarQueryConfig,
    build_alphafold_gateway,
    build_clinicaltrials_gateway,
    build_clinvar_gateway,
    build_drugbank_gateway,
    build_marrvel_discovery_service,
    build_mgi_gateway,
    build_uniprot_gateway,
    build_zfin_gateway,
)
from artana_evidence_api.source_result_capture import (
    SourceCaptureStage,
    attach_source_capture_metadata,
    compact_provenance,
    source_result_capture_metadata,
)
from artana_evidence_api.types.common import JSONObject, json_object_or_empty

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
# ClinVar enrichment
# ---------------------------------------------------------------------------


async def run_clinvar_enrichment(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Query ClinVar for variants related to seed gene symbols."""
    gene_symbols = _extract_likely_gene_symbols(seed_terms)
    if not gene_symbols:
        return SourceEnrichmentResult(source_key="clinvar")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0
    records_by_gene: dict[str, list[dict[str, object]]] = {}

    gateway = build_clinvar_gateway()
    if gateway is None:
        all_errors.append("ClinVar gateway not available")
    else:
        for gene_symbol in gene_symbols[:_MAX_TERMS_PER_SOURCE]:
            try:
                config = ClinVarQueryConfig(
                    query=f"{gene_symbol} pathogenic variant",
                    gene_symbol=gene_symbol,
                    max_results=20,
                )
                raw_records = await gateway.fetch_records(config=config)
                records_processed += len(raw_records)
                if raw_records:
                    records_by_gene[gene_symbol] = raw_records
                    text_content = _format_clinvar_results(gene_symbol, raw_records)
                    record = _create_enrichment_document(
                        space_id=space_id,
                        document_store=document_store,
                        run_registry=run_registry,
                        artifact_store=artifact_store,
                        parent_run=parent_run,
                        title=f"ClinVar variants for {gene_symbol}",
                        source_type="clinvar",
                        text_content=text_content,
                        metadata={
                            "source": "research-init-clinvar",
                            "gene_symbol": gene_symbol,
                            "variant_count": len(raw_records),
                        },
                    )
                    if record is not None:
                        documents.append(record)
            except Exception as exc:  # noqa: BLE001
                msg = f"ClinVar query for {gene_symbol}: {exc}"
                logger.warning(msg)
                all_errors.append(msg)

    # Create proposals directly from structured records
    all_proposals = _create_clinvar_proposals(gene_symbols, documents, records_by_gene)

    return SourceEnrichmentResult(
        source_key="clinvar",
        documents_created=documents,
        proposals_created=all_proposals,
        records_processed=records_processed,
        errors=tuple(all_errors),
    )


def _create_clinvar_proposals(
    gene_symbols: list[str],  # noqa: ARG001
    documents: list[HarnessDocumentRecord],  # noqa: ARG001
    records_by_gene: dict[str, list[dict[str, object]]],
) -> list[HarnessProposalDraft]:
    """Create unreviewed bootstrap drafts from ClinVar variant records.

    The drafts preserve deterministic source grounding. Research-init applies
    the bootstrap qualitative review boundary before persisting them.
    """
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    proposals: list[HarnessProposalDraft] = []
    for gene_symbol, records in records_by_gene.items():
        for rec in records:
            parsed = json_object_or_empty(rec.get("parsed_data"))
            clin_sig = (
                parsed.get("clinical_significance")
                or rec.get("clinical_significance")
                or rec.get("clinicalSignificance")
                or "unknown"
            )
            conditions = (
                parsed.get("conditions")
                or rec.get("conditions")
                or rec.get("condition_names")
                or []
            )
            variant_type = (
                parsed.get("variant_type")
                or rec.get("variation_type")
                or rec.get("variationType")
                or "unknown"
            )
            clinvar_id = rec.get("clinvar_id", "")

            # Normalize list-typed fields
            if isinstance(clin_sig, list):
                clin_sig = ", ".join(str(s) for s in clin_sig)

            # Skip records with no meaningful data
            if (
                str(clin_sig).lower() in ("unknown", "not provided", "")
                and not conditions
            ):
                continue

            # Format condition text
            if isinstance(conditions, list):
                condition_text = ", ".join(str(c) for c in conditions)
            else:
                condition_text = str(conditions)
            if not condition_text or condition_text.lower() == "not specified":
                condition_text = "unspecified condition"

            # Determine relation type from clinical significance
            clin_sig_lower = str(clin_sig).lower()
            if "likely pathogenic" in clin_sig_lower:
                relation_type = "PREDISPOSES_TO"
            elif "pathogenic" in clin_sig_lower:
                relation_type = "CAUSES"
            elif "benign" in clin_sig_lower:
                # Skip benign variants
                continue
            else:
                relation_type = "ASSOCIATED_WITH"

            proposals.append(
                HarnessProposalDraft(
                    proposal_type="candidate_claim",
                    source_kind="clinvar_enrichment",
                    source_key=f"clinvar:{clinvar_id}",
                    title=f"ClinVar: {gene_symbol} variant {relation_type} {condition_text}",
                    summary=(
                        f"ClinVar variant {clinvar_id} in {gene_symbol} ({variant_type}) "
                        f"classified as {clin_sig}, associated with {condition_text}."
                    ),
                    confidence=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
                    ranking_score=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
                    reasoning_path={
                        "source": "clinvar",
                        "gene": gene_symbol,
                        "clinvar_id": str(clinvar_id),
                    },
                    evidence_bundle=[
                        {
                            "source_type": "structured_database",
                            "locator": f"clinvar:{clinvar_id}",
                            "excerpt": (
                                f"{gene_symbol} variant (ClinVar {clinvar_id}): "
                                f"{clin_sig}. Conditions: {condition_text}."
                            ),
                            "relevance": 0.95,
                        },
                    ],
                    payload={
                        "proposed_subject_label": gene_symbol,
                        "proposed_claim_type": relation_type,
                        "proposed_object_label": condition_text,
                        "clinvar_id": str(clinvar_id),
                        "clinical_significance": str(clin_sig),
                        "variant_type": str(variant_type),
                    },
                    metadata=_bootstrap_proposal_metadata(
                        source="clinvar_enrichment",
                        extra={
                            "gene_symbol": gene_symbol,
                            "clinical_significance": str(clin_sig),
                        },
                    ),
                ),
            )

    return proposals


# ---------------------------------------------------------------------------
# DrugBank enrichment
# ---------------------------------------------------------------------------


async def run_drugbank_enrichment(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Query DrugBank for drug-target interactions related to seed terms."""
    if not seed_terms:
        return SourceEnrichmentResult(source_key="drugbank")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0

    gateway = build_drugbank_gateway()
    if gateway is None:
        all_errors.append("DrugBank gateway not available")
    else:
        for term in seed_terms[:_MAX_TERMS_PER_SOURCE]:
            try:
                # DrugBank gateway.fetch_records() uses asyncio.run() internally,
                # which fails inside an already-running event loop (research-init).
                # Run in a thread so it gets its own event loop.
                import asyncio

                result = await asyncio.to_thread(
                    gateway.fetch_records,
                    drug_name=term,
                    max_results=20,
                )
                records_processed += result.fetched_records
                if result.records:
                    text_content = _format_drugbank_results(term, result.records)
                    record = _create_enrichment_document(
                        space_id=space_id,
                        document_store=document_store,
                        run_registry=run_registry,
                        artifact_store=artifact_store,
                        parent_run=parent_run,
                        title=f"DrugBank interactions for {term}",
                        source_type="drugbank",
                        text_content=text_content,
                        metadata={
                            "source": "research-init-drugbank",
                            "query_term": term,
                            "record_count": len(result.records),
                        },
                    )
                    if record is not None:
                        documents.append(record)
            except Exception as exc:  # noqa: BLE001
                msg = f"DrugBank query for {term}: {exc}"
                logger.warning(msg)
                all_errors.append(msg)

    return SourceEnrichmentResult(
        source_key="drugbank",
        documents_created=documents,
        records_processed=records_processed,
        errors=tuple(all_errors),
    )


# ---------------------------------------------------------------------------
# AlphaFold enrichment
# ---------------------------------------------------------------------------

# UniProt accession IDs come in two flavours:
#   Classic (6-char): [OPQ][0-9][A-Z0-9]{3}[0-9]   e.g. Q9UHV7, P04637
#   New    (6-char): [A-NR-Z][0-9][A-Z0-9]{3}[0-9]  e.g. A0A0C5B5G6
# Both may carry an isoform suffix like "-2".
_UNIPROT_ACCESSION_PATTERN = re.compile(
    r"^[A-Z][0-9][A-Z0-9]{3}[0-9](-\d+)?$",
)


async def _resolve_gene_to_uniprot(gene_symbol: str) -> str | None:
    """Resolve a gene symbol to a UniProt accession ID.

    If *gene_symbol* already looks like a UniProt accession it is returned
    as-is.  Otherwise the UniProt gateway is queried for the first match.

    Returns the UniProt accession if found, ``None`` otherwise.
    """
    if _UNIPROT_ACCESSION_PATTERN.match(gene_symbol):
        return gene_symbol  # Already a UniProt ID

    try:
        import asyncio

        gateway = build_uniprot_gateway()
        if gateway is None:
            return None
        result = await asyncio.to_thread(
            gateway.fetch_records,
            query=gene_symbol,
            max_results=1,
        )
        if result.records:
            rec = result.records[0]
            # The parser stores the accession under "uniprot_id"
            # (sourced from primaryAccession).
            accession = (
                rec.get("uniprot_id")
                or rec.get("primaryAccession")
                or rec.get("accession")
                or rec.get("id")
            )
            if accession and isinstance(accession, str):
                return accession
    except Exception:  # noqa: BLE001, S110
        pass
    return None


async def run_alphafold_enrichment(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Query AlphaFold for protein structure predictions by UniProt ID or gene symbol."""
    # AlphaFold expects UniProt accession IDs. Gene symbols can sometimes work
    # as search queries but the primary key is UniProt ID.  Accept both.
    candidates = [t for t in seed_terms if t and t.strip()]
    if not candidates:
        return SourceEnrichmentResult(source_key="alphafold")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0
    # Collect (term, uniprot_id, records) for proposal creation
    alphafold_record_groups: list[tuple[str, str, list[dict[str, object]]]] = []

    gateway = build_alphafold_gateway()
    if gateway is None:
        all_errors.append("AlphaFold gateway not available")
    else:
        for term in candidates[:_MAX_TERMS_PER_SOURCE]:
            try:
                # Resolve gene symbols to UniProt accession IDs –
                # AlphaFold API requires UniProt IDs, not gene symbols.
                uniprot_id = await _resolve_gene_to_uniprot(term)
                if uniprot_id is None:
                    logger.info(
                        "AlphaFold: no UniProt mapping for %s, skipping",
                        term,
                    )
                    continue

                # AlphaFold gateway.fetch_records() uses asyncio.run() internally,
                # which fails inside an already-running event loop (research-init).
                # Run in a thread so it gets its own event loop.
                import asyncio

                result = await asyncio.to_thread(
                    gateway.fetch_records,
                    uniprot_id=uniprot_id,
                    max_results=10,
                )
                records_processed += result.fetched_records
                if result.records:
                    alphafold_record_groups.append((term, uniprot_id, result.records))
                    text_content = _format_alphafold_results(term, result.records)
                    record = _create_enrichment_document(
                        space_id=space_id,
                        document_store=document_store,
                        run_registry=run_registry,
                        artifact_store=artifact_store,
                        parent_run=parent_run,
                        title=f"AlphaFold predictions for {term}",
                        source_type="alphafold",
                        text_content=text_content,
                        metadata={
                            "source": "research-init-alphafold",
                            "query_term": term,
                            "resolved_uniprot_id": uniprot_id,
                            "prediction_count": len(result.records),
                        },
                    )
                    if record is not None:
                        documents.append(record)
            except Exception as exc:  # noqa: BLE001
                msg = f"AlphaFold query for {term}: {exc}"
                logger.warning(msg)
                all_errors.append(msg)

    # Create proposals directly from structured records
    all_proposals: list[HarnessProposalDraft] = []
    for term, uniprot_id, af_records in alphafold_record_groups:
        all_proposals.extend(
            _create_alphafold_proposals(term, uniprot_id, af_records),
        )

    return SourceEnrichmentResult(
        source_key="alphafold",
        documents_created=documents,
        proposals_created=all_proposals,
        records_processed=records_processed,
        errors=tuple(all_errors),
    )


def _create_alphafold_proposals(
    query_term: str,
    uniprot_id: str,
    records: list[dict[str, object]],
) -> list[HarnessProposalDraft]:
    """Create unreviewed bootstrap drafts from AlphaFold structure predictions.

    Returns ``PART_OF`` proposal drafts for domains identified by AlphaFold.
    Research-init applies qualitative review before these drafts are persisted.
    """
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    proposals: list[HarnessProposalDraft] = []
    for rec in records:
        protein_name = rec.get("protein_name") or rec.get("name") or query_term
        domains = rec.get("domains") or []

        # Create PART_OF proposals for each domain
        if isinstance(domains, list):
            for domain in domains:
                if isinstance(domain, dict):
                    domain_name = domain.get("name") or domain.get("domain_name") or ""
                    if not domain_name:
                        continue
                    start = domain.get("start", "?")
                    end = domain.get("end", "?")

                    proposals.append(
                        HarnessProposalDraft(
                            proposal_type="candidate_claim",
                            source_kind="alphafold_enrichment",
                            source_key=f"alphafold:{uniprot_id}:{domain_name}",
                            title=f"AlphaFold: {domain_name} PART_OF {protein_name}",
                            summary=(
                                f"AlphaFold structure prediction shows {domain_name} "
                                f"domain (residues {start}-{end}) is part of "
                                f"{protein_name} ({uniprot_id})."
                            ),
                            confidence=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
                            ranking_score=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
                            reasoning_path={
                                "source": "alphafold",
                                "uniprot_id": uniprot_id,
                            },
                            evidence_bundle=[
                                {
                                    "source_type": "structural_prediction",
                                    "locator": f"alphafold:{uniprot_id}",
                                    "excerpt": (
                                        f"AlphaFold predicts {domain_name} domain "
                                        f"at positions {start}-{end} in {protein_name}."
                                    ),
                                    "relevance": 0.9,
                                },
                            ],
                            payload={
                                "proposed_subject_label": str(domain_name),
                                "proposed_claim_type": "PART_OF",
                                "proposed_object_label": str(protein_name),
                                "uniprot_id": uniprot_id,
                            },
                            metadata=_bootstrap_proposal_metadata(
                                source="alphafold_enrichment",
                                extra={"uniprot_id": uniprot_id},
                            ),
                        ),
                    )

    return proposals


# ---------------------------------------------------------------------------
# MARRVEL enrichment
# ---------------------------------------------------------------------------


async def run_marrvel_enrichment(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Query MARRVEL for gene-centric data from seed terms."""
    gene_symbols = _extract_likely_gene_symbols(seed_terms)
    if not gene_symbols:
        return SourceEnrichmentResult(source_key="marrvel")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0

    service = build_marrvel_discovery_service()
    if service is None:
        all_errors.append("MARRVEL discovery service not available")
    else:
        for gene_symbol in gene_symbols[:_MAX_TERMS_PER_SOURCE]:
            try:
                result = await service.search(
                    gene_symbol=gene_symbol,
                    owner_id=_SYSTEM_OWNER_ID,
                    space_id=space_id,
                )
                if result.gene_found and result.panels:
                    records_processed += sum(result.panel_counts.values())
                    text_content = _format_marrvel_results(
                        gene_symbol,
                        result.panels,
                    )
                    record = _create_enrichment_document(
                        space_id=space_id,
                        document_store=document_store,
                        run_registry=run_registry,
                        artifact_store=artifact_store,
                        parent_run=parent_run,
                        title=f"MARRVEL gene data for {gene_symbol}",
                        source_type="marrvel",
                        text_content=text_content,
                        metadata={
                            "source": "research-init-marrvel",
                            "gene_symbol": gene_symbol,
                            "panel_count": len(result.panels),
                            "omim_count": result.omim_count,
                            "variant_count": result.variant_count,
                        },
                    )
                    if record is not None:
                        documents.append(record)
            except Exception as exc:  # noqa: BLE001
                msg = f"MARRVEL query for {gene_symbol}: {exc}"
                logger.warning(msg)
                all_errors.append(msg)
        service.close()

    return SourceEnrichmentResult(
        source_key="marrvel",
        documents_created=documents,
        records_processed=records_processed,
        errors=tuple(all_errors),
    )


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
    """Create a harness document for enrichment results, skipping duplicates.

    Returns ``None`` when the content hash already exists in the space.
    """
    content_bytes = text_content.encode("utf-8")
    sha256 = hashlib.sha256(content_bytes).hexdigest()

    existing = document_store.find_document_by_sha256(
        space_id=space_id,
        sha256=sha256,
    )
    if existing is not None:
        logger.debug(
            "Skipping duplicate enrichment document (sha256=%s, source=%s)",
            sha256[:12],
            source_type,
        )
        return None

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


# ---------------------------------------------------------------------------
# Helpers — formatting structured records as text
# ---------------------------------------------------------------------------


def _format_clinvar_results(
    gene_symbol: str,
    records: list[dict[str, object]],
) -> str:
    """Format ClinVar variant records into readable text for LLM extraction."""
    lines: list[str] = [
        f"ClinVar Variant Summary for {gene_symbol}",
        f"{'=' * 50}",
        f"Total variants retrieved: {len(records)}",
        "",
    ]
    for idx, rec in enumerate(records, 1):
        parsed = json_object_or_empty(rec.get("parsed_data"))
        hgvs_raw = parsed.get("hgvs_notations")
        hgvs_notations = (
            [item for item in hgvs_raw if isinstance(item, str)]
            if isinstance(hgvs_raw, list)
            else []
        )
        variant_name = (
            (hgvs_notations[0] if hgvs_notations else None)
            or rec.get("title")
            or rec.get("name")
            or rec.get("clinvar_id")
            or f"Variant {idx}"
        )
        clin_sig = (
            parsed.get("clinical_significance")
            or rec.get("clinical_significance")
            or rec.get("clinicalSignificance")
            or "not provided"
        )
        conditions = (
            parsed.get("conditions")
            or rec.get("conditions")
            or rec.get("condition_names")
            or "not specified"
        )
        review_status = (
            parsed.get("review_status")
            or rec.get("review_status")
            or rec.get("reviewStatus")
            or "unknown"
        )
        variation_type = (
            parsed.get("variant_type")
            or rec.get("variation_type")
            or rec.get("variationType")
            or "unknown"
        )

        # Normalize list-typed fields to comma-separated strings.
        if isinstance(conditions, list):
            conditions = ", ".join(str(c) for c in conditions)
        if isinstance(clin_sig, list):
            clin_sig = ", ".join(str(s) for s in clin_sig)

        lines.extend(
            [
                f"--- Variant {idx} ---",
                f"Name: {variant_name}",
                f"Type: {variation_type}",
                f"Clinical Significance: {clin_sig}",
                f"Associated Conditions: {conditions}",
                f"Review Status: {review_status}",
                "",
            ],
        )
    return "\n".join(lines)


def _format_drugbank_results(
    query: str,
    records: list[dict[str, object]],
) -> str:
    """Format DrugBank records into readable text for LLM extraction."""
    lines: list[str] = [
        f"DrugBank Interaction Summary for '{query}'",
        f"{'=' * 50}",
        f"Total records retrieved: {len(records)}",
        "",
    ]
    for idx, rec in enumerate(records, 1):
        drug_name = rec.get("name") or rec.get("drug_name") or f"Drug {idx}"
        drugbank_id = rec.get("drugbank_id") or rec.get("drugbank-id") or "N/A"
        targets = rec.get("targets") or rec.get("target_names") or "not specified"
        mechanism = (
            rec.get("mechanism_of_action") or rec.get("mechanism") or "not described"
        )
        interactions = (
            rec.get("drug_interactions") or rec.get("interactions") or "none listed"
        )
        categories = (
            rec.get("categories") or rec.get("drug_categories") or "not categorized"
        )

        if isinstance(targets, list):
            targets = ", ".join(str(t) for t in targets)
        if isinstance(interactions, list):
            interactions = ", ".join(str(i) for i in interactions)
        if isinstance(categories, list):
            categories = ", ".join(str(c) for c in categories)

        lines.extend(
            [
                f"--- Drug {idx} ---",
                f"Name: {drug_name}",
                f"DrugBank ID: {drugbank_id}",
                f"Targets: {targets}",
                f"Mechanism of Action: {mechanism}",
                f"Drug Interactions: {interactions}",
                f"Categories: {categories}",
                "",
            ],
        )
    return "\n".join(lines)


def _format_alphafold_results(
    query: str,
    records: list[dict[str, object]],
) -> str:
    """Format AlphaFold prediction records into readable text for LLM extraction."""
    lines: list[str] = [
        f"AlphaFold Structure Predictions for '{query}'",
        f"{'=' * 50}",
        f"Total predictions retrieved: {len(records)}",
        "",
    ]
    for idx, rec in enumerate(records, 1):
        protein_name = rec.get("protein_name") or rec.get("name") or f"Prediction {idx}"
        uniprot_id = rec.get("uniprot_id") or rec.get("uniprotAccession") or "N/A"
        organism = rec.get("organism") or rec.get("organismScientificName") or "unknown"
        gene_name = rec.get("gene_name") or rec.get("gene") or "N/A"
        confidence = (
            rec.get("predicted_structure_confidence")
            or rec.get("confidence_avg")
            or "N/A"
        )
        model_url = rec.get("model_url") or rec.get("cifUrl") or "not available"
        pdb_url = rec.get("pdb_url") or rec.get("pdbUrl") or "not available"
        domains = rec.get("domains") or []

        if isinstance(confidence, float):
            confidence = f"{confidence:.2f}"

        domain_text = "none listed"
        if isinstance(domains, list) and domains:
            domain_parts: list[str] = []
            for d in domains:
                if isinstance(d, dict):
                    d_name = d.get("name") or d.get("domain_name") or "unnamed"
                    d_start = d.get("start") or "?"
                    d_end = d.get("end") or "?"
                    domain_parts.append(f"{d_name} ({d_start}-{d_end})")
                else:
                    domain_parts.append(str(d))
            domain_text = "; ".join(domain_parts)

        lines.extend(
            [
                f"--- Prediction {idx} ---",
                f"Protein: {protein_name}",
                f"UniProt ID: {uniprot_id}",
                f"Gene: {gene_name}",
                f"Organism: {organism}",
                f"Confidence Score (avg pLDDT): {confidence}",
                f"Model URL: {model_url}",
                f"PDB URL: {pdb_url}",
                f"Domains: {domain_text}",
                "",
            ],
        )
    return "\n".join(lines)


def _format_marrvel_results(  # noqa: PLR0912, PLR0915
    gene_symbol: str,
    panels: Mapping[str, object],
) -> str:
    """Format MARRVEL panel data into readable text for LLM extraction."""
    lines: list[str] = [
        f"MARRVEL Gene Data Summary for {gene_symbol}",
        f"{'=' * 50}",
        f"Panels retrieved: {len(panels)}",
        "",
    ]

    # OMIM phenotypes
    omim_data = panels.get("omim")
    if omim_data is not None:
        lines.append("── OMIM Phenotypes ──")
        if isinstance(omim_data, dict):
            phenotypes = omim_data.get("phenotypes", [])
            if isinstance(phenotypes, list):
                for pheno in phenotypes:
                    if isinstance(pheno, dict):
                        name = pheno.get("phenotype", "unknown")
                        mim = pheno.get("mim_number", "N/A")
                        lines.append(f"  - {name} (MIM: {mim})")
            if not phenotypes:
                lines.append("  No phenotypes listed")
        elif isinstance(omim_data, list):
            for entry in omim_data:
                if isinstance(entry, dict):
                    phenotypes = entry.get("phenotypes", [])
                    if isinstance(phenotypes, list):
                        for pheno in phenotypes:
                            if isinstance(pheno, dict):
                                name = pheno.get("phenotype", "unknown")
                                mim = pheno.get("mim_number", "N/A")
                                lines.append(f"  - {name} (MIM: {mim})")
        lines.append("")

    # ClinVar variants
    clinvar_data = panels.get("clinvar")
    if clinvar_data is not None:
        lines.append("── ClinVar Variants ──")
        if isinstance(clinvar_data, list):
            lines.append(f"  Variant count: {len(clinvar_data)}")
            for variant in clinvar_data[:10]:
                if isinstance(variant, dict):
                    name = variant.get("title") or variant.get("name", "unnamed")
                    sig = variant.get("clinical_significance", "not provided")
                    lines.append(f"  - {name}: {sig}")
        elif isinstance(clinvar_data, dict):
            lines.append(f"  Data: {_summarize_panel_value(clinvar_data)}")
        lines.append("")

    # gnomAD frequencies
    gnomad_data = panels.get("gnomad")
    if gnomad_data is not None:
        lines.append("── gnomAD Gene Constraint ──")
        if isinstance(gnomad_data, dict):
            pli = gnomad_data.get("pLI", gnomad_data.get("pli", "N/A"))
            loeuf = gnomad_data.get("oe_lof_upper", gnomad_data.get("LOEUF", "N/A"))
            mis_z = gnomad_data.get("mis_z", gnomad_data.get("missense_z", "N/A"))
            lines.append(f"  pLI: {pli}")
            lines.append(f"  LOEUF: {loeuf}")
            lines.append(f"  Missense Z-score: {mis_z}")
        else:
            lines.append(f"  Data: {_summarize_panel_value(gnomad_data)}")
        lines.append("")

    # GTEx expression
    gtex_data = panels.get("gtex")
    if gtex_data is not None:
        lines.append("── GTEx Expression ──")
        if isinstance(gtex_data, list):
            lines.append(f"  Tissue count: {len(gtex_data)}")
            for tissue in gtex_data[:5]:
                if isinstance(tissue, dict):
                    tissue_name = tissue.get(
                        "tissue",
                        tissue.get("tissueSiteDetail", "unknown"),
                    )
                    tpm = tissue.get("median_tpm", tissue.get("median", "N/A"))
                    lines.append(f"  - {tissue_name}: {tpm} TPM")
        elif isinstance(gtex_data, dict):
            lines.append(f"  Data: {_summarize_panel_value(gtex_data)}")
        lines.append("")

    # DIOPT orthologs
    orthologs_data = panels.get("diopt_orthologs")
    if orthologs_data is not None:
        lines.append("── Orthologs (DIOPT) ──")
        if isinstance(orthologs_data, list):
            lines.append(f"  Ortholog count: {len(orthologs_data)}")
            for orth in orthologs_data[:5]:
                if isinstance(orth, dict):
                    species = orth.get("species", orth.get("organism", "unknown"))
                    symbol = orth.get("symbol", orth.get("gene_symbol", "N/A"))
                    score = orth.get("score", orth.get("diopt_score", "N/A"))
                    lines.append(f"  - {species}: {symbol} (score: {score})")
        elif isinstance(orthologs_data, dict):
            lines.append(f"  Data: {_summarize_panel_value(orthologs_data)}")
        lines.append("")

    # dbNSFP functional predictions
    dbnsfp_data = panels.get("dbnsfp")
    if dbnsfp_data is not None:
        lines.append("── dbNSFP Functional Predictions ──")
        if isinstance(dbnsfp_data, dict):
            sift = dbnsfp_data.get("sift_score", dbnsfp_data.get("SIFT_score", "N/A"))
            polyphen = dbnsfp_data.get(
                "polyphen2_score",
                dbnsfp_data.get("Polyphen2_HDIV_score", "N/A"),
            )
            cadd = dbnsfp_data.get("cadd_phred", dbnsfp_data.get("CADD_phred", "N/A"))
            lines.append(f"  SIFT: {sift}")
            lines.append(f"  PolyPhen-2: {polyphen}")
            lines.append(f"  CADD: {cadd}")
        else:
            lines.append(f"  Data: {_summarize_panel_value(dbnsfp_data)}")
        lines.append("")

    # Pharos targets
    pharos_data = panels.get("pharos")
    if pharos_data is not None:
        lines.append("── Pharos Target Classification ──")
        if isinstance(pharos_data, dict):
            tdl = pharos_data.get(
                "tdl",
                pharos_data.get("Target Development Level", "N/A"),
            )
            fam = pharos_data.get("fam", pharos_data.get("family", "N/A"))
            lines.append(f"  Development Level: {tdl}")
            lines.append(f"  Family: {fam}")
        elif isinstance(pharos_data, list):
            for target in pharos_data[:3]:
                if isinstance(target, dict):
                    tdl = target.get("tdl", "N/A")
                    name = target.get("name", "unnamed")
                    lines.append(f"  - {name}: {tdl}")
        lines.append("")

    # Any remaining panels not explicitly handled above
    handled_panels = {
        "omim",
        "clinvar",
        "gnomad",
        "gtex",
        "diopt_orthologs",
        "dbnsfp",
        "pharos",
    }
    for panel_name, panel_value in panels.items():
        if panel_name not in handled_panels and panel_value is not None:
            lines.append(f"── {panel_name} ──")
            lines.append(f"  {_summarize_panel_value(panel_value)}")
            lines.append("")

    return "\n".join(lines)


def _summarize_panel_value(value: object) -> str:
    """Return a short text summary of a panel value."""
    if isinstance(value, list):
        return f"{len(value)} records"
    if isinstance(value, dict):
        return f"{len(value)} fields"
    return str(value)[:200]


# ---------------------------------------------------------------------------
# ClinicalTrials.gov enrichment
# ---------------------------------------------------------------------------


async def run_clinicaltrials_enrichment(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Query ClinicalTrials.gov for registered trials matching seed terms.

    Pulls up to ``_MAX_TERMS_PER_SOURCE`` of the most relevant seed terms
    (preferring gene symbols when present, falling back to free-text terms),
    runs the v2 REST API search for each, and creates one enrichment
    document per term that returned results.  Each registered trial yields
    a proposal with proposed relations like
    ``DRUG → TREATS → DISEASE`` (when the intervention is a drug) or
    ``CLINICAL_TRIAL → TARGETS → DISEASE`` (otherwise).
    """
    # Prefer gene symbols (most actionable for biomedical research init);
    # fall back to free-text seed terms when no gene-shaped tokens are
    # present.  This keeps the search relevant without losing the
    # disease/condition queries the user typed in directly.
    candidate_terms: list[str] = _extract_likely_gene_symbols(seed_terms)
    if not candidate_terms:
        candidate_terms = [t for t in seed_terms if t and t.strip()]
    if not candidate_terms:
        return SourceEnrichmentResult(source_key="clinical_trials")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0
    records_by_term: dict[str, list[dict[str, object]]] = {}

    gateway = build_clinicaltrials_gateway()
    if gateway is None:
        all_errors.append("ClinicalTrials.gov gateway not available")
    else:
        for term in candidate_terms[:_MAX_TERMS_PER_SOURCE]:
            try:
                fetch_result = await gateway.fetch_records_async(
                    query=term,
                    max_results=10,
                )
                raw_records = list(fetch_result.records)
                records_processed += len(raw_records)
                if raw_records:
                    records_by_term[term] = raw_records
                    text_content = _format_clinicaltrials_results(term, raw_records)
                    record = _create_enrichment_document(
                        space_id=space_id,
                        document_store=document_store,
                        run_registry=run_registry,
                        artifact_store=artifact_store,
                        parent_run=parent_run,
                        title=f"ClinicalTrials.gov trials for {term}",
                        source_type="clinical_trials",
                        text_content=text_content,
                        metadata={
                            "source": "research-init-clinical-trials",
                            "query_term": term,
                            "trial_count": len(raw_records),
                        },
                    )
                    if record is not None:
                        documents.append(record)
            except Exception as exc:  # noqa: BLE001
                msg = f"ClinicalTrials.gov query for {term}: {exc}"
                logger.warning(msg)
                all_errors.append(msg)

    proposals = _create_clinicaltrials_proposals(records_by_term)

    return SourceEnrichmentResult(
        source_key="clinical_trials",
        documents_created=documents,
        proposals_created=proposals,
        records_processed=records_processed,
        errors=tuple(all_errors),
    )


def _format_clinicaltrials_results(
    term: str,
    records: list[dict[str, object]],
) -> str:
    """Render a short markdown summary of clinical trial records."""
    if not records:
        return f"No ClinicalTrials.gov trials returned for query '{term}'."
    lines = [f"# ClinicalTrials.gov trials matching '{term}'\n"]
    for rec in records:
        nct_id = rec.get("nct_id", "(no NCT ID)")
        title = rec.get("brief_title") or rec.get("official_title") or "(untitled)"
        status = rec.get("overall_status") or "unknown status"
        phases_raw = rec.get("phases") or []
        phases = (
            ", ".join(str(p) for p in phases_raw)
            if isinstance(phases_raw, list)
            else ""
        )
        conditions_raw = rec.get("conditions") or []
        conditions = (
            ", ".join(str(c) for c in conditions_raw)
            if isinstance(conditions_raw, list)
            else ""
        )
        lines.append(f"- **{nct_id}** — {title}")
        if conditions:
            lines.append(f"  - Conditions: {conditions}")
        if phases:
            lines.append(f"  - Phases: {phases}")
        lines.append(f"  - Status: {status}")
    return "\n".join(lines)


def _normalize_clinicaltrials_conditions(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(c).strip() for c in raw if isinstance(c, str) and c.strip()]


def _normalize_clinicaltrials_drugs(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    drugs: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        intervention_type = str(entry.get("type") or "").upper()
        if intervention_type == "DRUG" and isinstance(name, str) and name.strip():
            drugs.append(name.strip())
    return drugs


def _build_drug_treats_proposal(
    *,
    nct_id: str,
    title: str,
    drug_name: str,
    condition: str,
    term: str,
) -> HarnessProposalDraft:
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="clinicaltrials_enrichment",
        source_key=f"clinicaltrials:{nct_id}:{drug_name}:{condition}",
        title=f"ClinicalTrials.gov: {drug_name} TREATS {condition}",
        summary=(
            f"Trial {nct_id} ({title}) registered as testing "
            f"{drug_name} for {condition}."
        ),
        confidence=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        ranking_score=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        reasoning_path={
            "source": "clinicaltrials",
            "nct_id": nct_id,
            "query_term": term,
        },
        evidence_bundle=[
            {
                "source_type": "structured_database",
                "locator": f"clinicaltrials:{nct_id}",
                "excerpt": (
                    f"Trial {nct_id}: {title}.  Drug: {drug_name}. "
                    f"Condition: {condition}."
                ),
                "relevance": 0.9,
            },
        ],
        payload={
            "proposed_subject_label": drug_name,
            "proposed_claim_type": "TREATS",
            "proposed_object_label": condition,
            "nct_id": nct_id,
        },
        metadata=_bootstrap_proposal_metadata(
            source="clinicaltrials_enrichment",
            extra={"nct_id": nct_id, "query_term": term},
        ),
    )


def _build_trial_targets_proposal(
    *,
    nct_id: str,
    title: str,
    condition: str,
    term: str,
) -> HarnessProposalDraft:
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="clinicaltrials_enrichment",
        source_key=f"clinicaltrials:{nct_id}:{condition}",
        title=f"ClinicalTrials.gov: trial {nct_id} TARGETS {condition}",
        summary=(
            f"Trial {nct_id} ({title}) registered for investigation of {condition}."
        ),
        confidence=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        ranking_score=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        reasoning_path={
            "source": "clinicaltrials",
            "nct_id": nct_id,
            "query_term": term,
        },
        evidence_bundle=[
            {
                "source_type": "structured_database",
                "locator": f"clinicaltrials:{nct_id}",
                "excerpt": (f"Trial {nct_id}: {title}.  Condition: {condition}."),
                "relevance": 0.85,
            },
        ],
        payload={
            "proposed_subject_label": f"Trial {nct_id}",
            "proposed_claim_type": "TARGETS",
            "proposed_object_label": condition,
            "nct_id": nct_id,
        },
        metadata=_bootstrap_proposal_metadata(
            source="clinicaltrials_enrichment",
            extra={"nct_id": nct_id, "query_term": term},
        ),
    )


def _proposals_for_clinicaltrials_record(
    *,
    rec: dict[str, object],
    term: str,
) -> list[HarnessProposalDraft]:
    """Build the proposals derived from one trial record."""
    nct_id = str(rec.get("nct_id") or "")
    if not nct_id:
        return []
    title = str(
        rec.get("brief_title") or rec.get("official_title") or f"Trial {nct_id}",
    )
    conditions = _normalize_clinicaltrials_conditions(rec.get("conditions"))
    drug_interventions = _normalize_clinicaltrials_drugs(rec.get("interventions"))

    proposals: list[HarnessProposalDraft] = []
    if drug_interventions:
        condition_targets = conditions or ["unspecified condition"]
        proposals.extend(
            _build_drug_treats_proposal(
                nct_id=nct_id,
                title=title,
                drug_name=drug_name,
                condition=condition,
                term=term,
            )
            for drug_name in drug_interventions
            for condition in condition_targets
        )
    elif conditions:
        proposals.extend(
            _build_trial_targets_proposal(
                nct_id=nct_id,
                title=title,
                condition=condition,
                term=term,
            )
            for condition in conditions
        )
    return proposals


def _create_clinicaltrials_proposals(
    records_by_term: dict[str, list[dict[str, object]]],
) -> list[HarnessProposalDraft]:
    """Create unreviewed bootstrap drafts from clinical trial records.

    Heuristic: if any of the trial's interventions has type "DRUG", emit a
    ``DRUG → TREATS → DISEASE`` draft for each (drug, condition) pair.
    Otherwise emit a ``CLINICAL_TRIAL → TARGETS → DISEASE`` draft so the
    trial still becomes a graph entity downstream.
    """
    proposals: list[HarnessProposalDraft] = []
    for term, records in records_by_term.items():
        for rec in records:
            proposals.extend(_proposals_for_clinicaltrials_record(rec=rec, term=term))
    return proposals


# ---------------------------------------------------------------------------
# MGI (Mouse Genome Informatics) enrichment
# ---------------------------------------------------------------------------


async def run_mgi_enrichment(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Query MGI (via the Alliance API) for mouse gene records matching seed terms.

    Pulls up to ``_MAX_TERMS_PER_SOURCE`` likely gene symbols, runs the
    Alliance ``/search`` query for each (filtered to ``Mus musculus``), and
    creates one enrichment document per gene that returned results.  Each
    mouse gene yields proposals like ``GENE → ASSOCIATED_WITH → PHENOTYPE``
    for each mouse phenotype annotation, plus ``GENE → CAUSES → DISEASE`` for
    disease associations from the Alliance disease annotations.
    """
    candidate_terms: list[str] = _extract_likely_gene_symbols(seed_terms)
    if not candidate_terms:
        return SourceEnrichmentResult(source_key="mgi")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0
    records_by_term: dict[str, list[dict[str, object]]] = {}

    gateway = build_mgi_gateway()
    if gateway is None:
        all_errors.append("MGI gateway not available")
    else:
        for term in candidate_terms[:_MAX_TERMS_PER_SOURCE]:
            try:
                fetch_result = await gateway.fetch_records_async(
                    query=term,
                    max_results=10,
                )
                raw_records = list(fetch_result.records)
                records_processed += len(raw_records)
                if raw_records:
                    records_by_term[term] = raw_records
                    text_content = _format_mgi_results(term, raw_records)
                    record = _create_enrichment_document(
                        space_id=space_id,
                        document_store=document_store,
                        run_registry=run_registry,
                        artifact_store=artifact_store,
                        parent_run=parent_run,
                        title=f"MGI mouse gene records for {term}",
                        source_type="mgi",
                        text_content=text_content,
                        metadata={
                            "source": "research-init-mgi",
                            "query_term": term,
                            "gene_count": len(raw_records),
                        },
                    )
                    if record is not None:
                        documents.append(record)
            except Exception as exc:  # noqa: BLE001
                msg = f"MGI query for {term}: {exc}"
                logger.warning(msg)
                all_errors.append(msg)

    proposals = _create_mgi_proposals(records_by_term)

    return SourceEnrichmentResult(
        source_key="mgi",
        documents_created=documents,
        proposals_created=proposals,
        records_processed=records_processed,
        errors=tuple(all_errors),
    )


def _format_mgi_results(
    term: str,
    records: list[dict[str, object]],
) -> str:
    """Render a short markdown summary of MGI mouse gene records."""
    if not records:
        return f"No MGI mouse gene records returned for query '{term}'."
    lines = [f"# MGI mouse gene records matching '{term}'\n"]
    for rec in records:
        mgi_id = rec.get("mgi_id", "(no MGI ID)")
        symbol = rec.get("gene_symbol") or "(no symbol)"
        name = rec.get("gene_name") or "(no name)"
        lines.append(f"- **{symbol}** ({mgi_id}) — {name}")
        phenotypes_raw = rec.get("phenotype_statements") or []
        if isinstance(phenotypes_raw, list) and phenotypes_raw:
            phenotype_summary = ", ".join(str(p) for p in phenotypes_raw[:5])
            lines.append(f"  - Mouse phenotypes: {phenotype_summary}")
        diseases_raw = rec.get("disease_associations") or []
        if isinstance(diseases_raw, list) and diseases_raw:
            disease_names = [
                str(d.get("name") if isinstance(d, dict) else d)
                for d in diseases_raw[:5]
            ]
            lines.append(f"  - Disease associations: {', '.join(disease_names)}")
    return "\n".join(lines)


def _build_gene_phenotype_proposal(
    *,
    mgi_id: str,
    gene_symbol: str,
    phenotype: str,
    term: str,
) -> HarnessProposalDraft:
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="mgi_enrichment",
        source_key=f"mgi:{mgi_id}:phenotype:{phenotype}",
        title=f"MGI: {gene_symbol} ASSOCIATED_WITH {phenotype}",
        summary=(
            f"Mouse gene {gene_symbol} ({mgi_id}) is annotated in MGI with the "
            f"phenotype '{phenotype}'."
        ),
        confidence=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        ranking_score=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        reasoning_path={
            "source": "mgi",
            "mgi_id": mgi_id,
            "query_term": term,
        },
        evidence_bundle=[
            {
                "source_type": "structured_database",
                "locator": f"mgi:{mgi_id}",
                "excerpt": (
                    f"MGI mouse gene {gene_symbol} ({mgi_id}) is annotated with "
                    f"the mouse phenotype '{phenotype}'."
                ),
                "relevance": 0.9,
            },
        ],
        payload={
            "proposed_subject_label": gene_symbol,
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_object_label": phenotype,
            "mgi_id": mgi_id,
        },
        metadata=_bootstrap_proposal_metadata(
            source="mgi_enrichment",
            extra={"mgi_id": mgi_id, "query_term": term},
        ),
    )


def _build_gene_disease_proposal(
    *,
    mgi_id: str,
    gene_symbol: str,
    disease_name: str,
    do_id: str | None,
    term: str,
) -> HarnessProposalDraft:
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    locator = f"mgi:{mgi_id}:disease:{disease_name}"
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="mgi_enrichment",
        source_key=locator,
        title=f"MGI: {gene_symbol} CAUSES {disease_name}",
        summary=(
            f"Mouse gene {gene_symbol} ({mgi_id}) is annotated in MGI as "
            f"associated with disease '{disease_name}'."
        ),
        confidence=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        ranking_score=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        reasoning_path={
            "source": "mgi",
            "mgi_id": mgi_id,
            "do_id": do_id,
            "query_term": term,
        },
        evidence_bundle=[
            {
                "source_type": "structured_database",
                "locator": f"mgi:{mgi_id}",
                "excerpt": (
                    f"MGI mouse gene {gene_symbol} ({mgi_id}) is annotated with "
                    f"a disease association: {disease_name}."
                ),
                "relevance": 0.85,
            },
        ],
        payload={
            "proposed_subject_label": gene_symbol,
            "proposed_claim_type": "CAUSES",
            "proposed_object_label": disease_name,
            "mgi_id": mgi_id,
            "do_id": do_id,
        },
        metadata=_bootstrap_proposal_metadata(
            source="mgi_enrichment",
            extra={"mgi_id": mgi_id, "do_id": do_id, "query_term": term},
        ),
    )


def _proposals_for_mgi_record(
    *,
    rec: dict[str, object],
    term: str,
) -> list[HarnessProposalDraft]:
    """Build proposals derived from one MGI mouse gene record."""
    mgi_id = str(rec.get("mgi_id") or "")
    gene_symbol = str(rec.get("gene_symbol") or "")
    if not mgi_id or not gene_symbol:
        return []

    proposals: list[HarnessProposalDraft] = []

    phenotypes_raw = rec.get("phenotype_statements") or []
    if isinstance(phenotypes_raw, list):
        proposals.extend(
            _build_gene_phenotype_proposal(
                mgi_id=mgi_id,
                gene_symbol=gene_symbol,
                phenotype=str(phenotype).strip(),
                term=term,
            )
            for phenotype in phenotypes_raw
            if isinstance(phenotype, str) and phenotype.strip()
        )

    diseases_raw = rec.get("disease_associations") or []
    if isinstance(diseases_raw, list):
        for disease in diseases_raw:
            if not isinstance(disease, dict):
                continue
            name = disease.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            do_id_value = disease.get("do_id")
            do_id = (
                do_id_value.strip()
                if isinstance(do_id_value, str) and do_id_value.strip()
                else None
            )
            proposals.append(
                _build_gene_disease_proposal(
                    mgi_id=mgi_id,
                    gene_symbol=gene_symbol,
                    disease_name=name.strip(),
                    do_id=do_id,
                    term=term,
                ),
            )

    return proposals


def _create_mgi_proposals(
    records_by_term: dict[str, list[dict[str, object]]],
) -> list[HarnessProposalDraft]:
    """Create unreviewed bootstrap drafts from MGI mouse gene records."""
    proposals: list[HarnessProposalDraft] = []
    for term, records in records_by_term.items():
        for rec in records:
            proposals.extend(_proposals_for_mgi_record(rec=rec, term=term))
    return proposals


# ---------------------------------------------------------------------------
# ZFIN (Zebrafish Information Network) enrichment
# ---------------------------------------------------------------------------


async def run_zfin_enrichment(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Query ZFIN (via the Alliance API) for zebrafish gene records.

    Pulls up to ``_MAX_TERMS_PER_SOURCE`` likely gene symbols, runs the
    Alliance ``/search`` query for each (filtered to ``Danio rerio``), and
    creates one enrichment document per gene that returned results.  Each
    zebrafish gene yields proposals like ``GENE → ASSOCIATED_WITH →
    PHENOTYPE`` for each zebrafish phenotype annotation, ``GENE →
    EXPRESSED_IN → TISSUE`` for each zebrafish anatomy expression term, and
    ``GENE → CAUSES → DISEASE`` for disease associations.
    """
    candidate_terms: list[str] = _extract_likely_gene_symbols(seed_terms)
    if not candidate_terms:
        return SourceEnrichmentResult(source_key="zfin")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0
    records_by_term: dict[str, list[dict[str, object]]] = {}

    gateway = build_zfin_gateway()
    if gateway is None:
        all_errors.append("ZFIN gateway not available")
    else:
        for term in candidate_terms[:_MAX_TERMS_PER_SOURCE]:
            try:
                fetch_result = await gateway.fetch_records_async(
                    query=term,
                    max_results=10,
                )
                raw_records = list(fetch_result.records)
                records_processed += len(raw_records)
                if raw_records:
                    records_by_term[term] = raw_records
                    text_content = _format_zfin_results(term, raw_records)
                    record = _create_enrichment_document(
                        space_id=space_id,
                        document_store=document_store,
                        run_registry=run_registry,
                        artifact_store=artifact_store,
                        parent_run=parent_run,
                        title=f"ZFIN zebrafish gene records for {term}",
                        source_type="zfin",
                        text_content=text_content,
                        metadata={
                            "source": "research-init-zfin",
                            "query_term": term,
                            "gene_count": len(raw_records),
                        },
                    )
                    if record is not None:
                        documents.append(record)
            except Exception as exc:  # noqa: BLE001
                msg = f"ZFIN query for {term}: {exc}"
                logger.warning(msg)
                all_errors.append(msg)

    proposals = _create_zfin_proposals(records_by_term)

    return SourceEnrichmentResult(
        source_key="zfin",
        documents_created=documents,
        proposals_created=proposals,
        records_processed=records_processed,
        errors=tuple(all_errors),
    )


def _format_zfin_results(
    term: str,
    records: list[dict[str, object]],
) -> str:
    """Render a short markdown summary of ZFIN zebrafish gene records."""
    if not records:
        return f"No ZFIN zebrafish gene records returned for query '{term}'."
    lines = [f"# ZFIN zebrafish gene records matching '{term}'\n"]
    for rec in records:
        zfin_id = rec.get("zfin_id", "(no ZFIN ID)")
        symbol = rec.get("gene_symbol") or "(no symbol)"
        name = rec.get("gene_name") or "(no name)"
        lines.append(f"- **{symbol}** ({zfin_id}) — {name}")
        phenotypes_raw = rec.get("phenotype_statements") or []
        if isinstance(phenotypes_raw, list) and phenotypes_raw:
            phenotype_summary = ", ".join(str(p) for p in phenotypes_raw[:5])
            lines.append(f"  - Zebrafish phenotypes: {phenotype_summary}")
        expression_raw = rec.get("expression_terms") or []
        if isinstance(expression_raw, list) and expression_raw:
            expression_summary = ", ".join(str(e) for e in expression_raw[:5])
            lines.append(f"  - Expression: {expression_summary}")
        diseases_raw = rec.get("disease_associations") or []
        if isinstance(diseases_raw, list) and diseases_raw:
            disease_names = [
                str(d.get("name") if isinstance(d, dict) else d)
                for d in diseases_raw[:5]
            ]
            lines.append(f"  - Disease associations: {', '.join(disease_names)}")
    return "\n".join(lines)


def _build_zfin_phenotype_proposal(
    *,
    zfin_id: str,
    gene_symbol: str,
    phenotype: str,
    term: str,
) -> HarnessProposalDraft:
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="zfin_enrichment",
        source_key=f"zfin:{zfin_id}:phenotype:{phenotype}",
        title=f"ZFIN: {gene_symbol} ASSOCIATED_WITH {phenotype}",
        summary=(
            f"Zebrafish gene {gene_symbol} ({zfin_id}) is annotated in ZFIN with "
            f"the phenotype '{phenotype}'."
        ),
        confidence=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        ranking_score=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        reasoning_path={
            "source": "zfin",
            "zfin_id": zfin_id,
            "query_term": term,
        },
        evidence_bundle=[
            {
                "source_type": "structured_database",
                "locator": f"zfin:{zfin_id}",
                "excerpt": (
                    f"ZFIN zebrafish gene {gene_symbol} ({zfin_id}) is annotated "
                    f"with the zebrafish phenotype '{phenotype}'."
                ),
                "relevance": 0.9,
            },
        ],
        payload={
            "proposed_subject_label": gene_symbol,
            "proposed_claim_type": "ASSOCIATED_WITH",
            "proposed_object_label": phenotype,
            "zfin_id": zfin_id,
        },
        metadata=_bootstrap_proposal_metadata(
            source="zfin_enrichment",
            extra={"zfin_id": zfin_id, "query_term": term},
        ),
    )


def _build_zfin_expression_proposal(
    *,
    zfin_id: str,
    gene_symbol: str,
    tissue: str,
    term: str,
) -> HarnessProposalDraft:
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="zfin_enrichment",
        source_key=f"zfin:{zfin_id}:expression:{tissue}",
        title=f"ZFIN: {gene_symbol} EXPRESSED_IN {tissue}",
        summary=(
            f"Zebrafish gene {gene_symbol} ({zfin_id}) is annotated in ZFIN as "
            f"expressed in '{tissue}'."
        ),
        confidence=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        ranking_score=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        reasoning_path={
            "source": "zfin",
            "zfin_id": zfin_id,
            "query_term": term,
        },
        evidence_bundle=[
            {
                "source_type": "structured_database",
                "locator": f"zfin:{zfin_id}",
                "excerpt": (
                    f"ZFIN zebrafish gene {gene_symbol} ({zfin_id}) is expressed "
                    f"in {tissue}."
                ),
                "relevance": 0.85,
            },
        ],
        payload={
            "proposed_subject_label": gene_symbol,
            "proposed_claim_type": "EXPRESSED_IN",
            "proposed_object_label": tissue,
            "zfin_id": zfin_id,
        },
        metadata=_bootstrap_proposal_metadata(
            source="zfin_enrichment",
            extra={"zfin_id": zfin_id, "query_term": term},
        ),
    )


def _build_zfin_disease_proposal(
    *,
    zfin_id: str,
    gene_symbol: str,
    disease_name: str,
    do_id: str | None,
    term: str,
) -> HarnessProposalDraft:
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    locator = f"zfin:{zfin_id}:disease:{disease_name}"
    return HarnessProposalDraft(
        proposal_type="candidate_claim",
        source_kind="zfin_enrichment",
        source_key=locator,
        title=f"ZFIN: {gene_symbol} CAUSES {disease_name}",
        summary=(
            f"Zebrafish gene {gene_symbol} ({zfin_id}) is annotated in ZFIN as "
            f"associated with disease '{disease_name}'."
        ),
        confidence=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        ranking_score=_UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
        reasoning_path={
            "source": "zfin",
            "zfin_id": zfin_id,
            "do_id": do_id,
            "query_term": term,
        },
        evidence_bundle=[
            {
                "source_type": "structured_database",
                "locator": f"zfin:{zfin_id}",
                "excerpt": (
                    f"ZFIN zebrafish gene {gene_symbol} ({zfin_id}) is annotated "
                    f"with a disease association: {disease_name}."
                ),
                "relevance": 0.85,
            },
        ],
        payload={
            "proposed_subject_label": gene_symbol,
            "proposed_claim_type": "CAUSES",
            "proposed_object_label": disease_name,
            "zfin_id": zfin_id,
            "do_id": do_id,
        },
        metadata=_bootstrap_proposal_metadata(
            source="zfin_enrichment",
            extra={"zfin_id": zfin_id, "do_id": do_id, "query_term": term},
        ),
    )


def _proposals_for_zfin_record(
    *,
    rec: dict[str, object],
    term: str,
) -> list[HarnessProposalDraft]:
    """Build proposals derived from one ZFIN zebrafish gene record."""
    zfin_id = str(rec.get("zfin_id") or "")
    gene_symbol = str(rec.get("gene_symbol") or "")
    if not zfin_id or not gene_symbol:
        return []

    proposals: list[HarnessProposalDraft] = []

    phenotypes_raw = rec.get("phenotype_statements") or []
    if isinstance(phenotypes_raw, list):
        proposals.extend(
            _build_zfin_phenotype_proposal(
                zfin_id=zfin_id,
                gene_symbol=gene_symbol,
                phenotype=str(phenotype).strip(),
                term=term,
            )
            for phenotype in phenotypes_raw
            if isinstance(phenotype, str) and phenotype.strip()
        )

    expression_raw = rec.get("expression_terms") or []
    if isinstance(expression_raw, list):
        proposals.extend(
            _build_zfin_expression_proposal(
                zfin_id=zfin_id,
                gene_symbol=gene_symbol,
                tissue=str(tissue).strip(),
                term=term,
            )
            for tissue in expression_raw
            if isinstance(tissue, str) and tissue.strip()
        )

    diseases_raw = rec.get("disease_associations") or []
    if isinstance(diseases_raw, list):
        for disease in diseases_raw:
            if not isinstance(disease, dict):
                continue
            name = disease.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            do_id_value = disease.get("do_id")
            do_id = (
                do_id_value.strip()
                if isinstance(do_id_value, str) and do_id_value.strip()
                else None
            )
            proposals.append(
                _build_zfin_disease_proposal(
                    zfin_id=zfin_id,
                    gene_symbol=gene_symbol,
                    disease_name=name.strip(),
                    do_id=do_id,
                    term=term,
                ),
            )

    return proposals


def _create_zfin_proposals(
    records_by_term: dict[str, list[dict[str, object]]],
) -> list[HarnessProposalDraft]:
    """Create unreviewed bootstrap drafts from ZFIN zebrafish gene records."""
    proposals: list[HarnessProposalDraft] = []
    for term, records in records_by_term.items():
        for rec in records:
            proposals.extend(_proposals_for_zfin_record(rec=rec, term=term))
    return proposals


__all__ = [
    "SourceEnrichmentResult",
    "run_alphafold_enrichment",
    "run_clinicaltrials_enrichment",
    "run_clinvar_enrichment",
    "run_drugbank_enrichment",
    "run_marrvel_enrichment",
    "run_mgi_enrichment",
    "run_zfin_enrichment",
]
