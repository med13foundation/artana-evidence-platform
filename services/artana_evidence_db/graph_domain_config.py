"""Service-local biomedical graph-domain configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from artana_evidence_db.relation_autopromotion_policy import (
    RelationAutopromotionDefaults,
)

GraphDomainViewType = str
BuiltinRelationCategory = Literal[
    "core_causal",
    "extended_scientific",
    "document_governance",
]


@dataclass(frozen=True, slots=True)
class DictionaryDomainContextDefinition:
    """One builtin dictionary domain context definition."""

    id: str
    display_name: str
    description: str


@dataclass(frozen=True, slots=True)
class BuiltinEntityTypeDefinition:
    """One builtin canonical entity type definition."""

    entity_type: str
    display_name: str
    description: str
    domain_context: str


@dataclass(frozen=True, slots=True)
class BuiltinRelationTypeDefinition:
    """One builtin canonical relation type definition."""

    relation_type: str
    display_name: str
    description: str
    domain_context: str
    category: BuiltinRelationCategory
    is_directional: bool = True
    inverse_label: str | None = None


@dataclass(frozen=True, slots=True)
class BuiltinRelationSynonymDefinition:
    """One builtin relation synonym definition."""

    relation_type: str
    synonym: str
    source: str | None = None


@dataclass(frozen=True, slots=True)
class BuiltinRelationConstraintDefinition:
    """One builtin allowed relation constraint definition.

    The ``profile`` field controls governance behavior:
      - ``"FORBIDDEN"`` — nonsensical or explicitly prohibited combination.
        Claims are rejected at validation time.
      - ``"EXPECTED"`` — high-value combination actively sought by
        extraction agents. Claims are auto-promotable if evidence is strong.
      - ``"ALLOWED"`` — valid combination accepted through the governed path.
        Claims require standard review (default).
      - ``"REVIEW_ONLY"`` — valid but unusual combination. Claims always
        require human review before promotion.
    """

    source_type: str
    relation_type: str
    target_type: str
    requires_evidence: bool = True
    profile: str = "ALLOWED"


@dataclass(frozen=True, slots=True)
class BuiltinQualifierDefinition:
    """One builtin qualifier key for the claim participant qualifier registry.

    Qualifier keys are registered in the variable_definitions table so that
    extraction agents are constrained to known keys, preventing ad-hoc
    qualifier drift across agents or prompt versions.
    """

    variable_id: str
    canonical_name: str
    display_name: str
    data_type: str  # STRING, INTEGER, FLOAT, DATE, CODED
    description: str
    constraints: dict[str, object] | None = None
    is_scoping: bool = False


class GraphDictionaryLoadingExtension(Protocol):
    """Dictionary-loading semantics owned by the graph service."""

    @property
    def builtin_domain_contexts(self) -> tuple[DictionaryDomainContextDefinition, ...]:
        """Return builtin dictionary domain contexts seeded by the service."""

    @property
    def builtin_entity_types(self) -> tuple[BuiltinEntityTypeDefinition, ...]:
        """Return builtin canonical entity types seeded by the service."""

    @property
    def builtin_relation_types(self) -> tuple[BuiltinRelationTypeDefinition, ...]:
        """Return builtin canonical relation types seeded by the service."""

    @property
    def builtin_relation_synonyms(
        self,
    ) -> tuple[BuiltinRelationSynonymDefinition, ...]:
        """Return builtin relation synonyms seeded by the service."""

    @property
    def builtin_relation_constraints(
        self,
    ) -> tuple[BuiltinRelationConstraintDefinition, ...]:
        """Return builtin allowed relation constraints seeded by the service."""

    @property
    def builtin_qualifier_definitions(
        self,
    ) -> tuple[BuiltinQualifierDefinition, ...]:
        """Return builtin qualifier keys seeded by the service."""


@dataclass(frozen=True, slots=True)
class GraphDictionaryLoadingConfig:
    """Configurable dictionary-loading semantics for the graph service."""

    builtin_domain_contexts: tuple[DictionaryDomainContextDefinition, ...]
    builtin_entity_types: tuple[BuiltinEntityTypeDefinition, ...] = ()
    builtin_relation_types: tuple[BuiltinRelationTypeDefinition, ...] = ()
    builtin_relation_synonyms: tuple[BuiltinRelationSynonymDefinition, ...] = ()
    builtin_relation_constraints: tuple[BuiltinRelationConstraintDefinition, ...] = ()
    builtin_qualifier_definitions: tuple[BuiltinQualifierDefinition, ...] = ()


class GraphViewExtension(Protocol):
    """Graph-view semantics owned by the graph service."""

    @property
    def entity_view_types(self) -> dict[GraphDomainViewType, str]:
        """Return the entity view type mapping."""

    @property
    def document_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return the document view types."""

    @property
    def claim_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return the claim view types."""

    @property
    def mechanism_relation_types(self) -> frozenset[str]:
        """Return relation types used for mechanism-oriented graph views."""

    @property
    def supported_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return all supported view types."""

    def normalize_view_type(self, value: str) -> GraphDomainViewType:
        """Normalize one raw route value into a supported graph view type."""

    def is_entity_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets an entity resource."""

    def is_claim_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a claim resource."""

    def is_document_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a document resource."""


class GraphRelationSuggestionExtension(Protocol):
    """Relation-suggestion semantics owned by the graph service."""

    @property
    def vector_candidate_limit(self) -> int:
        """Return the maximum vector candidate count to retrieve."""

    @property
    def min_vector_similarity(self) -> float:
        """Return the minimum vector similarity threshold."""


@dataclass(frozen=True, slots=True)
class GraphViewConfig:
    """Configurable graph-view semantics for the graph service."""

    entity_view_types: dict[GraphDomainViewType, str]
    document_view_types: frozenset[GraphDomainViewType]
    claim_view_types: frozenset[GraphDomainViewType]
    mechanism_relation_types: frozenset[str]

    @property
    def supported_view_types(self) -> frozenset[GraphDomainViewType]:
        """Return all supported view types for the configured service domain."""
        return (
            frozenset(self.entity_view_types)
            | self.document_view_types
            | self.claim_view_types
        )

    def normalize_view_type(self, value: str) -> GraphDomainViewType:
        """Normalize one raw route value into a supported graph view type."""
        normalized = value.strip().lower()
        if normalized in self.supported_view_types:
            return normalized
        msg = f"Unsupported graph view type '{value}'"
        raise ValueError(msg)

    def is_entity_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets an entity resource."""
        return view_type in self.entity_view_types

    def is_claim_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a claim resource."""
        return view_type in self.claim_view_types

    def is_document_view(self, view_type: GraphDomainViewType) -> bool:
        """Return whether the given view type targets a document resource."""
        return view_type in self.document_view_types


@dataclass(frozen=True, slots=True)
class GraphRelationSuggestionConfig:
    """Default relation-suggestion extension configuration."""

    vector_candidate_limit: int = 100
    min_vector_similarity: float = 0.0


GRAPH_SERVICE_DICTIONARY_DOMAIN_CONTEXTS = (
    DictionaryDomainContextDefinition(
        id="general",
        display_name="General",
        description="Domain-agnostic defaults for shared dictionary terms.",
    ),
    DictionaryDomainContextDefinition(
        id="clinical",
        display_name="Clinical",
        description="Clinical and biomedical literature domain context.",
    ),
    DictionaryDomainContextDefinition(
        id="genomics",
        display_name="Genomics",
        description="Genomics and variant interpretation domain context.",
    ),
    DictionaryDomainContextDefinition(
        id="anatomy",
        display_name="Anatomy",
        description="Tissue, cell type, and subcellular compartment domain context.",
    ),
    DictionaryDomainContextDefinition(
        id="translational",
        display_name="Translational",
        description="Model organisms, clinical trials, and bench-to-bedside domain context.",
    ),
)

GRAPH_SERVICE_BUILTIN_ENTITY_TYPES = (
    BuiltinEntityTypeDefinition(
        entity_type="GENE",
        display_name="Gene",
        description="Protein-coding or non-coding gene entity.",
        domain_context="genomics",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="PROTEIN",
        display_name="Protein",
        description="Protein or translated gene product entity.",
        domain_context="genomics",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="VARIANT",
        display_name="Variant",
        description="Sequence variant or allelic change entity.",
        domain_context="genomics",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="PHENOTYPE",
        display_name="Phenotype",
        description="Observed phenotype, trait, or clinical feature entity.",
        domain_context="clinical",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="DISEASE",
        display_name="Disease",
        description="Disease or diagnostic condition entity.",
        domain_context="clinical",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="SYNDROME",
        display_name="Syndrome",
        description="Named syndrome or clinically recognized disorder pattern.",
        domain_context="clinical",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="PROTEIN_COMPLEX",
        display_name="Protein Complex",
        description="Stable protein complex or multi-subunit assembly.",
        domain_context="genomics",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="SIGNALING_PATHWAY",
        display_name="Signaling Pathway",
        description="Biological signaling or regulatory pathway entity.",
        domain_context="general",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="MOLECULAR_FUNCTION",
        display_name="Molecular Function",
        description="Biochemical activity or molecular function entity.",
        domain_context="general",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="DRUG",
        display_name="Drug",
        description="Therapeutic compound or intervention entity.",
        domain_context="clinical",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="PUBLICATION",
        display_name="Publication",
        description="Published scientific article or report entity.",
        domain_context="general",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="TISSUE",
        display_name="Tissue",
        description="Biological tissue type or organ region.",
        domain_context="anatomy",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="CELL_TYPE",
        display_name="Cell Type",
        description="Specific cell type or cell population.",
        domain_context="anatomy",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="CELLULAR_COMPARTMENT",
        display_name="Cellular Compartment",
        description="Subcellular structure, organelle, or compartment.",
        domain_context="anatomy",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="BIOLOGICAL_PROCESS",
        display_name="Biological Process",
        description="Biological process, pathway step, or cellular event.",
        domain_context="general",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="PROTEIN_DOMAIN",
        display_name="Protein Domain",
        description="Conserved protein domain, motif, or structural region.",
        domain_context="genomics",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="MODEL_ORGANISM",
        display_name="Model Organism",
        description="Non-human organism used in biomedical research.",
        domain_context="translational",
    ),
    BuiltinEntityTypeDefinition(
        entity_type="CLINICAL_TRIAL",
        display_name="Clinical Trial",
        description="Registered clinical trial or interventional study.",
        domain_context="translational",
    ),
)

GRAPH_SERVICE_CORE_CAUSAL_RELATION_TYPES = (
    BuiltinRelationTypeDefinition(
        relation_type="ASSOCIATED_WITH",
        display_name="Associated With",
        description="Generic biomedical association between two entities.",
        domain_context="general",
        category="core_causal",
        is_directional=True,
        inverse_label="ASSOCIATED_WITH",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="CAUSES",
        display_name="Causes",
        description="Directional causal relationship between biomedical entities.",
        domain_context="clinical",
        category="core_causal",
        is_directional=True,
        inverse_label="CAUSED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="TREATS",
        display_name="Treats",
        description="Therapeutic relationship from an intervention to a condition.",
        domain_context="clinical",
        category="core_causal",
        is_directional=True,
        inverse_label="TREATED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="TARGETS",
        display_name="Targets",
        description=(
            "Directed targeting relationship between an intervention and a "
            "molecular entity."
        ),
        domain_context="genomics",
        category="core_causal",
        is_directional=True,
        inverse_label="TARGETED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="BIOMARKER_FOR",
        display_name="Biomarker For",
        description=(
            "Biomarker relationship linking a measurable signal to a condition "
            "or mechanism."
        ),
        domain_context="clinical",
        category="core_causal",
        is_directional=True,
        inverse_label="HAS_BIOMARKER",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="PHYSICALLY_INTERACTS_WITH",
        display_name="Physically Interacts With",
        description=("Physical interaction relationship between molecular entities."),
        domain_context="genomics",
        category="core_causal",
        is_directional=False,
        inverse_label="PHYSICALLY_INTERACTS_WITH",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="ACTIVATES",
        display_name="Activates",
        description="Positive regulatory relationship between biomedical entities.",
        domain_context="genomics",
        category="core_causal",
        is_directional=True,
        inverse_label="ACTIVATED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="REGULATES",
        display_name="Regulates",
        description="Generic regulatory relationship between biomedical entities.",
        domain_context="genomics",
        category="core_causal",
        is_directional=True,
        inverse_label="REGULATED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="INHIBITS",
        display_name="Inhibits",
        description="Negative regulatory relationship between biomedical entities.",
        domain_context="genomics",
        category="core_causal",
        is_directional=True,
        inverse_label="INHIBITED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="SENSITIZES_TO",
        display_name="Sensitizes To",
        description=(
            "A variant or genetic factor that increases sensitivity "
            "to a drug or environmental exposure. Pharmacogenomics."
        ),
        domain_context="clinical",
        category="core_causal",
        is_directional=True,
        inverse_label="SENSITIZED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="PHENOCOPY_OF",
        display_name="Phenocopy Of",
        description=(
            "Diseases that are clinically indistinguishable but have "
            "different molecular causes."
        ),
        domain_context="clinical",
        category="core_causal",
        is_directional=False,
        inverse_label="PHENOCOPY_OF",
    ),
)

GRAPH_SERVICE_EXTENDED_SCIENTIFIC_RELATION_TYPES = (
    BuiltinRelationTypeDefinition(
        relation_type="UPSTREAM_OF",
        display_name="Upstream Of",
        description="Mechanistic ordering relationship for pathway and causal chains.",
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="DOWNSTREAM_OF",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="DOWNSTREAM_OF",
        display_name="Downstream Of",
        description="Mechanistic ordering relationship inverse to UPSTREAM_OF.",
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="UPSTREAM_OF",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="PART_OF",
        display_name="Part Of",
        description=(
            "Compositional relationship between biomedical structures or mechanisms."
        ),
        domain_context="general",
        category="extended_scientific",
        is_directional=True,
        inverse_label="HAS_PART",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="COMPONENT_OF",
        display_name="Component Of",
        description="Component relationship between a member and a larger assembly.",
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="HAS_COMPONENT",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="EXPRESSED_IN",
        display_name="Expressed In",
        description=(
            "Expression relationship from a molecular entity to a tissue or "
            "cell context."
        ),
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="EXPRESSES",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="PARTICIPATES_IN",
        display_name="Participates In",
        description="Participation relationship between an entity and a process.",
        domain_context="general",
        category="extended_scientific",
        is_directional=True,
        inverse_label="HAS_PARTICIPANT",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="LOCATED_IN",
        display_name="Located In",
        description=(
            "Spatial localization of a molecular entity within a cellular "
            "compartment or structural region."
        ),
        domain_context="general",
        category="extended_scientific",
        is_directional=True,
        inverse_label="CONTAINS",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="MODULATES",
        display_name="Modulates",
        description=(
            "Broad regulatory effect on a target entity's activity, "
            "expression, or function without specifying direction."
        ),
        domain_context="general",
        category="extended_scientific",
        is_directional=True,
        inverse_label="MODULATED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="LOSS_OF_FUNCTION",
        display_name="Loss of Function",
        description=(
            "A variant or mutation that reduces or abolishes normal "
            "gene/protein function."
        ),
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="HAS_LOSS_OF_FUNCTION_VARIANT",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="GAIN_OF_FUNCTION",
        display_name="Gain of Function",
        description=(
            "A variant or mutation that confers new or enhanced "
            "gene/protein activity."
        ),
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="HAS_GAIN_OF_FUNCTION_VARIANT",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="PREDISPOSES_TO",
        display_name="Predisposes To",
        description=(
            "A genetic or environmental factor that increases risk "
            "of a condition without directly causing it."
        ),
        domain_context="clinical",
        category="extended_scientific",
        is_directional=True,
        inverse_label="PREDISPOSED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="CO_OCCURS_WITH",
        display_name="Co-occurs With",
        description=(
            "Statistical or clinical co-occurrence of two entities "
            "without implying causation."
        ),
        domain_context="clinical",
        category="extended_scientific",
        is_directional=False,
        inverse_label="CO_OCCURS_WITH",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="COLOCALIZES_WITH",
        display_name="Colocalizes With",
        description=(
            "Spatial co-occurrence of entities in the same cell or tissue. "
            "Weaker than physical interaction."
        ),
        domain_context="anatomy",
        category="extended_scientific",
        is_directional=False,
        inverse_label="COLOCALIZES_WITH",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="COMPENSATED_BY",
        display_name="Compensated By",
        description=(
            "Functional compensation or redundancy. Gene B rescues loss "
            "of Gene A. Explains variable expressivity."
        ),
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="COMPENSATES_FOR",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="SUBSTRATE_OF",
        display_name="Substrate Of",
        description="Enzyme-substrate relationship.",
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="HAS_SUBSTRATE",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="TRANSPORTS",
        display_name="Transports",
        description="Molecular transport relationship.",
        domain_context="genomics",
        category="extended_scientific",
        is_directional=True,
        inverse_label="TRANSPORTED_BY",
    ),
)

GRAPH_SERVICE_DOCUMENT_GOVERNANCE_RELATION_TYPES = (
    BuiltinRelationTypeDefinition(
        relation_type="SUPPORTS",
        display_name="Supports",
        description=(
            "Evidence-bearing support relationship used in claims and "
            "publication views."
        ),
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="SUPPORTED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="REFINES",
        display_name="Refines",
        description=("Relationship indicating a more specific statement or mechanism."),
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="REFINED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="GENERALIZES",
        display_name="Generalizes",
        description=(
            "Relationship indicating a more general statement or abstraction."
        ),
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="SPECIALIZED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="INSTANCE_OF",
        display_name="Instance Of",
        description=(
            "Relationship linking a specific instance to a more general class."
        ),
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="HAS_INSTANCE",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="MENTIONS",
        display_name="Mentions",
        description=("Publication mention relationship for documented entities."),
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="MENTIONED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="CITES",
        display_name="Cites",
        description="Citation relationship between publications.",
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="CITED_BY",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="HAS_AUTHOR",
        display_name="Has Author",
        description=("Authorship relationship from a publication to an author entity."),
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="AUTHOR_OF",
    ),
    BuiltinRelationTypeDefinition(
        relation_type="HAS_KEYWORD",
        display_name="Has Keyword",
        description="Keyword tagging relationship from a publication to a keyword entity.",
        domain_context="general",
        category="document_governance",
        is_directional=True,
        inverse_label="KEYWORD_OF",
    ),
)

GRAPH_SERVICE_BUILTIN_RELATION_TYPES = (
    *GRAPH_SERVICE_CORE_CAUSAL_RELATION_TYPES,
    *GRAPH_SERVICE_EXTENDED_SCIENTIFIC_RELATION_TYPES,
    *GRAPH_SERVICE_DOCUMENT_GOVERNANCE_RELATION_TYPES,
)


def _syn(relation_type: str, synonym: str) -> BuiltinRelationSynonymDefinition:
    return BuiltinRelationSynonymDefinition(
        relation_type=relation_type,
        synonym=synonym,
        source="graph_service",
    )


GRAPH_SERVICE_BUILTIN_RELATION_SYNONYMS = (
    # --- ASSOCIATED_WITH (generic association) ---
    _syn("ASSOCIATED_WITH", "ASSOCIATES_WITH"),
    _syn("ASSOCIATED_WITH", "LINKED_TO"),
    _syn("ASSOCIATED_WITH", "CORRELATED_WITH"),
    _syn("ASSOCIATED_WITH", "RELATED_TO"),
    _syn("ASSOCIATED_WITH", "CONNECTED_TO"),
    _syn("ASSOCIATED_WITH", "IMPLICATED_IN"),
    _syn("ASSOCIATED_WITH", "TIED_TO"),
    _syn("ASSOCIATED_WITH", "OBSERVED_IN"),
    _syn("ASSOCIATED_WITH", "REPORTED_IN"),
    _syn("ASSOCIATED_WITH", "FOUND_IN_CASES_OF"),
    # --- CAUSES (causal) ---
    _syn("CAUSES", "LEADS_TO"),
    _syn("CAUSES", "RESULTS_IN"),
    _syn("CAUSES", "INDUCES"),
    _syn("CAUSES", "PRODUCES"),
    _syn("CAUSES", "GIVES_RISE_TO"),
    _syn("CAUSES", "TRIGGERS"),
    _syn("CAUSES", "ELICITS"),
    _syn("CAUSES", "DRIVES"),
    _syn("CAUSES", "ENGENDERS"),
    # --- TREATS (therapeutic) ---
    _syn("TREATS", "THERAPEUTIC_FOR"),
    _syn("TREATS", "AMELIORATES"),
    _syn("TREATS", "ALLEVIATES"),
    _syn("TREATS", "USED_TO_TREAT"),
    _syn("TREATS", "REVERSES"),
    _syn("TREATS", "CURES"),
    _syn("TREATS", "MANAGES"),
    _syn("TREATS", "MITIGATES"),
    _syn("TREATS", "RESOLVES"),
    # --- TARGETS (drug/molecular target) ---
    _syn("TARGETS", "ACTS_ON"),
    _syn("TARGETS", "BINDS_TO"),
    _syn("TARGETS", "DIRECTED_AT"),
    _syn("TARGETS", "ENGAGES"),
    _syn("TARGETS", "ATTACKS"),
    _syn("TARGETS", "ACTS_AGAINST"),
    # --- BIOMARKER_FOR ---
    _syn("BIOMARKER_FOR", "DIAGNOSTIC_FOR"),
    _syn("BIOMARKER_FOR", "PROGNOSTIC_FOR"),
    _syn("BIOMARKER_FOR", "INDICATIVE_OF"),
    _syn("BIOMARKER_FOR", "MARKER_FOR"),
    _syn("BIOMARKER_FOR", "PREDICTOR_OF"),
    _syn("BIOMARKER_FOR", "INDICATOR_OF"),
    _syn("BIOMARKER_FOR", "READ_OUT_FOR"),
    # --- PHYSICALLY_INTERACTS_WITH ---
    _syn("PHYSICALLY_INTERACTS_WITH", "INTERACTS_WITH"),
    _syn("PHYSICALLY_INTERACTS_WITH", "BINDS"),
    _syn("PHYSICALLY_INTERACTS_WITH", "COMPLEXES_WITH"),
    _syn("PHYSICALLY_INTERACTS_WITH", "DIMERIZES_WITH"),
    _syn("PHYSICALLY_INTERACTS_WITH", "FORMS_COMPLEX_WITH"),
    _syn("PHYSICALLY_INTERACTS_WITH", "INTERACTS_PHYSICALLY_WITH"),
    _syn("PHYSICALLY_INTERACTS_WITH", "DOCKS_WITH"),
    # --- ACTIVATES (regulation) ---
    _syn("ACTIVATES", "STIMULATES"),
    _syn("ACTIVATES", "ENHANCES"),
    _syn("ACTIVATES", "PROMOTES"),
    _syn("ACTIVATES", "UPREGULATES"),
    _syn("ACTIVATES", "INDUCES_EXPRESSION_OF"),
    _syn("ACTIVATES", "TURNS_ON"),
    _syn("ACTIVATES", "INITIATES"),
    _syn("ACTIVATES", "SWITCHES_ON"),
    _syn("ACTIVATES", "AUGMENTS"),
    # --- INHIBITS (regulation) ---
    _syn("INHIBITS", "SUPPRESSES"),
    _syn("INHIBITS", "REPRESSES"),
    _syn("INHIBITS", "BLOCKS"),
    _syn("INHIBITS", "DOWNREGULATES"),
    _syn("INHIBITS", "ATTENUATES"),
    _syn("INHIBITS", "SILENCES"),
    _syn("INHIBITS", "DAMPENS"),
    _syn("INHIBITS", "ANTAGONIZES"),
    _syn("INHIBITS", "ABROGATES"),
    _syn("INHIBITS", "ABOLISHES"),
    # --- REGULATES (regulation) ---
    _syn("REGULATES", "CONTROLS"),
    _syn("REGULATES", "GOVERNS"),
    _syn("REGULATES", "INFLUENCES"),
    _syn("REGULATES", "ORCHESTRATES"),
    _syn("REGULATES", "COORDINATES"),
    _syn("REGULATES", "MEDIATES"),
    # --- UPSTREAM_OF / DOWNSTREAM_OF (pathway ordering) ---
    _syn("UPSTREAM_OF", "PRECEDES"),
    _syn("UPSTREAM_OF", "SIGNALS_TO"),
    _syn("UPSTREAM_OF", "FEEDS_INTO"),
    _syn("UPSTREAM_OF", "ACTS_BEFORE"),
    _syn("UPSTREAM_OF", "PRECEDES_IN_PATHWAY"),
    _syn("DOWNSTREAM_OF", "FOLLOWS"),
    _syn("DOWNSTREAM_OF", "RECEIVES_SIGNAL_FROM"),
    _syn("DOWNSTREAM_OF", "TRIGGERED_BY"),
    _syn("DOWNSTREAM_OF", "ACTS_AFTER"),
    _syn("DOWNSTREAM_OF", "FOLLOWS_IN_PATHWAY"),
    # --- PART_OF (compositional) ---
    _syn("PART_OF", "SUBUNIT_OF"),
    _syn("PART_OF", "CONTAINED_IN"),
    _syn("PART_OF", "MEMBER_OF"),
    _syn("PART_OF", "BELONGS_TO"),
    _syn("PART_OF", "INCLUDED_IN"),
    _syn("PART_OF", "INTEGRAL_PART_OF"),
    # --- COMPONENT_OF (compositional) ---
    _syn("COMPONENT_OF", "CONSTITUENT_OF"),
    _syn("COMPONENT_OF", "ELEMENT_OF"),
    _syn("COMPONENT_OF", "SUBSTRUCTURE_OF"),
    _syn("COMPONENT_OF", "BUILDING_BLOCK_OF"),
    # --- EXPRESSED_IN (spatial biology) ---
    _syn("EXPRESSED_IN", "EXPRESSED_WITHIN"),
    _syn("EXPRESSED_IN", "EXPRESSED_BY"),
    _syn("EXPRESSED_IN", "SHOWS_EXPRESSION_IN"),
    _syn("EXPRESSED_IN", "DETECTED_IN"),
    _syn("EXPRESSED_IN", "PRESENT_IN"),
    _syn("EXPRESSED_IN", "TRANSCRIBED_IN"),
    _syn("EXPRESSED_IN", "ENRICHED_IN"),
    _syn("EXPRESSED_IN", "ABUNDANT_IN"),
    # --- PARTICIPATES_IN (process participation) ---
    _syn("PARTICIPATES_IN", "INVOLVED_IN"),
    _syn("PARTICIPATES_IN", "FUNCTIONS_IN"),
    _syn("PARTICIPATES_IN", "TAKES_PART_IN"),
    _syn("PARTICIPATES_IN", "CONTRIBUTES_TO"),
    _syn("PARTICIPATES_IN", "PLAYS_ROLE_IN"),
    _syn("PARTICIPATES_IN", "ACTIVE_IN"),
    _syn("PARTICIPATES_IN", "OPERATES_IN"),
    # --- LOCATED_IN (localization) ---
    _syn("LOCATED_IN", "LOCALIZES_TO"),
    _syn("LOCATED_IN", "FOUND_IN"),
    _syn("LOCATED_IN", "RESIDES_IN"),
    _syn("LOCATED_IN", "LOCALIZED_TO"),
    _syn("LOCATED_IN", "PRESENT_AT"),
    _syn("LOCATED_IN", "SITUATED_IN"),
    _syn("LOCATED_IN", "CONFINED_TO"),
    # --- SUPPORTS (evidence/governance) ---
    _syn("SUPPORTS", "PROVIDES_EVIDENCE_FOR"),
    _syn("SUPPORTS", "BACKS"),
    _syn("SUPPORTS", "CORROBORATES"),
    _syn("SUPPORTS", "VALIDATES"),
    _syn("SUPPORTS", "CONFIRMS"),
    _syn("SUPPORTS", "REINFORCES"),
    # --- REFINES (evidence/governance) ---
    _syn("REFINES", "NARROWS"),
    _syn("REFINES", "SPECIALIZES"),
    _syn("REFINES", "MAKES_MORE_SPECIFIC"),
    # --- GENERALIZES (evidence/governance) ---
    _syn("GENERALIZES", "BROADENS"),
    _syn("GENERALIZES", "ABSTRACTS"),
    _syn("GENERALIZES", "MAKES_MORE_GENERAL"),
    # --- INSTANCE_OF (evidence/governance) ---
    _syn("INSTANCE_OF", "EXAMPLE_OF"),
    _syn("INSTANCE_OF", "IS_A"),
    _syn("INSTANCE_OF", "TYPE_OF"),
    _syn("INSTANCE_OF", "KIND_OF"),
    # --- MENTIONS (document governance) ---
    _syn("MENTIONS", "REFERENCES"),
    _syn("MENTIONS", "DISCUSSES"),
    _syn("MENTIONS", "DESCRIBES"),
    _syn("MENTIONS", "NOTES"),
    _syn("MENTIONS", "REPORTS"),
    _syn("MENTIONS", "COVERS"),
    # --- CITES (document governance) ---
    _syn("CITES", "REFERENCES_PUBLICATION"),
    _syn("CITES", "CITED_BY"),
    _syn("CITES", "REFERS_TO"),
    _syn("CITES", "ACKNOWLEDGES"),
    # --- HAS_AUTHOR (document governance) ---
    _syn("HAS_AUTHOR", "AUTHORED_BY"),
    _syn("HAS_AUTHOR", "WRITTEN_BY"),
    _syn("HAS_AUTHOR", "PUBLISHED_BY"),
    # --- HAS_KEYWORD (document governance) ---
    _syn("HAS_KEYWORD", "TAGGED_WITH"),
    _syn("HAS_KEYWORD", "INDEXED_AS"),
    _syn("HAS_KEYWORD", "LABELED_WITH"),
    # --- MODULATES ---
    _syn("MODULATES", "MODULATES_ACTIVITY_OF"),
    _syn("MODULATES", "AFFECTS"),
    _syn("MODULATES", "ALTERS"),
    _syn("MODULATES", "TUNES"),
    _syn("MODULATES", "ADJUSTS"),
    # --- LOSS_OF_FUNCTION / GAIN_OF_FUNCTION ---
    _syn("LOSS_OF_FUNCTION", "LOF"),
    _syn("LOSS_OF_FUNCTION", "LOSS_OF_FUNCTION_IN"),
    _syn("LOSS_OF_FUNCTION", "ABLATES_FUNCTION_OF"),
    _syn("LOSS_OF_FUNCTION", "KNOCKS_OUT"),
    _syn("LOSS_OF_FUNCTION", "NULL_FOR"),
    _syn("LOSS_OF_FUNCTION", "INACTIVATES"),
    _syn("GAIN_OF_FUNCTION", "GOF"),
    _syn("GAIN_OF_FUNCTION", "GAIN_OF_FUNCTION_IN"),
    _syn("GAIN_OF_FUNCTION", "CONFERS_ACTIVITY_TO"),
    _syn("GAIN_OF_FUNCTION", "HYPERACTIVATES"),
    _syn("GAIN_OF_FUNCTION", "CONSTITUTIVELY_ACTIVATES"),
    # --- PREDISPOSES_TO ---
    _syn("PREDISPOSES_TO", "RISK_FACTOR_FOR"),
    _syn("PREDISPOSES_TO", "INCREASES_RISK_OF"),
    _syn("PREDISPOSES_TO", "SUSCEPTIBILITY_TO"),
    _syn("PREDISPOSES_TO", "CONFERS_SUSCEPTIBILITY"),
    _syn("PREDISPOSES_TO", "ELEVATES_RISK_OF"),
    _syn("PREDISPOSES_TO", "PREDISPOSES"),
    # --- CO_OCCURS_WITH ---
    _syn("CO_OCCURS_WITH", "COINCIDES_WITH"),
    _syn("CO_OCCURS_WITH", "COMORBID_WITH"),
    _syn("CO_OCCURS_WITH", "CO_PRESENTS_WITH"),
    _syn("CO_OCCURS_WITH", "COEXISTS_WITH"),
    _syn("CO_OCCURS_WITH", "FOUND_TOGETHER_WITH"),
    # --- SENSITIZES_TO ---
    _syn("SENSITIZES_TO", "INCREASES_SENSITIVITY_TO"),
    _syn("SENSITIZES_TO", "CONFERS_SENSITIVITY_TO"),
    _syn("SENSITIZES_TO", "RENDERS_SENSITIVE_TO"),
    _syn("SENSITIZES_TO", "ENHANCES_SENSITIVITY_TO"),
    _syn("SENSITIZES_TO", "MAKES_VULNERABLE_TO"),
    # --- PHENOCOPY_OF ---
    _syn("PHENOCOPY_OF", "PHENOTYPICALLY_MIMICS"),
    _syn("PHENOCOPY_OF", "CLINICALLY_INDISTINGUISHABLE_FROM"),
    _syn("PHENOCOPY_OF", "MIMICS"),
    _syn("PHENOCOPY_OF", "PHENOTYPICALLY_RESEMBLES"),
    _syn("PHENOCOPY_OF", "MIMICS_PHENOTYPE_OF"),
    # --- COLOCALIZES_WITH ---
    _syn("COLOCALIZES_WITH", "CO_LOCALIZES_WITH"),
    _syn("COLOCALIZES_WITH", "FOUND_WITH"),
    _syn("COLOCALIZES_WITH", "CO_EXPRESSED_WITH"),
    _syn("COLOCALIZES_WITH", "OCCUPIES_SAME_REGION_AS"),
    _syn("COLOCALIZES_WITH", "COMPARTMENTALIZED_WITH"),
    # --- COMPENSATED_BY ---
    _syn("COMPENSATED_BY", "RESCUED_BY"),
    _syn("COMPENSATED_BY", "FUNCTIONALLY_REPLACED_BY"),
    _syn("COMPENSATED_BY", "REDUNDANT_WITH"),
    _syn("COMPENSATED_BY", "SUBSTITUTED_BY"),
    _syn("COMPENSATED_BY", "BACKED_UP_BY"),
    # --- SUBSTRATE_OF ---
    _syn("SUBSTRATE_OF", "CLEAVED_BY"),
    _syn("SUBSTRATE_OF", "PHOSPHORYLATED_BY"),
    _syn("SUBSTRATE_OF", "ACTED_UPON_BY"),
    _syn("SUBSTRATE_OF", "HYDROLYZED_BY"),
    _syn("SUBSTRATE_OF", "MODIFIED_BY"),
    _syn("SUBSTRATE_OF", "PROCESSED_BY"),
    # --- TRANSPORTS ---
    _syn("TRANSPORTS", "CARRIES"),
    _syn("TRANSPORTS", "SHUTTLES"),
    _syn("TRANSPORTS", "TRANSLOCATES"),
    _syn("TRANSPORTS", "MOVES"),
    _syn("TRANSPORTS", "FERRIES"),
    _syn("TRANSPORTS", "EXPORTS"),
    _syn("TRANSPORTS", "IMPORTS"),
)

GRAPH_SERVICE_BUILTIN_RELATION_CONSTRAINTS = (
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="PHYSICALLY_INTERACTS_WITH",
        target_type="GENE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="PARTICIPATES_IN",
        target_type="SIGNALING_PATHWAY",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="PHYSICALLY_INTERACTS_WITH",
        target_type="PROTEIN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="CAUSES",
        target_type="PHENOTYPE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="CAUSES",
        target_type="DISEASE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="TARGETS",
        target_type="GENE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="TARGETS",
        target_type="PROTEIN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="TARGETS",
        target_type="SIGNALING_PATHWAY",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="TREATS",
        target_type="PHENOTYPE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="TREATS",
        target_type="DISEASE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="MENTIONS",
        target_type="GENE",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="MENTIONS",
        target_type="PROTEIN",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="MENTIONS",
        target_type="VARIANT",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="MENTIONS",
        target_type="PHENOTYPE",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="MENTIONS",
        target_type="DRUG",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="SUPPORTS",
        target_type="GENE",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="SUPPORTS",
        target_type="PROTEIN",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="SUPPORTS",
        target_type="VARIANT",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="CITES",
        target_type="PUBLICATION",
        requires_evidence=False,
    ),
    # --- TISSUE constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="EXPRESSED_IN",
        target_type="TISSUE",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="EXPRESSED_IN",
        target_type="TISSUE",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="TISSUE",
        relation_type="PART_OF",
        target_type="TISSUE",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="TISSUE",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
    ),
    # --- CELL_TYPE constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="EXPRESSED_IN",
        target_type="CELL_TYPE",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="EXPRESSED_IN",
        target_type="CELL_TYPE",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="CELL_TYPE",
        relation_type="PART_OF",
        target_type="TISSUE",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="CELL_TYPE",
        relation_type="PARTICIPATES_IN",
        target_type="BIOLOGICAL_PROCESS",
    ),
    # --- CELLULAR_COMPARTMENT constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="LOCATED_IN",
        target_type="CELLULAR_COMPARTMENT",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN_COMPLEX",
        relation_type="LOCATED_IN",
        target_type="CELLULAR_COMPARTMENT",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="CELLULAR_COMPARTMENT",
        relation_type="PART_OF",
        target_type="CELLULAR_COMPARTMENT",
        requires_evidence=False,
    ),
    # --- BIOLOGICAL_PROCESS constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="PARTICIPATES_IN",
        target_type="BIOLOGICAL_PROCESS",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="PARTICIPATES_IN",
        target_type="BIOLOGICAL_PROCESS",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="BIOLOGICAL_PROCESS",
        relation_type="PART_OF",
        target_type="BIOLOGICAL_PROCESS",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="BIOLOGICAL_PROCESS",
        relation_type="UPSTREAM_OF",
        target_type="BIOLOGICAL_PROCESS",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="BIOLOGICAL_PROCESS",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
    ),
    # --- PROTEIN_DOMAIN constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="LOCATED_IN",
        target_type="PROTEIN_DOMAIN",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN_DOMAIN",
        relation_type="PART_OF",
        target_type="PROTEIN",
        requires_evidence=False,
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN_DOMAIN",
        relation_type="PHYSICALLY_INTERACTS_WITH",
        target_type="PROTEIN_DOMAIN",
    ),
    # --- MODEL_ORGANISM constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="MODEL_ORGANISM",
        relation_type="ASSOCIATED_WITH",
        target_type="GENE",
        profile="REVIEW_ONLY",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="MODEL_ORGANISM",
        relation_type="ASSOCIATED_WITH",
        target_type="PHENOTYPE",
        profile="REVIEW_ONLY",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="MODEL_ORGANISM",
        relation_type="ASSOCIATED_WITH",
        target_type="DISEASE",
        profile="REVIEW_ONLY",
    ),
    # --- CLINICAL_TRIAL constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="CLINICAL_TRIAL",
        relation_type="TARGETS",
        target_type="DISEASE",
        profile="REVIEW_ONLY",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="CLINICAL_TRIAL",
        relation_type="TARGETS",
        target_type="GENE",
        profile="REVIEW_ONLY",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="BIOMARKER_FOR",
        target_type="CLINICAL_TRIAL",
        profile="REVIEW_ONLY",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="CLINICAL_TRIAL",
        relation_type="ASSOCIATED_WITH",
        target_type="DRUG",
        profile="REVIEW_ONLY",
    ),
    # --- MODULATES constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="MODULATES",
        target_type="GENE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="MODULATES",
        target_type="PROTEIN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="MODULATES",
        target_type="BIOLOGICAL_PROCESS",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="MODULATES",
        target_type="SIGNALING_PATHWAY",
    ),
    # --- LOSS_OF_FUNCTION / GAIN_OF_FUNCTION constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="LOSS_OF_FUNCTION",
        target_type="GENE",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="GAIN_OF_FUNCTION",
        target_type="GENE",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="LOSS_OF_FUNCTION",
        target_type="PROTEIN",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="GAIN_OF_FUNCTION",
        target_type="PROTEIN",
        profile="EXPECTED",
    ),
    # --- PREDISPOSES_TO constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="PREDISPOSES_TO",
        target_type="DISEASE",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="PREDISPOSES_TO",
        target_type="PHENOTYPE",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="PREDISPOSES_TO",
        target_type="DISEASE",
    ),
    # --- CO_OCCURS_WITH constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="DISEASE",
        relation_type="CO_OCCURS_WITH",
        target_type="DISEASE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PHENOTYPE",
        relation_type="CO_OCCURS_WITH",
        target_type="PHENOTYPE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DISEASE",
        relation_type="CO_OCCURS_WITH",
        target_type="PHENOTYPE",
    ),
    # --- SENSITIZES_TO constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="VARIANT",
        relation_type="SENSITIZES_TO",
        target_type="DRUG",
        profile="EXPECTED",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="SENSITIZES_TO",
        target_type="DRUG",
    ),
    # --- PHENOCOPY_OF constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="DISEASE",
        relation_type="PHENOCOPY_OF",
        target_type="DISEASE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="SYNDROME",
        relation_type="PHENOCOPY_OF",
        target_type="SYNDROME",
    ),
    # --- COLOCALIZES_WITH constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="COLOCALIZES_WITH",
        target_type="PROTEIN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="COLOCALIZES_WITH",
        target_type="GENE",
    ),
    # --- COMPENSATED_BY constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="GENE",
        relation_type="COMPENSATED_BY",
        target_type="GENE",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="COMPENSATED_BY",
        target_type="PROTEIN",
    ),
    # --- SUBSTRATE_OF constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="SUBSTRATE_OF",
        target_type="PROTEIN",
    ),
    # --- TRANSPORTS constraints ---
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="TRANSPORTS",
        target_type="PROTEIN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PROTEIN",
        relation_type="TRANSPORTS",
        target_type="DRUG",
    ),
    # --- FORBIDDEN constraints (nonsensical combinations) ---
    # Wildcard target_type="*" means the source can never appear with that
    # relation regardless of target.  Exact-match constraints take priority
    # over wildcards in the lookup (see get_triple_profile).
    #
    # PUBLICATION: describes causation, doesn't cause/treat/interact/express
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="CAUSES",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="TREATS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="PHYSICALLY_INTERACTS_WITH",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="ACTIVATES",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="INHIBITS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="EXPRESSED_IN",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="LOSS_OF_FUNCTION",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PUBLICATION",
        relation_type="GAIN_OF_FUNCTION",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    # DRUG: not expressed, no variants, doesn't participate in processes
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="EXPRESSED_IN",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="LOSS_OF_FUNCTION",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="GAIN_OF_FUNCTION",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DRUG",
        relation_type="PARTICIPATES_IN",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    # PHENOTYPE: observable trait, doesn't target/activate/inhibit/treat/express
    BuiltinRelationConstraintDefinition(
        source_type="PHENOTYPE",
        relation_type="TARGETS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PHENOTYPE",
        relation_type="ACTIVATES",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PHENOTYPE",
        relation_type="INHIBITS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PHENOTYPE",
        relation_type="TREATS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="PHENOTYPE",
        relation_type="EXPRESSED_IN",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    # DISEASE: doesn't target/activate/inhibit/treat/express
    BuiltinRelationConstraintDefinition(
        source_type="DISEASE",
        relation_type="TARGETS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DISEASE",
        relation_type="ACTIVATES",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DISEASE",
        relation_type="INHIBITS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DISEASE",
        relation_type="TREATS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="DISEASE",
        relation_type="EXPRESSED_IN",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    # TISSUE: doesn't cause disease, doesn't treat/target
    BuiltinRelationConstraintDefinition(
        source_type="TISSUE",
        relation_type="CAUSES",
        target_type="DISEASE",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="TISSUE",
        relation_type="TREATS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="TISSUE",
        relation_type="TARGETS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    # CLINICAL_TRIAL: not molecular, not expressed, doesn't cause
    BuiltinRelationConstraintDefinition(
        source_type="CLINICAL_TRIAL",
        relation_type="PHYSICALLY_INTERACTS_WITH",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="CLINICAL_TRIAL",
        relation_type="EXPRESSED_IN",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="CLINICAL_TRIAL",
        relation_type="CAUSES",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    # MODEL_ORGANISM: doesn't treat/target
    BuiltinRelationConstraintDefinition(
        source_type="MODEL_ORGANISM",
        relation_type="TREATS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="MODEL_ORGANISM",
        relation_type="TARGETS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    # CELLULAR_COMPARTMENT: doesn't cause/treat
    BuiltinRelationConstraintDefinition(
        source_type="CELLULAR_COMPARTMENT",
        relation_type="CAUSES",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
    BuiltinRelationConstraintDefinition(
        source_type="CELLULAR_COMPARTMENT",
        relation_type="TREATS",
        target_type="*",
        requires_evidence=False,
        profile="FORBIDDEN",
    ),
)

GRAPH_SERVICE_BUILTIN_QUALIFIER_DEFINITIONS = (
    # --- Scoping qualifiers (contribute to canonicalization key) ---
    BuiltinQualifierDefinition(
        variable_id="QUAL_POPULATION",
        canonical_name="population",
        display_name="Population",
        data_type="STRING",
        description="Ancestry or population context, e.g. European, East Asian.",
        is_scoping=True,
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_ORGANISM",
        canonical_name="organism",
        display_name="Organism",
        data_type="STRING",
        description="Source organism, e.g. human, mouse, zebrafish.",
        is_scoping=True,
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_DEVELOPMENTAL_STAGE",
        canonical_name="developmental_stage",
        display_name="Developmental Stage",
        data_type="STRING",
        description="Developmental timing, e.g. E14.5, postnatal, adult.",
        is_scoping=True,
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_SEX",
        canonical_name="sex",
        display_name="Sex",
        data_type="STRING",
        description="Sex-specific context, e.g. male, female.",
        is_scoping=True,
    ),
    # --- Descriptive qualifiers (stored as attributes, don't split relations) ---
    BuiltinQualifierDefinition(
        variable_id="QUAL_PENETRANCE",
        canonical_name="penetrance",
        display_name="Penetrance",
        data_type="FLOAT",
        description="Proportion of carriers who express the phenotype.",
        constraints={"min": 0.0, "max": 1.0},
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_FREQUENCY",
        canonical_name="frequency",
        display_name="Allele Frequency",
        data_type="FLOAT",
        description="Allele frequency in population.",
        constraints={"min": 0.0, "max": 1.0},
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_ODDS_RATIO",
        canonical_name="odds_ratio",
        display_name="Odds Ratio",
        data_type="FLOAT",
        description="Effect size for association studies.",
        constraints={"min": 0.0},
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_P_VALUE",
        canonical_name="p_value",
        display_name="P-value",
        data_type="FLOAT",
        description="Statistical significance.",
        constraints={"min": 0.0, "max": 1.0},
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_EFFECT_SIZE",
        canonical_name="effect_size",
        display_name="Effect Size",
        data_type="FLOAT",
        description="Generic effect magnitude (beta, Cohen's d, etc.).",
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_SAMPLE_SIZE",
        canonical_name="sample_size",
        display_name="Sample Size",
        data_type="INTEGER",
        description="Number of individuals or samples in the study.",
        constraints={"min": 1},
    ),
    BuiltinQualifierDefinition(
        variable_id="QUAL_POLARITY",
        canonical_name="polarity",
        display_name="Polarity",
        data_type="STRING",
        description="Participant-level polarity alias: SUPPORT, REFUTE, UNCERTAIN, HYPOTHESIS.",
    ),
)

GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG = GraphDictionaryLoadingConfig(
    builtin_domain_contexts=GRAPH_SERVICE_DICTIONARY_DOMAIN_CONTEXTS,
    builtin_entity_types=GRAPH_SERVICE_BUILTIN_ENTITY_TYPES,
    builtin_relation_types=GRAPH_SERVICE_BUILTIN_RELATION_TYPES,
    builtin_relation_synonyms=GRAPH_SERVICE_BUILTIN_RELATION_SYNONYMS,
    builtin_relation_constraints=GRAPH_SERVICE_BUILTIN_RELATION_CONSTRAINTS,
    builtin_qualifier_definitions=GRAPH_SERVICE_BUILTIN_QUALIFIER_DEFINITIONS,
)

GRAPH_SERVICE_VIEW_CONFIG = GraphViewConfig(
    entity_view_types={
        "gene": "GENE",
        "variant": "VARIANT",
        "phenotype": "PHENOTYPE",
    },
    document_view_types=frozenset({"paper"}),
    claim_view_types=frozenset({"claim"}),
    mechanism_relation_types=frozenset(
        {
            "CAUSES",
            "UPSTREAM_OF",
            "DOWNSTREAM_OF",
            "REFINES",
            "SUPPORTS",
            "GENERALIZES",
            "INSTANCE_OF",
        },
    ),
)

GRAPH_SERVICE_RELATION_SUGGESTION_CONFIG = GraphRelationSuggestionConfig()
GRAPH_SERVICE_RELATION_AUTOPROMOTION_DEFAULTS = RelationAutopromotionDefaults()


__all__ = [
    "BuiltinEntityTypeDefinition",
    "BuiltinQualifierDefinition",
    "BuiltinRelationConstraintDefinition",
    "BuiltinRelationCategory",
    "BuiltinRelationSynonymDefinition",
    "BuiltinRelationTypeDefinition",
    "DictionaryDomainContextDefinition",
    "GRAPH_SERVICE_BUILTIN_ENTITY_TYPES",
    "GRAPH_SERVICE_BUILTIN_QUALIFIER_DEFINITIONS",
    "GRAPH_SERVICE_BUILTIN_RELATION_CONSTRAINTS",
    "GRAPH_SERVICE_BUILTIN_RELATION_SYNONYMS",
    "GRAPH_SERVICE_BUILTIN_RELATION_TYPES",
    "GRAPH_SERVICE_DICTIONARY_DOMAIN_CONTEXTS",
    "GRAPH_SERVICE_DICTIONARY_LOADING_CONFIG",
    "GRAPH_SERVICE_RELATION_AUTOPROMOTION_DEFAULTS",
    "GRAPH_SERVICE_RELATION_SUGGESTION_CONFIG",
    "GRAPH_SERVICE_VIEW_CONFIG",
    "GraphDictionaryLoadingConfig",
    "GraphDictionaryLoadingExtension",
    "GraphRelationSuggestionConfig",
    "GraphRelationSuggestionExtension",
    "GraphDomainViewType",
    "GraphViewConfig",
    "GraphViewExtension",
]
