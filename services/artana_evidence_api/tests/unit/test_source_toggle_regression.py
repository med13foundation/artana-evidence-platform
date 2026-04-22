"""Regression tests for research-init source toggles and MARRVEL helpers."""

from __future__ import annotations

import logging

import pytest
from artana_evidence_api import marrvel_enrichment
from artana_evidence_api.marrvel_enrichment import (
    MARRVEL_API_BASE_URL,
    MARRVEL_API_FALLBACK_BASE_URL,
    MarrvelPhenotypeAssociation,
    build_marrvel_proposal_drafts,
    parse_marrvel_gene_symbols,
    prioritize_marrvel_gene_labels,
)
from artana_evidence_api.routers.research_init import (
    ResearchInitRequest,
    _build_pubmed_queries,
    _build_scope_refinement_questions,
    _resolve_research_init_sources,
    _resolve_research_orchestration_mode,
)


class TestPubMedQueryGeneration:
    """Verify PubMed queries are only built when PubMed is enabled."""

    def test_pubmed_queries_generated_when_enabled(self) -> None:
        queries = _build_pubmed_queries("Investigate BRCA1 in breast cancer", ["BRCA1"])
        assert len(queries) > 0

    def test_empty_queries_when_pubmed_disabled(self) -> None:
        _pubmed_enabled = False
        queries = _build_pubmed_queries("test", ["test"]) if _pubmed_enabled else []
        assert queries == []

    def test_pubmed_queries_with_seed_terms(self) -> None:
        queries = _build_pubmed_queries(
            "MED13 syndrome and developmental delay",
            ["MED13", "developmental delay"],
        )
        assert len(queries) >= 1


class TestSourcesConfigParsing:
    """Verify the sources config is resolved from request or persisted settings."""

    def test_default_sources_all_enabled(self) -> None:
        resolved = _resolve_research_init_sources(
            request_sources=None,
            space_settings=None,
        )
        assert resolved == {
            "pubmed": True,
            "marrvel": True,
            "clinvar": True,
            "mondo": True,
            "pdf": True,
            "text": True,
            "drugbank": False,
            "alphafold": False,
            "uniprot": False,
            "hgnc": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
        }

    def test_request_sources_override_saved_settings(self) -> None:
        resolved = _resolve_research_init_sources(
            request_sources={
                "pubmed": False,
                "marrvel": True,
                "pdf": False,
                "text": False,
            },
            space_settings={
                "sources": {
                    "pubmed": True,
                    "marrvel": False,
                    "pdf": True,
                    "text": True,
                },
            },
        )
        assert resolved == {
            "pubmed": False,
            "marrvel": True,
            "clinvar": False,
            "mondo": False,
            "pdf": False,
            "text": False,
            "drugbank": False,
            "alphafold": False,
            "uniprot": False,
            "hgnc": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
        }

    def test_partial_request_sources_are_authoritative(self) -> None:
        resolved = _resolve_research_init_sources(
            request_sources={
                "pubmed": True,
                "hgnc": True,
            },
            space_settings={
                "sources": {
                    "marrvel": True,
                    "clinvar": True,
                    "mondo": True,
                },
            },
        )

        assert resolved == {
            "pubmed": True,
            "marrvel": False,
            "clinvar": False,
            "mondo": False,
            "pdf": False,
            "text": False,
            "drugbank": False,
            "alphafold": False,
            "uniprot": False,
            "hgnc": True,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
        }

    def test_saved_settings_apply_when_request_omits_sources(self) -> None:
        resolved = _resolve_research_init_sources(
            request_sources=None,
            space_settings={
                "sources": {
                    "pubmed": False,
                    "marrvel": True,
                    "pdf": False,
                    "text": False,
                },
            },
        )
        assert resolved == {
            "pubmed": False,
            "marrvel": True,
            "clinvar": True,
            "mondo": True,
            "pdf": False,
            "text": False,
            "drugbank": False,
            "alphafold": False,
            "uniprot": False,
            "hgnc": False,
            "clinical_trials": False,
            "mgi": False,
            "zfin": False,
        }


class TestResearchOrchestrationModeParsing:
    """Verify research-init defaults to guarded mode and supports overrides."""

    def test_default_orchestration_mode_is_guarded_source_chase(self) -> None:
        resolved = _resolve_research_orchestration_mode(
            request_mode=None,
            space_settings=None,
        )

        assert resolved == "full_ai_guarded"

    def test_request_mode_overrides_saved_mode(self) -> None:
        resolved = _resolve_research_orchestration_mode(
            request_mode="deterministic",
            space_settings={"research_orchestration_mode": "full_ai_guarded"},
        )

        assert resolved == "deterministic"

    def test_saved_shadow_mode_is_used_when_request_omits_mode(self) -> None:
        resolved = _resolve_research_orchestration_mode(
            request_mode=None,
            space_settings={"research_orchestration_mode": "full_ai_shadow"},
        )

        assert resolved == "full_ai_shadow"


