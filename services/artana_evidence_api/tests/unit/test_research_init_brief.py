"""Unit tests for research-init brief generator."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from artana_evidence_api import research_init_brief, runtime_support, step_helpers
from artana_evidence_api.research_init_brief import (
    CrossSourceOverlap,
    ResearchBrief,
    ResearchBriefSection,
    _synthesize_cross_source_summary,
    compute_cross_source_overlaps,
    generate_llm_research_brief,
    generate_research_brief,
    store_research_brief,
)

# ---------------------------------------------------------------------------
# Fixtures — source_results matching _build_source_results() shape
# ---------------------------------------------------------------------------


def _full_source_results() -> dict[str, dict[str, object]]:
    """Source results where every source ran and produced data."""
    return {
        "pubmed": {
            "selected": True,
            "status": "completed",
            "documents_discovered": 42,
            "documents_selected": 15,
            "documents_ingested": 12,
            "documents_skipped_duplicate": 3,
            "observations_created": 28,
        },
        "marrvel": {
            "selected": True,
            "status": "completed",
            "proposal_count": 5,
        },
        "pdf": {
            "selected": True,
            "status": "completed",
            "documents_selected": 2,
            "observations_created": 6,
        },
        "text": {
            "selected": True,
            "status": "completed",
            "documents_selected": 1,
            "observations_created": 3,
        },
        "clinvar": {
            "selected": True,
            "status": "completed",
            "records_processed": 18,
            "observations_created": 10,
        },
        "mondo": {
            "selected": True,
            "status": "completed",
            "terms_loaded": 150,
            "hierarchy_edges": 320,
        },
        "drugbank": {
            "selected": True,
            "status": "completed",
            "records_processed": 7,
            "observations_created": 4,
        },
        "alphafold": {
            "selected": True,
            "status": "completed",
            "records_processed": 3,
            "observations_created": 0,
        },
        "uniprot": {
            "selected": True,
            "status": "completed",
            "records_processed": 5,
            "observations_created": 2,
        },
    }


def _pubmed_only_source_results() -> dict[str, dict[str, object]]:
    """Only PubMed active; everything else skipped."""
    return {
        "pubmed": {
            "selected": True,
            "status": "completed",
            "documents_discovered": 10,
            "documents_selected": 5,
            "documents_ingested": 5,
            "documents_skipped_duplicate": 0,
            "observations_created": 8,
        },
        "marrvel": {"selected": False, "status": "skipped", "proposal_count": 0},
        "pdf": {
            "selected": False,
            "status": "skipped",
            "documents_selected": 0,
            "observations_created": 0,
        },
        "text": {
            "selected": False,
            "status": "skipped",
            "documents_selected": 0,
            "observations_created": 0,
        },
        "clinvar": {
            "selected": False,
            "status": "skipped",
            "records_processed": 0,
            "observations_created": 0,
        },
        "mondo": {
            "selected": False,
            "status": "skipped",
            "terms_loaded": 0,
            "hierarchy_edges": 0,
        },
        "drugbank": {
            "selected": False,
            "status": "skipped",
            "records_processed": 0,
            "observations_created": 0,
        },
        "alphafold": {
            "selected": False,
            "status": "skipped",
            "records_processed": 0,
            "observations_created": 0,
        },
        "uniprot": {
            "selected": False,
            "status": "skipped",
            "records_processed": 0,
            "observations_created": 0,
        },
    }


# ---------------------------------------------------------------------------
# Test 1: full source results produce sections for each active source
# ---------------------------------------------------------------------------


class TestFullSourceResults:
    def test_produces_sections_for_each_active_source(self) -> None:
        brief = generate_research_brief(
            objective="MED13 in neurodevelopmental disorders",
            seed_terms=["MED13", "mediator complex", "neurodevelopment"],
            source_results=_full_source_results(),
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
            chase_rounds_completed=2,
        )

        section_headings = [s.heading for s in brief.sections]
        assert "Discovery Summary" in section_headings
        assert "Literature Findings" in section_headings
        assert "Genomic Variant Data" in section_headings
        assert "Disease Classification" in section_headings
        assert "Drug-Target Interactions" in section_headings
        assert "Protein Structure" in section_headings

    def test_alias_yield_section_uses_backend_counts(self) -> None:
        source_results = _full_source_results()
        source_results["hpo"] = {
            "selected": True,
            "status": "completed",
            "alias_candidates_count": 4,
            "aliases_registered": 4,
            "aliases_persisted": 3,
            "aliases_skipped": 1,
            "alias_entities_touched": 2,
            "alias_errors": [],
        }
        source_results["uniprot"].update(
            {
                "alias_candidates_count": 8,
                "aliases_persisted": 6,
                "aliases_skipped": 2,
                "alias_entities_touched": 2,
                "alias_errors": [],
            },
        )
        source_results["drugbank"].update(
            {
                "alias_candidates_count": 5,
                "aliases_persisted": 5,
                "aliases_skipped": 0,
                "alias_entities_touched": 1,
                "alias_errors": [],
            },
        )
        source_results["hgnc"] = {
            "selected": True,
            "status": "completed",
            "alias_candidates_count": 3,
            "aliases_persisted": 3,
            "aliases_skipped": 0,
            "alias_entities_touched": 1,
            "alias_errors": [],
        }

        brief = generate_research_brief(
            objective="MED13 in neurodevelopmental disorders",
            seed_terms=["MED13"],
            source_results=source_results,
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )

        alias_section = next(
            section for section in brief.sections if section.heading == "Alias Yield"
        )
        markdown = brief.to_markdown()
        assert "HPO phenotype aliases" in alias_section.body
        assert "UniProt protein/gene aliases" in alias_section.body
        assert "DrugBank drug aliases" in alias_section.body
        assert "HGNC gene aliases" in alias_section.body
        assert "Alias harvesting persisted **17** searchable aliases" in (
            alias_section.body
        )
        assert "## Alias Yield" in markdown

    def test_title_contains_objective(self) -> None:
        brief = generate_research_brief(
            objective="MED13 in neurodevelopmental disorders",
            seed_terms=["MED13"],
            source_results=_full_source_results(),
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )
        assert "MED13 in neurodevelopmental disorders" in brief.title

    def test_summary_contains_seed_terms(self) -> None:
        brief = generate_research_brief(
            objective="MED13 study",
            seed_terms=["MED13", "mediator complex"],
            source_results=_full_source_results(),
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )
        assert "MED13" in brief.summary
        assert "mediator complex" in brief.summary

    def test_summary_contains_objective(self) -> None:
        brief = generate_research_brief(
            objective="MED13 study",
            seed_terms=["MED13"],
            source_results=_full_source_results(),
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )
        assert "MED13 study" in brief.summary

    def test_discovery_summary_counts(self) -> None:
        brief = generate_research_brief(
            objective="test",
            seed_terms=["term"],
            source_results=_full_source_results(),
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )
        discovery = next(s for s in brief.sections if s.heading == "Discovery Summary")
        assert "**15**" in discovery.body
        assert "**20**" in discovery.body
        assert "**8**" in discovery.body

    def test_literature_section_contains_paper_counts(self) -> None:
        brief = generate_research_brief(
            objective="test",
            seed_terms=["term"],
            source_results=_full_source_results(),
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )
        lit = next(s for s in brief.sections if s.heading == "Literature Findings")
        assert "**42**" in lit.body  # discovered
        assert "**15**" in lit.body  # selected
        assert "**12**" in lit.body  # ingested

    def test_clinvar_section_shows_records(self) -> None:
        brief = generate_research_brief(
            objective="test",
            seed_terms=["term"],
            source_results=_full_source_results(),
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )
        clinvar_sec = next(
            s for s in brief.sections if s.heading == "Genomic Variant Data"
        )
        assert "**18**" in clinvar_sec.body  # records processed

    def test_mondo_section_shows_terms_and_edges(self) -> None:
        brief = generate_research_brief(
            objective="test",
            seed_terms=["term"],
            source_results=_full_source_results(),
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )
        mondo_sec = next(
            s for s in brief.sections if s.heading == "Disease Classification"
        )
        assert "**150**" in mondo_sec.body
        assert "**320**" in mondo_sec.body

    def test_mondo_section_mentions_background_loading(self) -> None:
        source_results = _full_source_results()
        source_results["mondo"] = {
            "selected": True,
            "status": "background",
            "terms_loaded": 0,
            "hierarchy_edges": 0,
        }

        brief = generate_research_brief(
            objective="test",
            seed_terms=["term"],
            source_results=source_results,
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )

        mondo_sec = next(
            s for s in brief.sections if s.heading == "Disease Classification"
        )
        assert "continues in the background" in mondo_sec.body

    def test_drugbank_section_shows_interactions(self) -> None:
        brief = generate_research_brief(
            objective="test",
            seed_terms=["term"],
            source_results=_full_source_results(),
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )
        drug_sec = next(
            s for s in brief.sections if s.heading == "Drug-Target Interactions"
        )
        assert "**7**" in drug_sec.body

    def test_alphafold_section_shows_predictions(self) -> None:
        brief = generate_research_brief(
            objective="test",
            seed_terms=["term"],
            source_results=_full_source_results(),
            documents_ingested=15,
            proposal_count=20,
            entity_count=8,
            errors=[],
        )
        af_sec = next(s for s in brief.sections if s.heading == "Protein Structure")
        assert "**3**" in af_sec.body


# ---------------------------------------------------------------------------
# Test 2: PubMed only — no ClinVar/DrugBank sections
# ---------------------------------------------------------------------------


class TestPubmedOnly:
    def test_no_clinvar_or_drugbank_sections(self) -> None:
        brief = generate_research_brief(
            objective="PubMed-only run",
            seed_terms=["BRCA1"],
            source_results=_pubmed_only_source_results(),
            documents_ingested=5,
            proposal_count=3,
            entity_count=2,
            errors=[],
        )
        section_headings = [s.heading for s in brief.sections]
        assert "Discovery Summary" in section_headings
        assert "Literature Findings" in section_headings
        assert "Genomic Variant Data" not in section_headings
        assert "Disease Classification" not in section_headings
        assert "Drug-Target Interactions" not in section_headings
        assert "Protein Structure" not in section_headings

    def test_next_steps_suggest_enabling_drugbank_and_alphafold(self) -> None:
        brief = generate_research_brief(
            objective="PubMed-only run",
            seed_terms=["BRCA1"],
            source_results=_pubmed_only_source_results(),
            documents_ingested=5,
            proposal_count=3,
            entity_count=2,
            errors=[],
        )
        assert any("DrugBank" in s for s in brief.next_steps)
        assert any("AlphaFold" in s for s in brief.next_steps)

    def test_gaps_mention_skipped_sources(self) -> None:
        brief = generate_research_brief(
            objective="PubMed-only run",
            seed_terms=["BRCA1"],
            source_results=_pubmed_only_source_results(),
            documents_ingested=5,
            proposal_count=3,
            entity_count=2,
            errors=[],
        )
        assert any("not enabled" in g for g in brief.gaps)


# ---------------------------------------------------------------------------
# Test 3: zero proposals → gap identified
# ---------------------------------------------------------------------------


class TestZeroProposals:
    def test_gap_when_no_proposals(self) -> None:
        brief = generate_research_brief(
            objective="sparse results",
            seed_terms=["obscure-gene"],
            source_results=_pubmed_only_source_results(),
            documents_ingested=5,
            proposal_count=0,
            entity_count=0,
            errors=[],
        )
        assert any("No proposals" in g for g in brief.gaps)

    def test_next_steps_still_suggest_review_when_proposals_exist(self) -> None:
        brief = generate_research_brief(
            objective="normal run",
            seed_terms=["term"],
            source_results=_full_source_results(),
            documents_ingested=10,
            proposal_count=5,
            entity_count=3,
            errors=[],
        )
        assert any("proposal" in s.lower() for s in brief.next_steps)


# ---------------------------------------------------------------------------
# Test 4: errors → mentioned in gaps
# ---------------------------------------------------------------------------


class TestWithErrors:
    def test_errors_appear_in_gaps(self) -> None:
        errors = [
            "ClinVar enrichment failed: connection timeout",
            "DrugBank enrichment failed: API rate limit",
        ]
        source_results = _full_source_results()
        source_results["clinvar"]["status"] = "failed"
        source_results["drugbank"]["status"] = "failed"

        brief = generate_research_brief(
            objective="error run",
            seed_terms=["term"],
            source_results=source_results,
            documents_ingested=10,
            proposal_count=5,
            entity_count=3,
            errors=errors,
        )

        gap_text = " ".join(brief.gaps)
        assert "connection timeout" in gap_text
        assert "API rate limit" in gap_text

    def test_failed_sources_flagged_in_gaps(self) -> None:
        source_results = _full_source_results()
        source_results["clinvar"]["status"] = "failed"

        brief = generate_research_brief(
            objective="error run",
            seed_terms=["term"],
            source_results=source_results,
            documents_ingested=10,
            proposal_count=5,
            entity_count=3,
            errors=[],
        )
        assert any("clinvar" in g.lower() and "failed" in g.lower() for g in brief.gaps)

    def test_failed_source_note_in_section_body(self) -> None:
        source_results = _full_source_results()
        source_results["clinvar"]["status"] = "failed"

        brief = generate_research_brief(
            objective="error run",
            seed_terms=["term"],
            source_results=source_results,
            documents_ingested=10,
            proposal_count=5,
            entity_count=3,
            errors=[],
        )
        clinvar_sec = next(
            s for s in brief.sections if s.heading == "Genomic Variant Data"
        )
        assert "errors" in clinvar_sec.body.lower()


# ---------------------------------------------------------------------------
# Test 5: to_markdown produces valid markdown
# ---------------------------------------------------------------------------


class TestMarkdownOutput:
    def test_markdown_has_title_heading(self) -> None:
        brief = generate_research_brief(
            objective="Markdown test",
            seed_terms=["A", "B"],
            source_results=_full_source_results(),
            documents_ingested=10,
            proposal_count=5,
            entity_count=3,
            errors=[],
        )
        md = brief.to_markdown()
        assert md.startswith("# Research Brief: Markdown test\n")

    def test_markdown_has_section_headings(self) -> None:
        brief = generate_research_brief(
            objective="Markdown test",
            seed_terms=["A"],
            source_results=_full_source_results(),
            documents_ingested=10,
            proposal_count=5,
            entity_count=3,
            errors=[],
        )
        md = brief.to_markdown()
        assert "## Discovery Summary" in md
        assert "## Literature Findings" in md

    def test_markdown_gaps_section(self) -> None:
        brief = generate_research_brief(
            objective="gap test",
            seed_terms=["term"],
            source_results=_pubmed_only_source_results(),
            documents_ingested=5,
            proposal_count=0,
            entity_count=0,
            errors=["Something failed"],
        )
        md = brief.to_markdown()
        assert "## Gaps & Limitations" in md
        assert "- No proposals" in md
        assert "- Error: Something failed" in md

    def test_markdown_next_steps_section(self) -> None:
        brief = generate_research_brief(
            objective="next steps test",
            seed_terms=["term"],
            source_results=_pubmed_only_source_results(),
            documents_ingested=5,
            proposal_count=3,
            entity_count=2,
            errors=[],
        )
        md = brief.to_markdown()
        assert "## Suggested Next Steps" in md

    def test_empty_brief_renders(self) -> None:
        """A brief with no sections, gaps, or next_steps still renders."""
        brief = ResearchBrief(title="Empty", summary="Nothing here.")
        md = brief.to_markdown()
        assert "# Empty" in md
        assert "Nothing here." in md
        assert "## Gaps" not in md
        assert "## Suggested" not in md


# ---------------------------------------------------------------------------
# Test 6: chase rounds mention cross-source discovery
# ---------------------------------------------------------------------------


class TestChaseRounds:
    def test_chase_rounds_mentioned_in_discovery_summary(self) -> None:
        brief = generate_research_brief(
            objective="chase test",
            seed_terms=["term"],
            source_results=_full_source_results(),
            documents_ingested=10,
            proposal_count=5,
            entity_count=3,
            errors=[],
            chase_rounds_completed=3,
        )
        discovery = next(s for s in brief.sections if s.heading == "Discovery Summary")
        assert "**3**" in discovery.body
        assert "cross-source" in discovery.body.lower()

    def test_no_chase_rounds_omits_chase_line(self) -> None:
        brief = generate_research_brief(
            objective="no chase",
            seed_terms=["term"],
            source_results=_full_source_results(),
            documents_ingested=10,
            proposal_count=5,
            entity_count=3,
            errors=[],
            chase_rounds_completed=0,
        )
        discovery = next(s for s in brief.sections if s.heading == "Discovery Summary")
        assert "chase" not in discovery.body.lower()

    def test_chase_rounds_noted_in_gaps(self) -> None:
        brief = generate_research_brief(
            objective="chase test",
            seed_terms=["term"],
            source_results=_full_source_results(),
            documents_ingested=10,
            proposal_count=5,
            entity_count=3,
            errors=[],
            chase_rounds_completed=2,
        )
        assert any("chase round" in g.lower() for g in brief.gaps)


# ---------------------------------------------------------------------------
# Test: store_research_brief calls patch_workspace correctly
# ---------------------------------------------------------------------------


class TestStoreResearchBrief:
    def test_store_calls_patch_workspace(self) -> None:
        brief = ResearchBrief(
            title="Test Brief",
            summary="Summary here.",
            sections=(ResearchBriefSection(heading="Section A", body="Body A"),),
            gaps=("Gap one",),
            next_steps=("Step one",),
        )
        mock_store = MagicMock()
        space_id = uuid4()

        store_research_brief(
            brief=brief,
            artifact_store=mock_store,
            space_id=space_id,
            run_id="run-123",
        )

        mock_store.patch_workspace.assert_called_once()
        call_kwargs = mock_store.patch_workspace.call_args.kwargs
        assert call_kwargs["space_id"] == space_id
        assert call_kwargs["run_id"] == "run-123"
        patch = call_kwargs["patch"]
        rb = patch["research_brief"]
        assert rb["title"] == "Test Brief"
        assert rb["summary"] == "Summary here."
        assert "# Test Brief" in rb["markdown"]
        assert len(rb["sections"]) == 1
        assert rb["sections"][0]["heading"] == "Section A"
        assert rb["gaps"] == ["Gap one"]
        assert rb["next_steps"] == ["Step one"]


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_seed_terms(self) -> None:
        brief = generate_research_brief(
            objective="no seeds",
            seed_terms=[],
            source_results=_pubmed_only_source_results(),
            documents_ingested=0,
            proposal_count=0,
            entity_count=0,
            errors=[],
        )
        assert "(none)" in brief.summary
        assert "no seeds" in brief.summary

    def test_pubmed_zero_discovered_flags_gap(self) -> None:
        source_results = _pubmed_only_source_results()
        source_results["pubmed"]["documents_discovered"] = 0
        source_results["pubmed"]["documents_selected"] = 0
        source_results["pubmed"]["documents_ingested"] = 0

        brief = generate_research_brief(
            objective="no pubmed",
            seed_terms=["term"],
            source_results=source_results,
            documents_ingested=0,
            proposal_count=0,
            entity_count=0,
            errors=[],
        )
        assert any("no results" in g.lower() for g in brief.gaps)

    def test_thin_pubmed_coverage_suggests_upload(self) -> None:
        source_results = _pubmed_only_source_results()
        source_results["pubmed"]["documents_ingested"] = 1

        brief = generate_research_brief(
            objective="thin coverage",
            seed_terms=["term"],
            source_results=source_results,
            documents_ingested=1,
            proposal_count=2,
            entity_count=1,
            errors=[],
        )
        assert any("upload" in s.lower() for s in brief.next_steps)

    def test_singular_plurals(self) -> None:
        """Verify singular forms when counts are 1."""
        source_results = _pubmed_only_source_results()
        source_results["pubmed"]["documents_discovered"] = 1
        source_results["pubmed"]["documents_selected"] = 1
        source_results["pubmed"]["documents_ingested"] = 1
        source_results["pubmed"]["observations_created"] = 1

        brief = generate_research_brief(
            objective="singular",
            seed_terms=["one"],
            source_results=source_results,
            documents_ingested=1,
            proposal_count=1,
            entity_count=1,
            errors=[],
        )
        discovery = next(s for s in brief.sections if s.heading == "Discovery Summary")
        # "1 document" not "1 documents"
        assert "**1** document " in discovery.body
        assert "**1** proposal " in discovery.body
        assert "**1** entity " in discovery.body


# ---------------------------------------------------------------------------
# Test: _synthesize_cross_source_summary
# ---------------------------------------------------------------------------


class TestSynthesizeCrossSourceSummary:
    def test_multiple_active_sources_produces_cross_source_narrative(self) -> None:
        summary = _synthesize_cross_source_summary(
            source_results=_full_source_results(),
            objective="MED13 in neurodevelopmental disorders",
            seed_terms=["MED13", "mediator complex", "neurodevelopment"],
            proposal_count=20,
            entity_count=8,
            chase_rounds_completed=0,
        )
        assert "MED13 in neurodevelopmental disorders" in summary
        assert "MED13, mediator complex, neurodevelopment" in summary
        assert "sources" in summary.lower()
        # Cross-source connection narrative for pubmed+clinvar
        assert "PubMed" in summary
        assert "ClinVar" in summary
        # DrugBank narrative
        assert "DrugBank" in summary
        # MONDO narrative
        assert "MONDO" in summary

    def test_mentions_chase_rounds_when_positive(self) -> None:
        summary = _synthesize_cross_source_summary(
            source_results=_full_source_results(),
            objective="test objective",
            seed_terms=["term"],
            proposal_count=5,
            entity_count=3,
            chase_rounds_completed=2,
        )
        assert "2 additional discovery round" in summary
        assert "connections" in summary.lower()

    def test_omits_chase_narrative_when_zero(self) -> None:
        summary = _synthesize_cross_source_summary(
            source_results=_full_source_results(),
            objective="test objective",
            seed_terms=["term"],
            proposal_count=5,
            entity_count=3,
            chase_rounds_completed=0,
        )
        assert "discovery round" not in summary

    def test_mentions_proposal_count(self) -> None:
        summary = _synthesize_cross_source_summary(
            source_results=_full_source_results(),
            objective="test objective",
            seed_terms=["term"],
            proposal_count=15,
            entity_count=6,
            chase_rounds_completed=0,
        )
        assert "**15 proposals**" in summary
        assert "**6 entities**" in summary

    def test_omits_proposal_narrative_when_zero(self) -> None:
        summary = _synthesize_cross_source_summary(
            source_results=_full_source_results(),
            objective="test objective",
            seed_terms=["term"],
            proposal_count=0,
            entity_count=0,
            chase_rounds_completed=0,
        )
        assert "proposals" not in summary.lower()

    def test_single_source_no_coordination_narrative(self) -> None:
        summary = _synthesize_cross_source_summary(
            source_results=_pubmed_only_source_results(),
            objective="single source",
            seed_terms=["BRCA1"],
            proposal_count=3,
            entity_count=2,
            chase_rounds_completed=0,
        )
        # Only one source completed, so no "sources in coordination" narrative
        assert "in coordination" not in summary

    def test_empty_seed_terms_shows_none(self) -> None:
        summary = _synthesize_cross_source_summary(
            source_results=_pubmed_only_source_results(),
            objective="test",
            seed_terms=[],
            proposal_count=0,
            entity_count=0,
            chase_rounds_completed=0,
        )
        assert "(none)" in summary

    def test_chase_singular_round(self) -> None:
        summary = _synthesize_cross_source_summary(
            source_results=_full_source_results(),
            objective="test",
            seed_terms=["term"],
            proposal_count=5,
            entity_count=3,
            chase_rounds_completed=1,
        )
        assert "1 additional discovery round**" in summary
        assert "rounds**" not in summary


# ---------------------------------------------------------------------------
# Test: generate_llm_research_brief
# ---------------------------------------------------------------------------


class _FakeKernelStore:
    def __init__(self) -> None:
        self.closed = False
        self.kernel: _FakeKernel | None = None

    async def close(self) -> None:
        self.closed = True


class _FakeKernel:
    def __init__(self, *, store, model_port, **kwargs) -> None:
        del kwargs
        self.store = store
        self.model_port = model_port
        self.closed = False
        store.kernel = self

    async def close(self) -> None:
        self.closed = True


class _FakeSingleStepClient:
    def __init__(self, *, kernel) -> None:
        self.kernel = kernel


def _make_deterministic_brief() -> ResearchBrief:
    return ResearchBrief(
        title="Test Brief",
        summary="Deterministic summary.",
        sections=(ResearchBriefSection(heading="Section", body="Body"),),
        gaps=("Gap one",),
        next_steps=("Step one",),
    )


class TestGenerateLlmResearchBrief:
    @pytest.mark.asyncio
    async def test_import_failure_returns_deterministic_brief(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When artana kernel imports fail, falls back to deterministic brief."""
        deterministic = _make_deterministic_brief()

        # Force ImportError by making _generate_brief_with_kernel raise
        async def _raise_import(*_args, **_kwargs):
            raise ImportError("no artana kernel")

        monkeypatch.setattr(
            research_init_brief,
            "_generate_brief_with_kernel",
            _raise_import,
        )

        result = await generate_llm_research_brief(
            objective="test",
            seed_terms=["term"],
            deterministic_brief=deterministic,
            llm_adapter=None,
        )
        assert result is deterministic

    @pytest.mark.asyncio
    async def test_kernel_error_returns_deterministic_brief(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the kernel call fails, falls back to deterministic brief."""
        deterministic = _make_deterministic_brief()

        async def _raise_runtime(*_args, **_kwargs):
            raise RuntimeError("synthetic llm outage")

        monkeypatch.setattr(
            research_init_brief,
            "_generate_brief_with_kernel",
            _raise_runtime,
        )

        result = await generate_llm_research_brief(
            objective="test",
            seed_terms=["term"],
            deterministic_brief=deterministic,
            llm_adapter=None,
        )
        assert result is deterministic

    @pytest.mark.asyncio
    async def test_explicit_adapter_returns_deterministic(self) -> None:
        """When a non-None adapter is passed, deterministic brief is returned."""
        deterministic = ResearchBrief(
            title="Brief",
            summary="Summary.",
        )
        result = await generate_llm_research_brief(
            objective="test",
            seed_terms=[],
            deterministic_brief=deterministic,
            llm_adapter=object(),
        )
        assert result is deterministic

    @pytest.mark.asyncio
    async def test_happy_path_returns_llm_enhanced_brief(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When the kernel succeeds, returns an LLM-enhanced brief."""
        deterministic = _make_deterministic_brief()

        async def _fake_run_single_step(*_args, **kwargs):
            return SimpleNamespace(
                output={
                    "title": "LLM-Enhanced Brief: BRCA1",
                    "summary": "A comprehensive cross-source analysis.",
                    "key_findings": [
                        "Finding 1 across PubMed and ClinVar",
                        "Finding 2 from DrugBank",
                    ],
                    "gaps": ["Missing AlphaFold data", "No MONDO match"],
                    "next_steps": ["Query additional databases"],
                },
            )

        def _create_store() -> _FakeKernelStore:
            return _FakeKernelStore()

        monkeypatch.setattr(
            runtime_support,
            "get_model_registry",
            lambda: SimpleNamespace(
                get_default_model=lambda _capability: SimpleNamespace(
                    model_id="openai:gpt-5.4-mini",
                ),
            ),
        )
        monkeypatch.setattr(
            runtime_support,
            "normalize_litellm_model_id",
            lambda model_id: model_id,
        )
        monkeypatch.setattr(
            runtime_support,
            "create_artana_postgres_store",
            _create_store,
        )
        monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
        monkeypatch.setattr(
            "artana.agent.SingleStepModelClient",
            _FakeSingleStepClient,
        )
        monkeypatch.setattr(
            step_helpers,
            "run_single_step_with_policy",
            _fake_run_single_step,
        )

        result = await generate_llm_research_brief(
            objective="BRCA1 research",
            seed_terms=["BRCA1"],
            deterministic_brief=deterministic,
        )

        assert result.title == "LLM-Enhanced Brief: BRCA1"
        assert result.summary == "A comprehensive cross-source analysis."
        assert result.gaps == ("Missing AlphaFold data", "No MONDO match")
        assert result.next_steps == ("Query additional databases",)
        # Sections are preserved from deterministic brief
        assert result.sections == deterministic.sections

    @pytest.mark.asyncio
    async def test_happy_path_preserves_deterministic_sections(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The per-source sections from the deterministic brief are kept."""
        sections = (
            ResearchBriefSection(heading="Literature Findings", body="Papers found"),
            ResearchBriefSection(heading="Genomic Variant Data", body="Variants"),
        )
        deterministic = ResearchBrief(
            title="Original",
            summary="Original summary.",
            sections=sections,
            gaps=("Original gap",),
            next_steps=("Original step",),
        )

        async def _fake_run_single_step(*_args, **kwargs):
            return SimpleNamespace(
                output={
                    "title": "LLM Title",
                    "summary": "LLM summary.",
                    "key_findings": ["Finding 1"],
                    "gaps": ["LLM gap"],
                    "next_steps": ["LLM step"],
                },
            )

        def _create_store() -> _FakeKernelStore:
            return _FakeKernelStore()

        monkeypatch.setattr(
            runtime_support,
            "get_model_registry",
            lambda: SimpleNamespace(
                get_default_model=lambda _capability: SimpleNamespace(
                    model_id="openai:gpt-5.4-mini",
                ),
            ),
        )
        monkeypatch.setattr(
            runtime_support,
            "normalize_litellm_model_id",
            lambda model_id: model_id,
        )
        monkeypatch.setattr(
            runtime_support,
            "create_artana_postgres_store",
            _create_store,
        )
        monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
        monkeypatch.setattr(
            "artana.agent.SingleStepModelClient",
            _FakeSingleStepClient,
        )
        monkeypatch.setattr(
            step_helpers,
            "run_single_step_with_policy",
            _fake_run_single_step,
        )

        result = await generate_llm_research_brief(
            objective="test",
            seed_terms=["term"],
            deterministic_brief=deterministic,
        )

        # Per-source sections preserved from deterministic brief
        assert result.sections == sections
        # Summary, gaps, next_steps come from LLM
        assert result.summary == "LLM summary."
        assert result.gaps == ("LLM gap",)
        assert result.next_steps == ("LLM step",)

    @pytest.mark.asyncio
    async def test_empty_llm_gaps_falls_back_to_deterministic(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When LLM returns empty gaps/next_steps, deterministic ones are used."""
        deterministic = _make_deterministic_brief()

        async def _fake_run_single_step(*_args, **kwargs):
            return SimpleNamespace(
                output={
                    "title": "LLM Title",
                    "summary": "LLM summary.",
                    "key_findings": ["Finding"],
                    "gaps": [],
                    "next_steps": [],
                },
            )

        def _create_store() -> _FakeKernelStore:
            return _FakeKernelStore()

        monkeypatch.setattr(
            runtime_support,
            "get_model_registry",
            lambda: SimpleNamespace(
                get_default_model=lambda _capability: SimpleNamespace(
                    model_id="openai:gpt-5.4-mini",
                ),
            ),
        )
        monkeypatch.setattr(
            runtime_support,
            "normalize_litellm_model_id",
            lambda model_id: model_id,
        )
        monkeypatch.setattr(
            runtime_support,
            "create_artana_postgres_store",
            _create_store,
        )
        monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
        monkeypatch.setattr(
            "artana.agent.SingleStepModelClient",
            _FakeSingleStepClient,
        )
        monkeypatch.setattr(
            step_helpers,
            "run_single_step_with_policy",
            _fake_run_single_step,
        )

        result = await generate_llm_research_brief(
            objective="test",
            seed_terms=["term"],
            deterministic_brief=deterministic,
        )

        # Empty LLM gaps/next_steps -> fall back to deterministic
        assert result.gaps == deterministic.gaps
        assert result.next_steps == deterministic.next_steps

    @pytest.mark.asyncio
    async def test_store_closed_on_success(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The postgres store is closed after successful LLM generation."""
        deterministic = _make_deterministic_brief()
        created_stores: list[_FakeKernelStore] = []

        async def _fake_run_single_step(*_args, **kwargs):
            return SimpleNamespace(
                output={
                    "title": "Title",
                    "summary": "Summary.",
                    "key_findings": ["Finding"],
                    "gaps": ["Gap"],
                    "next_steps": ["Step"],
                },
            )

        def _create_store() -> _FakeKernelStore:
            store = _FakeKernelStore()
            created_stores.append(store)
            return store

        monkeypatch.setattr(
            runtime_support,
            "get_model_registry",
            lambda: SimpleNamespace(
                get_default_model=lambda _capability: SimpleNamespace(
                    model_id="openai:gpt-5.4-mini",
                ),
            ),
        )
        monkeypatch.setattr(
            runtime_support,
            "normalize_litellm_model_id",
            lambda model_id: model_id,
        )
        monkeypatch.setattr(
            runtime_support,
            "create_artana_postgres_store",
            _create_store,
        )
        monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
        monkeypatch.setattr(
            "artana.agent.SingleStepModelClient",
            _FakeSingleStepClient,
        )
        monkeypatch.setattr(
            step_helpers,
            "run_single_step_with_policy",
            _fake_run_single_step,
        )

        await generate_llm_research_brief(
            objective="test",
            seed_terms=["term"],
            deterministic_brief=deterministic,
        )

        assert len(created_stores) == 1
        assert created_stores[0].closed is True

    @pytest.mark.asyncio
    async def test_store_closed_on_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The postgres store is closed even when the LLM call fails."""
        deterministic = _make_deterministic_brief()
        created_stores: list[_FakeKernelStore] = []

        async def _boom(*_args, **kwargs):
            raise RuntimeError("synthetic llm outage")

        def _create_store() -> _FakeKernelStore:
            store = _FakeKernelStore()
            created_stores.append(store)
            return store

        monkeypatch.setattr(
            runtime_support,
            "get_model_registry",
            lambda: SimpleNamespace(
                get_default_model=lambda _capability: SimpleNamespace(
                    model_id="openai:gpt-5.4-mini",
                ),
            ),
        )
        monkeypatch.setattr(
            runtime_support,
            "normalize_litellm_model_id",
            lambda model_id: model_id,
        )
        monkeypatch.setattr(
            runtime_support,
            "create_artana_postgres_store",
            _create_store,
        )
        monkeypatch.setattr("artana.kernel.ArtanaKernel", _FakeKernel)
        monkeypatch.setattr(
            "artana.agent.SingleStepModelClient",
            _FakeSingleStepClient,
        )
        monkeypatch.setattr(
            step_helpers,
            "run_single_step_with_policy",
            _boom,
        )

        result = await generate_llm_research_brief(
            objective="test",
            seed_terms=["term"],
            deterministic_brief=deterministic,
        )

        # Fallback to deterministic
        assert result is deterministic
        # Store still closed
        assert len(created_stores) == 1
        assert created_stores[0].closed is True


# ---------------------------------------------------------------------------
# compute_cross_source_overlaps
# ---------------------------------------------------------------------------


class TestComputeCrossSourceOverlaps:
    """The deterministic helper that grounds LLM brief synthesis."""

    def test_returns_empty_for_no_proposals(self) -> None:
        assert compute_cross_source_overlaps([]) == ()

    def test_finds_entity_in_two_sources(self) -> None:
        proposals = [
            {
                "source_kind": "document_extraction",
                "payload": {
                    "proposed_subject_label": "BRCA1",
                    "proposed_object_label": "breast cancer",
                },
                "metadata": {},
            },
            {
                "source_kind": "clinvar_enrichment",
                "payload": {
                    "proposed_subject_label": "BRCA1",
                    "proposed_object_label": "c.5266dupC",
                },
                "metadata": {},
            },
        ]

        overlaps = compute_cross_source_overlaps(proposals)
        labels = {o.entity_label for o in overlaps}
        assert "BRCA1" in labels
        brca1 = next(o for o in overlaps if o.entity_label == "BRCA1")
        assert brca1.source_kinds == ("clinvar_enrichment", "document_extraction")
        assert brca1.proposal_count == 2

    def test_skips_entity_in_single_source(self) -> None:
        proposals = [
            {
                "source_kind": "document_extraction",
                "payload": {"proposed_subject_label": "MED13"},
                "metadata": {},
            },
            {
                "source_kind": "document_extraction",
                "payload": {"proposed_subject_label": "MED13"},
                "metadata": {},
            },
        ]

        overlaps = compute_cross_source_overlaps(proposals)
        assert overlaps == ()

    def test_orders_by_source_count_then_proposal_count(self) -> None:
        proposals = [
            # PARP1: 3 sources, 4 proposals
            {
                "source_kind": "document_extraction",
                "payload": {"proposed_subject_label": "PARP1"},
                "metadata": {},
            },
            {
                "source_kind": "drugbank_enrichment",
                "payload": {"proposed_object_label": "PARP1"},
                "metadata": {},
            },
            {
                "source_kind": "alphafold_enrichment",
                "payload": {"proposed_subject_label": "PARP1"},
                "metadata": {},
            },
            {
                "source_kind": "drugbank_enrichment",
                "payload": {"proposed_object_label": "PARP1"},
                "metadata": {},
            },
            # BRCA1: 2 sources, 2 proposals
            {
                "source_kind": "document_extraction",
                "payload": {"proposed_subject_label": "BRCA1"},
                "metadata": {},
            },
            {
                "source_kind": "clinvar_enrichment",
                "payload": {"proposed_subject_label": "BRCA1"},
                "metadata": {},
            },
        ]

        overlaps = compute_cross_source_overlaps(proposals)
        assert overlaps[0].entity_label == "PARP1"
        assert len(overlaps[0].source_kinds) == 3
        assert overlaps[1].entity_label == "BRCA1"
        assert len(overlaps[1].source_kinds) == 2

    def test_uses_metadata_labels_when_payload_missing(self) -> None:
        proposals = [
            {
                "source_kind": "document_extraction",
                "payload": {},
                "metadata": {"subject_label": "TP53", "object_label": "apoptosis"},
            },
            {
                "source_kind": "clinvar_enrichment",
                "payload": {},
                "metadata": {"subject_label": "TP53", "object_label": "Li-Fraumeni"},
            },
        ]

        overlaps = compute_cross_source_overlaps(proposals)
        labels = {o.entity_label for o in overlaps}
        assert "TP53" in labels


# ---------------------------------------------------------------------------
# generate_research_brief — proposals integration
# ---------------------------------------------------------------------------


class TestGenerateResearchBriefWithProposals:
    """Verify cross-source overlaps appear when proposals are provided."""

    def test_brief_includes_cross_source_overlaps(self) -> None:
        proposals = [
            {
                "source_kind": "document_extraction",
                "payload": {"proposed_subject_label": "BRCA1"},
                "metadata": {},
            },
            {
                "source_kind": "clinvar_enrichment",
                "payload": {"proposed_subject_label": "BRCA1"},
                "metadata": {},
            },
        ]
        brief = generate_research_brief(
            objective="BRCA1 in breast cancer",
            seed_terms=["BRCA1"],
            source_results={},
            documents_ingested=5,
            proposal_count=2,
            entity_count=3,
            errors=[],
            chase_rounds_completed=0,
            proposals=proposals,
        )

        assert len(brief.cross_source_overlaps) == 1
        assert brief.cross_source_overlaps[0].entity_label == "BRCA1"

    def test_brief_omits_overlaps_when_no_proposals(self) -> None:
        brief = generate_research_brief(
            objective="x",
            seed_terms=[],
            source_results={},
            documents_ingested=0,
            proposal_count=0,
            entity_count=0,
            errors=[],
        )
        assert brief.cross_source_overlaps == ()

    def test_markdown_renders_overlaps_section(self) -> None:
        brief = ResearchBrief(
            title="Test",
            summary="Summary.",
            cross_source_overlaps=(
                CrossSourceOverlap(
                    entity_label="BRCA1",
                    source_kinds=("clinvar_enrichment", "document_extraction"),
                    proposal_count=3,
                ),
            ),
        )
        markdown = brief.to_markdown()
        assert "Cross-Source Connections" in markdown
        assert "BRCA1" in markdown
        assert "3 proposals" in markdown
