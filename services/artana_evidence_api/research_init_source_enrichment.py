"""Structured source enrichment for research-init.

Queries ClinVar, DrugBank, AlphaFold, MARRVEL, and UniProt gateways using
seed terms extracted from PubMed discovery, creates harness documents from the
results, and tracks progress in source_results.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.research_init_literature_source_enrichment import (
    run_clinicaltrials_enrichment_impl,
    run_mgi_enrichment_impl,
    run_zfin_enrichment_impl,
)
from artana_evidence_api.research_init_marrvel_enrichment import (
    _format_marrvel_results,
    run_marrvel_enrichment_impl,
)
from artana_evidence_api.research_init_source_enrichment_common import (
    _MAX_TERMS_PER_SOURCE,
    _UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
    SourceEnrichmentResult,
    _bootstrap_proposal_metadata,
    _create_enrichment_document,
    _extract_likely_gene_symbols,
    extract_gene_mentions_from_text,
    logger,
)
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
from artana_evidence_api.types.common import json_object_or_empty

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.proposal_store import HarnessProposalDraft
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry

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
    document_ids_by_gene: dict[str, str] = {}

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
                        records_by_gene[gene_symbol] = raw_records
                        document_ids_by_gene[gene_symbol] = record.id
            except Exception as exc:  # noqa: BLE001
                msg = f"ClinVar query for {gene_symbol}: {exc}"
                logger.warning(msg)
                all_errors.append(msg)

    # Create proposals directly from structured records
    all_proposals = _create_clinvar_proposals(
        records_by_gene,
        document_ids_by_gene=document_ids_by_gene,
    )

    return SourceEnrichmentResult(
        source_key="clinvar",
        documents_created=documents,
        proposals_created=all_proposals,
        records_processed=records_processed,
        errors=tuple(all_errors),
    )


def _create_clinvar_proposals(
    records_by_gene: dict[str, list[dict[str, object]]],
    *,
    document_ids_by_gene: Mapping[str, str],
) -> list[HarnessProposalDraft]:
    """Create unreviewed bootstrap drafts from ClinVar variant records.

    The drafts preserve deterministic source grounding. Research-init applies
    the bootstrap qualitative review boundary before persisting them.
    """
    from artana_evidence_api.proposal_store import HarnessProposalDraft

    proposals: list[HarnessProposalDraft] = []
    for gene_symbol, records in records_by_gene.items():
        document_id = document_ids_by_gene.get(gene_symbol)
        if document_id is None:
            logger.warning(
                "Skipping ClinVar proposals for %s because no source document "
                "was resolved",
                gene_symbol,
            )
            continue
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
                    document_id=document_id,
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
                            "source_document_id": document_id,
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
    # Collect (term, uniprot_id, records, document_id) for proposal creation.
    alphafold_record_groups: list[tuple[str, str, list[dict[str, object]], str]] = []

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
                        alphafold_record_groups.append(
                            (term, uniprot_id, result.records, record.id),
                        )
            except Exception as exc:  # noqa: BLE001
                msg = f"AlphaFold query for {term}: {exc}"
                logger.warning(msg)
                all_errors.append(msg)

    # Create proposals directly from structured records
    all_proposals: list[HarnessProposalDraft] = []
    for term, uniprot_id, af_records, document_id in alphafold_record_groups:
        all_proposals.extend(
            _create_alphafold_proposals(
                term,
                uniprot_id,
                af_records,
                document_id=document_id,
            ),
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
    *,
    document_id: str,
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
                            document_id=document_id,
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
                                extra={
                                    "uniprot_id": uniprot_id,
                                    "source_document_id": document_id,
                                },
                            ),
                        ),
                    )

    return proposals


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
    return await run_marrvel_enrichment_impl(
        space_id=space_id,
        seed_terms=seed_terms,
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        discovery_service_factory=build_marrvel_discovery_service,
    )


async def run_clinicaltrials_enrichment(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Query ClinicalTrials.gov for registered trials matching seed terms."""
    return await run_clinicaltrials_enrichment_impl(
        space_id=space_id,
        seed_terms=seed_terms,
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        gateway_factory=build_clinicaltrials_gateway,
    )


async def run_mgi_enrichment(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Query MGI for mouse model gene-phenotype evidence."""
    return await run_mgi_enrichment_impl(
        space_id=space_id,
        seed_terms=seed_terms,
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        gateway_factory=build_mgi_gateway,
    )


async def run_zfin_enrichment(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
) -> SourceEnrichmentResult:
    """Query ZFIN for zebrafish model gene-phenotype evidence."""
    return await run_zfin_enrichment_impl(
        space_id=space_id,
        seed_terms=seed_terms,
        document_store=document_store,
        run_registry=run_registry,
        artifact_store=artifact_store,
        parent_run=parent_run,
        gateway_factory=build_zfin_gateway,
    )

__all__ = [
    "SourceEnrichmentResult",
    "_create_enrichment_document",
    "_format_marrvel_results",
    "extract_gene_mentions_from_text",
    "run_alphafold_enrichment",
    "run_clinicaltrials_enrichment",
    "run_clinvar_enrichment",
    "run_drugbank_enrichment",
    "run_marrvel_enrichment",
    "run_mgi_enrichment",
    "run_zfin_enrichment",
]
