"""Research brief generator for research-init.

Synthesizes findings from all sources into a structured narrative
that highlights cross-source connections and identifies gaps.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING
from uuid import UUID

from src.application.services.alias_yield_reporting import build_alias_yield_rollup

if TYPE_CHECKING:
    from .artifact_store import HarnessArtifactStore
    from .types.common import JSONObject

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResearchBriefSection:
    """One section of the research brief."""

    heading: str
    body: str


@dataclass(frozen=True)
class CrossSourceOverlap:
    """One entity that appears across two or more sources.

    Cross-source overlaps are the seeds the LLM uses to identify connections
    that no single source contains.  Computed deterministically from
    proposals so the LLM can reference real entity chains rather than invent.
    """

    entity_label: str
    source_kinds: tuple[str, ...]
    proposal_count: int


@dataclass(frozen=True)
class ResearchBrief:
    """Structured research brief from research-init."""

    title: str
    summary: str
    sections: tuple[ResearchBriefSection, ...] = ()
    gaps: tuple[str, ...] = ()
    next_steps: tuple[str, ...] = ()
    cross_source_overlaps: tuple[CrossSourceOverlap, ...] = ()

    def to_markdown(self) -> str:
        """Render the brief as markdown."""
        parts = [f"# {self.title}\n", self.summary, ""]
        for section in self.sections:
            parts.append(f"## {section.heading}\n")
            parts.append(section.body)
            parts.append("")
        if self.cross_source_overlaps:
            parts.append("## Cross-Source Connections\n")
            parts.append(
                "Entities mentioned by evidence from two or more sources — "
                "these are the connections that no single source contains:\n",
            )
            for overlap in self.cross_source_overlaps[:10]:
                sources = ", ".join(overlap.source_kinds)
                parts.append(
                    f"- **{overlap.entity_label}** "
                    f"(across {sources}; {overlap.proposal_count} proposals)",
                )
            parts.append("")
        if self.gaps:
            parts.append("## Gaps & Limitations\n")
            parts.extend(f"- {gap}" for gap in self.gaps)
            parts.append("")
        if self.next_steps:
            parts.append("## Suggested Next Steps\n")
            parts.extend(f"- {step}" for step in self.next_steps)
            parts.append("")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _source_was_active(source: JSONObject) -> bool:
    """Return True if the source was selected and did not stay pending."""
    return bool(source.get("selected")) and source.get("status") != "skipped"


def _source_completed(source: JSONObject) -> bool:
    return source.get("status") == "completed"


def _source_failed(source: JSONObject) -> bool:
    return source.get("status") == "failed"


def _int(value: object, default: int = 0) -> int:
    """Safely coerce a value to int."""
    if isinstance(value, int):
        return value
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return default


_MIN_SOURCES_FOR_OVERLAP = 2

_ALIAS_SOURCE_LABELS = {
    "hpo": "HPO phenotype aliases",
    "mondo": "MONDO disease aliases",
    "uniprot": "UniProt protein/gene aliases",
    "drugbank": "DrugBank drug aliases",
    "hgnc": "HGNC gene aliases",
}


def compute_cross_source_overlaps(
    proposals: list[JSONObject],
) -> tuple[CrossSourceOverlap, ...]:
    """Find entities mentioned by proposals from 2+ source kinds.

    Used to seed the LLM brief synthesis with concrete cross-source
    connection candidates.  Each proposal is expected to carry a
    ``source_kind`` and have ``proposed_subject_label`` /
    ``proposed_object_label`` fields in its payload (or ``subject_label``
    / ``object_label`` in metadata).
    """
    label_to_sources: dict[str, set[str]] = {}
    label_counts: dict[str, int] = {}

    for proposal in proposals:
        source_kind = proposal.get("source_kind")
        if not isinstance(source_kind, str) or not source_kind:
            continue
        payload = proposal.get("payload") or {}
        metadata = proposal.get("metadata") or {}
        labels: list[str] = []
        if isinstance(payload, dict):
            for field in ("proposed_subject_label", "proposed_object_label"):
                value = payload.get(field)
                if isinstance(value, str) and value.strip():
                    labels.append(value.strip())
        if isinstance(metadata, dict):
            for field in ("subject_label", "object_label"):
                value = metadata.get(field)
                if isinstance(value, str) and value.strip():
                    labels.append(value.strip())
        for label in labels:
            label_to_sources.setdefault(label, set()).add(source_kind)
            label_counts[label] = label_counts.get(label, 0) + 1

    overlaps: list[CrossSourceOverlap] = []
    for label, source_kinds in label_to_sources.items():
        if len(source_kinds) < _MIN_SOURCES_FOR_OVERLAP:
            continue
        overlaps.append(
            CrossSourceOverlap(
                entity_label=label,
                source_kinds=tuple(sorted(source_kinds)),
                proposal_count=label_counts.get(label, 0),
            ),
        )
    # Order by (most sources, most proposals) so the strongest overlaps come first.
    overlaps.sort(
        key=lambda o: (-len(o.source_kinds), -o.proposal_count, o.entity_label),
    )
    return tuple(overlaps)


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------


def _build_discovery_summary(
    *,
    documents_ingested: int,
    proposal_count: int,
    entity_count: int,
    chase_rounds_completed: int,
    source_results: dict[str, JSONObject],
) -> ResearchBriefSection:
    """Section 1: high-level discovery summary."""
    active_sources = [
        name for name, info in source_results.items() if _source_was_active(info)
    ]

    lines = [
        f"Research initialization queried **{len(active_sources)}** "
        f"data source{'s' if len(active_sources) != 1 else ''} "
        f"({', '.join(active_sources)}).",
        "",
        f"- **{documents_ingested}** document{'s' if documents_ingested != 1 else ''} ingested",
        f"- **{proposal_count}** proposal{'s' if proposal_count != 1 else ''} generated",
        f"- **{entity_count}** entit{'ies' if entity_count != 1 else 'y'} created",
    ]
    if chase_rounds_completed > 0:
        lines.append(
            f"- **{chase_rounds_completed}** chase round{'s' if chase_rounds_completed != 1 else ''} "
            "of cross-source discovery completed",
        )
    return ResearchBriefSection(heading="Discovery Summary", body="\n".join(lines))


def _build_alias_yield_section(
    source_results: dict[str, JSONObject],
) -> ResearchBriefSection | None:
    """Summarize backend-derived alias persistence counts."""
    rollup = build_alias_yield_rollup(source_results)
    if rollup is None:
        return None

    totals = rollup.totals
    lines = [
        f"Alias harvesting persisted **{totals.aliases_persisted}** searchable "
        f"alias{'es' if totals.aliases_persisted != 1 else ''} "
        f"from **{totals.source_count}** source"
        f"{'s' if totals.source_count != 1 else ''}.",
    ]
    if totals.alias_candidates_count > 0:
        lines.append(
            f"Backend persistence evaluated **{totals.alias_candidates_count}** "
            f"candidate label{'s' if totals.alias_candidates_count != 1 else ''} "
            f"and skipped **{totals.aliases_skipped}** already-known or "
            "unpersistable aliases.",
        )

    for source_key, source_summary in sorted(rollup.sources.items()):
        label = _ALIAS_SOURCE_LABELS.get(source_key, source_key.replace("_", " "))
        parts = [
            f"**{source_summary.alias_candidates_count}** candidate"
            f"{'s' if source_summary.alias_candidates_count != 1 else ''}",
        ]
        if source_summary.aliases_registered is not None:
            parts.append(f"**{source_summary.aliases_registered}** registered")
        parts.append(f"**{source_summary.aliases_persisted}** persisted")
        parts.append(f"**{source_summary.aliases_skipped}** skipped")
        if source_summary.alias_entities_touched > 0:
            parts.append(
                f"**{source_summary.alias_entities_touched}** entities touched",
            )
        lines.append(f"- **{label}**: {', '.join(parts)}.")

    if totals.alias_error_count > 0:
        lines.append(
            f"**{totals.alias_error_count}** alias persistence issue"
            f"{'s' if totals.alias_error_count != 1 else ''} "
            "were recorded for follow-up.",
        )

    return ResearchBriefSection(heading="Alias Yield", body="\n".join(lines))


def _build_literature_section(
    pubmed: JSONObject,
) -> ResearchBriefSection | None:
    """Section 2: PubMed literature findings."""
    if not _source_was_active(pubmed):
        return None

    discovered = _int(pubmed.get("documents_discovered"))
    selected = _int(pubmed.get("documents_selected"))
    ingested = _int(pubmed.get("documents_ingested"))
    observations = _int(pubmed.get("observations_created"))

    lines = []
    if discovered > 0:
        lines.append(
            f"PubMed search discovered **{discovered}** candidate paper{'s' if discovered != 1 else ''}, "
            f"of which **{selected}** {'were' if selected != 1 else 'was'} selected for ingestion.",
        )
    else:
        lines.append(
            "PubMed search returned no candidate papers for the given seed terms.",
        )

    if ingested > 0:
        lines.append(
            f"After deduplication, **{ingested}** document{'s' if ingested != 1 else ''} "
            f"{'were' if ingested != 1 else 'was'} successfully ingested.",
        )
    if observations > 0:
        lines.append(
            f"Extraction produced **{observations}** observation{'s' if observations != 1 else ''} "
            "from PubMed abstracts.",
        )
    if _source_failed(pubmed):
        lines.append("**Note:** PubMed processing encountered errors (see Gaps).")

    return ResearchBriefSection(
        heading="Literature Findings",
        body="\n".join(lines),
    )


def _build_clinvar_section(
    clinvar: JSONObject,
) -> ResearchBriefSection | None:
    """Section 3: ClinVar genomic variant data."""
    if not _source_was_active(clinvar):
        return None

    records = _int(clinvar.get("records_processed"))
    observations = _int(clinvar.get("observations_created"))

    lines = []
    if records > 0:
        lines.append(
            f"ClinVar contributed **{records}** variant record{'s' if records != 1 else ''}.",
        )
        if observations > 0:
            lines.append(
                f"These yielded **{observations}** observation{'s' if observations != 1 else ''} "
                "linking genomic variants to phenotypes.",
            )
    else:
        lines.append("ClinVar was queried but returned no matching variant records.")

    if _source_failed(clinvar):
        lines.append("**Note:** ClinVar processing encountered errors (see Gaps).")

    return ResearchBriefSection(
        heading="Genomic Variant Data",
        body="\n".join(lines),
    )


def _build_mondo_section(
    mondo: JSONObject,
) -> ResearchBriefSection | None:
    """Section 4: MONDO disease classification."""
    if not _source_was_active(mondo):
        return None

    if mondo.get("status") == "background":
        return ResearchBriefSection(
            heading="Disease Classification",
            body=(
                "MONDO disease ontology loading continues in the background. "
                "Disease alias grounding and hierarchy coverage will be patched "
                "into the run artifacts when it completes."
            ),
        )

    terms = _int(mondo.get("terms_loaded"))
    edges = _int(mondo.get("hierarchy_edges"))

    lines = []
    if terms > 0:
        lines.append(
            f"MONDO disease ontology loaded **{terms}** term{'s' if terms != 1 else ''} "
            f"with **{edges}** hierarchy edge{'s' if edges != 1 else ''}.",
        )
        lines.append(
            "This structured vocabulary enables cross-source entity resolution "
            "by mapping disease mentions across PubMed, ClinVar, and other sources "
            "to canonical identifiers.",
        )
    else:
        lines.append("MONDO ontology was loaded but contributed no terms.")

    if _source_failed(mondo):
        lines.append("**Note:** MONDO loading encountered errors (see Gaps).")

    return ResearchBriefSection(
        heading="Disease Classification",
        body="\n".join(lines),
    )


def _build_drugbank_section(
    drugbank: JSONObject,
) -> ResearchBriefSection | None:
    """Section 5: DrugBank drug-target interactions."""
    if not _source_was_active(drugbank):
        return None

    records = _int(drugbank.get("records_processed"))
    observations = _int(drugbank.get("observations_created"))

    lines = []
    if records > 0:
        lines.append(
            f"DrugBank contributed **{records}** drug-target interaction record{'s' if records != 1 else ''}.",
        )
        if observations > 0:
            lines.append(
                f"These produced **{observations}** observation{'s' if observations != 1 else ''} "
                "capturing drug-target binding, pharmacological action, and mechanism data.",
            )
    else:
        lines.append(
            "DrugBank was queried but returned no matching drug-target records.",
        )

    if _source_failed(drugbank):
        lines.append("**Note:** DrugBank processing encountered errors (see Gaps).")

    return ResearchBriefSection(
        heading="Drug-Target Interactions",
        body="\n".join(lines),
    )


def _build_alphafold_section(
    alphafold: JSONObject,
) -> ResearchBriefSection | None:
    """Section 6: AlphaFold protein structure predictions."""
    if not _source_was_active(alphafold):
        return None

    records = _int(alphafold.get("records_processed"))

    lines = []
    if records > 0:
        lines.append(
            f"AlphaFold contributed **{records}** protein structure prediction{'s' if records != 1 else ''}.",
        )
    else:
        lines.append(
            "AlphaFold was queried but returned no matching structure predictions.",
        )

    if _source_failed(alphafold):
        lines.append(
            "**Note:** AlphaFold processing encountered errors (see Gaps).",
        )

    return ResearchBriefSection(
        heading="Protein Structure",
        body="\n".join(lines),
    )


# ---------------------------------------------------------------------------
# Gap and next-step detection
# ---------------------------------------------------------------------------


def _identify_gaps(
    *,
    source_results: dict[str, JSONObject],
    proposal_count: int,
    chase_rounds_completed: int,
    errors: list[str],
) -> tuple[str, ...]:
    """Identify gaps and limitations in the research-init results."""
    gaps: list[str] = []

    # Sources that failed
    for name, info in source_results.items():
        if _source_failed(info):
            gaps.append(f"{name} enrichment failed during processing.")

    # Sources that were skipped
    skipped = [
        name for name, info in source_results.items() if info.get("status") == "skipped"
    ]
    if skipped:
        gaps.append(
            f"The following sources were not enabled: {', '.join(skipped)}.",
        )

    # No PubMed results
    pubmed = source_results.get("pubmed", {})
    if _source_was_active(pubmed) and _int(pubmed.get("documents_discovered")) == 0:
        gaps.append(
            "PubMed search returned no results. Consider broadening or "
            "adjusting the seed terms.",
        )

    # No proposals generated
    if proposal_count == 0:
        gaps.append(
            "No proposals were generated from the ingested documents. "
            "The seed terms may be too narrow, or the documents may not "
            "contain extractable claims.",
        )

    # Chase rounds found nothing new
    if chase_rounds_completed > 0:
        # If chase happened but entity count didn't grow, note it
        # (Caller can check entity_count, but we flag the rounds themselves)
        gaps.append(
            f"{chase_rounds_completed} chase round{'s' if chase_rounds_completed != 1 else ''} "
            "completed but may not have discovered additional entities.",
        )

    # Explicit errors from the run
    gaps.extend(f"Error: {error}" for error in errors)

    return tuple(gaps)


def _suggest_next_steps(
    *,
    source_results: dict[str, JSONObject],
    proposal_count: int,
    documents_ingested: int,
) -> tuple[str, ...]:
    """Suggest next steps based on the research-init results."""
    steps: list[str] = []

    pubmed = source_results.get("pubmed", {})
    _min_pubmed_docs = 3
    if (
        _source_was_active(pubmed)
        and _int(pubmed.get("documents_ingested")) < _min_pubmed_docs
    ):
        steps.append(
            "Upload specific papers to supplement the limited PubMed coverage.",
        )

    drugbank = source_results.get("drugbank", {})
    if not _source_was_active(drugbank):
        steps.append(
            "Enable DrugBank to discover drug-target interactions related "
            "to the research objective.",
        )

    alphafold = source_results.get("alphafold", {})
    if not _source_was_active(alphafold):
        steps.append(
            "Enable AlphaFold to retrieve protein structure predictions "
            "for identified gene targets.",
        )

    if proposal_count > 0:
        steps.append(
            f"Review the {proposal_count} proposal{'s' if proposal_count != 1 else ''} "
            "in the proposal queue to accept or refine extracted claims.",
        )

    if documents_ingested == 0 and not _source_was_active(pubmed):
        steps.append(
            "Upload PDF or text documents to seed the research space with "
            "domain-specific literature.",
        )

    return tuple(steps)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _synthesize_cross_source_summary(
    *,
    source_results: dict[str, JSONObject],
    objective: str,
    seed_terms: list[str],
    proposal_count: int,
    entity_count: int,
    chase_rounds_completed: int,
) -> str:
    """Build a narrative summary connecting findings across sources."""
    parts: list[str] = []

    terms_display = ", ".join(seed_terms[:3]) if seed_terms else "(none)"

    # Opening
    parts.append(f"Research into **{objective}** has been initialized ")
    parts.append(f"using {terms_display} as seed entities.")

    # Cross-source connections narrative
    active_sources = [
        name
        for name, info in source_results.items()
        if info.get("status") == "completed"
    ]

    if len(active_sources) > 1:
        parts.append(f"\n\nThe system queried **{len(active_sources)} sources** ")
        parts.append(
            "in coordination, using findings from each to inform queries to the next.",
        )

    # Highlight what each source found and how they connect
    pubmed = source_results.get("pubmed", {})
    clinvar = source_results.get("clinvar", {})
    drugbank = source_results.get("drugbank", {})
    mondo = source_results.get("mondo", {})

    if pubmed.get("status") == "completed" and clinvar.get("status") == "completed":
        parts.append(
            "\n\nPubMed literature identified key genes and mechanisms, "
            "which were then cross-referenced against ClinVar's variant database "
            "to find clinically significant variants.",
        )

    if drugbank.get("status") == "completed":
        parts.append(
            "\n\nDrugBank was queried for existing therapeutics targeting "
            "the identified genes and proteins.",
        )

    if mondo.get("status") == "completed":
        terms_loaded = _int(mondo.get("terms_loaded"))
        if terms_loaded:
            parts.append(
                f"\n\nMONDO disease ontology loaded {terms_loaded} disease terms, "
                "enabling cross-database entity resolution for disease mentions "
                "across all sources.",
            )

    if chase_rounds_completed > 0:
        parts.append(
            f"\n\n**{chase_rounds_completed} additional discovery "
            f"round{'s' if chase_rounds_completed > 1 else ''}** "
            "chased newly discovered entities across structured databases, "
            "finding connections that no single source contains.",
        )

    if proposal_count > 0:
        parts.append(
            f"\n\nIn total, **{proposal_count} proposals** were generated across all sources, "
            f"covering **{entity_count} entities**. "
            "These proposals are ready for review in the proposal queue.",
        )

    return "".join(parts)


def generate_research_brief(
    *,
    objective: str,
    seed_terms: list[str],
    source_results: dict[str, JSONObject],
    documents_ingested: int,
    proposal_count: int,
    entity_count: int,
    errors: list[str],
    chase_rounds_completed: int = 0,
    proposals: list[JSONObject] | None = None,
) -> ResearchBrief:
    """Generate a structured research brief from research-init results.

    This is a deterministic summary (no LLM call). It organizes the
    source results into a narrative structure that highlights what was
    found, what connections exist, and what gaps remain.
    """
    title = f"Research Brief: {objective}"
    summary = _synthesize_cross_source_summary(
        source_results=source_results,
        objective=objective,
        seed_terms=seed_terms,
        proposal_count=proposal_count,
        entity_count=entity_count,
        chase_rounds_completed=chase_rounds_completed,
    )

    sections: list[ResearchBriefSection] = []

    # Section 1: Discovery Summary (always present)
    sections.append(
        _build_discovery_summary(
            documents_ingested=documents_ingested,
            proposal_count=proposal_count,
            entity_count=entity_count,
            chase_rounds_completed=chase_rounds_completed,
            source_results=source_results,
        ),
    )
    alias_yield_section = _build_alias_yield_section(source_results)
    if alias_yield_section is not None:
        sections.append(alias_yield_section)

    # Section 2-6: per-source sections (only if active)
    section_builders = [
        ("pubmed", _build_literature_section),
        ("clinvar", _build_clinvar_section),
        ("mondo", _build_mondo_section),
        ("drugbank", _build_drugbank_section),
        ("alphafold", _build_alphafold_section),
    ]
    for source_key, builder in section_builders:
        source_data = source_results.get(source_key, {})
        if not isinstance(source_data, dict):
            continue
        section = builder(source_data)
        if section is not None:
            sections.append(section)

    gaps = _identify_gaps(
        source_results=source_results,
        proposal_count=proposal_count,
        chase_rounds_completed=chase_rounds_completed,
        errors=errors,
    )

    next_steps = _suggest_next_steps(
        source_results=source_results,
        proposal_count=proposal_count,
        documents_ingested=documents_ingested,
    )

    overlaps = compute_cross_source_overlaps(proposals) if proposals else ()

    return ResearchBrief(
        title=title,
        summary=summary,
        sections=tuple(sections),
        gaps=gaps,
        next_steps=next_steps,
        cross_source_overlaps=overlaps,
    )


def store_research_brief(
    *,
    brief: ResearchBrief,
    artifact_store: HarnessArtifactStore,
    space_id: UUID | str,
    run_id: str,
) -> None:
    """Store the research brief as a workspace artifact."""
    artifact_store.patch_workspace(
        space_id=space_id,
        run_id=run_id,
        patch={
            "research_brief": {
                "title": brief.title,
                "summary": brief.summary,
                "markdown": brief.to_markdown(),
                "sections": [
                    {"heading": s.heading, "body": s.body} for s in brief.sections
                ],
                "gaps": list(brief.gaps),
                "next_steps": list(brief.next_steps),
                "cross_source_overlaps": [
                    {
                        "entity_label": o.entity_label,
                        "source_kinds": list(o.source_kinds),
                        "proposal_count": o.proposal_count,
                    }
                    for o in brief.cross_source_overlaps
                ],
            },
        },
    )


async def generate_llm_research_brief(
    *,
    objective: str,
    seed_terms: list[str],
    deterministic_brief: ResearchBrief,
    llm_adapter: object | None = None,
) -> ResearchBrief:
    """Generate an LLM-enhanced research brief.

    Uses the deterministic brief as context and asks an LLM to
    synthesize a narrative highlighting cross-source connections.
    Falls back to deterministic brief on any error.
    """
    if llm_adapter is None:
        # Try to create one from the environment
        try:
            return await _generate_brief_with_kernel(
                objective=objective,
                seed_terms=seed_terms,
                deterministic_brief=deterministic_brief,
            )
        except Exception:  # noqa: BLE001
            return deterministic_brief

    return deterministic_brief


async def _generate_brief_with_kernel(
    *,
    objective: str,
    seed_terms: list[str],
    deterministic_brief: ResearchBrief,
) -> ResearchBrief:
    """Call the Artana kernel to synthesize a research brief.

    The prompt asks for a theme-organized synthesis (mechanism chains,
    drug-target relationships, variant impact, etc.) rather than per-source
    summaries, and explicitly grounds cross-source connection claims in the
    overlap candidates the deterministic brief computed.
    """
    from contextlib import suppress
    from uuid import uuid4

    from pydantic import BaseModel, Field

    # Define output schema
    class LLMBriefOutput(BaseModel):
        """Structured output from the LLM brief generation."""

        title: str = Field(description="Brief title")
        summary: str = Field(
            description=(
                "2-3 paragraph narrative summary organized by theme "
                "(mechanism chains, drug-target relationships, variant "
                "impact). Explicitly highlight cross-source connections."
            ),
        )
        key_findings: list[str] = Field(
            description=(
                "3-5 specific findings that span multiple data sources. "
                "Each finding should reference real entity chains "
                "(e.g., 'ClinVar variant X disrupts AlphaFold domain Y, "
                "which PubMed links to mechanism Z')."
            ),
        )
        gaps: list[str] = Field(
            description=(
                "What the system could not find, framed as concrete "
                "questions for the researcher to investigate."
            ),
        )
        next_steps: list[str] = Field(
            description="Suggested next actions for the researcher",
        )

    # Build prompt — include the cross-source overlap candidates so the LLM
    # can reference real entity chains rather than invent them.
    brief_markdown = deterministic_brief.to_markdown()
    overlaps_block = ""
    if deterministic_brief.cross_source_overlaps:
        overlap_lines = [
            f"- **{o.entity_label}** "
            f"(across {', '.join(o.source_kinds)}; "
            f"{o.proposal_count} proposals)"
            for o in deterministic_brief.cross_source_overlaps[:10]
        ]
        overlaps_block = (
            "\n## Cross-Source Connection Candidates\n"
            "The following entities are mentioned by proposals from two or "
            "more sources. These are real connections you can reference:\n"
            + "\n".join(overlap_lines)
            + "\n"
        )

    prompt = (
        "You are a biomedical research assistant synthesizing findings "
        "from a multi-source research initialization.\n\n"
        f"## Research Objective\n{objective}\n\n"
        f"## Seed Entities\n{', '.join(seed_terms)}\n\n"
        f"## Raw Findings (from automated analysis)\n{brief_markdown}\n"
        f"{overlaps_block}\n"
        "## Your Task\n"
        "Synthesize the findings above into a coherent research brief "
        "**organized by theme, not by source**. Focus on:\n\n"
        "1. **Theme organization**: Group findings into mechanism chains, "
        "drug-target relationships, variant impact, and disease "
        "classification rather than per-source summaries.\n"
        "2. **Cross-source connections**: For each cross-source connection "
        "candidate above, write a concrete narrative that explains how the "
        "connection works. Example format: 'ClinVar variant c.5266dupC "
        "disrupts the BRCT domain (AlphaFold structure), which PubMed "
        "literature links to homologous recombination deficiency, making "
        "carriers candidates for PARP inhibitor therapy (DrugBank: "
        "Olaparib).' These are the hidden connections the platform exists "
        "to find.\n"
        "3. **Gaps as questions**: Frame what's missing as concrete "
        "questions the researcher should investigate, not just 'no data "
        "found'.\n"
        "4. **Next steps**: What specific actions should the researcher "
        "take?\n\n"
        "Write in a professional, informative tone. Be specific — "
        "reference actual genes, diseases, drugs, and variants. Do not "
        "invent connections that are not supported by the candidates above."
    )

    try:
        from artana.agent import SingleStepModelClient
        from artana.kernel import ArtanaKernel
        from artana.models import TenantContext
        from artana.ports.model import LiteLLMAdapter
    except ImportError:
        logger.debug("Artana kernel not available for LLM brief generation")
        return deterministic_brief

    import artana_evidence_api.runtime_support as _runtime_support
    import artana_evidence_api.step_helpers as _step_helpers

    store = None
    try:
        registry = _runtime_support.get_model_registry()
        model_spec = registry.get_default_model(
            _runtime_support.ModelCapability.EVIDENCE_EXTRACTION,
        )
        model_id = _runtime_support.normalize_litellm_model_id(model_spec.model_id)

        tenant = TenantContext(
            tenant_id="research-brief-generation",
            capabilities=frozenset(),
            budget_usd_limit=0.50,
        )

        store = _runtime_support.create_artana_postgres_store()
        kernel = ArtanaKernel(
            store=store,
            model_port=LiteLLMAdapter(timeout_seconds=90.0),
        )

        client = SingleStepModelClient(kernel=kernel)
        result = await _step_helpers.run_single_step_with_policy(
            client,
            run_id=f"research-brief:{uuid4()}",
            tenant=tenant,
            model=model_id,
            prompt=prompt,
            output_schema=LLMBriefOutput,
            step_key="research.llm_brief_synthesis.v1",
            replay_policy="fork_on_drift",
        )

        output = (
            result.output
            if isinstance(result.output, LLMBriefOutput)
            else LLMBriefOutput.model_validate(result.output)
        )

        # Convert LLM output to ResearchBrief, preserving deterministic sections
        # and the cross-source overlap candidates.
        return ResearchBrief(
            title=output.title or deterministic_brief.title,
            summary=output.summary,
            sections=deterministic_brief.sections,  # Keep the per-source sections
            gaps=tuple(output.gaps) if output.gaps else deterministic_brief.gaps,
            next_steps=(
                tuple(output.next_steps)
                if output.next_steps
                else deterministic_brief.next_steps
            ),
            cross_source_overlaps=deterministic_brief.cross_source_overlaps,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "LLM brief generation failed, using deterministic brief: %s",
            exc,
        )
        return deterministic_brief
    finally:
        if store is not None:
            with suppress(Exception):
                await store.close()


__all__ = [
    "ResearchBrief",
    "ResearchBriefSection",
    "generate_llm_research_brief",
    "generate_research_brief",
    "store_research_brief",
]
