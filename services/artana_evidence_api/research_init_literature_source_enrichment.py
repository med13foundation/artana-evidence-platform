"""ClinicalTrials.gov, MGI, and ZFIN research-init enrichments."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID

from artana_evidence_api.research_init.source_caps import (
    ResearchInitSourceCaps,
    default_source_caps,
)
from artana_evidence_api.research_init_source_enrichment_common import (
    _UNREVIEWED_BOOTSTRAP_PROPOSAL_SCORE,
    SourceEnrichmentResult,
    _bootstrap_proposal_metadata,
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
    from artana_evidence_api.proposal_store import HarnessProposalDraft
    from artana_evidence_api.run_registry import HarnessRunRecord, HarnessRunRegistry
    from artana_evidence_api.source_enrichment_bridges import (
        AllianceGeneGatewayProtocol,
        ClinicalTrialsGatewayProtocol,
    )

# ---------------------------------------------------------------------------
# ClinicalTrials.gov enrichment
# ---------------------------------------------------------------------------


async def run_clinicaltrials_enrichment_impl(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
    gateway_factory: Callable[[], ClinicalTrialsGatewayProtocol | None],
    source_caps: ResearchInitSourceCaps | None = None,
) -> SourceEnrichmentResult:
    """Query ClinicalTrials.gov for registered trials matching seed terms.

    Pulls up to the configured maximum number of relevant seed terms
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
    effective_source_caps = source_caps or default_source_caps()
    candidate_terms: list[str] = _extract_likely_gene_symbols(seed_terms)
    if not candidate_terms:
        candidate_terms = [t for t in seed_terms if t and t.strip()]
    if not candidate_terms:
        return SourceEnrichmentResult(source_key="clinical_trials")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0
    records_by_term: dict[str, list[dict[str, object]]] = {}

    gateway = gateway_factory()
    if gateway is None:
        all_errors.append("ClinicalTrials.gov gateway not available")
    else:
        for term in candidate_terms[: effective_source_caps.max_terms_per_source]:
            try:
                fetch_result = await gateway.fetch_records_async(
                    query=term,
                    max_results=effective_source_caps.clinical_trials_max_results,
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


async def run_mgi_enrichment_impl(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
    gateway_factory: Callable[[], AllianceGeneGatewayProtocol | None],
    source_caps: ResearchInitSourceCaps | None = None,
) -> SourceEnrichmentResult:
    """Query MGI (via the Alliance API) for mouse gene records matching seed terms.

    Pulls up to the configured maximum number of likely gene symbols, runs the
    Alliance ``/search`` query for each (filtered to ``Mus musculus``), and
    creates one enrichment document per gene that returned results.  Each
    mouse gene yields proposals like ``GENE → ASSOCIATED_WITH → PHENOTYPE``
    for each mouse phenotype annotation, plus ``GENE → CAUSES → DISEASE`` for
    disease associations from the Alliance disease annotations.
    """
    effective_source_caps = source_caps or default_source_caps()
    candidate_terms: list[str] = _extract_likely_gene_symbols(seed_terms)
    if not candidate_terms:
        return SourceEnrichmentResult(source_key="mgi")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0
    records_by_term: dict[str, list[dict[str, object]]] = {}

    gateway = gateway_factory()
    if gateway is None:
        all_errors.append("MGI gateway not available")
    else:
        for term in candidate_terms[: effective_source_caps.max_terms_per_source]:
            try:
                fetch_result = await gateway.fetch_records_async(
                    query=term,
                    max_results=effective_source_caps.mgi_max_results,
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


async def run_zfin_enrichment_impl(
    *,
    space_id: UUID,
    seed_terms: list[str],
    document_store: HarnessDocumentStore,
    run_registry: HarnessRunRegistry,
    artifact_store: HarnessArtifactStore,
    parent_run: HarnessRunRecord,
    gateway_factory: Callable[[], AllianceGeneGatewayProtocol | None],
    source_caps: ResearchInitSourceCaps | None = None,
) -> SourceEnrichmentResult:
    """Query ZFIN (via the Alliance API) for zebrafish gene records.

    Pulls up to the configured maximum number of likely gene symbols, runs the
    Alliance ``/search`` query for each (filtered to ``Danio rerio``), and
    creates one enrichment document per gene that returned results.  Each
    zebrafish gene yields proposals like ``GENE → ASSOCIATED_WITH →
    PHENOTYPE`` for each zebrafish phenotype annotation, ``GENE →
    EXPRESSED_IN → TISSUE`` for each zebrafish anatomy expression term, and
    ``GENE → CAUSES → DISEASE`` for disease associations.
    """
    effective_source_caps = source_caps or default_source_caps()
    candidate_terms: list[str] = _extract_likely_gene_symbols(seed_terms)
    if not candidate_terms:
        return SourceEnrichmentResult(source_key="zfin")

    documents: list[HarnessDocumentRecord] = []
    all_errors: list[str] = []
    records_processed = 0
    records_by_term: dict[str, list[dict[str, object]]] = {}

    gateway = gateway_factory()
    if gateway is None:
        all_errors.append("ZFIN gateway not available")
    else:
        for term in candidate_terms[: effective_source_caps.max_terms_per_source]:
            try:
                fetch_result = await gateway.fetch_records_async(
                    query=term,
                    max_results=effective_source_caps.zfin_max_results,
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
    "run_clinicaltrials_enrichment_impl",
    "run_mgi_enrichment_impl",
    "run_zfin_enrichment_impl",
]