class TestOnboardingMessageSourceAwareness:
    """Verify onboarding messages remain source-neutral."""

    def test_scope_refinement_questions_no_pubmed_mention(self) -> None:
        questions = _build_scope_refinement_questions(
            objective="Investigate MED13 syndrome",
            seed_terms=["MED13"],
        )
        assert len(questions) >= 1
        for question in questions:
            assert "PubMed" not in question

    def test_scope_refinement_uses_generic_language(self) -> None:
        questions = _build_scope_refinement_questions(
            objective="covid19 mechanisms",
            seed_terms=[],
        )
        assert any("research pass" in question for question in questions)


class TestMarrvelEnrichmentHelpers:
    """Verify the shared MARRVEL helper behavior used by bootstrap and init."""

    def test_marrvel_api_base_url_correct(self) -> None:
        assert MARRVEL_API_BASE_URL == "https://api.marrvel.org/data"
        assert MARRVEL_API_FALLBACK_BASE_URL == "http://api.marrvel.org/data"

    def test_prioritize_marrvel_gene_labels_filters_non_gene_noise(self) -> None:
        prioritized = prioritize_marrvel_gene_labels(
            ["ADHD", "BRCA1", "ASD", "MED13", "TP53"],
            objective="Investigate MED13 syndrome",
            limit=3,
        )
        assert prioritized == ["MED13", "BRCA1", "TP53"]

    def test_resolve_gene_labels_falls_back_to_llm_when_graph_lookup_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        class _FailingGraphGateway:
            def list_entities(
                self,
                *,
                space_id: str,
                entity_type: str,
                limit: int,
            ) -> None:
                del space_id, entity_type, limit
                raise RuntimeError("graph unavailable")

        monkeypatch.setattr(
            marrvel_enrichment,
            "infer_marrvel_gene_labels_from_objective",
            lambda **_kwargs: ["MED13"],
        )

        labels = marrvel_enrichment.resolve_marrvel_gene_labels(
            space_id="space-1",  # type: ignore[arg-type]
            objective="Investigate MED13 syndrome",
            graph_api_gateway=_FailingGraphGateway(),  # type: ignore[arg-type]
            logger=logging.getLogger(__name__),
        )

        assert labels == ["MED13"]

    def test_parse_marrvel_gene_symbols_handles_none_response(self) -> None:
        gene_labels = parse_marrvel_gene_symbols(
            "NONE",
            objective="Investigate MED13 syndrome",
        )
        assert gene_labels == []

    def test_parse_marrvel_gene_symbols_parses_comma_separated_values(self) -> None:
        gene_labels = parse_marrvel_gene_symbols(
            "MED13, MED13L, CDK8, CCNC",
            objective="Investigate MED13 syndrome",
        )
        assert gene_labels == ["MED13", "MED13L", "CDK8"]

    def test_parse_marrvel_gene_symbols_filters_long_tokens(self) -> None:
        gene_labels = parse_marrvel_gene_symbols(
            "BRCA1, VERY_LONG_GENE_NAME_HERE, TP53",
            objective="Investigate BRCA1 and TP53",
        )
        assert gene_labels == ["BRCA1", "TP53"]

    def test_parse_marrvel_gene_symbols_limits_to_five(self) -> None:
        gene_labels = parse_marrvel_gene_symbols(
            "A1, B2, C3, D4, E5, F6, G7, H8",
            objective="Investigate A1",
        )
        assert len(gene_labels) == 5

    def test_build_marrvel_proposal_drafts_uses_associated_with_claims(self) -> None:
        drafts = build_marrvel_proposal_drafts(
            [
                MarrvelPhenotypeAssociation(
                    gene_symbol="MED13",
                    phenotype_label="developmental delay",
                ),
            ],
        )

        assert len(drafts) == 1
        draft = drafts[0]
        assert draft.payload["proposed_claim_type"] == "ASSOCIATED_WITH"
        assert draft.source_key == "marrvel:omim:MED13:developmental delay"
        assert draft.confidence == 0.5
        assert draft.ranking_score == 0.5
        assert draft.evidence_bundle[0]["locator"] == "marrvel:omim:MED13"
        assert draft.metadata["requires_qualitative_review"] is True
        assert draft.metadata["direct_graph_promotion_allowed"] is False


class TestResearchInitRequestSources:
    """Verify the request model accepts source toggles."""

    def test_request_accepts_sources(self) -> None:
        request = ResearchInitRequest(
            objective="Test objective",
            sources={"pubmed": False, "marrvel": True},
        )
        assert request.sources is not None
        assert request.sources["pubmed"] is False
        assert request.sources["marrvel"] is True

    def test_request_sources_defaults_to_none(self) -> None:
        request = ResearchInitRequest(objective="Test objective")
        assert request.sources is None

    def test_request_with_all_fields(self) -> None:
        request = ResearchInitRequest(
            objective="Investigate BRCA1",
            seed_terms=["BRCA1"],
            title="Test",
            max_depth=2,
            max_hypotheses=10,
            sources={"pubmed": True, "marrvel": True, "pdf": False, "text": False},
        )
        assert request.objective == "Investigate BRCA1"
        assert request.sources["pdf"] is False
