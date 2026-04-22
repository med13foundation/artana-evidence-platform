"""Shared helper functions for AI data source test services."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.domain.entities import data_source_configs, user_data_source
from src.type_definitions import data_sources as data_source_types

if TYPE_CHECKING:
    from src.type_definitions.common import RawRecord, SourceMetadata

LOW_CONFIDENCE_THRESHOLD: float = 0.5
CLINVAR_DISCOVERY_SOURCE_IDS: frozenset[str] = frozenset(
    {"clinvar", "clinvar_benchmark"},
)
DEFAULT_CLINVAR_AGENT_PROMPT = (
    "Use ClinVar-specific ontology and evidence criteria to generate targeted "
    "queries for pathogenicity-focused tasks."
)
DEFAULT_CLINVAR_QUERY = "MED13 pathogenic variant"


def normalize_catalog_entry_id(metadata: SourceMetadata) -> str | None:
    catalog_entry_id = metadata.get("catalog_entry_id")
    if not isinstance(catalog_entry_id, str):
        return None
    normalized = catalog_entry_id.strip().lower()
    return normalized if normalized else None


def is_clinvar_discovery_source(metadata: SourceMetadata) -> bool:
    catalog_entry_id = normalize_catalog_entry_id(metadata)
    return (
        catalog_entry_id in CLINVAR_DISCOVERY_SOURCE_IDS
        if catalog_entry_id is not None
        else False
    )


def apply_clinvar_defaults(metadata: SourceMetadata) -> SourceMetadata:
    """Backfill AI defaults for legacy ClinVar discovery sources."""
    if not is_clinvar_discovery_source(metadata):
        return metadata

    normalized_metadata: SourceMetadata = dict(metadata)
    query = normalized_metadata.get("query")
    if not isinstance(query, str) or not query.strip():
        normalized_metadata["query"] = DEFAULT_CLINVAR_QUERY

    raw_agent_config = normalized_metadata.get("agent_config")
    if isinstance(raw_agent_config, dict):
        agent_config: SourceMetadata = dict(raw_agent_config)
    else:
        agent_config = {}

    agent_config.setdefault("is_ai_managed", True)
    agent_config.setdefault("query_agent_source_type", "clinvar")
    agent_config.setdefault("use_research_space_context", True)
    agent_config.setdefault("agent_prompt", DEFAULT_CLINVAR_AGENT_PROMPT)

    normalized_metadata["agent_config"] = agent_config
    return normalized_metadata


def should_use_pubmed_gateway(
    source: user_data_source.UserDataSource,
    config: data_source_configs.PubMedQueryConfig,
) -> bool:
    """
    Determine if the configured source should run through PubMed fetch for AI tests.
    """
    return (
        source.source_type == user_data_source.SourceType.PUBMED
        or config.agent_config.query_agent_source_type.lower() == "pubmed"
    )


def should_use_clinvar_gateway(
    source: user_data_source.UserDataSource,
    config: data_source_configs.PubMedQueryConfig,
) -> bool:
    """Determine if the configured source should run through ClinVar fetch."""
    return (
        source.source_type == user_data_source.SourceType.CLINVAR
        or config.agent_config.query_agent_source_type.lower() == "clinvar"
    )


def coerce_scalar(value: object | None) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, int | float):
        return str(value)
    return None


def extract_journal_title(value: object | None) -> str | None:
    if not isinstance(value, dict):
        return None
    title_value = value.get("title")
    return (
        title_value.strip()
        if isinstance(title_value, str) and title_value.strip()
        else None
    )


def build_links(
    pubmed_id: str | None,
    pmc_id: str | None,
    doi: str | None,
) -> list[data_source_types.DataSourceAiTestLink]:
    links: list[data_source_types.DataSourceAiTestLink] = []
    if pubmed_id:
        links.append(
            data_source_types.DataSourceAiTestLink(
                label="PubMed",
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/",
            ),
        )
    if pmc_id:
        links.append(
            data_source_types.DataSourceAiTestLink(
                label="PubMed Central",
                url=f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmc_id}/",
            ),
        )
    if doi:
        links.append(
            data_source_types.DataSourceAiTestLink(
                label="DOI",
                url=f"https://doi.org/{doi}",
            ),
        )
    return links


def build_findings(
    records: list[RawRecord],
    sample_size: int,
) -> list[data_source_types.DataSourceAiTestFinding]:
    findings: list[data_source_types.DataSourceAiTestFinding] = []
    for record in records[:sample_size]:
        pubmed_id = coerce_scalar(record.get("pubmed_id"))
        title = coerce_scalar(record.get("title")) or "Untitled PubMed record"
        doi = coerce_scalar(record.get("doi"))
        pmc_id = coerce_scalar(record.get("pmc_id"))
        publication_date = coerce_scalar(record.get("publication_date"))
        journal = extract_journal_title(record.get("journal"))
        links = build_links(pubmed_id, pmc_id, doi)

        findings.append(
            data_source_types.DataSourceAiTestFinding(
                title=title,
                pubmed_id=pubmed_id,
                doi=doi,
                pmc_id=pmc_id,
                publication_date=publication_date,
                journal=journal,
                links=links,
            ),
        )
    return findings


def build_clinvar_findings(
    records: list[RawRecord],
    sample_size: int,
) -> list[data_source_types.DataSourceAiTestFinding]:
    findings: list[data_source_types.DataSourceAiTestFinding] = []
    for record in records[:sample_size]:
        clinvar_id = coerce_scalar(record.get("clinvar_id"))
        parsed_data_raw = record.get("parsed_data")
        parsed_data = parsed_data_raw if isinstance(parsed_data_raw, dict) else {}
        gene_symbol = coerce_scalar(parsed_data.get("gene_symbol"))
        clinical_significance = coerce_scalar(parsed_data.get("clinical_significance"))
        title_parts = [part for part in (gene_symbol, clinical_significance) if part]
        title = (
            " - ".join(title_parts)
            if title_parts
            else (f"ClinVar variant {clinvar_id}" if clinvar_id else "ClinVar variant")
        )
        links: list[data_source_types.DataSourceAiTestLink] = []
        if clinvar_id:
            links.append(
                data_source_types.DataSourceAiTestLink(
                    label="ClinVar",
                    url=(
                        "https://www.ncbi.nlm.nih.gov/clinvar/variation/"
                        f"{clinvar_id}/"
                    ),
                ),
            )

        findings.append(
            data_source_types.DataSourceAiTestFinding(
                title=title,
                publication_date=coerce_scalar(record.get("fetched_at")),
                links=links,
            ),
        )
    return findings


def extract_search_terms(query: str | None) -> list[str]:
    if not query:
        return []

    terms: list[str] = []
    quoted_terms = re.findall(r'"([^"]+)"', query)
    for term in quoted_terms:
        normalized = term.strip()
        if normalized and normalized not in terms:
            terms.append(normalized)

    scrubbed = re.sub(r'"[^"]+"', " ", query)
    scrubbed = re.sub(r"\[[^\]]+\]", " ", scrubbed)
    scrubbed = scrubbed.replace("(", " ").replace(")", " ")
    for token in scrubbed.split():
        normalized = token.strip()
        if not normalized:
            continue
        if normalized.upper() in {"AND", "OR", "NOT"}:
            continue
        if normalized not in terms:
            terms.append(normalized)

    return terms
