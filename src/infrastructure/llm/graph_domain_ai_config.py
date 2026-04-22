"""AI-side graph-domain config selected by the active graph pack."""

from __future__ import annotations

from src.domain.agents.graph_domain_ai_contracts import (
    BootstrapRelationConstraintDefinition,
    BootstrapRelationTypeDefinition,
    BootstrapVariableDefinition,
    DomainBootstrapEntityTypes,
    EntityRecognitionBootstrapConfig,
    EntityRecognitionCompactRecordRule,
    EntityRecognitionHeuristicFieldMap,
    EntityRecognitionPayloadConfig,
    EntityRecognitionPromptConfig,
    ExtractionCompactRecordRule,
    ExtractionHeuristicConfig,
    ExtractionHeuristicRelation,
    ExtractionPayloadConfig,
    ExtractionPromptConfig,
    GraphConnectionPromptConfig,
    GraphDomainAiConfig,
    GraphSearchConfig,
)
from src.infrastructure.llm.prompts.entity_recognition.clinvar import (
    CLINVAR_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT,
    CLINVAR_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.entity_recognition.marrvel import (
    MARRVEL_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT,
    MARRVEL_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.entity_recognition.pubmed import (
    PUBMED_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT,
    PUBMED_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.extraction.clinvar import (
    CLINVAR_EXTRACTION_DISCOVERY_SYSTEM_PROMPT,
    CLINVAR_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.extraction.marrvel import (
    MARRVEL_EXTRACTION_DISCOVERY_SYSTEM_PROMPT,
    MARRVEL_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.extraction.pubmed import (
    PUBMED_EXTRACTION_DISCOVERY_SYSTEM_PROMPT,
    PUBMED_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.graph_connection.clinvar import (
    CLINVAR_GRAPH_CONNECTION_DISCOVERY_SYSTEM_PROMPT,
    CLINVAR_GRAPH_CONNECTION_SYNTHESIS_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.graph_connection.pubmed import (
    PUBMED_GRAPH_CONNECTION_DISCOVERY_SYSTEM_PROMPT,
    PUBMED_GRAPH_CONNECTION_SYNTHESIS_SYSTEM_PROMPT,
)
from src.infrastructure.llm.prompts.graph_search import GRAPH_SEARCH_SYSTEM_PROMPT

BIOMEDICAL_ENTITY_RECOGNITION_BOOTSTRAP = EntityRecognitionBootstrapConfig(
    default_relation_type="ASSOCIATED_WITH",
    default_relation_display_name="Associated With",
    default_relation_description=(
        "Generic bootstrap relation for domain initialization and cross-entity linkage."
    ),
    default_relation_inverse_label="ASSOCIATED_WITH",
    interaction_relation_type="PHYSICALLY_INTERACTS_WITH",
    interaction_relation_display_name="Physically Interacts With",
    interaction_relation_description=(
        "Physical interaction relation for molecular entities derived from curated evidence."
    ),
    interaction_relation_inverse_label="PHYSICALLY_INTERACTS_WITH",
    min_entity_types_for_default_relation=2,
    interaction_entity_types=("GENE", "PROTEIN"),
    domain_entity_types=(
        DomainBootstrapEntityTypes(
            domain_context="genomics",
            entity_types=("GENE", "PROTEIN", "VARIANT", "PHENOTYPE"),
        ),
        DomainBootstrapEntityTypes(
            domain_context="clinical",
            entity_types=("PATIENT", "PHENOTYPE", "PUBLICATION"),
        ),
        DomainBootstrapEntityTypes(
            domain_context="general",
            entity_types=("SUBJECT", "PHENOTYPE"),
        ),
    ),
    source_types_with_publication_baseline=("pubmed",),
    publication_baseline_source_label="pubmed",
    publication_baseline_entity_description=(
        "PubMed publication-graph bootstrap entity type used for relation validation."
    ),
    publication_baseline_entity_types=(
        "PUBLICATION",
        "AUTHOR",
        "KEYWORD",
        "GENE",
        "PROTEIN",
        "VARIANT",
        "PHENOTYPE",
        "DRUG",
        "MECHANISM",
    ),
    publication_baseline_relation_types=(
        BootstrapRelationTypeDefinition(
            relation_type="MENTIONS",
            display_name="Mentions",
            description="Publication reference relationship for documented entities.",
            is_directional=True,
            inverse_label="MENTIONED_BY",
        ),
        BootstrapRelationTypeDefinition(
            relation_type="SUPPORTS",
            display_name="Supports",
            description="Publication evidence support relationship.",
            is_directional=True,
            inverse_label="SUPPORTED_BY",
        ),
        BootstrapRelationTypeDefinition(
            relation_type="CITES",
            display_name="Cites",
            description="Citation relationship between publications.",
            is_directional=True,
            inverse_label="CITED_BY",
        ),
        BootstrapRelationTypeDefinition(
            relation_type="HAS_AUTHOR",
            display_name="Has Author",
            description="Authorship relationship from publication to author entity.",
            is_directional=True,
            inverse_label="AUTHOR_OF",
        ),
        BootstrapRelationTypeDefinition(
            relation_type="HAS_KEYWORD",
            display_name="Has Keyword",
            description="Keyword tagging relationship from publication to keyword entity.",
            is_directional=True,
            inverse_label="KEYWORD_OF",
        ),
    ),
    publication_baseline_constraints=(
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="MENTIONS",
            target_type="GENE",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="MENTIONS",
            target_type="PROTEIN",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="MENTIONS",
            target_type="VARIANT",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="MENTIONS",
            target_type="PHENOTYPE",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="MENTIONS",
            target_type="DRUG",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="SUPPORTS",
            target_type="GENE",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="SUPPORTS",
            target_type="PROTEIN",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="SUPPORTS",
            target_type="VARIANT",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="SUPPORTS",
            target_type="MECHANISM",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="HAS_AUTHOR",
            target_type="AUTHOR",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="HAS_KEYWORD",
            target_type="KEYWORD",
            requires_evidence=False,
        ),
        BootstrapRelationConstraintDefinition(
            source_type="PUBLICATION",
            relation_type="CITES",
            target_type="PUBLICATION",
            requires_evidence=False,
        ),
    ),
    publication_metadata_variables=(
        BootstrapVariableDefinition(
            variable_id="VAR_PUBLICATION_TITLE",
            canonical_name="publication_title",
            display_name="Publication Title",
            data_type="STRING",
            description="Title of the academic publication.",
            constraints=None,
            synonyms=("title", "paper_title", "publication_title"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_ABSTRACT",
            canonical_name="abstract",
            display_name="Abstract",
            data_type="STRING",
            description="Publication abstract text.",
            constraints=None,
            synonyms=("abstract", "abstract_text"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_PUBLICATION_YEAR",
            canonical_name="publication_year",
            display_name="Publication Year",
            data_type="INTEGER",
            description="Year of publication.",
            constraints={"min": 1900, "max": 2100},
            synonyms=("publication_year", "year", "pub_year"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_PUBLICATION_DATE",
            canonical_name="publication_date",
            display_name="Publication Date",
            data_type="DATE",
            description="Calendar publication date for the article.",
            constraints=None,
            synonyms=("publication_date", "pub_date", "date_published"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_JOURNAL_NAME",
            canonical_name="journal_name",
            display_name="Journal Name",
            data_type="STRING",
            description="Journal of publication.",
            constraints=None,
            synonyms=("journal", "journal_name"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_PUBMED_ID",
            canonical_name="pubmed_id",
            display_name="PubMed ID",
            data_type="STRING",
            description="PubMed stable identifier for a publication.",
            constraints=None,
            synonyms=("pubmed_id", "pmid"),
        ),
        BootstrapVariableDefinition(
            variable_id="VAR_DOI",
            canonical_name="doi",
            display_name="DOI",
            data_type="STRING",
            description="Digital Object Identifier for a publication.",
            constraints=None,
            synonyms=("doi",),
        ),
    ),
)

BIOMEDICAL_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP = EntityRecognitionHeuristicFieldMap(
    source_type_fields={
        "clinvar": {
            "variant": ("clinvar_id", "variation_id", "accession", "hgvs"),
            "gene": ("gene_symbol", "gene", "hgnc_id"),
            "phenotype": ("condition", "disease_name", "phenotype"),
            "publication": ("title", "pubmed_id", "doi"),
        },
        "file_upload": {
            "variant": ("hgvs", "variant"),
            "gene": ("gene_symbol", "gene", "hgnc_id"),
            "phenotype": ("condition", "disease", "phenotype"),
            "publication": ("title", "filename"),
        },
        "marrvel": {
            "gene": ("gene_symbol", "gene", "hgnc_id", "gene_info"),
            "variant": ("clinvar_entries", "dbnsfp_variants", "geno2mp_entries"),
            "phenotype": ("omim_entries", "clinvar_entries"),
            "publication": ("pharos_targets", "gtex_expression"),
        },
        "pubmed": {
            "variant": ("hgvs", "variant"),
            "gene": ("gene_symbol", "gene", "hgnc_id"),
            "phenotype": ("condition", "disease", "phenotype"),
            "publication": ("title", "pubmed_id", "pmid", "doi"),
        },
    },
    default_source_type="clinvar",
    primary_entity_types={
        "clinvar": "VARIANT",
        "file_upload": "PUBLICATION",
        "marrvel": "GENE",
        "pubmed": "PUBLICATION",
    },
)

BIOMEDICAL_ENTITY_RECOGNITION_PAYLOAD_CONFIG = EntityRecognitionPayloadConfig(
    compact_record_rules={
        "pubmed": EntityRecognitionCompactRecordRule(
            fields=(
                "pubmed_id",
                "title",
                "doi",
                "source",
                "full_text_source",
                "full_text_chunk_index",
                "full_text_chunk_total",
                "full_text_chunk_start_char",
                "full_text_chunk_end_char",
                "publication_date",
                "publication_types",
                "journal",
                "keywords",
            ),
            preferred_text_fields=("full_text", "abstract"),
        ),
        "file_upload": EntityRecognitionCompactRecordRule(
            fields=(
                "title",
                "filename",
                "media_type",
                "source",
                "page_count",
                "full_text_source",
            ),
            preferred_text_fields=("full_text", "text"),
        ),
        "marrvel": EntityRecognitionCompactRecordRule(
            fields=(
                "gene_symbol",
                "taxon_id",
                "record_type",
                "source",
                "fetched_at",
                "marrvel_grounding",
                "gene_info",
                "omim_entries",
                "dbnsfp_variants",
                "clinvar_entries",
                "geno2mp_entries",
                "gnomad_gene",
                "dgv_entries",
                "diopt_orthologs",
                "diopt_alignments",
                "gtex_expression",
                "ortholog_expression",
                "pharos_targets",
            ),
            preferred_text_fields=("gene_info",),
        ),
        "clinvar": EntityRecognitionCompactRecordRule(
            fields=(
                "variation_id",
                "gene_symbol",
                "variant_name",
                "clinical_significance",
                "condition_name",
                "review_status",
                "submission_count",
                "source",
            ),
        ),
    },
)

BIOMEDICAL_ENTITY_RECOGNITION_PROMPT_CONFIG = EntityRecognitionPromptConfig(
    system_prompts_by_source_type={
        "clinvar": (
            f"{CLINVAR_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{CLINVAR_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT}"
        ),
        "file_upload": (
            f"{PUBMED_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{PUBMED_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT}"
        ),
        "marrvel": (
            f"{MARRVEL_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{MARRVEL_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT}"
        ),
        "pubmed": (
            f"{PUBMED_ENTITY_RECOGNITION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{PUBMED_ENTITY_RECOGNITION_POLICY_SYSTEM_PROMPT}"
        ),
    },
)

BIOMEDICAL_EXTRACTION_HEURISTIC_CONFIG = ExtractionHeuristicConfig(
    relation_when_variant_and_phenotype_present=ExtractionHeuristicRelation(
        source_type="VARIANT",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        polarity="UNCERTAIN",
    ),
    claim_text_fields=("abstract", "text", "full_text", "title"),
)

BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG = ExtractionPayloadConfig(
    compact_record_rules={
        "pubmed": ExtractionCompactRecordRule(
            fields=(
                "pubmed_id",
                "title",
                "abstract",
                "full_text",
                "keywords",
                "journal",
                "publication_date",
                "publication_types",
                "doi",
                "source",
                "full_text_source",
                "full_text_chunk_index",
                "full_text_chunk_total",
                "full_text_chunk_start_char",
                "full_text_chunk_end_char",
            ),
            chunk_fields=(
                "pubmed_id",
                "title",
                "doi",
                "source",
                "full_text",
                "full_text_source",
                "full_text_chunk_index",
                "full_text_chunk_total",
                "full_text_chunk_start_char",
                "full_text_chunk_end_char",
            ),
            chunk_indicator_field="full_text_chunk_index",
            fallback_text_field="text",
        ),
        "marrvel": ExtractionCompactRecordRule(
            fields=(
                "gene_symbol",
                "taxon_id",
                "record_type",
                "source",
                "fetched_at",
                "marrvel_grounding",
                "gene_info",
                "omim_entries",
                "dbnsfp_variants",
                "clinvar_entries",
                "geno2mp_entries",
                "gnomad_gene",
                "dgv_entries",
                "diopt_orthologs",
                "diopt_alignments",
                "gtex_expression",
                "ortholog_expression",
                "pharos_targets",
            ),
            fallback_text_field="gene_info",
        ),
        "clinvar": ExtractionCompactRecordRule(
            fields=(
                "variation_id",
                "gene_symbol",
                "variant_name",
                "clinical_significance",
                "condition_name",
                "review_status",
                "submission_count",
                "source",
            ),
        ),
    },
)

BIOMEDICAL_EXTRACTION_PROMPT_CONFIG = ExtractionPromptConfig(
    system_prompts_by_source_type={
        "clinvar": (
            f"{CLINVAR_EXTRACTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{CLINVAR_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT}"
        ),
        "marrvel": (
            f"{MARRVEL_EXTRACTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{MARRVEL_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT}"
        ),
        "pubmed": (
            f"{PUBMED_EXTRACTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{PUBMED_EXTRACTION_SYNTHESIS_SYSTEM_PROMPT}"
        ),
    },
)

BIOMEDICAL_GRAPH_CONNECTION_PROMPT_CONFIG = GraphConnectionPromptConfig(
    default_source_type="clinvar",
    system_prompts_by_source_type={
        "clinvar": (
            f"{CLINVAR_GRAPH_CONNECTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{CLINVAR_GRAPH_CONNECTION_SYNTHESIS_SYSTEM_PROMPT}"
        ),
        "pubmed": (
            f"{PUBMED_GRAPH_CONNECTION_DISCOVERY_SYSTEM_PROMPT}\n\n"
            f"{PUBMED_GRAPH_CONNECTION_SYNTHESIS_SYSTEM_PROMPT}"
        ),
    },
)

BIOMEDICAL_GRAPH_SEARCH_EXTENSION = GraphSearchConfig(
    system_prompt=GRAPH_SEARCH_SYSTEM_PROMPT,
)

SPORTS_ENTITY_RECOGNITION_BOOTSTRAP = EntityRecognitionBootstrapConfig(
    default_relation_type="PARTICIPATED_IN",
    default_relation_display_name="Participated In",
    default_relation_description="Default sports bootstrap relation.",
    default_relation_inverse_label="HAD_PARTICIPANT",
    interaction_relation_type="PLAYS_FOR",
    interaction_relation_display_name="Plays For",
    interaction_relation_description="Roster relationship between player and team.",
    interaction_relation_inverse_label="HAS_PLAYER",
    min_entity_types_for_default_relation=2,
    interaction_entity_types=("PLAYER", "TEAM"),
    domain_entity_types=(
        DomainBootstrapEntityTypes(
            domain_context="competition",
            entity_types=("MATCH", "SEASON", "LEAGUE", "TEAM"),
        ),
        DomainBootstrapEntityTypes(
            domain_context="roster",
            entity_types=("PLAYER", "TEAM", "POSITION"),
        ),
    ),
    source_types_with_publication_baseline=(),
    publication_baseline_source_label="match_report",
    publication_baseline_entity_description=(
        "Sports report bootstrap entity type used for relation validation."
    ),
    publication_baseline_entity_types=("MATCH", "TEAM", "PLAYER"),
    publication_baseline_relation_types=(
        BootstrapRelationTypeDefinition(
            relation_type="MENTIONS",
            display_name="Mentions",
            description="Report mentions a sports entity.",
            is_directional=True,
            inverse_label="MENTIONED_BY",
        ),
    ),
    publication_baseline_constraints=(
        BootstrapRelationConstraintDefinition(
            source_type="MATCH",
            relation_type="PARTICIPATED_IN",
            target_type="TEAM",
            requires_evidence=True,
        ),
    ),
    publication_metadata_variables=(),
)

SPORTS_ENTITY_RECOGNITION_FALLBACK = EntityRecognitionHeuristicFieldMap(
    source_type_fields={
        "match_report": {
            "primary_label": ("home_team", "away_team", "player"),
            "secondary_label": ("league", "season", "position"),
        },
        "roster": {
            "primary_label": ("player", "team"),
            "secondary_label": ("position", "league"),
        },
    },
    default_source_type="match_report",
    primary_entity_types={
        "match_report": "MATCH",
        "roster": "PLAYER",
    },
)

SPORTS_ENTITY_RECOGNITION_PAYLOAD = EntityRecognitionPayloadConfig(
    compact_record_rules={
        "match_report": EntityRecognitionCompactRecordRule(
            fields=("home_team", "away_team", "score", "match_date"),
            preferred_text_fields=("summary", "report_text"),
        ),
        "roster": EntityRecognitionCompactRecordRule(
            fields=("player", "team", "position"),
            preferred_text_fields=("notes",),
        ),
    },
)

SPORTS_ENTITY_RECOGNITION_PROMPTS = EntityRecognitionPromptConfig(
    system_prompts_by_source_type={
        "match_report": "Identify teams, players, matches, and competitions.",
        "roster": "Identify rostered players, teams, and positions.",
    },
)

SPORTS_EXTRACTION_FALLBACK = ExtractionHeuristicConfig(
    relation_when_variant_and_phenotype_present=ExtractionHeuristicRelation(
        source_type="match_report",
        relation_type="PARTICIPATED_IN",
        target_type="MATCH",
    ),
    claim_text_fields=("summary", "report_text", "notes"),
)

SPORTS_EXTRACTION_PAYLOAD = ExtractionPayloadConfig(
    compact_record_rules={
        "match_report": ExtractionCompactRecordRule(
            fields=("home_team", "away_team", "score", "summary"),
            fallback_text_field="report_text",
        ),
        "roster": ExtractionCompactRecordRule(
            fields=("player", "team", "position"),
            fallback_text_field="notes",
        ),
    },
)

SPORTS_EXTRACTION_PROMPTS = ExtractionPromptConfig(
    system_prompts_by_source_type={
        "match_report": "Extract sports match facts as graph relation candidates.",
        "roster": "Extract roster facts as graph relation candidates.",
    },
)

SPORTS_GRAPH_CONNECTION_PROMPTS = GraphConnectionPromptConfig(
    default_source_type="match_report",
    system_prompts_by_source_type={
        "match_report": "Suggest sports graph connections from match reports.",
        "roster": "Suggest sports graph connections from roster records.",
    },
)

BIOMEDICAL_GRAPH_DOMAIN_AI_CONFIG = GraphDomainAiConfig(
    pack_name="biomedical",
    entity_recognition_bootstrap=BIOMEDICAL_ENTITY_RECOGNITION_BOOTSTRAP,
    entity_recognition_fallback=BIOMEDICAL_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP,
    entity_recognition_payload=BIOMEDICAL_ENTITY_RECOGNITION_PAYLOAD_CONFIG,
    entity_recognition_prompt=BIOMEDICAL_ENTITY_RECOGNITION_PROMPT_CONFIG,
    extraction_fallback=BIOMEDICAL_EXTRACTION_HEURISTIC_CONFIG,
    extraction_payload=BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG,
    extraction_prompt=BIOMEDICAL_EXTRACTION_PROMPT_CONFIG,
    graph_connection_prompt=BIOMEDICAL_GRAPH_CONNECTION_PROMPT_CONFIG,
    search_extension=BIOMEDICAL_GRAPH_SEARCH_EXTENSION,
)

SPORTS_GRAPH_SEARCH_EXTENSION = GraphSearchConfig(
    system_prompt="Answer sports graph questions using stored graph evidence.",
)

SPORTS_GRAPH_DOMAIN_AI_CONFIG = GraphDomainAiConfig(
    pack_name="sports",
    entity_recognition_bootstrap=SPORTS_ENTITY_RECOGNITION_BOOTSTRAP,
    entity_recognition_fallback=SPORTS_ENTITY_RECOGNITION_FALLBACK,
    entity_recognition_payload=SPORTS_ENTITY_RECOGNITION_PAYLOAD,
    entity_recognition_prompt=SPORTS_ENTITY_RECOGNITION_PROMPTS,
    extraction_fallback=SPORTS_EXTRACTION_FALLBACK,
    extraction_payload=SPORTS_EXTRACTION_PAYLOAD,
    extraction_prompt=SPORTS_EXTRACTION_PROMPTS,
    graph_connection_prompt=SPORTS_GRAPH_CONNECTION_PROMPTS,
    search_extension=SPORTS_GRAPH_SEARCH_EXTENSION,
)

_GRAPH_DOMAIN_AI_CONFIGS = {
    "biomedical": BIOMEDICAL_GRAPH_DOMAIN_AI_CONFIG,
    "sports": SPORTS_GRAPH_DOMAIN_AI_CONFIG,
}


def create_graph_domain_ai_config(pack_name: str = "biomedical") -> GraphDomainAiConfig:
    """Return AI runtime config for one graph domain pack."""
    normalized_pack_name = pack_name.strip().lower()
    try:
        return _GRAPH_DOMAIN_AI_CONFIGS[normalized_pack_name]
    except KeyError as exc:
        supported = ", ".join(sorted(_GRAPH_DOMAIN_AI_CONFIGS))
        msg = (
            f"Unsupported graph domain AI config '{pack_name}'. "
            f"Supported configs: {supported}"
        )
        raise RuntimeError(msg) from exc


__all__ = [
    "BIOMEDICAL_GRAPH_DOMAIN_AI_CONFIG",
    "BIOMEDICAL_ENTITY_RECOGNITION_BOOTSTRAP",
    "BIOMEDICAL_ENTITY_RECOGNITION_HEURISTIC_FIELD_MAP",
    "BIOMEDICAL_ENTITY_RECOGNITION_PAYLOAD_CONFIG",
    "BIOMEDICAL_ENTITY_RECOGNITION_PROMPT_CONFIG",
    "BIOMEDICAL_EXTRACTION_HEURISTIC_CONFIG",
    "BIOMEDICAL_EXTRACTION_PAYLOAD_CONFIG",
    "BIOMEDICAL_EXTRACTION_PROMPT_CONFIG",
    "BIOMEDICAL_GRAPH_CONNECTION_PROMPT_CONFIG",
    "BIOMEDICAL_GRAPH_SEARCH_EXTENSION",
    "SPORTS_GRAPH_DOMAIN_AI_CONFIG",
    "SPORTS_GRAPH_SEARCH_EXTENSION",
    "create_graph_domain_ai_config",
]
