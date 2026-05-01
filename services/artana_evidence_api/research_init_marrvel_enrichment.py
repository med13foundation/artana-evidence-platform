"""MARRVEL-specific research-init source enrichment."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.research_init.source_caps import (
    ResearchInitSourceCaps,
    default_source_caps,
)
from artana_evidence_api.research_init_source_enrichment_common import (
    _SYSTEM_OWNER_ID,
    SourceEnrichmentResult,
    _create_enrichment_document,
    _extract_likely_gene_symbols,
    logger,
)

if TYPE_CHECKING:
    from artana_evidence_api.artifact_store import HarnessArtifactStore
    from artana_evidence_api.document_store import (
        HarnessDocumentRecord,
        HarnessDocumentStore,
    )
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
    from artana_evidence_api.source_enrichment_bridges import (
        MarrvelDiscoveryServiceProtocol,
    )

# ---------------------------------------------------------------------------
# MARRVEL enrichment
# ---------------------------------------------------------------------------


async def run_marrvel_enrichment_impl(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
    discovery_service_factory: Callable[[], MarrvelDiscoveryServiceProtocol | None],
    source_caps: ResearchInitSourceCaps | None = None,
) -> SourceEnrichmentResult:
    """Query MARRVEL for gene-centric data from seed terms."""
    effective_source_caps = source_caps or default_source_caps()
    gene_symbols = _extract_likely_gene_symbols(seed_terms)
    if not gene_symbols:
        return SourceEnrichmentResult(source_key="marrvel")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0

    service = discovery_service_factory()
    if service is None:
        all_errors.append("MARRVEL discovery service not available")
    else:
        for gene_symbol in gene_symbols[: effective_source_caps.max_terms_per_source]:
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




__all__ = ["_format_marrvel_results", "run_marrvel_enrichment_impl"]
