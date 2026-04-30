"""Builtin graph-domain contexts, entity types, and relation types."""

from __future__ import annotations

from artana_evidence_db.graph_domain_types import (
    BuiltinEntityTypeDefinition,
    BuiltinRelationTypeDefinition,
    DictionaryDomainContextDefinition,
)

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



